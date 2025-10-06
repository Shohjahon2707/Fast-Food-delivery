from django.db import models
from apps.common.models import BaseModel
from apps.orders.models import Order
from apps.courier.models import Courier
class Delivery(BaseModel):
    STATUS_CHOICES = [
        ("assigned", "Назначен"),
        ("in_progress", "В пути"),
        ("delivered", "Доставлен"),
        ("failed", "Не удалось"),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="delivery")
    courier = models.ForeignKey(Courier, on_delete=models.SET_NULL, null=True, blank=True, related_name="deliveries")
    address = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="assigned")

    def __str__(self):
        return f"Доставка заказа #{self.order.id} - {self.get_status_display()}"
