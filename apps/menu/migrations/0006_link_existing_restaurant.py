from django.db import migrations


def link_existing(apps, schema_editor):
    Item = apps.get_model("menu", "MenuItem")
    Order = apps.get_model("orders", "Order")
    Restaurant = apps.get_model("orders", "Restaurant")
    db = schema_editor.connection.alias
    if Item.objects.using(db).filter(restaurant__isnull=True).exists() or Order.objects.using(db).filter(restaurant__isnull=True).exists():
        restaurant, _ = Restaurant.objects.using(db).get_or_create(pk=1)
        Item.objects.using(db).filter(restaurant__isnull=True).update(restaurant_id=restaurant.pk)
        Order.objects.using(db).filter(restaurant__isnull=True).update(restaurant_id=restaurant.pk)


class Migration(migrations.Migration):
    dependencies = [("menu", "0005_menuitem_restaurant")]
    operations = [migrations.RunPython(link_existing, migrations.RunPython.noop)]
