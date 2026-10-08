from django.core.management.base import BaseCommand
from django.db import transaction

from apps.menu.models import Category, MenuItem

PRODUCTS = [
    (
        "Бургеры",
        "Классик бургер",
        "Сочная говяжья котлета, свежие овощи и фирменный соус в румяной булочке.",
        32000,
        "280 г",
        "burger",
        False,
        "Любимчик",
    ),
    (
        "Бургеры",
        "Чизбургер",
        "Говядина, нежный чеддер, маринованный огурчик и горчичный соус.",
        38000,
        "300 г",
        "cheeseburger",
        False,
        "Больше сыра",
    ),
    (
        "Закуски",
        "Картофель фри",
        "Золотистые ломтики картофеля с хрустящей корочкой и щепоткой соли.",
        15000,
        "150 г",
        "fries",
        True,
        "",
    ),
    (
        "Курица",
        "Крылышки BBQ",
        "Румяные куриные крылышки в густом соусе барбекю. Немного сладости, много вкуса.",
        35000,
        "6 шт.",
        "wings",
        False,
        "Попробуйте",
    ),
    (
        "Бургеры",
        "Двойной чизбургер",
        "Две говяжьи котлеты, двойной чеддер, огурчики и наш фирменный соус.",
        49000,
        "380 г",
        "cheeseburger",
        False,
        "",
    ),
    (
        "Салаты",
        "Свежий салат",
        "Хрустящий салат, томаты, огурцы и лёгкая заправка из оливкового масла.",
        22000,
        "200 г",
        "salad",
        True,
        "",
    ),
    (
        "Закуски",
        "Большая картошка",
        "Золотистая картошка на двоих. Или только для вас — мы поймём.",
        24000,
        "250 г",
        "fries",
        True,
        "",
    ),
    (
        "Курица",
        "Крылышки на компанию",
        "Большая порция крылышек BBQ для тёплых встреч и долгих разговоров.",
        62000,
        "12 шт.",
        "wings",
        False,
        "На двоих",
    ),
]


class Command(BaseCommand):
    help = "Add the starter menu without replacing existing restaurant data or creating accounts."

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        for category_name, name, description, price, weight, image, vegetarian, badge in PRODUCTS:
            category, _ = Category.objects.get_or_create(name=category_name)
            _, new = MenuItem.objects.get_or_create(
                name=name,
                category=category,
                defaults={
                    "description": description,
                    "price": price,
                    "weight": weight,
                    "seed_image": f"food/{image}.webp",
                    "is_vegetarian": vegetarian,
                    "badge": badge,
                },
            )
            created += new
        self.stdout.write(
            self.style.SUCCESS(f"Добавлено блюд: {created}. Существующие данные сохранены.")
        )
