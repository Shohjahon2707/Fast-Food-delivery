from django.core.validators import MinValueValidator
from django.db import models
from django.templatetags.static import static

from apps.common.models import BaseModel


class Category(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name


class MenuItem(BaseModel):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="items")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=0, validators=[MinValueValidator(1)])
    image = models.ImageField(upload_to="menu/", blank=True, null=True)
    is_available = models.BooleanField(default=True)
    is_vegetarian = models.BooleanField(default=False, verbose_name="Без мяса")
    weight = models.CharField(max_length=30, blank=True, verbose_name="Вес / объём")
    badge = models.CharField(max_length=30, blank=True, verbose_name="Метка")
    seed_image = models.CharField(max_length=100, blank=True, editable=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gt=0), name="menu_price_positive")
        ]
        verbose_name = "блюдо"
        verbose_name_plural = "Меню"

    @property
    def photo_sheet(self):
        return not self.image or str(self.image).endswith(".jfif")

    @property
    def photo_slot(self):
        if "двойн" in self.name.lower():
            return 5
        key = (self.seed_image or str(self.image)).lower()
        return next(
            (
                index
                for word, index in [
                    ("cheese", 1),
                    ("сыр", 1),
                    ("fries", 2),
                    ("карто", 2),
                    ("wings", 3),
                    ("крыл", 3),
                    ("salad", 4),
                    ("салат", 4),
                ]
                if word in key or word in self.name.lower()
            ),
            0,
        )

    @property
    def image_url(self):
        return static("food/street-menu.webp") if self.photo_sheet else self.image.url

    def __str__(self):
        return self.name
