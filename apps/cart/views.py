from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.common.access import customer_required
from apps.menu.models import MenuItem
from apps.orders.services import shipping

from .models import Cart, CartItem


@customer_required
def cart_detail(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    items = list(cart.items.select_related("menu_item"))
    subtotal = sum(item.total for item in items)
    fee = shipping(subtotal) if items else 0
    return render(
        request,
        "cart/cart_detail.html",
        {
            "cart": cart,
            "items": items,
            "subtotal": subtotal,
            "fee": fee,
            "total": subtotal + fee,
            "unavailable": any(not item.menu_item.is_available for item in items),
        },
    )


@customer_required
@require_POST
@transaction.atomic
def add_to_cart(request, item_id):
    item = get_object_or_404(MenuItem, pk=item_id, is_available=True)
    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    line, created = CartItem.objects.get_or_create(cart=cart, menu_item=item)
    if not created and line.quantity < 30:
        line.quantity += 1
        line.save(update_fields=["quantity"])
    message = (
        f"{item.name} — в корзине!"
        if created or line.quantity < 30
        else "В корзине уже 30 порций этого блюда."
    )
    if request.headers.get("Accept") == "application/json":
        return JsonResponse(
            {"count": cart.items.aggregate(n=Sum("quantity"))["n"] or 0, "message": message}
        )
    messages.success(request, message)
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url, {request.get_host()}, require_https=request.is_secure()
    ):
        next_url = "cart_detail"
    return redirect(next_url or "cart_detail")


@customer_required
@require_POST
@transaction.atomic
def remove_from_cart(request, cart_item_id):
    cart = get_object_or_404(Cart.objects.select_for_update(), user=request.user)
    get_object_or_404(CartItem, pk=cart_item_id, cart=cart).delete()
    return redirect("cart_detail")


@customer_required
@require_POST
@transaction.atomic
def update_quantity(request, item_id):
    cart = get_object_or_404(Cart.objects.select_for_update(), user=request.user)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    try:
        quantity = int(request.POST.get("quantity", ""))
    except ValueError:
        quantity = -1
    if 1 <= quantity <= 30:
        item.quantity = quantity
        item.save(update_fields=["quantity"])
    elif quantity == 0:
        item.delete()
    else:
        messages.error(request, "Можно выбрать от 1 до 30 порций.")
    return redirect("cart_detail")
