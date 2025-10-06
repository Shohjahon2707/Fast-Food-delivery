from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from .models import Order, OrderItem
from apps.cart.models import Cart
@login_required
def create_order(request):
    cart = get_object_or_404(Cart, user=request.user)
    
    if not cart.items.exists():
        return redirect('cart_detail')
    
    # Определяем метод оплаты
    payment_method = request.POST.get('payment_method', 'card')
    
    # Вычисляем общую сумму
    total_price = sum(item.total for item in cart.items.all())
    
    # Создаем заказ
    order = Order.objects.create(
        user=request.user,
        total_price=total_price,
        status='pending'
    )
    
    # Переносим товары из корзины в заказ
    for cart_item in cart.items.all():
        OrderItem.objects.create(
            order=order,
            menu_item=cart_item.menu_item,
            quantity=cart_item.quantity,
            price=cart_item.menu_item.price
        )
    
    # Очищаем корзину
    cart.items.all().delete()
    
    # Редирект в зависимости от метода оплаты
    if payment_method == 'cash':
        # Сразу отмечаем как оплаченный наличными
        order.status = 'paid'
        order.save()
        
        # Создаем запись о платеже
        from apps.payments.models import Payment
        Payment.objects.create(
            order=order,
            user=request.user,
            method="cash",
            status="paid"
        )
        
        return redirect('order_list')
    else:
        # Исправьте эту строку:
        return redirect('pay_with_card', order_id=order.id)  # ← БЕЗ namespace
    
@login_required
def order_list(request):
    """Список заказов текущего пользователя"""
    orders = Order.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "orders/order_list.html", {"orders": orders})


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, "orders/order_detail.html", {
        "order": order,
        "courier_info": f"{order.courier.name} ({order.courier.get_vehicle_display()})"
                        if order.courier else "Информация будет назначена позже"
    })

@login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, "orders/order_success.html", {"order": order})


@login_required
def mark_as_paid(request, order_id):
    """Отметить заказ как оплаченный наличными"""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    
    if order.status == 'pending':
        order.status = 'paid'
        order.save()
        
        # Создаем запись о платеже
        from apps.payments.models import Payment
        Payment.objects.create(
            order=order,
            user=request.user,
            method="cash",
            status="paid"
        )
    
    # Редирект на список заказов (без namespace)
    return redirect('order_list')