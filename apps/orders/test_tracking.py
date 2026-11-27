from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.courier.models import Courier

from .models import Order


class TrackingTests(TestCase):
    def test_position_is_only_visible_to_owner_during_delivery(self):
        users = get_user_model().objects
        owner = users.create_user(username="owner")
        other = users.create_user(username="other")
        courier = Courier.objects.create(
            user=users.create_user(username="courier", role="courier"),
            latitude=41.31, longitude=69.24, location_updated_at=timezone.now(),
        )
        order = Order.objects.create(user=owner, courier=courier, status="delivery")
        live = reverse("order_status", args=[order.pk])
        self.client.force_login(other)
        self.assertEqual(self.client.get(live).status_code, 404)
        self.client.force_login(owner)
        page = self.client.get(reverse("order_detail", args=[order.pk]))
        self.assertContains(page, "data-courier-tracking")
        result = self.client.get(live)
        self.assertEqual(result.json()["courier_position"], [41.31, 69.24])
        self.assertIn("no-store", result["Cache-Control"])
        order.status = "done"
        order.save(update_fields=["status"])
        self.assertNotIn("courier_position", self.client.get(live).json())
