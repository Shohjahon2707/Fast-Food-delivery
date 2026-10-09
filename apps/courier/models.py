from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class Courier(BaseModel):
    VEHICLE_CHOICES = [
        ("foot", "Пешком"),
        ("bike", "Велосипед"),
        ("car", "Автомобиль"),
        ("scooter", "Скутер"),
    ]
    SHIFT_STATUS_CHOICES = [
        ("active", "На смене"),
        ("inactive", "Не на смене"),
        ("busy", "На доставке"),
    ]
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="courier_profile"
    )
    name = models.CharField(max_length=100, verbose_name="Имя")
    phone = models.CharField(max_length=20, verbose_name="Телефон")
    vehicle = models.CharField(
        max_length=20, choices=VEHICLE_CHOICES, default="foot", verbose_name="Транспорт"
    )
    shift_status = models.CharField(
        max_length=20, choices=SHIFT_STATUS_CHOICES, default="inactive", verbose_name="Смена"
    )
    is_approved = models.BooleanField(default=False, verbose_name="Одобрен администратором")

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_updated_at = models.DateTimeField(null=True, blank=True)
    location_accuracy = models.FloatField(null=True, blank=True)
    last_delivery_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name
