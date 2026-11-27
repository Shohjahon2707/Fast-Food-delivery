from collections import Counter

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.menu.models import MenuItem
from apps.menu.smart import load_lunch
from apps.orders.delivery import is_open, quote_delivery, remember_point, saved_point

from .basket import MAX_QUANTITY, SESSION_KEY, Basket


def check_customer(request):
    if request.user.is_authenticated and not request.user.is_customer:
        raise PermissionDenied


def cart_detail(request):
    check_customer(request)
    basket = Basket(request)
    items = basket.lines
    subtotal = sum(item.total for item in items)
    restaurant = items[0].menu_item.restaurant if items else None
    delivery, error = None, ""
    if items:
        try:
            delivery = quote_delivery(restaurant, subtotal, saved_point(request))
        except ValidationError as exc:
            error = exc.messages[0]
    fee = delivery.fee if delivery else 0
    return render(
        request, "cart/cart_detail.html",
        {
            "cart": basket.cart,
            "items": items,
            "subtotal": subtotal,
            "fee": fee,
            "total": subtotal + fee,
            "restaurant": restaurant,
            "delivery": delivery,
            "delivery_error": error,
            "unavailable": any(not line.menu_item.is_available for line in items),
            "guest_conflict": request.user.is_authenticated and request.session.get(SESSION_KEY),
        },
    )


def basket_response(request, count, message):
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"count": count, "message": message})
    messages.success(request, message)
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url, {request.get_host()}, require_https=request.is_secure()
    ):
        next_url = ""
    return redirect(next_url or "cart_detail")


def basket_error(request, message, redirect_to="cart_detail"):
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"message": message}, status=409)
    messages.error(request, message)
    return redirect(redirect_to)


def confirm_replacement(request, message, **context):
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"replace_required": True, "message": message}, status=409)
    return render(request, "cart/replace.html", {"confirm_message": message, **context})


@require_POST
@transaction.atomic
def add_to_cart(request, item_id):
    check_customer(request)
    item = get_object_or_404(
        MenuItem.objects.select_related("restaurant"), pk=item_id, is_available=True
    )
    if item.restaurant and not is_open(item.restaurant):
        return basket_error(request, _("Ресторан сейчас закрыт."))
    basket = Basket(request, lock=True)
    contents = basket.contents
    if any(line.menu_item.restaurant_id != item.restaurant_id for line in basket.lines):
        if request.POST.get("replace") != "yes":
            return confirm_replacement(
                request,
                _("В корзине блюда другого ресторана. Заменить их?"),
                item=item,
            )
        contents.clear()
    contents[item.pk] = min(MAX_QUANTITY, contents[item.pk] + 1)
    basket.store(contents)
    return basket_response(request, sum(contents.values()), _("Блюдо в корзине."))


@require_POST
@transaction.atomic
def add_lunch(request):
    check_customer(request)
    token = request.POST.get("lunch", "")
    try:
        lunch, criteria = load_lunch(token)
    except (signing.BadSignature, ValidationError):
        return basket_error(
            request, _("Условия изменились. Подберите обед ещё раз."), "smart_lunch"
        )
    basket = Basket(request, lock=True)
    contents = Counter({item.pk: quantity for item, quantity in lunch.lines})
    if basket.lines and basket.contents != contents and request.POST.get("replace") != "yes":
        return confirm_replacement(
            request,
            _("Заменить текущие блюда выбранным набором?"),
            lunch_token=token,
        )
    basket.store(contents)
    remember_point(request, criteria.get("point"))
    preferences = {
        key: criteria[key] for key in ("people", "diet", "max_minutes", "allergens")
    }
    if request.user.is_authenticated:
        request.user.lunch_preferences = preferences
        request.user.save(update_fields=["lunch_preferences"])
    else:
        request.session["lunch_preferences"] = preferences
    return basket_response(request, sum(contents.values()), _("Набор в корзине."))


def change_line(request, line_id, quantity):
    basket = Basket(request, lock=True)
    line = next((line for line in basket.lines if line.pk == line_id), None)
    if line is None:
        raise Http404
    contents = basket.contents
    if quantity:
        contents[line.menu_item.pk] = quantity
    else:
        contents.pop(line.menu_item.pk, None)
    basket.store(contents)
    return redirect("cart_detail")


@require_POST
@transaction.atomic
def remove_from_cart(request, cart_item_id):
    check_customer(request)
    return change_line(request, cart_item_id, 0)


@require_POST
@transaction.atomic
def update_quantity(request, item_id):
    check_customer(request)
    try:
        quantity = int(request.POST.get("quantity", ""))
    except ValueError:
        quantity = -1
    if not 0 <= quantity <= MAX_QUANTITY:
        return basket_error(request, _("Можно выбрать от 1 до 30 порций."))
    return change_line(request, item_id, quantity)


@require_POST
@transaction.atomic
def resolve_guest_basket(request):
    if not request.user.is_authenticated:
        return redirect_to_login(request.path)
    check_customer(request)
    guest = request.session.get(SESSION_KEY, {})
    if guest and request.POST.get("keep") == "guest":
        items = MenuItem.objects.in_bulk(guest)
        if items:
            Basket(request, lock=True).store({key: guest[str(key)] for key in items})
    request.session.pop(SESSION_KEY, None)
    return redirect("cart_detail")
