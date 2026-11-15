import io
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.cart.models import Cart, CartItem
from apps.menu.models import Category, MenuItem
from apps.orders.models import Order, Restaurant
from apps.orders.services import checkout


class MarketplaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.first = Restaurant.objects.create(name="First", accepting_orders=True)
        cls.second = Restaurant.objects.create(name="Second", accepting_orders=True)
        cls.closed = Restaurant.objects.create(name="Closed", accepting_orders=False)
        cls.category = Category.objects.create(name="Горячие блюда")
        cls.other_category = Category.objects.create(name="Салаты")
        cls.items = []
        for restaurant, category, price, available in [
            (cls.first, cls.category, 40000, True),
            (cls.second, cls.category, 70000, True),
            (cls.first, cls.category, 39999, True),
            (cls.first, cls.category, 70001, True),
            (cls.second, cls.other_category, 50000, True),
            (cls.closed, cls.category, 50000, True),
            (cls.second, cls.category, 55000, False),
        ]:
            cls.items.append(
                MenuItem.objects.create(
                    restaurant=restaurant,
                    category=category,
                    name=f"Dish {len(cls.items)}",
                    price=price,
                    is_available=available,
                )
            )
        cls.user = get_user_model().objects.create_user(
            "web-customer", password="Safe-testing-572!"
        )

    def test_smart_lunch_combines_category_budget_and_all_open_restaurants(self):
        response = self.client.get(
            reverse("smart_lunch"),
            {
                "category": self.category.pk,
                "min_price": 40000,
                "max_price": 70000,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["page_obj"]), self.items[:2])
        self.assertEqual(response.context["restaurant_count"], 2)
        self.assertContains(response, "без доставки")

    def test_search_is_case_insensitive_for_cyrillic_on_sqlite(self):
        item = self.items[0]
        item.name = "Шурпа с говядиной"
        item.save()
        response = self.client.get(reverse("smart_lunch"), {"q": "шурпа"})
        self.assertEqual(list(response.context["page_obj"]), [item])
        self.assertContains(self.client.get(reverse("home"), {"q": "ШУРПА"}), self.first.name)

    def test_invalid_ranges_never_silently_show_unfiltered_results(self):
        for params in [
            {"min_price": -1},
            {"min_price": "bad"},
            {"min_price": 70000, "max_price": 40000},
            {"max_price": "NaN"},
            {"category": "9999999999"},
        ]:
            response = self.client.get(reverse("smart_lunch"), params)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
            self.assertEqual(response.context["page_obj"].paginator.count, 0)

    def test_unbounded_filter_sort_and_pagination_preserve_search(self):
        response = self.client.get(reverse("smart_lunch"), {"min_price": 70000, "sort": "-price"})
        self.assertEqual(
            [x.price for x in response.context["page_obj"]], [Decimal(70001), Decimal(70000)]
        )
        response = self.client.get(reverse("smart_lunch"), {"q": "Second", "sort": "price"})
        self.assertEqual({x.restaurant_id for x in response.context["page_obj"]}, {self.second.pk})

    def test_restaurant_pages_and_dish_page_are_scoped(self):
        response = self.client.get(reverse("restaurant_detail", args=[self.first.pk]))
        self.assertTrue(all(x.restaurant_id == self.first.pk for x in response.context["page_obj"]))
        self.assertEqual(
            self.client.get(reverse("menu_item_detail", args=[self.items[5].pk])).status_code, 404
        )
        response = self.client.get(reverse("restaurant_detail", args=[self.closed.pk]))
        self.assertEqual(response.context["page_obj"].paginator.count, 0)

    def test_switching_restaurants_requires_explicit_confirmation(self):
        self.client.force_login(self.user)
        self.client.post(reverse("add_to_cart", args=[self.items[0].pk]))
        response = self.client.post(
            reverse("add_to_cart", args=[self.items[1].pk]), HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["replace_required"])
        cart = Cart.objects.get(user=self.user)
        self.assertEqual(cart.items.get().menu_item_id, self.items[0].pk)
        response = self.client.post(
            reverse("add_to_cart", args=[self.items[1].pk]), {"replace": "yes"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(cart.items.get().menu_item_id, self.items[1].pk)

    def test_closed_restaurant_cannot_be_added(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("add_to_cart", args=[self.items[5].pk]), HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(CartItem.objects.exists())

    def checkout_data(self):
        return {
            "checkout_token": uuid.uuid4(),
            "customer_name": "Customer",
            "phone": "+998901234567",
            "address": "Ташкент, тестовая улица 25",
            "payment_method": "cash",
            "total_price": 1,
        }

    def test_checkout_uses_correct_restaurant_prices_shipping_and_is_idempotent(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, menu_item=self.items[1])
        data = self.checkout_data()
        order = checkout(self.user, data)
        self.assertEqual(order.restaurant_id, self.second.pk)
        self.assertEqual(order.total_price, Decimal(80000))
        self.assertEqual(checkout(self.user, data).pk, order.pk)
        self.assertEqual(Order.objects.count(), 1)
        self.assertFalse(cart.items.exists())
        self.items[1].price = 99999
        self.items[1].save()
        self.assertEqual(order.items.get().price, Decimal(70000))

    def test_checkout_rejects_mixed_or_closed_restaurant_and_keeps_cart(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, menu_item=self.items[0])
        second = CartItem.objects.create(cart=cart, menu_item=self.items[1])
        with self.assertRaises(ValidationError):
            checkout(self.user, self.checkout_data())
        self.assertEqual(cart.items.count(), 2)
        second.delete()
        self.first.accepting_orders = False
        self.first.save()
        with self.assertRaises(ValidationError):
            checkout(self.user, self.checkout_data())
        self.assertFalse(Order.objects.exists())
        self.assertEqual(cart.items.count(), 1)

    def test_language_switch_keeps_filter_url_and_translates_interface(self):
        for language, expected in [
            ("en", "Smart lunch"),
            ("uz", "Aqlli tushlik"),
            ("ru", "Умный обед"),
        ]:
            response = self.client.post(
                reverse("set_language"),
                {"language": language, "next": "/smart-lunch/?min_price=40000&max_price=70000"},
                follow=True,
            )
            self.assertContains(response, expected)
            self.assertContains(response, 'value="40000"')
            self.assertEqual(response.wsgi_request.LANGUAGE_CODE, language)

    def test_seed_is_repeatable_and_preserves_custom_data(self):
        call_command("seed_marketplace", stdout=io.StringIO())
        counts = (Restaurant.objects.count(), MenuItem.objects.count())
        call_command("seed_marketplace", stdout=io.StringIO())
        self.assertEqual(counts, (Restaurant.objects.count(), MenuItem.objects.count()))
        self.items[0].refresh_from_db()
        self.assertEqual(self.items[0].price, 40000)

    def test_login_returns_customer_to_selected_dish(self):
        target = reverse("menu_item_detail", args=[self.items[0].pk])
        response = self.client.post(
            reverse("login") + "?next=" + target,
            {
                "username": self.user.username,
                "password": "Safe-testing-572!",
            },
        )
        self.assertRedirects(response, target)
