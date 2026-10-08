from django.conf import settings
from django.db import models

from apps.menu.models import MenuItem


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total_price(self):
        return sum(item.total for item in self.items.select_related("menu_item"))

    def __str__(self):
        return f"Корзина {self.user}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name="items", on_delete=models.CASCADE)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cart", "menu_item"], name="one_item_per_cart"),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, quantity__lte=30), name="cart_quantity_range"
            ),
        ]

    @property
    def total(self):
        return self.menu_item.price * self.quantity

    def __str__(self):
        return f"{self.quantity} × {self.menu_item}"
