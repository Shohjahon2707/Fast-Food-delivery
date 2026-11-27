import base64
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from .models import StatusNotification


def enqueue_status(event):
    user = event.order.user
    targets = []
    if user.notify_sms and event.order.phone:
        targets.append("sms")
    if user.notify_telegram and user.telegram_chat_id:
        targets.append("telegram")
    StatusNotification.objects.bulk_create([
        StatusNotification(event=event, channel=channel) for channel in targets
    ], ignore_conflicts=True)


def send_notification(entry):
    order = entry.event.order
    user = order.user
    status = dict(order.STATUS_CHOICES).get(entry.event.status, entry.event.status)
    text = f"Тёпло · №{order.pk} · {status}"
    settings_available = False
    if entry.channel == "telegram":
        enabled = user.notify_telegram and user.telegram_chat_id
        settings_available = bool(settings.TELEGRAM_BOT_TOKEN)
        if enabled and settings_available:
            request = Request(
                f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                data=urlencode({"chat_id": user.telegram_chat_id, "text": text}).encode(),
            )
    else:
        enabled = user.notify_sms and order.phone
        settings_available = all((settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_FROM))
        if enabled and settings_available:
            secret = f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}"
            auth = "Basic " + base64.b64encode(secret.encode()).decode()
            request = Request(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
                data=urlencode({"From": settings.TWILIO_FROM, "To": order.phone, "Body": text}).encode(),
                headers={"Authorization": auth},
            )
    if enabled and not settings_available:
        return False
    if enabled:
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
        if entry.channel == "telegram" and not payload.get("ok"):
            return False
    entry.handled_at = timezone.now()
    entry.save(update_fields=["handled_at"])
    return True
