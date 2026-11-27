from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Promotion


def promotion_for(code, subtotal, *, lock=False):
    code = code.strip().upper()
    if not code:
        return None
    promotions = Promotion.objects.filter(code=code, active=True)
    if lock:
        promotions = promotions.select_for_update()
    promo = promotions.first()
    now = timezone.now()
    if (
        promo is None or (promo.starts_at and promo.starts_at > now)
        or (promo.ends_at and promo.ends_at <= now)
        or (promo.max_uses is not None and promo.used_count >= promo.max_uses)
    ):
        raise ValidationError(_("Промокод недоступен."))
    if subtotal < promo.minimum_subtotal:
        raise ValidationError(_("Сумма блюд ниже минимума для промокода."))
    return promo


def discount_for(promo, subtotal):
    # Leave a positive amount for providers that cannot process zero-value orders.
    return min(promo.amount, max(0, subtotal - 1)) if promo else 0
