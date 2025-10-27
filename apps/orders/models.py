from django.db import models
from django.conf import settings
from apps.common.models import BaseModel
from apps.menu.models import MenuItem
from apps.courier.models import Courier
# Create your models here.


User = settings.AUTH_USER_MODEL

class Order(BaseModel):
    STATUS_CHOICES = [
        ("new", "Новый"),
        ("cooking", "Готовится"),
        ("delivery", "Доставка"),
        ("done", "Доставлен"),
        ("cancel", "Отменён"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")
    courier = models.ForeignKey(Courier, null=True, blank=True, on_delete=models.SET_NULL)

    address = models.CharField(max_length=255, blank=True, null=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)

    def __str__(self):
        return f"Заказ #{self.id} ({self.user}) - {self.get_status_display()}"


class OrderItem(BaseModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name}"

    def total(self):
        return self.menu_item.price * self.quantity
