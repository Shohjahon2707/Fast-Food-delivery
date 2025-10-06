from django.db import models
from apps.common.models import BaseModel
# Create your models here.

class Category(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True) 
    image = models.ImageField(upload_to="categories/", blank=True, null=True)

    def __str__(self):
        return self.name



class MenuItem(BaseModel):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=0)
    image = models.ImageField(upload_to="menu/", blank=True, null=True)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.price}UZS)"
