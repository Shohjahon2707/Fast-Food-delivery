from django.db import models
from django.contrib.auth.models import AbstractUser
from apps.common.models import BaseModel


class User(AbstractUser, BaseModel):
    ROLE_CHOICES = [
        ("customer", "Клиент"),
        ("courier", "Курьер"),
        ("admin", "Админ"),
    ]

    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="customer")

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
