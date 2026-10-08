from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.cart.models import Cart, CartItem
from apps.courier.models import Courier
from apps.menu.models import Category, MenuItem
from apps.orders import services
from apps.orders.models import Order

User = get_user_model()


@skipUnless(connection.vendor == "postgresql", "Row-lock concurrency requires PostgreSQL")
class ConcurrentDeliveryTests(TransactionTestCase):
    def setUp(self):
        self.customer = User.objects.create_user("customer")
        self.riders = [User.objects.create_user(f"rider{i}", role="courier") for i in range(2)]
        for rider in self.riders:
            Courier.objects.create(
                user=rider,
                name=rider.username,
                phone="123",
                is_approved=True,
                shift_status="active",
            )
        category = Category.objects.create(name="Food")
        self.item = MenuItem.objects.create(category=category, name="Burger", price=32000)
        self.cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=self.cart, menu_item=self.item)

    def race(self, callbacks):
        barrier = Barrier(len(callbacks))

        def call(callback):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    callback()
                    return "ok"
                except ValidationError:
                    return "conflict"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(callbacks)) as pool:
            return list(pool.map(call, callbacks))

    def test_duplicate_checkout_creates_one_order(self):
        data = {
            "checkout_token": uuid4(),
            "customer_name": "Customer",
            "phone": "+998901234567",
            "address": "Tashkent, test street 12",
            "payment_method": "cash",
        }
        results = self.race([lambda: services.checkout(self.customer, data)] * 2)
        self.assertEqual(results, ["ok", "ok"])
        self.assertEqual(Order.objects.count(), 1)
        self.assertFalse(self.cart.items.exists())

    def test_two_couriers_cannot_take_the_same_order(self):
        order = Order.objects.create(user=self.customer, status="ready")
        results = self.race(
            [
                lambda: services.take_order(order.pk, self.riders[0]),
                lambda: services.take_order(order.pk, self.riders[1]),
            ]
        )
        self.assertCountEqual(results, ["ok", "conflict"])
        order.refresh_from_db()
        self.assertEqual(order.status, "delivery")

    def test_one_courier_cannot_take_two_orders(self):
        orders = [Order.objects.create(user=self.customer, status="ready") for _ in range(2)]
        results = self.race(
            [
                lambda: services.take_order(orders[0].pk, self.riders[0]),
                lambda: services.take_order(orders[1].pk, self.riders[0]),
            ]
        )
        self.assertCountEqual(results, ["ok", "conflict"])
        self.assertEqual(Order.objects.filter(status="delivery").count(), 1)
