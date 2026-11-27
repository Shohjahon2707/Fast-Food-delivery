import base64
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.orders.models import Order

from .models import Payment, PaymeTransaction
from .payme import now_ms


@override_settings(PAYME_MERCHANT_ID="sandbox-demo", PAYME_API_KEY="sandbox-key")
class PaymeCallbackTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="buyer")
        cls.order = Order.objects.create(user=cls.user, total_price=60000)
        cls.payment = Payment.objects.create(order=cls.order, user=cls.user, method="payme")

    def call(self, method, params, key="sandbox-key"):
        auth = base64.b64encode(f"Paycom:{key}".encode()).decode()
        result = self.client.post(
            reverse("payme_callback"),
            json.dumps({"id": 1, "method": method, "params": params}),
            content_type="application/json", headers={"Authorization": f"Basic {auth}"},
        )
        self.assertEqual(result.status_code, 200)
        return result.json()

    def create(self):
        return self.call("CreateTransaction", {
            "id": "p-001", "time": now_ms(), "amount": 6000000,
            "account": {"order_id": str(self.order.pk)},
        })

    def test_confirmation_and_repeated_callbacks(self):
        created = self.create()
        self.assertEqual(created, self.create())
        self.assertEqual(created["result"]["state"], 1)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "pending")
        paid = self.call("PerformTransaction", {"id": "p-001"})
        self.assertEqual(paid, self.call("PerformTransaction", {"id": "p-001"}))
        self.assertEqual(paid["result"]["state"], 2)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "paid")
        self.assertEqual(PaymeTransaction.objects.count(), 1)
        self.assertEqual(self.order.events.count(), 1)
        result = self.call("GetStatement", {"from": 0, "to": now_ms()})
        self.assertEqual(result["result"]["transactions"][0]["amount"], 6000000)

    def test_invalid_auth_and_amount_leave_payment_pending(self):
        params = {"amount": 5999999, "account": {"order_id": str(self.order.pk)}}
        error = self.call("CheckPerformTransaction", params, key="wrong")
        self.assertEqual(error["error"]["code"], -32504)
        error = self.call("CheckPerformTransaction", params)
        self.assertEqual(error["error"]["code"], -31001)
        self.assertFalse(PaymeTransaction.objects.exists())

    def test_cancel_is_idempotent_and_stops_fulfillment(self):
        self.create()
        result = self.call("CancelTransaction", {"id": "p-001", "reason": 5})
        self.assertEqual(result, self.call("CancelTransaction", {"id": "p-001", "reason": 5}))
        self.assertEqual(result["result"]["state"], -1)
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual((self.order.status, self.payment.status), ("cancel", "cancelled"))
