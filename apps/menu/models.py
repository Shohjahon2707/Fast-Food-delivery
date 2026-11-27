from django.core.validators import MinValueValidator
from django.db import models
from django.templatetags.static import static
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


class DishOption(models.Model):
    dish = models.ForeignKey("MenuItem", related_name="options", on_delete=models.CASCADE)
    name = models.CharField(max_length=80)
    extra_price = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return self.name


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
    class LunchRole(models.TextChoices):
        MAIN = "main", _("Основное")
        SIDE = "side", _("Гарнир или салат")
        DRINK = "drink", _("Напиток")
        DESSERT = "dessert", _("Десерт")

    restaurant = models.ForeignKey(
        "orders.Restaurant", on_delete=models.PROTECT, null=True, related_name="menu_items"
    )
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
    lunch_role = models.CharField(max_length=10, choices=LunchRole, blank=True)
    servings = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    is_halal = models.BooleanField(blank=True, null=True)
    spice_level = models.PositiveSmallIntegerField(
        choices=[(0, _("Неострое")), (1, _("Умеренно острое")), (2, _("Острое"))],
        blank=True, null=True,
    )
    calories = models.PositiveSmallIntegerField(blank=True, null=True)
    protein = models.PositiveSmallIntegerField(blank=True, null=True)
    fat = models.PositiveSmallIntegerField(blank=True, null=True)
    carbohydrates = models.PositiveSmallIntegerField(blank=True, null=True)
    allergens = models.JSONField(blank=True, null=True)
    cooking_minutes = models.PositiveSmallIntegerField(blank=True, null=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gt=0), name="menu_price_positive"),
            models.CheckConstraint(condition=models.Q(servings__gte=1), name="menu_servings_positive"),
        ]
        verbose_name = "блюдо"
        verbose_name_plural = "Меню"

    @property
    def photo_sheet(self):
        return (not self.image and not self.seed_image) or str(self.image).endswith(".jfif")

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
        if self.photo_sheet:
            return static("food/street-menu.webp")
        return self.image.url if self.image else static(self.seed_image)

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.allergens is not None:
            from .smart_forms import ALLERGEN_CHOICES

            valid = dict(ALLERGEN_CHOICES)
            if not isinstance(self.allergens, list) or any(
                not isinstance(code, str) or code not in valid for code in self.allergens
            ):
                raise ValidationError({"allergens": _("Укажите список кодов аллергенов.")})
