from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from apps.cart.models import Cart, CartItem
from apps.menu.models import Category, DishOption, MenuItem
from apps.users.models import SavedAddress

from .models import DishReview, Order, OrderItem, OrderReview, Promotion, Restaurant, StatusNotification
from .schedule import preparation_start
from .services import event


class CustomerFeaturesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.owner = users.create_user(username="food-owner")
        cls.other = users.create_user(username="food-other")
        cls.restaurant = Restaurant.objects.create(name="Test kitchen")
        category = Category.objects.create(name="Test menu")
        cls.dish = MenuItem.objects.create(
            name="Rice", category=category, restaurant=cls.restaurant, price=30000,
        )
        cls.order = Order.objects.create(user=cls.owner, restaurant=cls.restaurant, status="done")
        OrderItem.objects.create(order=cls.order, name="Rice", menu_item=cls.dish, price=28000)

    def test_review_is_for_delivered_order_owner_and_counts_once(self):
        url = reverse("review_order", args=[self.order.pk])
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url, {"score": 5}).status_code, 404)
        self.client.force_login(self.owner)
        data = {"score": 4, f"dish_{self.dish.pk}": 5, "comment": "Good"}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(OrderReview.objects.count(), 1)
        self.assertEqual(DishReview.objects.get().score, 5)
        self.assertContains(self.client.get(reverse("restaurant_detail", args=[self.restaurant.pk])), "★")
        self.assertEqual(self.client.get(reverse("menu_list"), {"sort": "rating"}).status_code, 200)

    def test_repeat_uses_current_price_and_skips_unavailable_dishes(self):
        self.client.force_login(self.owner)
        url = reverse("repeat_order", args=[self.order.pk])
        self.assertRedirects(self.client.post(url), reverse("cart_detail"))
        self.assertEqual(CartItem.objects.get().total, 30000)
        self.dish.is_available = False
        self.dish.save(update_fields=["is_available"])
        self.assertRedirects(self.client.post(url), reverse("order_detail", args=[self.order.pk]))

    def test_favorite_and_saved_address_are_private(self):
        self.client.force_login(self.owner)
        add = reverse("favorite_dish", args=[self.dish.pk])
        self.client.post(add)
        self.assertContains(self.client.get(reverse("favorites")), "Rice")
        address = SavedAddress.objects.create(user=self.owner, label="Home", address="Street 123")
        delete = reverse("delete_address", args=[address.pk])
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("favorites")), "Rice")
        self.assertEqual(self.client.post(delete).status_code, 404)
        self.assertTrue(SavedAddress.objects.filter(pk=address.pk).exists())

    def test_promo_recalculates_total_and_consumes_one_use(self):
        self.client.force_login(self.owner)
        cart = Cart.objects.create(user=self.owner)
        CartItem.objects.create(cart=cart, menu_item=self.dish)
        promo = Promotion.objects.create(code="lunch", amount=5000, max_uses=1)
        url = reverse("create_order")
        form = self.client.get(url).context["form"]
        data = {
            "checkout_token": form.initial["checkout_token"], "customer_name": "Buyer",
            "phone": "+998901234567", "address": "Tashkent, house 5",
            "payment_method": "cash", "promo_code": "lunch", "quoted_fee": 10000,
        }
        response = self.client.post(url, {**data, "action": "quote"})
        self.assertEqual(response.context["total"], 35000)
        self.assertEqual(self.client.post(url, {**data, "quoted_total": 35000}).status_code, 302)
        self.assertEqual(self.client.post(url, {**data, "quoted_total": 35000}).status_code, 302)
        promo.refresh_from_db()
        self.assertEqual(promo.used_count, 1)
        placed = Order.objects.get(checkout_token=data["checkout_token"])
        self.assertEqual((placed.total_price, placed.discount, placed.subtotal), (35000, 5000, 30000))

    def test_partner_only_reads_and_changes_own_restaurant(self):
        partner = get_user_model().objects.create_user(username="partner", role="partner")
        restaurant = Restaurant.objects.create(name="Own kitchen", partner=partner)
        own = MenuItem.objects.create(
            name="Soup", restaurant=restaurant, category=self.dish.category, price=20000,
        )
        self.client.force_login(partner)
        response = self.client.get(reverse("partner_dashboard"))
        self.assertContains(response, "Own kitchen")
        self.assertNotContains(response, self.restaurant.name)
        self.assertEqual(self.client.get(reverse("partner_edit_dish", args=[self.dish.pk])).status_code, 404)
        self.assertContains(self.client.get(reverse("partner_edit_dish", args=[own.pk])), "Soup")

    def test_schedule_stays_inside_the_same_opening_period(self):
        self.restaurant.opens_at, self.restaurant.closes_at = time(10), time(22)
        tomorrow = timezone.localdate() + timedelta(days=1)
        arrival = timezone.make_aware(datetime.combine(tomorrow, time(13)))
        self.assertEqual(preparation_start(self.restaurant, arrival, 35), arrival - timedelta(minutes=35))
        early = timezone.make_aware(datetime.combine(tomorrow, time(10, 15)))
        with self.assertRaises(ValidationError):
            preparation_start(self.restaurant, early, 35)

    def test_options_from_another_dish_are_rejected_and_valid_price_is_used(self):
        option = DishOption.objects.create(dish=self.dish, name="Extras", extra_price=3500)
        url = reverse("add_to_cart", args=[self.dish.pk])
        self.client.force_login(self.owner)
        self.client.post(url, {"option": [999999]})
        self.assertFalse(CartItem.objects.exists())
        self.client.post(url, {"option": [option.pk], "note": "No onions"})
        line = CartItem.objects.get()
        self.assertEqual((line.unit_price, line.note), (33500, "No onions"))
        self.assertContains(self.client.get(reverse("cart_detail")), "No onions")

    def test_notification_enqueues_once_per_status_change(self):
        self.owner.notify_sms = True
        self.owner.save(update_fields=["notify_sms"])
        self.order.phone = "+998901234567"
        event(self.order, self.owner, "Delivered")
        event(self.order, self.owner, "Support note")
        self.assertEqual(StatusNotification.objects.count(), 1)
        self.assertEqual(StatusNotification.objects.get().channel, "sms")

    def test_transliterated_search_and_suggestions(self):
        self.dish.name = "Ташкентский плов"
        self.dish.save(update_fields=["name"])
        self.assertContains(self.client.get(reverse("menu_list"), {"q": "plov"}), "Ташкентский плов")
        result = self.client.get(reverse("menu_suggestions"), {"q": "plov"}).json()
        self.assertEqual(result["suggestions"], ["Ташкентский плов"])

    def test_translated_content_and_schema_escape_user_input(self):
        self.dish.name_en = "Rice with chickpeas"
        self.dish.description_en = "</script><script>demo()</script>"
        self.dish.save(update_fields=["name_en", "description_en"])
        with override("en"):
            self.assertEqual(self.dish.localized_name, "Rice with chickpeas")
        url = reverse("restaurant_detail", args=[self.restaurant.pk])
        page = self.client.get(url, headers={"Accept-Language": "en"})
        self.assertContains(page, "application/ld+json")
        self.assertContains(page, "Rice with chickpeas")
        self.assertNotContains(page, "</script><script>demo()")
        self.assertEqual(self.client.get(reverse("readiness")).json(), {"status": "ok"})
