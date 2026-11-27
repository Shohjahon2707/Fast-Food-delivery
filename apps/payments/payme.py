import base64
import json
import re
from time import time_ns
from urllib.parse import quote

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.orders.models import Order, OrderEvent

from .models import Payment, PaymeTransaction

TIMEOUT_MS = 12 * 60 * 60 * 1000


class PaymeError(Exception):
    def __init__(self, code, message, data=None):
        self.payload = {"code": code, "message": message, "data": data}


def enabled():
    return (
        bool(settings.PAYME_API_KEY)
        and re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", settings.PAYME_MERCHANT_ID) is not None
    )


def checkout_url(order):
    host = "test.paycom.uz" if settings.PAYME_SANDBOX else "checkout.paycom.uz"
    params = f"m={settings.PAYME_MERCHANT_ID};ac.order_id={order.pk};a={amount_for(order)}"
    return f"https://{host}/{quote(base64.b64encode(params.encode()).decode(), safe='')}"


def amount_for(order):
    return int(order.total_price * 100)


def now_ms():
    return time_ns() // 1_000_000


def integer(value):
    if type(value) is not int or not 0 <= value < 2**63:
        raise PaymeError(-32602, "Invalid parameters")
    return value


def payment_for(params):
    account = params.get("account")
    order_id = str(account.get("order_id", "")) if isinstance(account, dict) else ""
    order = (
        Order.objects.select_for_update().filter(pk=int(order_id)).first()
        if re.fullmatch(r"[1-9][0-9]{0,17}", order_id) else None
    )
    payment = (
        Payment.objects.select_for_update().filter(order=order, method="payme").first()
        if order else None
    )
    if payment is None:
        raise PaymeError(-31050, {
            "ru": "Заказ не найден", "uz": "Buyurtma topilmadi", "en": "Order not found",
        }, "order_id")
    if integer(params.get("amount")) != amount_for(order):
        raise PaymeError(-31001, "Invalid amount")
    return order, payment


def ensure_payable(order, payment):
    if order.status != "new" or payment.status != "pending":
        raise PaymeError(-31008, "Order cannot be paid")


def find_transaction(params):
    provider_id = params.get("id")
    if not isinstance(provider_id, str) or not provider_id or len(provider_id) > 100:
        raise PaymeError(-32602, "Invalid transaction identifier")
    return PaymeTransaction.objects.filter(provider_id=provider_id).first()


def state(entry):
    return {
        "transaction": str(entry.pk), "state": entry.state, "reason": entry.reason,
        "create_time": entry.create_time, "perform_time": entry.perform_time,
        "cancel_time": entry.cancel_time,
    }


def cancel_entry(entry, order, payment, reason):
    previous_state = entry.state
    entry.state = -2 if previous_state == 2 else -1
    entry.cancel_time, entry.reason = now_ms(), reason
    entry.save(update_fields=["state", "cancel_time", "reason"])
    payment.status = "refunded" if previous_state == 2 else "cancelled"
    payment.save(update_fields=["status"])
    if order.status == "new":
        order.status, order.cancel_reason = "cancel", "Платёж Payme отменён."
        order.save(update_fields=["status", "cancel_reason", "updated_at"])
        OrderEvent.objects.create(order=order, status="cancel", note=order.cancel_reason)


@transaction.atomic
def call(method, params):
    if method == "GetStatement":
        entries = PaymeTransaction.objects.filter(
            provider_time__range=(integer(params.get("from")), integer(params.get("to")))
        ).select_related("payment").order_by("provider_time", "pk")
        return {"transactions": [
            {
                **state(entry), "id": entry.provider_id, "time": entry.provider_time,
                "amount": entry.amount, "account": {"order_id": str(entry.payment.order_id)},
            }
            for entry in entries
        ]}
    if method == "CheckPerformTransaction":
        ensure_payable(*payment_for(params))
        return {"allow": True}
    if method == "CreateTransaction":
        order, payment = payment_for(params)
        entry = find_transaction(params)
        if entry is not None:
            if entry.payment_id != payment.pk:
                raise PaymeError(-31008, "Transaction already exists")
            return state(entry)
        ensure_payable(order, payment)
        if PaymeTransaction.objects.filter(payment=payment).exists():
            raise PaymeError(-31008, "A transaction already exists for this order")
        return state(PaymeTransaction.objects.create(
            payment=payment, provider_id=params["id"], provider_time=integer(params.get("time")),
            amount=amount_for(order), create_time=now_ms(),
        ))
    if method not in ("CheckTransaction", "PerformTransaction", "CancelTransaction"):
        raise PaymeError(-32601, "Method not found")
    entry = find_transaction(params)
    if entry is None:
        raise PaymeError(-31003, "Transaction not found")
    order = Order.objects.select_for_update().get(pk=entry.payment.order_id)
    payment = Payment.objects.select_for_update().get(pk=entry.payment_id)
    entry.refresh_from_db()
    if entry.state == 1 and now_ms() - entry.create_time >= TIMEOUT_MS:
        cancel_entry(entry, order, payment, 4)
    if method == "CheckTransaction":
        return state(entry)
    if method == "CancelTransaction":
        if entry.state < 0:
            return state(entry)
        if order.status not in ("new", "cancel"):
            raise PaymeError(-31007, "Order fulfillment has already started")
        cancel_entry(entry, order, payment, integer(params.get("reason")))
        return state(entry)
    if entry.state == 2:
        return state(entry)
    if entry.state < 0 or order.status != "new" or payment.status != "pending":
        return PaymeError(-31008, "Transaction cannot be performed")
    entry.state, entry.perform_time = 2, now_ms()
    entry.save(update_fields=["state", "perform_time"])
    payment.status, payment.paid_at = "paid", timezone.now()
    payment.save(update_fields=["status", "paid_at"])
    OrderEvent.objects.create(order=order, status=order.status, note="Оплата Payme подтверждена.")
    return state(entry)


@csrf_exempt
@require_POST
def callback(request):
    if not enabled():
        return JsonResponse({}, status=404)
    request_id = None
    try:
        try:
            payload = json.loads(request.body)
        except (ValueError, UnicodeError) as exc:
            raise PaymeError(-32700, "Invalid JSON") from exc
        if not isinstance(payload, dict):
            raise PaymeError(-32600, "Invalid request")
        request_id = payload.get("id")
        secret = f"{settings.PAYME_LOGIN}:{settings.PAYME_API_KEY}".encode()
        expected = "Basic " + base64.b64encode(secret).decode()
        if not constant_time_compare(request.headers.get("Authorization", ""), expected):
            raise PaymeError(-32504, "Access denied")
        method, params = payload.get("method"), payload.get("params")
        if not isinstance(method, str) or not isinstance(params, dict):
            raise PaymeError(-32600, "Invalid request")
        result = call(method, params)
        if isinstance(result, PaymeError):
            raise result
    except PaymeError as exc:
        return JsonResponse({"id": request_id, "error": exc.payload})
    except IntegrityError:
        return JsonResponse({"id": request_id, "error": {
            "code": -31008, "message": "Transaction already exists", "data": None,
        }})
    return JsonResponse({"id": request_id, "result": result})
