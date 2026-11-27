from collections import Counter

from django.db import transaction

from apps.menu.models import MenuItem

from .models import Cart, CartItem

SESSION_KEY = "guest_cart"
MAX_QUANTITY = 30


OPTIONS_SESSION_KEY = "guest_cart_options"


class Basket:
    def __init__(self, request, lock=False):
        self.session = request.session
        self.cart = None
        if request.user.is_authenticated:
            self.cart, _ = Cart.objects.get_or_create(user=request.user)
            if lock:
                self.cart = Cart.objects.select_for_update().get(pk=self.cart.pk)
            self.lines = list(
                self.cart.items.select_related("menu_item__restaurant").prefetch_related("menu_item__options")
            )
        else:
            stored = self.session.get(SESSION_KEY, {})
            items = MenuItem.objects.select_related("restaurant").prefetch_related("options").in_bulk(stored)
            details = self.session.get(OPTIONS_SESSION_KEY, {})
            self.lines = [
                CartItem(id=int(key), menu_item=items[int(key)], quantity=quantity, **details.get(key, {}))
                for key, quantity in stored.items() if int(key) in items
            ]

    @property
    def contents(self):
        return Counter({line.menu_item.pk: line.quantity for line in self.lines})

    def store(self, contents, options=None):
        saved = {
            line.menu_item.pk: {"option_ids": line.option_ids, "note": line.note}
            for line in self.lines
        } if options is None else options
        if self.cart:
            self.cart.items.exclude(menu_item_id__in=contents).delete()
            for item_id, quantity in contents.items():
                self.cart.items.update_or_create(
                    menu_item_id=item_id, defaults={
                        "quantity": quantity,
                        "option_ids": saved.get(item_id, {}).get("option_ids", []),
                        "note": saved.get(item_id, {}).get("note", ""),
                    }
                )
        else:
            self.session[SESSION_KEY] = {str(pk): quantity for pk, quantity in contents.items()}
            self.session[OPTIONS_SESSION_KEY] = {
                str(pk): value for pk, value in saved.items() if pk in contents
            }


@transaction.atomic
def transfer_guest_basket(request):
    if not request.user.is_customer:
        return
    preferences = request.session.pop("lunch_preferences", None)
    guest = request.session.get(SESSION_KEY, {})
    if not guest and preferences is None:
        return
    basket = Basket(request, lock=True)
    if preferences is not None:
        request.user.lunch_preferences = preferences
        request.user.save(update_fields=["lunch_preferences"])
    if not guest:
        return
    items = MenuItem.objects.in_bulk(guest)
    if not items:
        request.session.pop(SESSION_KEY, None)
        request.session.pop(OPTIONS_SESSION_KEY, None)
        return
    incoming = Counter({key: guest[str(key)] for key in items})
    restaurant_id = next(iter(items.values())).restaurant_id
    if basket.lines and basket.lines[0].menu_item.restaurant_id != restaurant_id:
        return
    guest_options = {int(key): value for key, value in request.session.get(OPTIONS_SESSION_KEY, {}).items()}
    options = {line.menu_item.pk: {"option_ids": line.option_ids, "note": line.note} for line in basket.lines}
    empty = {"option_ids": [], "note": ""}
    if any(options[pk] != guest_options.get(pk, empty) for pk in incoming.keys() & options.keys()):
        return
    contents = basket.contents + incoming
    basket.store({key: min(MAX_QUANTITY, value) for key, value in contents.items()}, options | guest_options)
    request.session.pop(SESSION_KEY, None)
    request.session.pop(OPTIONS_SESSION_KEY, None)
