from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.common.models import BaseModel


class User(AbstractUser, BaseModel):
    ROLE_CHOICES = [
        ("customer", "Покупатель"),
        ("courier", "Курьер"),
        ("admin", "Администратор"),
        ("kitchen", "Кухня"),
        ("partner", "Партнёр ресторана"),
    ]
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    address_latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    address_longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    lunch_preferences = models.JSONField(default=dict, blank=True)
    notify_sms = models.BooleanField(default=False)
    notify_telegram = models.BooleanField(default=False)
    telegram_chat_id = models.BigIntegerField(null=True, blank=True, unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="customer")

    def __str__(self):
        return self.username

    @property
    def is_customer(self):
        return self.role == "customer" and not self.is_staff

    @property
    def is_courier(self):
        return self.role == "courier" and not self.is_staff

    @property
    def is_admin(self):
        return self.is_active and self.is_staff


class SavedAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_addresses")
    label = models.CharField(max_length=40)
    address = models.CharField(max_length=255)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        ordering = ["label", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["user", "label"], name="unique_address_label"),
        ]

    def __str__(self):
        return f"{self.label} · {self.address}"


class FavoriteDish(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorite_dishes")
    dish = models.ForeignKey("menu.MenuItem", on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "dish"], name="unique_favorite_dish"),
        ]


class FavoriteRestaurant(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorite_restaurants")
    restaurant = models.ForeignKey("orders.Restaurant", on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "restaurant"], name="unique_favorite_restaurant"),
        ]
