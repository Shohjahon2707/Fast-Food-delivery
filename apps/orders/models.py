import uuid

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class Order(BaseModel):
    STATUS_CHOICES = [
        ("new", "Принят"),
        ("cooking", "Готовится"),
        ("ready", "Готов к выдаче"),
        ("delivery", "Курьер в пути"),
        ("done", "Доставлен"),
        ("cancel", "Отменён"),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new", db_index=True)
    courier = models.ForeignKey("courier.Courier", null=True, blank=True, on_delete=models.SET_NULL)
    address = models.CharField(max_length=255, blank=True, null=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    customer_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    comment = models.TextField(blank=True, max_length=500)
    checkout_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    cancel_reason = models.TextField(blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    delivery_eta = models.DateTimeField(null=True, blank=True)
    dispatch_alert = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["courier", "status"]),
            models.Index(fields=["user", "-created_at"]),
        ]
        permissions = [("work_kitchen", "Работать с очередью кухни")]
        verbose_name = "заказ"
        verbose_name_plural = "Заказы"

    @property
    def subtotal(self):
        return self.total_price - self.delivery_fee

    @property
    def is_active(self):
        return self.status not in ("done", "cancel")

    @property
    def can_cancel(self):
        return self.status == "new"

    @property
    def steps(self):
        states = self.STATUS_CHOICES[:-1]
        index = next((i for i, (key, _) in enumerate(states) if key == self.status), -1)
        return [
            {"label": label, "complete": i < index, "current": i == index}
            for i, (_, label) in enumerate(states)
        ]

    def __str__(self):
        return f"Заказ #{self.pk}"


class OrderItem(BaseModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey("menu.MenuItem", on_delete=models.PROTECT)
    name = models.CharField(max_length=200, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def total(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.quantity} × {self.name or self.menu_item.name}"


class OrderEvent(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=20, choices=Order.STATUS_CHOICES)
    note = models.CharField(max_length=500)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class OrderIssue(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="issues")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField(max_length=500)
    resolution = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["order"],
                condition=models.Q(resolved_at__isnull=True),
                name="one_open_issue_per_order",
            )
        ]


class Restaurant(models.Model):
    """One dispatch origin; configuration is shared by all workers."""

    name = models.CharField(max_length=100, default="Тёпло")
    address = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    preparation_minutes = models.PositiveSmallIntegerField(default=15)
    accepting_orders = models.BooleanField(default=True)
    last_dispatch_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "кухня и доставка"
        verbose_name_plural = "Кухня и доставка"

    def clean(self):
        from django.core.exceptions import ValidationError

        if (self.latitude is None) != (self.longitude is None):
            raise ValidationError("Укажите обе координаты кухни.")
        if self.latitude is not None and not (
            -90 <= self.latitude <= 90 and -180 <= self.longitude <= 180
        ):
            raise ValidationError("Координаты кухни вне допустимого диапазона.")
        if not 1 <= self.preparation_minutes <= 120:
            raise ValidationError("Время приготовления должно быть от 1 до 120 минут.")

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class DeliveryOffer(models.Model):
    STATES = [
        ("pending", "Предложен"),
        ("accepted", "Зарезервирован"),
        ("declined", "Отказ"),
        ("expired", "Нет ответа"),
        ("cancelled", "Снят"),
        ("picked_up", "Забран"),
    ]
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="offers")
    courier = models.ForeignKey("courier.Courier", on_delete=models.CASCADE, related_name="offers")
    state = models.CharField(max_length=20, choices=STATES, default="pending")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    pickup_minutes = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order"],
                condition=models.Q(state__in=["pending", "accepted"]),
                name="one_live_offer_per_order",
            ),
            models.UniqueConstraint(
                fields=["courier"],
                condition=models.Q(state__in=["pending", "accepted"]),
                name="one_next_offer_per_courier",
            ),
        ]
        indexes = [models.Index(fields=["state", "expires_at"])]
