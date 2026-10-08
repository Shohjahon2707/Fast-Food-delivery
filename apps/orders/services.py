from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.cart.models import Cart
from apps.courier.models import Courier
from apps.payments.models import Payment

from .models import Order, OrderEvent, OrderIssue, OrderItem


def shipping(subtotal):
    return Decimal("0") if subtotal >= settings.FREE_DELIVERY_FROM else settings.DELIVERY_FEE


def event(order, actor, note):
    OrderEvent.objects.create(order=order, status=order.status, actor=actor, note=note)


def require_operator(actor):
    if not actor.is_staff or not actor.has_perm("orders.change_order"):
        raise PermissionDenied


@transaction.atomic
def checkout(user, data):
    if not user.is_customer:
        raise PermissionDenied
    # Lock the cart for both quantity changes and checkout. The unique token is an
    # additional guard against a repeated browser submit after the cart is refilled.
    cart, _ = Cart.objects.get_or_create(user=user)
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    previous = Order.objects.filter(checkout_token=data["checkout_token"]).first()
    if previous:
        if previous.user_id != user.pk:
            raise PermissionDenied
        return previous
    lines = list(cart.items.select_related("menu_item"))
    if not lines:
        raise ValidationError("Корзина пуста. Добавьте любимое блюдо.")
    if any(not line.menu_item.is_available for line in lines):
        raise ValidationError("Некоторые блюда закончились. Удалите их из корзины.")
    if data["payment_method"] != "cash":
        raise ValidationError("Выберите оплату наличными при получении.")
    subtotal = sum((line.total for line in lines), Decimal("0"))
    fee = shipping(subtotal)
    order = Order.objects.create(
        user=user,
        total_price=subtotal + fee,
        delivery_fee=fee,
        customer_name=data["customer_name"],
        phone=data["phone"],
        address=data["address"],
        comment=data.get("comment", ""),
        checkout_token=data["checkout_token"],
    )
    for line in lines:
        OrderItem.objects.create(
            order=order,
            menu_item=line.menu_item,
            name=line.menu_item.name,
            quantity=line.quantity,
            price=line.menu_item.price,
        )
    Payment.objects.create(order=order, user=user, method="cash")
    event(order, user, "Заказ принят. Оплата наличными после получения.")
    cart.items.all().delete()
    if data.get("save_address"):
        user.address = data["address"]
        user.phone = data["phone"]
        user.save(update_fields=["address", "phone"])
    return order


@transaction.atomic
def advance_order(order_id, actor, target):
    require_operator(actor)
    order = Order.objects.select_for_update().get(pk=order_id)
    if {"new": "cooking", "cooking": "ready"}.get(order.status) != target:
        raise ValidationError("Этот переход уже выполнен или недоступен.")
    if order.issues.filter(resolved_at__isnull=True).exists():
        raise ValidationError("Сначала обработайте открытое обращение.")
    order.status = target
    order.save(update_fields=["status", "updated_at"])
    event(order, actor, dict(Order.STATUS_CHOICES)[target])
    return order


@transaction.atomic
def take_order(order_id, actor):
    if not actor.is_courier:
        raise PermissionDenied
    # Lock order first in every delivery operation, then courier: consistent lock order.
    order = Order.objects.select_for_update().get(pk=order_id)
    courier = Courier.objects.select_for_update().get(user=actor)
    if not courier.is_approved or courier.shift_status != "active":
        raise ValidationError("Нужны одобрение администратора и активная смена.")
    if Order.objects.filter(courier=courier, status="delivery").exists():
        raise ValidationError("Сначала завершите текущую доставку.")
    if (
        order.status != "ready"
        or order.courier_id
        or order.issues.filter(resolved_at__isnull=True).exists()
    ):
        raise ValidationError("Заказ уже забрали или он ещё не готов.")
    order.courier = courier
    order.status = "delivery"
    order.save(update_fields=["courier", "status", "updated_at"])
    courier.shift_status = "busy"
    courier.save(update_fields=["shift_status"])
    event(order, actor, "Курьер забрал заказ и направляется к вам.")
    return order


@transaction.atomic
def deliver_order(order_id, actor):
    if not actor.is_courier:
        raise PermissionDenied
    order = Order.objects.select_for_update().get(pk=order_id)
    courier = Courier.objects.select_for_update().get(user=actor)
    if order.courier_id != courier.pk:
        raise PermissionDenied
    if order.status == "done":
        return order
    if order.status != "delivery" or not courier.is_approved:
        raise ValidationError("Этот заказ нельзя завершить.")
    if order.issues.filter(resolved_at__isnull=True).exists():
        raise ValidationError("Администратор должен сначала решить вопрос с заказом.")
    payment = Payment.objects.select_for_update().get(order=order)
    if payment.method != "cash" or payment.status != "pending":
        raise ValidationError("Платёж требует проверки администратора.")
    payment.status, payment.paid_at, payment.confirmed_by = "paid", timezone.now(), actor
    payment.save(update_fields=["status", "paid_at", "confirmed_by"])
    order.status = "done"
    order.save(update_fields=["status", "updated_at"])
    courier.shift_status = "active"
    courier.save(update_fields=["shift_status"])
    event(order, actor, "Заказ доставлен. Курьер подтвердил получение наличных.")
    return order


