import uuid
from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.cart.models import Cart
from apps.common.access import customer_required

from . import services
from .delivery import get_point, quote_delivery, remember_point, saved_point
from .forms import CheckoutForm, ReasonForm
from .models import Order
from .promotions import discount_for, promotion_for
from .schedule import preparation_start


@customer_required
def create_order(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    items = list(cart.items.select_related("menu_item__restaurant").prefetch_related("menu_item__options"))
    initial = {
        "customer_name": request.user.first_name or request.user.username,
        "phone": request.user.phone,
        "address": request.user.address,
        "checkout_token": uuid.uuid4(),
    }
    if not items and request.method == "GET":
        return redirect("cart_detail")
    from .models import Restaurant

    restaurant = items[0].menu_item.restaurant if items else None
    if restaurant is None:
        restaurant, _ = Restaurant.objects.get_or_create(pk=1)
    subtotal = sum(item.total for item in items)
    point = saved_point(request)
    addresses = list(request.user.saved_addresses.all())
    delivery, delivery_error = None, ""
    posted = request.POST.copy() if request.method == "POST" else None
    if posted is not None and posted.get("action") == "address":
        selected = get_object_or_404(
            request.user.saved_addresses, pk=posted.get("saved_address")
        ) if posted.get("saved_address", "").isdigit() else None
        if selected:
            posted["address"] = selected.address
            posted["latitude"] = "" if selected.latitude is None else str(selected.latitude)
            posted["longitude"] = "" if selected.longitude is None else str(selected.longitude)
            point = get_point({"latitude": selected.latitude, "longitude": selected.longitude})
    form = CheckoutForm(posted, initial=initial)
    valid = form.is_bound and form.is_valid()
    discount = 0
    arrival = None
    if valid:
        arrival = form.cleaned_data.get("scheduled_at")
        point = get_point(form.cleaned_data)
        remember_point(request, point)
        if request.POST.get("action") not in ("quote", "address"):
            try:
                order = services.checkout(request.user, form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                return redirect("order_success", order_id=order.pk)
        try:
            promotion = promotion_for(form.cleaned_data.get("promo_code", ""), subtotal)
        except ValidationError as exc:
            form.add_error("promo_code", exc)
        else:
            discount = discount_for(promotion, subtotal)
    if items:
        try:
            delivery = quote_delivery(
                restaurant, subtotal, point, require_address=True, scheduled_at=arrival,
            )
            preparation_start(restaurant, arrival, delivery.minutes)
        except ValidationError as exc:
            delivery = None
            delivery_error = exc.messages[0]
    fee = delivery.fee if delivery else 0
    if not form.is_bound:
        if point:
            initial.update(latitude=point[0], longitude=point[1])
        initial["quoted_fee"] = fee if delivery else None
        initial["quoted_total"] = subtotal + fee if delivery else None
        form = CheckoutForm(initial=initial)
    elif valid and delivery:
        posted["quoted_fee"] = str(fee)
        posted["quoted_total"] = str(subtotal + fee - discount)
    return render(
        request,
        "orders/checkout.html",
        {
            "form": form,
            "items": items,
            "subtotal": subtotal,
            "restaurant": restaurant,
            "fee": fee,
            "total": subtotal + fee - discount,
            "discount": discount,
            "delivery": delivery,
            "delivery_error": delivery_error,
            "payme_available": len(form.fields["payment_method"].choices) > 1,
            "addresses": addresses,
        },
    )


@customer_required
def order_list(request):
    orders = (
        Order.objects.filter(user=request.user)
        .select_related("payment", "restaurant")
        .prefetch_related("items__menu_item")
    )
    return render(
        request,
        "orders/order_list.html",
        {"page_obj": Paginator(orders, 10).get_page(request.GET.get("page"))},
    )


@customer_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("payment", "courier").prefetch_related(
            "items__menu_item", "events"
        ),
        pk=order_id,
        user=request.user,
    )
    return render(
        request,
        "orders/order_detail.html",
        {"order": order, "open_issue": order.issues.filter(resolved_at__isnull=True).first()},
    )


@customer_required
def order_success(request, order_id):
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    return render(request, "orders/order_success.html", {"order": order})


@customer_required
@require_POST
def cancel(request, order_id):
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    form = ReasonForm(request.POST)
    if form.is_valid():
        try:
            if order.can_cancel:
                services.cancel_order(order.pk, request.user, form.cleaned_data["reason"])
                messages.success(request, "Заказ отменён. Оплачивать его не нужно.")
            else:
                services.report_issue(order.pk, request.user, form.cleaned_data["reason"])
                messages.success(
                    request, "Запрос отправлен администратору. Ответ появится в истории заказа."
                )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    else:
        messages.error(request, "Укажите причину: от 5 до 500 символов.")
    return redirect("order_detail", order_id=order.pk)


@customer_required
def live_status(request, order_id):
    order = get_object_or_404(Order.objects.select_related("courier"), pk=order_id, user=request.user)
    courier = order.courier
    payload = {"version": order.events.count(), "status": order.status}
    if (
        order.status == "delivery" and courier and courier.location_updated_at
        and courier.location_updated_at >= timezone.now() - timedelta(seconds=80)
        and courier.latitude is not None and courier.longitude is not None
    ):
        payload["courier_position"] = [float(courier.latitude), float(courier.longitude)]
    response = JsonResponse(payload)
    response["Cache-Control"] = "private, no-store"
    return response
