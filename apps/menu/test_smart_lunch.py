from datetime import time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.cart.models import Cart, CartItem
from apps.orders.delivery import is_open, quote_delivery
from apps.orders.models import Order, Restaurant

from .models import Category, MenuItem


@override_settings(DELIVERY_FEE=Decimal("10000"), FREE_DELIVERY_FROM=Decimal("100000"))
class SmartLunchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.restaurant = Restaurant.objects.create(name="Green", delivery_minutes=35)
        cls.category = Category.objects.create(name="Demo")
        cls.user = get_user_model().objects.create_user(
            username="lunch@example.test", password="Test-guest-8536"
        )
        cls.main = cls.dish("Rice", 15000, "main")
        cls.side = cls.dish("Salad", 6000, "side")
        cls.drink = cls.dish("Water", 4000, "drink")
        cls.dish("Chicken", 5000, "main", vegetarian=False)

    @classmethod
    def dish(cls, name, price, role, vegetarian=True, **attrs):
        return MenuItem.objects.create(
            name=name, restaurant=cls.restaurant, category=cls.category,
            price=price, lunch_role=role, is_vegetarian=vegetarian, **attrs,
        )

    def search(self, budget=60000, **params):
        return self.client.get(reverse("smart_lunch"), {
            "budget": budget, "people": 2, "diet": "vegetarian", "max_minutes": 40, **params,
        })

    def test_budget_and_checkout_are_consistent_after_login(self):
        lunch, token = self.search().context["lunches"][0]
        self.assertEqual(lunch.total, 60000)
        self.assertEqual([item.pk for item, _ in lunch.lines], [
            self.main.pk, self.side.pk, self.drink.pk,
        ])
        self.client.post(reverse("add_lunch"), {"lunch": token})
        self.assertEqual(self.client.get(reverse("cart_detail")).context["total"], 60000)
        response = self.client.post(reverse("login"), {
            "username": self.user.username, "password": "Test-guest-8536",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CartItem.objects.filter(cart__user=self.user).count(), 3)
        checkout = self.client.get(reverse("create_order"))
        self.assertEqual(checkout.context["total"], 60000)
        self.client.post(reverse("create_order"), {
            "checkout_token": checkout.context["form"].initial["checkout_token"],
            "customer_name": "Demo",
            "phone": "+998901234567",
            "address": "Tashkent, building 15",
            "payment_method": "cash",
            "quoted_fee": "10000",
        })
        self.assertEqual(Order.objects.get(user=self.user).total_price, 60000)

    def test_lower_budget_and_closest_option(self):
        self.assertTrue(all(lunch.total <= 59999 for lunch, _ in self.search(59999).context["lunches"]))
        result = self.search(39999)
        self.assertFalse(result.context["lunches"])
        self.assertEqual(result.context["closest"].extra, 1)

    def test_filters_respect_unknown_allergens_closed_restaurants_and_time(self):
        self.assertFalse(self.search(allergens=["gluten"]).context["lunches"])
        self.assertFalse(self.search(max_minutes=30).context["lunches"])
        self.restaurant.accepting_orders = False
        self.restaurant.save(update_fields=["accepting_orders"])
        self.assertFalse(self.search().context["lunches"])

    def test_stale_lunch_does_not_modify_existing_cart(self):
        _, token = self.search().context["lunches"][0]
        self.client.post(reverse("add_to_cart", args=[self.drink.pk]))
        self.main.price = 16000
        self.main.save(update_fields=["price"])
        result = self.client.post(reverse("add_lunch"), {"lunch": token, "replace": "yes"})
        self.assertRedirects(result, reverse("smart_lunch"))
        cart = self.client.get(reverse("cart_detail"))
        self.assertEqual(cart.context["subtotal"], 4000)

    def test_login_with_another_restaurant_keeps_both_until_customer_chooses(self):
        cart = Cart.objects.create(user=self.user)
        another = Restaurant.objects.create(name="Another")
        other_item = MenuItem.objects.create(
            name="Other", price=45000, restaurant=another, category=self.category,
        )
        CartItem.objects.create(cart=cart, menu_item=other_item)
        self.client.post(reverse("add_to_cart", args=[self.main.pk]))
        response = self.client.post(reverse("login"), {
            "username": self.user.username, "password": "Test-guest-8536",
        })
        self.assertRedirects(response, reverse("cart_detail"))
        self.assertTrue(self.client.get(reverse("cart_detail")).context["guest_conflict"])
        self.client.post(reverse("resolve_guest_basket"), {"keep": "guest"})
        self.assertEqual(cart.items.get().menu_item_id, self.main.pk)

    def test_delivery_checks_zone_minimum_and_night_schedule(self):
        restaurant = self.restaurant
        restaurant.latitude, restaurant.longitude = Decimal("41.31"), Decimal("69.24")
        restaurant.delivery_radius_km = Decimal("8")
        restaurant.minimum_subtotal = 20000
        with self.assertRaises(ValidationError):
            quote_delivery(restaurant, 19999)
        with self.assertRaises(ValidationError):
            quote_delivery(restaurant, 20000, (Decimal("42"), Decimal("69.24")))
        point = (Decimal("41.35"), Decimal("69.24"))
        self.assertGreater(quote_delivery(restaurant, 99999, point).fee, 10000)
        self.assertEqual(quote_delivery(restaurant, 100000, point).fee, 0)
        restaurant.opens_at, restaurant.closes_at = time(18), time(2)
        self.assertTrue(is_open(restaurant, time(1)))
        self.assertFalse(is_open(restaurant, time(2)))
