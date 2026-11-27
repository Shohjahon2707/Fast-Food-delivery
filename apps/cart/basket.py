from collections import Counter
from dataclasses import dataclass

from django.db import transaction

from apps.menu.models import MenuItem

from .models import Cart, CartItem

SESSION_KEY = "guest_cart"
MAX_QUANTITY = 30


@dataclass
class GuestLine:
    menu_item: MenuItem
    quantity: int

    @property
    def pk(self):
        return self.menu_item.pk

    @property
    def total(self):
        return self.menu_item.price * self.quantity


class Basket:
    def __init__(self, request, lock=False):
        self.session = request.session
        self.cart = None
        if request.user.is_authenticated:
            self.cart, _ = Cart.objects.get_or_create(user=request.user)
            if lock:
                self.cart = Cart.objects.select_for_update().get(pk=self.cart.pk)
            self.lines = list(self.cart.items.select_related("menu_item__restaurant"))
        else:
            stored = self.session.get(SESSION_KEY, {})
            items = MenuItem.objects.select_related("restaurant").in_bulk(stored)
            self.lines = [
                GuestLine(items[int(key)], quantity)
                for key, quantity in stored.items() if int(key) in items
            ]

    @property
    def contents(self):
        return Counter({line.menu_item.pk: line.quantity for line in self.lines})

    def store(self, contents):
        if self.cart:
            self.cart.items.exclude(menu_item_id__in=contents).delete()
            for item_id, quantity in contents.items():
                self.cart.items.update_or_create(
                    menu_item_id=item_id, defaults={"quantity": quantity}
                )
        else:
            self.session[SESSION_KEY] = {str(pk): quantity for pk, quantity in contents.items()}


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
        return
    incoming = Counter({key: guest[str(key)] for key in items})
    restaurant_id = next(iter(items.values())).restaurant_id
    if basket.lines and basket.lines[0].menu_item.restaurant_id != restaurant_id:
        return
    contents = basket.contents + incoming
    basket.store({key: min(MAX_QUANTITY, value) for key, value in contents.items()})
    request.session.pop(SESSION_KEY, None)
