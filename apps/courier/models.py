from django.db import models
from apps.common.models import BaseModel
from django.conf import settings
class Courier(BaseModel):
    user = models.OneToOneField(
    settings.AUTH_USER_MODEL,
    on_delete=models.CASCADE,
    related_name='courier_profile'
    )
    settings.AUTH_USER_MODEL,
    on_delete=models.CASCADE,
    related_name='courier_profile'
    VEHICLE_CHOICES = [
        ("foot", "Пеший"),
        ("bike", "Велосипед"), 
        ("car", "Машина"),
        ("scooter", "Скутер"),
    ]
    
    SHIFT_STATUS_CHOICES = [
        ("active", "Активен"),
        ("inactive", "Неактивен"),
        ("busy", "Занят"),
    ]
    
    name = models.CharField(max_length=100, verbose_name="Имя")
    phone = models.CharField(max_length=20, verbose_name="Телефон")
    vehicle = models.CharField(
        max_length=20,
        choices=VEHICLE_CHOICES,
        default="foot",
        verbose_name="Транспорт"
    )
    shift_status = models.CharField(
        max_length=20,
        choices=SHIFT_STATUS_CHOICES, 
        default="active",
        verbose_name="Статус смены"
    )

    def __str__(self):
        return f"{self.name} ({self.get_vehicle_display()})"