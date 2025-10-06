from django.db import models
from django.conf import settings
from apps.menu.models import MenuItem

class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart of {self.user}"

    @property
    def total_price(self):
        """Вычисляем общую сумму корзины"""
        return sum(item.total for item in self.items.all())

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name}"

    @property
    def total(self):
        """Вычисляем общую стоимость для этого товара"""
        return self.menu_item.price * self.quantity