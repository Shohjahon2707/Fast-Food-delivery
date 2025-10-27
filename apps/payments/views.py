import random
import re
from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Payment
from apps.orders.models import Order


def _render_error(request, template, order, msg):

    return render(request, template, {"order": order, "error": msg})


def _send_otp_email(user, order, otp):

    subject = f"Код подтверждения оплаты заказа #{order.id}"
    message = f"""
Ваш код подтверждения: {otp}

Детали заказа:
- Номер заказа: #{order.id}
- Сумма: {order.total_price} UZS
- Способ оплаты: Карта

Если это не вы — проигнорируйте сообщение.
"""
    send_mail(subject, message.strip(), settings.DEFAULT_FROM_EMAIL, [user.email])


@login_required
def start_payment_card(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if request.method == "POST":
        card = request.POST.get("card_number", "").replace(" ", "")
        phone = re.sub(r"\D", "", request.POST.get("phone", ""))

        if not (card.isdigit() and len(card) == 16):
            return _render_error(request, "payments/pay_with_card.html", order, "Введите корректный 16-значный номер карты")

        if not (phone.startswith("998") and len(phone) == 12):
            return _render_error(request, "payments/pay_with_card.html", order, "Номер должен быть в формате +998 XX XXX XX XX")

        otp = str(random.randint(100000, 999999))
        payment, _ = Payment.objects.update_or_create(
            order=order,
            defaults=dict(
                user=request.user,
                method="card",
                card_last4=card[-4:],
                phone=f"+{phone}",
                otp_code=otp,
                status="pending",
            ),
        )

        try:
            _send_otp_email(request.user, order, otp)
        except Exception as e:
            return _render_error(request, "payments/pay_with_card.html", order, f"Ошибка отправки email: {e}")

        request.session["payment_id"] = payment.id
        return redirect("confirm_payment")

    return render(request, "payments/pay_with_card.html", {"order": order})


@login_required
def confirm_payment(request):
    payment_id = request.session.get("payment_id")
    if not payment_id:
        return redirect("order_list")

    payment = get_object_or_404(Payment, id=payment_id, user=request.user)
    order = payment.order

    if request.method == "POST":
        if request.POST.get("otp_code", "").strip() == payment.otp_code:
            payment.status = order.status = "paid"
            payment.save()
            order.save()
            request.session.pop("payment_id", None)
            return redirect("order_list")

        return render(request, "payments/enter_otp.html", {"payment": payment, "error": "Неверный код. Попробуйте снова."})

    return render(request, "payments/enter_otp.html", {"payment": payment})


@login_required
def cash_payment_success(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    Payment.objects.create(order=order, user=request.user, method="cash", status="paid")
    order.status = "paid"
    order.save()
    return render(request, "payments/success.html", {"order": order})