@transaction.atomic
def cancel_order(order_id, actor, reason):
    order = Order.objects.select_for_update().get(pk=order_id)
    is_owner = actor.is_customer and order.user_id == actor.pk
    if not is_owner:
        require_operator(actor)
    if order.status == "cancel":
        return order
    if not order.is_active or (is_owner and not order.can_cancel):
        raise ValidationError("Заказ уже готовится. Отправьте запрос на отмену администратору.")
    if len(reason.strip()) < 5:
        raise ValidationError("Укажите причину отмены.")
    order.status, order.cancel_reason = "cancel", reason[:500]
    order.save(update_fields=["status", "cancel_reason", "updated_at"])
    payment = Payment.objects.select_for_update().filter(order=order).first()
    if payment:
        payment.status = "refund_due" if payment.status == "paid" else "cancelled"
        payment.save(update_fields=["status"])
    if order.courier_id:
        Courier.objects.filter(pk=order.courier_id).update(shift_status="active")
    order.issues.filter(resolved_at__isnull=True).update(
        resolved_at=timezone.now(), resolution="Заказ отменён: " + reason[:450]
    )
    event(order, actor, "Заказ отменён: " + reason[:450])
    return order


@transaction.atomic
def report_issue(order_id, actor, reason):
    order = Order.objects.select_for_update().get(pk=order_id)
    is_owner = actor.is_customer and order.user_id == actor.pk
    is_courier = actor.is_courier and order.courier_id and order.courier.user_id == actor.pk
    if not (is_owner or is_courier):
        raise PermissionDenied
    if not order.is_active:
        raise ValidationError("Заказ уже завершён.")
    if len(reason.strip()) < 5:
        raise ValidationError("Опишите проблему подробнее.")
    _, created = OrderIssue.objects.get_or_create(
        order=order, resolved_at=None, defaults={"author": actor, "reason": reason[:500]}
    )
    if created:
        event(order, actor, "Получено обращение. Администратор разбирается в ситуации.")
    return order


@transaction.atomic
def resolve_issue(order_id, actor, resolution, return_to_kitchen=False):
    require_operator(actor)
    order = Order.objects.select_for_update().get(pk=order_id)
    if not order.is_active:
        raise ValidationError("Заказ уже завершён.")
    issues = order.issues.filter(resolved_at__isnull=True)
    if not issues.exists() or len(resolution.strip()) < 5:
        raise ValidationError("Нужны открытое обращение и описание решения.")
    if return_to_kitchen:
        if order.status != "delivery" or order.payment.status != "pending":
            raise ValidationError("Вернуть на выдачу можно только неоплаченный заказ в доставке.")
        Courier.objects.filter(pk=order.courier_id).update(shift_status="active")
        order.courier = None
        order.status = "ready"
        order.save(update_fields=["courier", "status", "updated_at"])
    issues.update(resolved_at=timezone.now(), resolution=resolution[:500])
    event(
        order,
        actor,
        ("Заказ возвращён в ресторан. " if return_to_kitchen else "Обращение решено. ")
        + resolution[:400],
    )


@transaction.atomic
def confirm_refund(order_id, actor):
    require_operator(actor)
    order = Order.objects.select_for_update().get(pk=order_id)
    payment = Payment.objects.select_for_update().get(order=order)
    if order.status != "cancel" or payment.status != "refund_due":
        raise ValidationError("Нет ожидающего возврата.")
    payment.status = "refunded"
    payment.save(update_fields=["status"])
    event(order, actor, "Администратор подтвердил фактический возврат средств.")


@transaction.atomic
def reconcile_cash(order_id, actor, reason):
    require_operator(actor)
    order = Order.objects.select_for_update().get(pk=order_id)
    payment = Payment.objects.select_for_update().get(order=order)
    if not order.is_active or payment.status == "pending" and payment.method == "cash":
        raise ValidationError("Для этого заказа изменение оплаты не требуется.")
    if len(reason.strip()) < 5:
        raise ValidationError("Укажите результат согласования с покупателем.")
    payment.method, payment.status = "cash", "pending"
    payment.card_last4, payment.phone = None, None
    payment.paid_at, payment.confirmed_by = None, None
    payment.save()
    event(
        order, actor, "После проверки согласована оплата наличными при получении. " + reason[:350]
    )


@transaction.atomic
def complete_by_admin(order_id, actor, reason):
    require_operator(actor)
    order = Order.objects.select_for_update().get(pk=order_id)
    payment = Payment.objects.select_for_update().get(order=order)
    if (
        order.status != "delivery"
        or payment.method != "cash"
        or payment.status not in ("pending", "paid")
    ):
        raise ValidationError("Завершить можно только доставляемый заказ с оплатой наличными.")
    if len(reason.strip()) < 5:
        raise ValidationError("Укажите, как подтверждены доставка и получение денег.")
    payment.status, payment.paid_at, payment.confirmed_by = "paid", timezone.now(), actor
    payment.save(update_fields=["status", "paid_at", "confirmed_by"])
    order.status = "done"
    order.save(update_fields=["status", "updated_at"])
    if order.courier_id:
        Courier.objects.filter(pk=order.courier_id).update(shift_status="active")
    order.issues.filter(resolved_at__isnull=True).update(
        resolved_at=timezone.now(), resolution=reason[:500]
    )
    event(order, actor, "Администратор подтвердил доставку и получение наличных. " + reason[:350])
