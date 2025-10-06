import random
import re
from django.core.mail import send_mail
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from .models import Payment
from apps.orders.models import Order
from django.conf import settings

@login_required
def start_payment_card(request, order_id):
    """
    Старт оплаты картой: форма ввода 16-значного номера карты и телефона.
    Создаём Payment, генерируем otp, отправляем email и редиректим на подтверждение.
    """
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if request.method == "POST":
        card_number = request.POST.get("card_number", "").replace(" ", "")  # убираем пробелы
        phone = request.POST.get("phone", "").strip()

        # Валидация 16 цифр
        if not (card_number.isdigit() and len(card_number) == 16):
            return render(request, "payments/pay_with_card.html", {
                "order": order,
                "error": "Введите корректный 16-значный номер карты (ровно 16 цифр)",
            })

        # Валидация узбекского номера телефона
        phone_digits = re.sub(r'\D', '', phone)  # убираем все нецифровые символы
        
        # Проверяем формат +998 XX XXX XX XX (12 цифр с кодом страны)
        if not (phone_digits.startswith('998') and len(phone_digits) == 12):
            return render(request, "payments/pay_with_card.html", {
                "order": order,
                "error": "Введите корректный номер телефона Узбекистана в формате +998 XX XXX XX XX",
            })

        # Только последние 4 цифры сохраняем
        last4 = card_number[-4:]

        # Генерация OTP — 6 цифр
        otp_code = str(random.randint(100000, 999999))

        # Создаем или обновляем платеж
        payment, created = Payment.objects.get_or_create(
            order=order,
            defaults={
                "user": request.user,
                "method": "card",
                "card_last4": last4,
                "phone": phone,
                "otp_code": otp_code,
                "status": "pending",
            }
        )
        
        if not created:
            # Обновляем поля и код
            payment.card_last4 = last4
            payment.phone = phone
            payment.otp_code = otp_code
            payment.status = "pending"
            payment.save()

        # Отправляем email с кодом
        subject = f"Код подтверждения оплаты заказа #{order.id}"
        message = f"""
Ваш код подтверждения: {otp_code}

Детали заказа:
- Номер заказа: #{order.id}
- Сумма: {order.total_price} UZS
- Способ оплаты: Карта

Если это не вы - проигнорируйте это сообщение.
"""
        recipient = [request.user.email]

        try:
            send_mail(subject, message.strip(), settings.DEFAULT_FROM_EMAIL, recipient, fail_silently=False)
        except Exception as e:
            # В разработке показываем ошибку, в продакшене логируем
            return render(request, "payments/pay_with_card.html", {
                "order": order,
                "error": f"Ошибка отправки email: {e}",
            })

        # Сохраняем payment_id в сессии для подтверждения
        request.session["payment_id"] = payment.id
        request.session.modified = True

        return redirect("confirm_payment")

    return render(request, "payments/pay_with_card.html", {"order": order})
@login_required
def confirm_payment(request):
    payment_id = request.session.get("payment_id")
    if not payment_id:
        return redirect("order_list")  # на список заказов

    payment = get_object_or_404(Payment, id=payment_id, user=request.user)
    order = payment.order

    if request.method == "POST":
        entered_otp = request.POST.get("otp_code", "").strip()
        
        if entered_otp == payment.otp_code:
            # Успешная оплата
            payment.status = "paid"
            payment.save()
            order.status = "paid"
            order.save()
            
            # Очищаем сессию
            request.session.pop("payment_id", None)
            
            # Редирект на список заказов вместо шаблона
            return redirect("order_list")
        else:
            # Неверный код
            return render(request, "payments/enter_otp.html", {
                "payment": payment, 
                "error": "Неверный код. Попробуйте снова."
            })

    return render(request, "payments/enter_otp.html", {"payment": payment})
@login_required
def cash_payment_success(request, order_id):
    """Страница успеха для наличной оплаты"""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    
    # Создаем запись о наличном платеже
    Payment.objects.create(
        order=order,
        user=request.user,
        method="cash",
        status="paid"
    )
    
    # Обновляем статус заказа
    order.status = "paid"
    order.save()
    
    return render(request, "payments/success.html", {"order": order})