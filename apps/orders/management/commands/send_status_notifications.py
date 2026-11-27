from datetime import timedelta
from urllib.error import URLError

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from apps.orders.models import StatusNotification
from apps.orders.notifications import send_notification


class Command(BaseCommand):
    help = "Deliver pending order status notifications. Run periodically from one worker on SQLite."

    def handle(self, *args, **options):
        ready = StatusNotification.objects.filter(
            handled_at__isnull=True, next_attempt_at__lte=timezone.now(), attempts__lt=5,
        )
        sent = 0
        for pk in list(ready.order_by("pk").values_list("pk", flat=True)[:40]):
            with transaction.atomic():
                rows = ready.select_for_update(skip_locked=connection.features.has_select_for_update_skip_locked)
                entry = rows.select_related("event__order__user").filter(pk=pk).first()
                if entry is None:
                    continue
                try:
                    if send_notification(entry):
                        sent += 1
                        continue
                except (URLError, TimeoutError, ValueError):
                    entry.attempts += 1
                entry.next_attempt_at = timezone.now() + timedelta(minutes=5 * (entry.attempts + 1))
                entry.save(update_fields=["attempts", "next_attempt_at"])
        self.stdout.write(f"Processed {sent} status notifications.")
