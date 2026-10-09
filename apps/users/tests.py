import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.courier.models import Courier
from apps.menu.models import Category, MenuItem
from apps.orders import services
from apps.orders.models import DeliveryOffer, Order
from apps.payments.models import Payment

User = get_user_model()


class DeliveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(
            "customer",
            email="customer@example.com",
            password="Nice-password123!",
            first_name="Анна",
            phone="+998901234567",
        )
        cls.other = User.objects.create_user("other", password="Nice-password123!")
        cls.courier_user = User.objects.create_user(
            "courier", role="courier", password="Nice-password123!"
        )
        cls.courier = Courier.objects.create(
            user=cls.courier_user,
            name="Курьер",
            phone="+998901112233",
            is_approved=True,
            shift_status="active",
        )
        cls.admin = User.objects.create_superuser("admin", "admin@example.com", "Nice-password123!")
        cls.category = Category.objects.create(name="Бургеры")
        cls.item = MenuItem.objects.create(category=cls.category, name="Бургер", price=32000)

    def setUp(self):
        cache.clear()
        self.client.force_login(self.customer)

    def cart(self, quantity=2):
        cart, _ = Cart.objects.get_or_create(user=self.customer)
        CartItem.objects.create(cart=cart, menu_item=self.item, quantity=quantity)
        return cart

    def checkout_data(self, **kwargs):
        data = {
            "customer_name": "Анна",
            "phone": "+998901234567",
            "address": "Ташкент, улица Амира Темура, дом 12",
            "payment_method": "cash",
            "checkout_token": str(uuid.uuid4()),
            "save_address": True,
            "comment": "Домофон 4",
        }
        data.update(kwargs)
        return data

    def order(self, status="new", **kwargs):
        self.cart()
        order = services.checkout(self.customer, self.checkout_data())
        if status != "new":
            order.status = status
            order.save(update_fields=["status"])
        for key, value in kwargs.items():
            setattr(order, key, value)
        if kwargs:
            order.save()
        if status == "ready":
            self.reserve(order)
        return order

    def reserve(self, order):
        DeliveryOffer.objects.create(
            order=order,
            courier=self.courier,
            state="accepted",
            expires_at=timezone.now() + timedelta(minutes=15),
        )

    def test_cash_checkout_snapshot_and_duplicate_submit(self):
        cart = self.cart()
        data = self.checkout_data()
        response = self.client.post(reverse("create_order"), data)
        order = Order.objects.get()
        self.assertRedirects(response, reverse("order_success", args=[order.pk]))
        self.assertEqual(order.total_price, Decimal("74000"))
        self.assertEqual(order.delivery_fee, 10000)
        self.assertEqual(order.items.get().name, "Бургер")
        self.assertEqual(order.items.get().price, 32000)
        self.assertEqual(order.payment.status, "pending")
        self.assertEqual(order.status, "new")
        self.assertFalse(cart.items.exists())
        self.client.post(reverse("create_order"), data)
        self.assertEqual(Order.objects.count(), 1)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.address, data["address"])
        self.item.price = 40000
        self.item.save()
        self.assertEqual(order.items.get().total(), 64000)

    def test_free_delivery_threshold(self):
        self.cart(quantity=4)
        order = services.checkout(self.customer, self.checkout_data())
        self.assertEqual(order.delivery_fee, 0)
        self.assertEqual(order.total_price, 128000)

    def test_checkout_get_cannot_mutate(self):
        cart = self.cart()
        self.assertEqual(self.client.get(reverse("create_order")).status_code, 200)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(cart.items.count(), 1)

    def test_invalid_checkout_preserves_cart(self):
        cart = self.cart()
        for changes in [
            {"payment_method": "card"},
            {"phone": "abc"},
            {"address": "x"},
            {"checkout_token": "x"},
        ]:
            response = self.client.post(reverse("create_order"), self.checkout_data(**changes))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
        self.assertFalse(Order.objects.exists())
        self.assertEqual(cart.items.count(), 1)

    def test_unavailable_product_blocks_checkout(self):
        self.cart()
        self.item.is_available = False
        self.item.save()
        with self.assertRaises(ValidationError):
            services.checkout(self.customer, self.checkout_data())
        self.assertFalse(Order.objects.exists())

    def test_checkout_rollback_preserves_cart(self):
        cart = self.cart()
        with patch(
            "apps.orders.services.OrderItem.objects.create",
            side_effect=RuntimeError("write failed"),
        ):
            with self.assertRaises(RuntimeError):
                services.checkout(self.customer, self.checkout_data())
        self.assertEqual(cart.items.count(), 1)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Payment.objects.exists())

    def test_quantity_limits_and_post_only(self):
        cart = self.cart()
        line = cart.items.get()
        for route, args in [
            ("add_to_cart", [self.item.pk]),
            ("remove_from_cart", [line.pk]),
            ("update_quantity", [line.pk]),
        ]:
            self.assertEqual(self.client.get(reverse(route, args=args)).status_code, 405)
        for quantity in [-1, 31, "abc", "999999999999999999999999"]:
            self.client.post(reverse("update_quantity", args=[line.pk]), {"quantity": quantity})
            line.refresh_from_db()
            self.assertEqual(line.quantity, 2)
        self.client.post(reverse("update_quantity", args=[line.pk]), {"quantity": 0})
        self.assertFalse(cart.items.exists())

    def test_cart_ownership_and_safe_redirect(self):
        cart = Cart.objects.create(user=self.other)
        line = CartItem.objects.create(cart=cart, menu_item=self.item)
        self.assertEqual(
            self.client.post(reverse("remove_from_cart", args=[line.pk])).status_code, 404
        )
        response = self.client.post(
            reverse("add_to_cart", args=[self.item.pk]), {"next": "https://evil.example/"}
        )
        self.assertRedirects(response, reverse("cart_detail"))

    def test_ajax_cart(self):
        response = self.client.post(
            reverse("add_to_cart", args=[self.item.pk]), HTTP_ACCEPT="application/json"
        )
        self.assertEqual(response.json()["count"], 1)

    def test_database_cart_uniqueness(self):
        cart = self.cart()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CartItem.objects.create(cart=cart, menu_item=self.item)

    def test_roles_and_admin_routes(self):
        for user in [self.customer, self.courier_user]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("operations")).status_code, 403)
            self.assertEqual(self.client.get("/admin/").status_code, 302)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("courier_orders")).status_code, 403)
        self.client.force_login(self.courier_user)
        for route in ["cart_detail", "create_order", "order_list", "profile"]:
            self.assertEqual(self.client.get(reverse(route)).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("add_to_cart", args=[self.item.pk])).status_code, 403
        )
        self.assertRedirects(self.client.get("/"), reverse("courier_orders"))

    def test_admin_role_string_does_not_grant_privilege(self):
        self.customer.role = "admin"
        self.customer.save()
        self.assertFalse(self.customer.is_admin)
        self.assertEqual(self.client.get(reverse("operations")).status_code, 403)

    def test_foreign_orders_are_not_visible(self):
        order = self.order()
        self.client.force_login(self.other)
        for route in ["order_detail", "order_success", "cash_success", "pay_with_card"]:
            self.assertEqual(self.client.get(reverse(route, args=[order.pk])).status_code, 404)
        self.assertEqual(
            self.client.post(
                reverse("cancel_order", args=[order.pk]), {"reason": "Ошибка адреса"}
            ).status_code,
            404,
        )

    def test_complete_lifecycle(self):
        order = self.order()
        services.advance_order(order.pk, self.admin, "cooking")
        services.advance_order(order.pk, self.admin, "ready")
        self.reserve(order)
        services.take_order(order.pk, self.courier_user)
        self.client.force_login(self.courier_user)
        self.assertContains(self.client.get(reverse("courier_orders")), self.customer.phone)
        self.client.post(reverse("confirm_cash_payment", args=[order.pk]), {"cash_received": "yes"})
        order.refresh_from_db()
        order.payment.refresh_from_db()
        self.courier.refresh_from_db()
        self.assertEqual(order.status, "done")
        self.assertEqual(order.payment.status, "paid")
        self.assertEqual(order.payment.confirmed_by, self.courier_user)
        self.assertIsNotNone(order.payment.paid_at)
        self.assertEqual(self.courier.shift_status, "active")
        self.assertEqual(order.events.count(), 5)
        services.deliver_order(order.pk, self.courier_user)
        self.assertEqual(order.events.count(), 5)

    def test_customer_cannot_mark_paid_and_old_card_cannot_pay(self):
        order = self.order()
        self.assertEqual(self.client.post(f"/orders/mark_paid/{order.pk}/").status_code, 404)
        self.client.post(
            reverse("pay_with_card", args=[order.pk]), {"card_number": "4242424242424242"}
        )
        self.client.post(reverse("confirm_payment"), {"otp_code": "123456"})
        for _ in range(2):
            self.client.get(reverse("cash_success", args=[order.pk]))
        order.payment.refresh_from_db()
        self.assertEqual(order.payment.status, "pending")

    def test_invalid_state_transitions(self):
        order = self.order()
        with self.assertRaises(ValidationError):
            services.advance_order(order.pk, self.admin, "done")
        with self.assertRaises(PermissionDenied):
            services.advance_order(order.pk, self.customer, "cooking")
        with self.assertRaises(ValidationError):
            services.take_order(order.pk, self.courier_user)

    def test_courier_must_be_approved_and_on_shift(self):
        order = self.order(status="ready")
        self.courier.is_approved = False
        self.courier.save()
        with self.assertRaises(ValidationError):
            services.take_order(order.pk, self.courier_user)
        self.courier.is_approved = True
        self.courier.shift_status = "inactive"
        self.courier.save()
        with self.assertRaises(ValidationError):
            services.take_order(order.pk, self.courier_user)

    def test_only_one_courier_and_one_active_delivery(self):
        order = self.order(status="ready")
        services.take_order(order.pk, self.courier_user)
        other_user = User.objects.create_user("courier2", role="courier")
        Courier.objects.create(
            user=other_user, name="Второй", phone="123", is_approved=True, shift_status="active"
        )
        with self.assertRaises(ValidationError):
            services.take_order(order.pk, other_user)
        second = Order.objects.create(user=self.customer, status="ready")
        with self.assertRaises(ValidationError):
            services.take_order(second.pk, self.courier_user)

    def test_unassigned_courier_cannot_complete(self):
        order = self.order(status="delivery")
        with self.assertRaises(PermissionDenied):
            services.deliver_order(order.pk, self.courier_user)

    def test_completion_requires_explicit_cash_confirmation(self):
        order = self.order(status="ready")
        services.take_order(order.pk, self.courier_user)
        self.client.force_login(self.courier_user)
        self.client.post(reverse("confirm_cash_payment", args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.status, "delivery")

    def test_courier_busy_cannot_end_shift(self):
        order = self.order(status="ready")
        services.take_order(order.pk, self.courier_user)
        self.client.force_login(self.courier_user)
        self.client.post(reverse("courier_shift"))
        self.courier.refresh_from_db()
        self.assertEqual(self.courier.shift_status, "busy")

    def test_early_cancellation_and_idempotency(self):
        order = self.order()
        self.client.post(
            reverse("cancel_order", args=[order.pk]), {"reason": "Выбрал неверный адрес"}
        )
        order.refresh_from_db()
        order.payment.refresh_from_db()
        self.assertEqual(order.status, "cancel")
        self.assertEqual(order.payment.status, "cancelled")
        services.cancel_order(order.pk, self.customer, "Выбрал неверный адрес")
        self.assertEqual(order.events.count(), 2)

    def test_late_cancellation_is_issue_then_admin_cancels(self):
        order = self.order(status="cooking")
        self.client.post(
            reverse("cancel_order", args=[order.pk]), {"reason": "Нужно срочно уехать"}
        )
        order.refresh_from_db()
        self.assertEqual(order.status, "cooking")
        self.assertEqual(order.issues.count(), 1)
        services.report_issue(order.pk, self.customer, "Повторное обращение")
        self.assertEqual(order.issues.count(), 1)
        with self.assertRaises(ValidationError):
            services.advance_order(order.pk, self.admin, "ready")
        services.cancel_order(order.pk, self.admin, "Согласовано с покупателем")
        self.assertIsNotNone(order.issues.get().resolved_at)

    def test_delivery_issue_and_reassignment(self):
        order = self.order(status="ready")
        services.take_order(order.pk, self.courier_user)
        services.report_issue(order.pk, self.courier_user, "Сломался велосипед")
        with self.assertRaises(ValidationError):
            services.deliver_order(order.pk, self.courier_user)
        services.resolve_issue(
            order.pk, self.admin, "Заказ возвращён в ресторан", return_to_kitchen=True
        )
        order.refresh_from_db()
        self.courier.refresh_from_db()
        self.assertEqual(order.status, "ready")
        self.assertIsNone(order.courier)
        self.assertEqual(self.courier.shift_status, "active")
        self.assertFalse(order.issues.filter(resolved_at__isnull=True).exists())

    def test_paid_cancellation_tracks_manual_refund(self):
        order = self.order(status="delivery", courier=self.courier)
        payment = order.payment
        payment.status = "paid"
        payment.save()
        services.cancel_order(order.pk, self.admin, "Доставка не состоялась")
        payment.refresh_from_db()
        self.assertEqual(payment.status, "refund_due")
        with self.assertRaises(PermissionDenied):
            services.confirm_refund(order.pk, self.customer)
        services.confirm_refund(order.pk, self.admin)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "refunded")

    def test_courier_contact_hidden_until_assignment(self):
        order = self.order(status="ready")
        self.client.force_login(self.courier_user)
        response = self.client.get(reverse("courier_orders"))
        self.assertNotContains(response, order.phone)
        self.assertNotContains(response, order.address)

    def test_admin_workflows_and_minimum_permissions(self):
        order = self.order()
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("operations")), "Рабочая панель")
        self.client.post(reverse("operation_action", args=[order.pk]), {"action": "cooking"})
        order.refresh_from_db()
        self.assertEqual(order.status, "cooking")
        self.client.post(reverse("approve_courier", args=[self.courier.pk]), {"approved": "no"})
        self.courier.refresh_from_db()
        self.assertFalse(self.courier.is_approved)
        staff = User.objects.create_user("staff", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("operations")).status_code, 403)

    def test_customer_signup_cannot_escalate_role(self):
        self.client.logout()
        self.client.post(
            reverse("register_user"),
            {
                "first_name": "Лола",
                "username": "lola",
                "email": "lola@example.com",
                "phone": "+998 90 333 44 55",
                "password1": "Unique-Pass347!",
                "password2": "Unique-Pass347!",
                "role": "admin",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        user = User.objects.get(username="lola")
        self.assertTrue(user.is_customer)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.phone, "+998903334455")

    def test_courier_registration_both_urls(self):
        for index, route in enumerate(["register_courier", "courier_register"]):
            self.client.logout()
            response = self.client.post(
                reverse(route),
                {
                    "name": "Курьер",
                    "username": f"rider{index}",
                    "email": f"rider{index}@example.com",
                    "phone": "+998901112233",
                    "vehicle": "bike",
                    "password1": "Unique-Pass347!",
                    "password2": "Unique-Pass347!",
                },
            )
            self.assertRedirects(response, reverse("courier_orders"))
            user = User.objects.get(username=f"rider{index}")
            self.assertTrue(user.is_courier)
            self.assertFalse(user.courier_profile.is_approved)
            self.assertEqual(user.courier_profile.shift_status, "inactive")

    def test_login_portals_remember_and_rate_limit(self):
        self.client.logout()
        response = self.client.post(
            reverse("login"), {"username": "courier", "password": "Nice-password123!"}
        )
        self.assertContains(response, "отдельный вход")
        response = self.client.post(
            reverse("courier_login"),
            {"username": "courier", "password": "Nice-password123!", "remember_me": "on"},
        )
        self.assertRedirects(response, reverse("courier_orders"))
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.client.logout()
        cache.clear()
        for _ in range(10):
            self.client.post(reverse("login"), {"username": "bad", "password": "wrong"})
        self.assertEqual(
            self.client.post(
                reverse("login"), {"username": "bad", "password": "wrong"}
            ).status_code,
            429,
        )

    def test_password_reset_and_preferences(self):
        self.client.logout()
        self.client.post(reverse("password_reset"), {"email": self.customer.email})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/users/password/reset/", mail.outbox[0].body)
        response = self.client.post(
            reverse("save_preferences"), {"diet": "vegetarian", "motion": "reduce"}
        )
        self.assertTrue(response.cookies["food_preferences"]["httponly"])
        self.assertEqual(response.cookies["food_preferences"]["samesite"], "Lax")
        self.assertContains(self.client.get(reverse("preferences")), 'class="reduce-motion"')
        self.assertNotContains(self.client.get(reverse("menu_list")), "product-card")
        response = self.client.post(reverse("save_preferences"), {"action": "forget"})
        self.assertEqual(response.cookies["food_preferences"]["max-age"], 0)

    def test_private_pages_not_cached_or_admin_links_leaked(self):
        response = self.client.get(reverse("order_list"))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotContains(response, 'href="/admin/')
        self.assertNotContains(response, 'href="/operations/')

    def test_csrf_enforced_for_actions(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.customer)
        self.assertEqual(client.post(reverse("add_to_cart", args=[self.item.pk])).status_code, 403)

    def test_seed_menu_is_idempotent(self):
        call_command("seed_menu", verbosity=0)
        count = MenuItem.objects.count()
        call_command("seed_menu", verbosity=0)
        self.assertEqual(MenuItem.objects.count(), count)

    def test_public_pages_and_empty_states(self):
        self.client.logout()
        for route in [
            "home",
            "menu_list",
            "login",
            "register_user",
            "courier_login",
            "courier_register",
            "preferences",
            "password_reset",
        ]:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(route)).status_code, 200)

    def test_status_polling_is_private_and_versioned(self):
        order = self.order()
        url = reverse("order_status", args=[order.pk])
        response = self.client.get(url)
        self.assertEqual(response.json(), {"status": "new", "version": 1})
        self.assertIn("no-store", response["Cache-Control"])
        services.advance_order(order.pk, self.admin, "cooking")
        self.assertEqual(self.client.get(url).json()["version"], 2)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.courier_user)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_admin_can_reconcile_archived_payment_and_finish_incident(self):
        order = self.order(status="delivery", courier=self.courier)
        payment = order.payment
        payment.method, payment.status = "card", "review"
        payment.save()
        services.report_issue(order.pk, self.customer, "Проверьте старую оплату")
        self.client.force_login(self.admin)
        endpoint = reverse("operation_action", args=[order.pk])
        self.client.post(endpoint, {"action": "reconcile", "reason": "Согласовано по телефону"})
        payment.refresh_from_db()
        self.assertEqual(payment.method, "card")
        self.client.post(
            endpoint, {"action": "reconcile", "reason": "Согласовано по телефону", "agreed": "yes"}
        )
        payment.refresh_from_db()
        self.assertEqual(payment.method, "cash")
        self.assertEqual(payment.status, "pending")
        self.client.post(
            endpoint,
            {"action": "complete", "reason": "Клиент и курьер подтвердили", "received": "yes"},
        )
        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(order.status, "done")
        self.assertEqual(payment.status, "paid")
        self.assertEqual(payment.confirmed_by, self.admin)
        self.assertFalse(order.issues.filter(resolved_at__isnull=True).exists())
