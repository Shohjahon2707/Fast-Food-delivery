from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext as _

from .delivery import is_open


def preparation_start(restaurant, arrival, minutes):
    if arrival is None:
        return None
    now = timezone.now()
    start = arrival - timedelta(minutes=minutes)
    if start < now or arrival > now + timedelta(days=7):
        raise ValidationError(_("Выберите время с учётом доставки в пределах семи дней."))
    if not all(is_open(restaurant, timezone.localtime(instant).time()) for instant in (start, arrival)):
        raise ValidationError(_("Выбранное время выходит за часы работы ресторана."))
    opens, closes = restaurant.opens_at, restaurant.closes_at
    if opens is not None and closes is not None and opens != closes:
        local_start, local_arrival = map(timezone.localtime, (start, arrival))
        day = timedelta(days=1)
        start_shift = local_start.date() - (day if local_start.time() < opens else timedelta(0))
        arrival_shift = local_arrival.date() - (day if local_arrival.time() < opens else timedelta(0))
        if start_shift != arrival_shift:
            raise ValidationError(_("Выбранное время выходит за часы работы ресторана."))
    return start
