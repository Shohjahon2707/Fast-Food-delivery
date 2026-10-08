from django.conf import settings
from django.db import models


class Payment(models.Model):
    METHOD_CHOICES = [("cash", "Наличными при получении"), ("card", "Карта (архив)")]
    STATUS_CHOICES = [
        ("pending", "К оплате при получении"),
        ("paid", "Оплачено"),
        ("cancelled", "Оплата отменена"),
        ("failed", "Ошибка"),
        ("review", "Требует проверки"),
        ("refund_due", "Ожидает возврата"),
        ("refunded", "Возвращено"),
    ]
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="payment")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default="cash")
    card_last4 = models.CharField(max_length=4, blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_payments",
    )

    class Meta:
        verbose_name = "платёж"
        verbose_name_plural = "Платежи"

    def __str__(self):
        return f"Оплата заказа #{self.order_id}"
