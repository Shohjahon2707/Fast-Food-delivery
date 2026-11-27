import math
from dataclasses import dataclass
from datetime import time
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext as _

POINT_SESSION_KEY = "delivery_point"


@dataclass(frozen=True)
class DeliveryQuote:
    fee: Decimal
    minutes: int
    distance_km: float | None


@dataclass(frozen=True)
class DeliveryTerms:
    minimum: int
    fee_below_threshold: Decimal
    minutes: int
    distance: float | None

    def fee(self, subtotal):
        return Decimal(0) if subtotal >= settings.FREE_DELIVERY_FROM else self.fee_below_threshold


def distance_km(restaurant, point):
    if not point or restaurant.latitude is None or restaurant.longitude is None:
        return None
    a, b, c, d = map(math.radians, (*point, restaurant.latitude, restaurant.longitude))
    h = math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def is_open(restaurant, now: time | None = None):
    if not restaurant.accepting_orders:
        return False
    opens, closes = restaurant.opens_at, restaurant.closes_at
    if opens is None or closes is None or opens == closes:
        return True
    now = now or timezone.localtime().time()
    if opens < closes:
        return opens <= now < closes
    return now >= opens or now < closes


def get_point(data):
    lat, lon = data.get("latitude"), data.get("longitude")
    return (lat, lon) if lat is not None and lon is not None else None


def saved_point(request):
    if POINT_SESSION_KEY in request.session:
        point = request.session[POINT_SESSION_KEY]
        return tuple(map(Decimal, point)) if point else None
    if request.user.is_authenticated:
        lat, lon = request.user.address_latitude, request.user.address_longitude
        if lat is not None and lon is not None:
            return lat, lon
    return None


def remember_point(request, point):
    request.session[POINT_SESSION_KEY] = [str(value) for value in point] if point else None


def delivery_terms(restaurant, point=None, *, require_address=False, scheduled_at=None):
    at = timezone.localtime(scheduled_at).time() if scheduled_at is not None else None
    if restaurant and not is_open(restaurant, at):
        raise ValidationError(_("Ресторан сейчас закрыт."))
    distance = distance_km(restaurant, point) if restaurant else None
    if restaurant and restaurant.delivery_radius_km is not None:
        if distance is None and require_address:
            raise ValidationError(_("Укажите точку доставки, чтобы проверить зону ресторана."))
        if distance is not None and distance > float(restaurant.delivery_radius_km):
            raise ValidationError(_("Адрес вне зоны доставки этого ресторана."))
    surcharge = Decimal(0)
    if distance is not None:
        surcharge = (Decimal(str(max(0, distance - 2))) * 1500).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    base_minutes = restaurant.delivery_minutes if restaurant else 35
    minutes = base_minutes + math.ceil(max(0, (distance or 0) - 2) * 4)
    return DeliveryTerms(
        restaurant.minimum_subtotal if restaurant else 0,
        settings.DELIVERY_FEE + surcharge,
        minutes,
        distance,
    )


def quote_delivery(restaurant, subtotal, point=None, *, require_address=False, scheduled_at=None):
    terms = delivery_terms(restaurant, point, require_address=require_address, scheduled_at=scheduled_at)
    if subtotal < terms.minimum:
        raise ValidationError(
            _("Минимальная сумма блюд в этом ресторане — %(amount)s сум."),
            params={"amount": terms.minimum},
        )
    return DeliveryQuote(terms.fee(subtotal), terms.minutes, terms.distance)
