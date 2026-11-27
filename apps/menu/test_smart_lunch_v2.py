from datetime import time
from decimal import Decimal
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.orders.models import Restaurant

from .models import Category, MenuItem
from .smart_lunch import build_bundles


@override_settings(DELIVERY_FEE=Decimal("10000"), FREE_DELIVERY_FROM=Decimal("100000"))
class SmartLunchV2Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.restaurant = Restaurant.objects.create(name="Green", delivery_minutes=30)
        cls.category = Category.objects.create(name="Lunch")
        cls.main = cls.dish("Vegetable rice", 15000, "main", allergens=["soy"])
        cls.side = cls.dish("Salad", 6000, "side")
        cls.drink = cls.dish("Water", 4000, "drink")

    @classmethod
    def dish(cls, name, price, role, **kwargs):
        data = {
            "restaurant": cls.restaurant, "category": cls.category, "is_vegetarian": True,
            "is_halal": True, "allergens": [],
        }
        return MenuItem.objects.create(name=name, price=price, lunch_role=role, **(data | kwargs))

    def build(self, **kwargs):
        params = {"budget": 60000, "people": 2, "diet": "all", "exclude": "", "max_minutes": None}
        return build_bundles(**(params | kwargs))

    def search(self, **kwargs):
        return self.client.get(
            reverse("smart_lunch_v2"), {"budget": 60000, "people": 2, "diet": "vegetarian"} | kwargs,
        )

    def test_budget_boundary_and_closest_bundle(self):
        bundles, closest = self.build(max_minutes=30)
        self.assertIsNone(closest)
        self.assertEqual([bundle.total for bundle in bundles], [60000])
        self.assertEqual(
            bundles[0].lines, ((self.main, 2), (self.side, 2), (self.drink, 2)),
        )
        bundles, closest = self.build(budget=59999)
        self.assertEqual(bundles, [])
        self.assertEqual(closest.shortfall, 1)
        self.assertEqual(self.search(budget=59999).context["closest"].shortfall, 1)

    def test_free_delivery_at_threshold_uses_group_portions(self):
        self.main.price, self.main.servings = 80000, 2
        self.main.save(update_fields=["price", "servings"])
        (bundle,), _ = self.build(budget=100000)
        self.assertEqual(bundle.lines[0], (self.main, 1))
        self.assertEqual((bundle.subtotal, bundle.delivery_fee, bundle.total), (100000, 0, 100000))
        self.assertIn("free_delivery", bundle.reasons)

    def test_diet_and_exclusions_apply_before_composition(self):
        self.dish("Chicken", 15000, "main", is_vegetarian=False)
        self.dish("Unknown halal rice", 15000, "main", is_halal=None)
        self.dish("Mushroom rice", 15000, "main", description_en="With truffle oil")
        (bundle,), _ = self.build(diet="vegetarian", exclude="TRUFFLE OIL; unknown halal")
        self.assertEqual(bundle.lines[0][0], self.main)
        self.assertEqual(
            self.build(diet="halal", exclude="chicken, TRUFFLE OIL", allergens=["soy"]),
            ([], None),
        )

    def test_closed_restaurant_unavailable_dish_and_eta(self):
        self.dish("Sold out", 15000, "main", is_available=False)
        closed = Restaurant.objects.create(name="Closed", opens_at=time(18), closes_at=time(20))
        self.dish("Closed main", 24000, "main", restaurant=closed)
        with patch("apps.orders.delivery.timezone.localtime") as localtime:
            localtime.return_value.time.return_value = time(12)
            self.assertEqual(self.build(max_minutes=29), ([], None))
            (bundle,), _ = self.build()
        self.assertEqual(bundle.lines[0][0], self.main)

    def test_rank_is_stable_and_each_bundle_uses_one_restaurant(self):
        other = Restaurant.objects.create(name="Other", delivery_minutes=25)
        first = self.dish("Other main A", 21000, "main", restaurant=other)
        second = self.dish("Other main B", 21000, "main", restaurant=other)
        self.dish("Other salad", 4000, "side", restaurant=other)
        bundles, _ = self.build()
        self.assertEqual(bundles, self.build()[0])
        self.assertEqual([bundle.lines[0][0] for bundle in bundles], [first, second, self.main])
        for bundle in bundles:
            self.assertEqual({item.restaurant_id for item, _ in bundle.lines}, {bundle.restaurant.pk})

    def test_v2_route_form_and_bounded_page_queries(self):
        legacy = self.client.get(reverse("smart_lunch"))
        self.assertContains(legacy, reverse("smart_lunch_v2"))
        with CaptureQueriesContext(connection) as queries:
            response = self.search()
        self.assertLessEqual(len(queries), 5)
        self.assertTemplateUsed(response, "includes/bundle_card.html")
        self.assertContains(response, reverse("menu_item_detail", args=[self.main.pk]))
        add_form = response.content.decode().split(f'action="{reverse("add_lunch")}"', 1)[1]
        self.assertIn('name="csrfmiddlewaretoken"', add_form.split("</form>", 1)[0])
        invalid = self.search(budget=9999, people=11, max_minutes=14, exclude="x" * 101)
        self.assertFalse(invalid.context["lunches"])
        self.assertEqual(
            set(invalid.context["form"].errors), {"budget", "people", "max_minutes", "exclude"},
        )

    def test_bundle_uses_existing_cart_confirmation_and_server_prices(self):
        _, token = self.search().context["lunches"][0]
        other = Restaurant.objects.create(name="Other")
        other_main = self.dish("Other dish", 1000, "main", restaurant=other)
        self.client.post(reverse("add_to_cart", args=[other_main.pk]))
        cart = reverse("cart_detail")
        add = reverse("add_lunch")
        response = self.client.post(add, {"lunch": token, "price": 1, "restaurant": other.pk})
        self.assertTemplateUsed(response, "cart/replace.html")
        self.assertEqual(self.client.get(cart).context["subtotal"], 1000)
        self.assertRedirects(self.client.post(add, {"lunch": token, "replace": "yes", "price": 1}), cart)
        self.assertEqual(self.client.get(cart).context["total"], 60000)
        self.main.price = 15001
        self.main.save(update_fields=["price"])
        self.assertRedirects(
            self.client.post(add, {"lunch": token, "replace": "yes"}), reverse("smart_lunch"),
        )
