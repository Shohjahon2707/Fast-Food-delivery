from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect

from apps.common.access import customer_required
from apps.orders.models import Order


@customer_required
def unavailable_card(request, order_id=None):
    if order_id is not None:
        get_object_or_404(Order, pk=order_id, user=request.user)
    messages.info(
        request,
        "Онлайн-оплата пока не подключена. Новые заказы оплачиваются наличными при получении.",
    )
    return redirect("order_detail", order_id=order_id) if order_id else redirect("order_list")


@customer_required
def cash_payment_success(request, order_id):
    get_object_or_404(Order, pk=order_id, user=request.user)
    return redirect("order_detail", order_id=order_id)
