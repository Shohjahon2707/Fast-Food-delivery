from django.db import models
from django.conf import settings
from apps.orders.models import Order 

User = settings.AUTH_USER_MODEL

class Payment(models.Model):
    METHOD_CHOICES = [
        ("cash", "Наличные"),
        ("card", "Карта"),
    ]
    STATUS_CHOICES = [
        ("pending", "В ожидании"),
        ("paid", "Оплачен"),
        ("failed", "Ошибка"),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="payment")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES)
    card_last4 = models.CharField(max_length=4, blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment #{self.id} for Order #{self.order.id} ({self.method})"
