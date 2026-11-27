from django.db import migrations

ROLES = {
    "Первые блюда": "main",
    "Вторые блюда": "main",
    "Горячие блюда": "main",
    "Бургеры": "main",
    "Пицца": "main",
    "Салаты": "side",
    "Закуски": "side",
    "Гарниры": "side",
    "Напитки": "drink",
    "Десерты": "dessert",
}


def assign_roles(apps, schema_editor):
    items = apps.get_model("menu", "MenuItem").objects.using(schema_editor.connection.alias)
    for category, role in ROLES.items():
        items.filter(category__name=category, lunch_role="").update(lunch_role=role)


class Migration(migrations.Migration):
    dependencies = [("menu", "0007_menuitem_allergens_menuitem_calories_and_more")]
    operations = [migrations.RunPython(assign_roles, migrations.RunPython.noop)]
