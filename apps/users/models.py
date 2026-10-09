from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.common.models import BaseModel


class User(AbstractUser, BaseModel):
    ROLE_CHOICES = [
        ("customer", "Покупатель"),
        ("courier", "Курьер"),
        ("admin", "Администратор"),
        ("kitchen", "Кухня"),
    ]
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
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
