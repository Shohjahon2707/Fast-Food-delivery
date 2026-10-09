import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.orders.dispatch import dispatch_once


class Command(BaseCommand):
    help = "Expire offers and assign deliveries; run --loop as a separate supervised worker."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--interval", type=int, default=5)

    def handle(self, *args, **options):
        try:
            while True:
                close_old_connections()
                try:
                    assigned = dispatch_once()
                    if assigned or not options["loop"]:
                        self.stdout.write(f"Предложений: {assigned}")
                except Exception:
                    if not options["loop"]:
                        raise
                    logging.getLogger(__name__).exception("Dispatch pass failed; will retry")
                if not options["loop"]:
                    break
                time.sleep(max(1, options["interval"]))
        except KeyboardInterrupt:
            pass
