from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.courier.models import Courier
from apps.orders import services
from apps.orders.dispatch import dispatch_once, respond
from apps.orders.forms import CheckoutForm
from apps.orders.models import DeliveryOffer, Order, OrderIssue, Restaurant
from apps.payments.models import Payment

User = get_user_model()


class DispatchTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user("buyer", phone="+998901234567")
        self.restaurant = Restaurant.objects.create(
            address="Kitchen street 12", latitude=41, longitude=69
        )
        self.user = User.objects.create_user("rider", role="courier")
        self.rider = Courier.objects.create(
            user=self.user,
            name="Rider",
            phone="123",
            is_approved=True,
            shift_status="active",
            latitude=41,
            longitude=69,
            location_accuracy=10,
            location_updated_at=timezone.now(),
        )
        self.order = Order.objects.create(
            user=self.customer, status="ready", latitude=41, longitude=69
        )
        Payment.objects.create(
            user=self.customer, order=self.order, method="cash", status="pending"
        )

    def another_rider(self):
        user = User.objects.create_user("rider2", role="courier")
        return Courier.objects.create(
            user=user,
            name="Rider2",
            phone="123",
            is_approved=True,
            shift_status="active",
            latitude=42,
            longitude=70,
            location_accuracy=10,
            location_updated_at=timezone.now(),
        )

    def test_nearest_courier_gets_personal_offer_and_can_pick_up(self):
        self.another_rider()
        self.assertEqual(dispatch_once(), 1)
        offer = DeliveryOffer.objects.get()
        self.assertEqual(offer.courier_id, self.rider.pk)
        with self.assertRaises(ValidationError):
            services.take_order(self.order.pk, self.user)
        respond(offer.pk, self.user, True)
        services.take_order(self.order.pk, self.user)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "delivery")
        self.assertIsNotNone(self.order.delivery_eta)

    def test_stale_or_imprecise_or_missing_location_is_ineligible(self):
        for fields in [
            {"location_updated_at": timezone.now() - timedelta(minutes=4)},
            {"location_updated_at": timezone.now(), "location_accuracy": 201},
            {"location_accuracy": None},
        ]:
            Courier.objects.filter(pk=self.rider.pk).update(**fields)
            self.assertEqual(dispatch_once(), 0)
        self.assertFalse(DeliveryOffer.objects.exists())

    def test_disabled_staff_and_off_shift_are_ineligible(self):
        for change in [
            {"is_active": False},
            {"is_active": True, "is_staff": True},
            {"is_staff": False, "role": "customer"},
        ]:
            User.objects.filter(pk=self.user.pk).update(**change)
            self.assertEqual(dispatch_once(), 0)
        User.objects.filter(pk=self.user.pk).update(role="courier")
        Courier.objects.filter(pk=self.rider.pk).update(shift_status="inactive")
        self.assertEqual(dispatch_once(), 0)

    def test_cooking_offer_waits_until_five_minutes_before_ready(self):
        self.order.status = "cooking"
        self.order.ready_at = timezone.now() + timedelta(minutes=10)
        self.order.save()
        self.assertEqual(dispatch_once(), 0)
        self.order.ready_at = timezone.now() + timedelta(minutes=4)
        self.order.save()
        self.assertEqual(dispatch_once(), 1)

    def test_busy_courier_can_reserve_next_but_cannot_pick_up(self):
        current = Order.objects.create(
            user=self.customer,
            courier=self.rider,
            status="delivery",
            latitude=41,
            longitude=69,
            delivery_eta=timezone.now() + timedelta(minutes=4),
        )
        self.rider.shift_status = "busy"
        self.rider.save()
        self.assertEqual(dispatch_once(), 1)
        offer = DeliveryOffer.objects.get()
        respond(offer.pk, self.user, True)
        with self.assertRaises(ValidationError):
            services.take_order(self.order.pk, self.user)
        Payment.objects.create(user=self.customer, order=current, method="cash", status="pending")
        services.deliver_order(current.pk, self.user)
        services.take_order(self.order.pk, self.user)
        self.assertEqual(Order.objects.filter(status="delivery").count(), 1)

    def test_busy_without_recent_five_minute_forecast_is_ineligible(self):
        current = Order.objects.create(
            user=self.customer, courier=self.rider, status="delivery", latitude=41, longitude=69
        )
        for estimate in [
            None,
            timezone.now() + timedelta(minutes=6),
            timezone.now() - timedelta(minutes=3),
        ]:
            current.delivery_eta = estimate
            current.save()
            self.assertEqual(dispatch_once(), 0)

    def test_decline_and_timeout_pass_to_another_courier(self):
        other = self.another_rider()
        dispatch_once()
        offer = DeliveryOffer.objects.get()
        respond(offer.pk, self.user, False)
        dispatch_once()
        second = DeliveryOffer.objects.get(state="pending")
        self.assertEqual(second.courier_id, other.pk)
        second.expires_at = timezone.now() - timedelta(seconds=1)
        second.save()
        dispatch_once()
        second.refresh_from_db()
        self.assertEqual(second.state, "expired")
        self.assertFalse(DeliveryOffer.objects.filter(state="pending").exists())

    def test_cancelled_order_and_open_issue_remove_reservation(self):
        dispatch_once()
        offer = DeliveryOffer.objects.get()
        self.order.status = "cancel"
        self.order.save()
        dispatch_once()
        offer.refresh_from_db()
        self.assertEqual(offer.state, "cancelled")
        self.order.status = "ready"
        self.order.save()
        OrderIssue.objects.create(
            order=self.order, author=self.customer, reason="Please cancel this order"
        )
        self.assertEqual(dispatch_once(), 0)

    def test_expired_offer_cannot_be_accepted(self):
        dispatch_once()
        offer = DeliveryOffer.objects.get()
        offer.expires_at = timezone.now() - timedelta(seconds=1)
        offer.save()
        with self.assertRaises(ValidationError):
            respond(offer.pk, self.user, True)

    def test_personal_offer_cannot_be_accepted_by_another_courier(self):
        other = self.another_rider()
        dispatch_once()
        with self.assertRaises(PermissionDenied):
            respond(DeliveryOffer.objects.get().pk, other.user, True)

    def test_location_endpoint_validates_coordinates_and_clears_on_stop(self):
        self.client.force_login(self.user)
        for lat, lon, accuracy in [
            ("NaN", "69", "10"),
            ("91", "69", "10"),
            ("41", "181", "10"),
            ("41", "69", "NaN"),
            ("41", "69", "-1"),
        ]:
            self.assertEqual(
                self.client.post(
                    reverse("courier_location"),
                    {"latitude": lat, "longitude": lon, "accuracy": accuracy},
                ).status_code,
                400,
            )
        self.assertEqual(
            self.client.post(
                reverse("courier_location"),
                {"latitude": "41.12345678", "longitude": "69", "accuracy": "20"},
            ).status_code,
            200,
        )
        self.rider.refresh_from_db()
        self.assertEqual(self.rider.latitude, Decimal("41.123457"))
        dispatch_once()
        self.client.post(reverse("courier_stop_location"))
        self.rider.refresh_from_db()
        self.assertIsNone(self.rider.latitude)
        self.assertFalse(DeliveryOffer.objects.filter(state__in=["pending", "accepted"]).exists())

    def test_live_endpoint_is_private_and_contains_no_customer_details(self):
        dispatch_once()
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("courier_live")).status_code, 403)
        self.client.force_login(self.user)
        response = self.client.get(reverse("courier_live"))
        self.assertEqual(set(response.json()), {"offer", "state", "current", "approved"})
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_missing_kitchen_configuration_reports_problem(self):
        self.restaurant.latitude = None
        self.restaurant.longitude = None
        self.restaurant.save()
        self.assertEqual(dispatch_once(), 0)
        self.order.refresh_from_db()
        self.assertIn("координаты кухни", self.order.dispatch_alert)

    def test_no_courier_after_twenty_minutes_reports_problem(self):
        Courier.objects.filter(pk=self.rider.pk).update(is_approved=False)
        Order.objects.filter(pk=self.order.pk).update(
            created_at=timezone.now() - timedelta(minutes=21)
        )
        dispatch_once()
        self.order.refresh_from_db()
        self.assertTrue(self.order.dispatch_alert)

    def test_kitchen_has_own_permission_without_admin_or_customer_access(self):
        cook = User.objects.create_user("cook", role="kitchen")
        cook.user_permissions.add(
            Permission.objects.get(codename="work_kitchen", content_type__app_label="orders")
        )
        self.order.status = "new"
        self.order.save()
        self.client.force_login(cook)
        self.assertEqual(self.client.get(reverse("kitchen")).status_code, 200)
        self.assertEqual(self.client.get(reverse("operations")).status_code, 403)
        self.assertEqual(self.client.get(reverse("cart_detail")).status_code, 403)
        self.client.post(reverse("kitchen_action", args=[self.order.pk]), {"action": "cooking"})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cooking")
        self.assertIsNotNone(self.order.ready_at)
        for user in [self.customer, self.user]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("kitchen")).status_code, 403)

    def test_checkout_point_requires_valid_pair_but_is_optional(self):
        base = {
            "customer_name": "Buyer",
            "phone": "+998901234567",
            "address": "Street number 12",
            "checkout_token": "a4809eb9-9200-4d84-9ae9-c16e9b99e105",
            "payment_method": "cash",
        }
        self.assertTrue(CheckoutForm(base).is_valid())
        for changes in [
            {"latitude": "41"},
            {"latitude": "91", "longitude": "69"},
            {"latitude": "NaN", "longitude": "69"},
        ]:
            self.assertFalse(CheckoutForm(base | changes).is_valid())
        self.assertTrue(
            CheckoutForm(base | {"latitude": "41.000000", "longitude": "69.000000"}).is_valid()
        )

    def test_problem_on_current_delivery_releases_next_reservation(self):
        current = Order.objects.create(
            user=self.customer,
            courier=self.rider,
            status="delivery",
            latitude=41,
            longitude=69,
            delivery_eta=timezone.now() + timedelta(minutes=4),
        )
        dispatch_once()
        offer = DeliveryOffer.objects.get()
        respond(offer.pk, self.user, True)
        OrderIssue.objects.create(order=current, author=self.user, reason="Vehicle broke down")
        dispatch_once()
        offer.refresh_from_db()
        self.assertEqual(offer.state, "cancelled")

    def test_admin_alerts_are_private_and_report_worker_health(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("operations_alerts")).status_code, 403)
        admin = User.objects.create_superuser("admin", "admin@example.test", "test-password")
        self.client.force_login(admin)
        before = self.client.get(reverse("operations_alerts")).json()
        self.assertTrue(before["configured"])
        self.assertFalse(before["healthy"])
        dispatch_once()
        self.assertTrue(self.client.get(reverse("operations_alerts")).json()["healthy"])
