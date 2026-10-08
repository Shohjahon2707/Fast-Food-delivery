from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class UpgradeTests(TransactionTestCase):
    def test_existing_orders_carts_and_legacy_card_survive_upgrade(self):
        old_targets = [
            ("users", "0003_alter_user_role"),
            ("cart", "0003_remove_cartitem_created_at_and_more"),
            ("menu", "0003_alter_menuitem_price"),
            ("courier", "0004_courier_user"),
            ("orders", "0006_order_latitude_order_longitude"),
            ("payments", "0002_remove_payment_card_number_and_more"),
        ]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(old_targets)
        try:
            apps = executor.loader.project_state(old_targets).apps
            User = apps.get_model("users", "User")
            Category = apps.get_model("menu", "Category")
            Item = apps.get_model("menu", "MenuItem")
            user = User.objects.create(
                username="legacy", first_name="Old Name", phone="+998901234567"
            )
            category = Category.objects.create(name="Legacy")
            item = Item.objects.create(category=category, name="Legacy burger", price=32000)
            cart = apps.get_model("cart", "Cart").objects.create(user=user)
            Line = apps.get_model("cart", "CartItem")
            Line.objects.create(cart=cart, menu_item=item, quantity=20)
            Line.objects.create(cart=cart, menu_item=item, quantity=20)
            Order = apps.get_model("orders", "Order")
            Payment = apps.get_model("payments", "Payment")
            ids = []
            for status, method in [("pending", "cash"), ("paid", "card"), ("cancel", "cash")]:
                order = Order.objects.create(user=user, status=status, total_price=32000)
                apps.get_model("orders", "OrderItem").objects.create(
                    order=order, menu_item=item, quantity=1, price=32000
                )
                Payment.objects.create(
                    order=order,
                    user=user,
                    method=method,
                    status="paid" if method == "card" else "pending",
                )
                ids.append(order.pk)
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            from apps.cart.models import CartItem
            from apps.orders.models import Order as NewOrder

            orders = list(NewOrder.objects.filter(pk__in=ids).order_by("pk"))
            self.assertEqual(len({order.checkout_token for order in orders}), 3)
            self.assertEqual([order.status for order in orders], ["new", "new", "cancel"])
            self.assertEqual(orders[0].customer_name, "Old Name")
            self.assertEqual(orders[0].items.get().name, "Legacy burger")
            self.assertEqual(orders[1].issues.count(), 1)
            self.assertEqual(orders[2].payment.status, "cancelled")
            self.assertEqual(CartItem.objects.get(cart_id=cart.pk).quantity, 30)
        finally:
            MigrationExecutor(connection).migrate(latest)
