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

    def __str__(self):
        return self.name
