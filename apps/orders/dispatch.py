import math
import secrets
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.courier.models import Courier

from .models import DeliveryOffer, Order, Restaurant

LOCATION_TTL = timedelta(minutes=3)
OFFER_TTL = timedelta(seconds=60)
RESERVATION_TTL = timedelta(minutes=15)


def distance_minutes(start, destination, vehicle):
    """Conservative distance estimate, NOT a road-route or a promise."""
    if any(value is None for value in (*start, *destination)):
        return 15
    a, b, c, d = map(lambda v: math.radians(float(v)), (*start, *destination))
    h = math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
    km = 6371 * 2 * math.asin(math.sqrt(min(1, max(0, h))))
    speed = {"foot": 4, "bike": 12, "scooter": 20, "car": 18}.get(vehicle, 12)
    return max(1, math.ceil(km * 1.4 / speed * 60))


@transaction.atomic
def dispatch_once():
    Restaurant.objects.get_or_create(pk=1)
    restaurant = Restaurant.objects.select_for_update().get(pk=1)
    now = timezone.now()
    restaurant.last_dispatch_at = now
    restaurant.save(update_fields=["last_dispatch_at"])
    # Shared row serializes dispatch passes across web callbacks and worker processes.
    for offer in DeliveryOffer.objects.filter(
        state__in=["pending", "accepted"], expires_at__lte=now
    ).order_by("order_id"):
        order = Order.objects.select_for_update().get(pk=offer.order_id)
        DeliveryOffer.objects.filter(pk=offer.pk, state=offer.state).update(
            state="expired", responded_at=now
        )
        if offer.state == "accepted" and order.is_active:
            order.dispatch_alert = "Курьер не забрал заказ вовремя. Ищем замену."
            order.save(update_fields=["dispatch_alert"])
    blocked_couriers = (
        Order.objects.filter(status="delivery", courier__isnull=False)
        .filter(
            Q(delivery_eta__isnull=True)
            | Q(delivery_eta__gt=now + timedelta(minutes=5))
            | Q(delivery_eta__lt=now - timedelta(minutes=2))
            | Q(latitude__isnull=True)
            | Q(longitude__isnull=True)
            | Q(issues__resolved_at__isnull=True, issues__isnull=False)
        )
        .values_list("courier_id", flat=True)
    )
    invalid = DeliveryOffer.objects.filter(state__in=["pending", "accepted"]).filter(
        Q(order__status__in=["cancel", "done", "delivery"])
        | Q(courier__is_approved=False)
        | Q(courier__user__is_active=False)
        | Q(courier__shift_status="inactive")
        | ~Q(courier__user__role="courier")
        | Q(courier__user__is_staff=True)
        | Q(courier_id__in=blocked_couriers)
        | Q(order__issues__resolved_at__isnull=True, order__issues__isnull=False)
    )
    for offer_id, order_id in invalid.order_by("order_id").values_list("pk", "order_id").distinct():
        Order.objects.select_for_update().get(pk=order_id)
        DeliveryOffer.objects.filter(pk=offer_id, state__in=["pending", "accepted"]).update(
            state="cancelled", responded_at=now
        )
    if restaurant.latitude is None or restaurant.longitude is None or not restaurant.address:
        Order.objects.filter(status__in=["cooking", "ready"], courier__isnull=True).update(
            dispatch_alert="Укажите адрес и координаты кухни в настройках доставки."
        )
        return 0
    Order.objects.filter(status__in=["cancel", "done"]).exclude(dispatch_alert="").update(
        dispatch_alert=""
    )
    queue = Order.objects.filter(status__in=["cooking", "ready"], courier__isnull=True).order_by(
        "created_at", "pk"
    )
    assigned = 0
    for candidate in queue[:100]:
        order = Order.objects.select_for_update().get(pk=candidate.pk)
        if (
            order.status not in ("cooking", "ready")
            or order.courier_id is not None
            or order.offers.filter(state__in=["pending", "accepted"]).exists()
            or order.issues.filter(resolved_at__isnull=True).exists()
        ):
            continue
        # Start looking near readiness, not at checkout.
        if (
            order.status == "cooking"
            and order.ready_at
            and order.ready_at > now + timedelta(minutes=5)
        ):
            continue
        options = []
        for courier in Courier.objects.filter(
            is_approved=True, user__is_active=True, user__role="courier", user__is_staff=False
        ).exclude(shift_status="inactive"):
            if (
                courier.location_updated_at is None
                or courier.location_updated_at < now - LOCATION_TTL
            ):
                continue
            if courier.location_accuracy is None or courier.location_accuracy > 200:
                continue
            if courier.offers.filter(state__in=["pending", "accepted"]).exists():
                continue
            if order.offers.filter(
                courier=courier,
                created_at__gte=now - timedelta(minutes=5),
                state__in=["declined", "expired"],
            ).exists():
                continue
            current = Order.objects.filter(courier=courier, status="delivery").first()
            wait = 0
            origin = (courier.latitude, courier.longitude)
            if current:
                if (
                    current.delivery_eta is None
                    or current.issues.filter(resolved_at__isnull=True).exists()
                ):
                    continue
                wait = max(0, (current.delivery_eta - now).total_seconds() / 60)
                if wait > 5 or current.delivery_eta < now - timedelta(minutes=2):
                    continue
                # Never assume an overdue delivery is complete. Reserve only; pickup remains blocked.
                if current.latitude is None or current.longitude is None:
                    continue
                origin = (current.latitude, current.longitude)
            travel = distance_minutes(
                origin, (restaurant.latitude, restaurant.longitude), courier.vehicle
            )
            prep = max(0, ((order.ready_at or now) - now).total_seconds() / 60)
            arrival = wait + travel
            score = max(arrival, prep) + abs(arrival - prep) * 0.2
            idle_since = courier.last_delivery_at.timestamp() if courier.last_delivery_at else 0
            options.append(
                (
                    round(score),
                    idle_since,
                    secrets.randbelow(1000000),
                    courier.pk,
                    math.ceil(arrival),
                )
            )
        if not options:
            if now - order.created_at > timedelta(minutes=20):
                Order.objects.filter(pk=order.pk).update(
                    dispatch_alert="Нет доступного курьера со свежей геопозицией."
                )
            continue
        _, _, _, courier_pk, arrival = min(options)
        courier = Courier.objects.select_for_update().get(pk=courier_pk)
        # Recheck mutable eligibility after acquiring the courier lock.
        if (
            not courier.is_approved
            or courier.shift_status == "inactive"
            or courier.offers.filter(state__in=["pending", "accepted"]).exists()
        ):
            continue
        DeliveryOffer.objects.create(
            order=order,
            courier=courier,
            expires_at=now + OFFER_TTL,
            pickup_minutes=min(arrival, 65535),
        )
        Order.objects.filter(pk=order.pk).update(dispatch_alert="")
        assigned += 1
    return assigned


@transaction.atomic
def respond(offer_id, actor, accept):
    if not actor.is_courier:
        raise PermissionDenied
    initial = DeliveryOffer.objects.get(pk=offer_id)
    order = Order.objects.select_for_update().get(pk=initial.order_id)
    courier = Courier.objects.select_for_update().get(user=actor)
    offer = DeliveryOffer.objects.select_for_update().get(pk=offer_id)
    if offer.courier_id != courier.pk:
        raise PermissionDenied
    now = timezone.now()
    if offer.state != "pending" or offer.expires_at <= now:
        raise ValidationError("Время предложения истекло. Ожидайте следующего.")
    if (
        order.status not in ("cooking", "ready")
        or order.issues.filter(resolved_at__isnull=True).exists()
        or not courier.is_approved
        or courier.shift_status == "inactive"
    ):
        raise ValidationError("Это предложение больше недоступно.")
    offer.state = "accepted" if accept else "declined"
    offer.responded_at = now
    offer.expires_at = max(now, order.ready_at or now) + RESERVATION_TTL
    offer.save(update_fields=["state", "responded_at", "expires_at"])
    transaction.on_commit(dispatch_once)
    return offer
