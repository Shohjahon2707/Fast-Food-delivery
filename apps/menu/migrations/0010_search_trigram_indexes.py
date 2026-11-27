from django.db import migrations

INDEXES = (
    ("menu_dish_name_trgm", "menu_menuitem", "name"),
    ("menu_dish_description_trgm", "menu_menuitem", "description"),
    ("orders_restaurant_name_trgm", "orders_restaurant", "name"),
    ("orders_restaurant_cuisine_trgm", "orders_restaurant", "cuisine"),
)


def add_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, table, column in INDEXES:
        schema_editor.execute(
            f"CREATE INDEX {name} ON {table} USING gin (UPPER({column}) gin_trgm_ops)"
        )
    schema_editor.execute(
        "CREATE INDEX menu_dish_name_fuzzy ON menu_menuitem USING gin (name gin_trgm_ops)"
    )
    schema_editor.execute(
        "CREATE INDEX restaurant_name_fuzzy ON orders_restaurant USING gin (name gin_trgm_ops)"
    )


def remove_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name, _, _ in INDEXES:
        schema_editor.execute(f"DROP INDEX IF EXISTS {name}")
    schema_editor.execute("DROP INDEX IF EXISTS menu_dish_name_fuzzy")
    schema_editor.execute("DROP INDEX IF EXISTS restaurant_name_fuzzy")


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0009_dishoption"),
        ("orders", "0015_orderitem_note_orderitem_options_statusnotification"),
    ]
    operations = [migrations.RunPython(add_indexes, remove_indexes)]
