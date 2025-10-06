from django.db import models
from apps.common.models import BaseModel


class Courier(BaseModel):
    VEHICLE_CHOICES = [
        ("foot", "Пеший"),
        ("bike", "Велосипед"),
        ("car", "Машина"),
        ("scooter", "Скутер"),
    ]
    
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    vehicle = models.CharField(
        max_length=20,
        choices=VEHICLE_CHOICES,
        default="foot"
    )

    def __str__(self):
        return f"{self.name} ({self.get_vehicle_display()})"
