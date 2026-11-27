from bisect import insort
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from heapq import nsmallest
from itertools import product

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.orders.delivery import delivery_terms
from apps.orders.models import Restaurant

from .models import MenuItem
from .smart import EXCLUSION_FIELDS, Lunch, exclusion_terms, matches_text

ROLE_LIMIT = 8
ROLES = (MenuItem.LunchRole.MAIN, MenuItem.LunchRole.SIDE, MenuItem.LunchRole.DRINK)
ROLE_WEIGHTS = (2, 1, 1)
NO_PORTION = (0, 0, Decimal(0), 0)


@dataclass(frozen=True)
class Bundle(Lunch):
    reasons: tuple[str, ...] = ()

    @property
    def delivery_fee(self):
        return self.fee

    @property
    def eta_minutes(self):
        return self.minutes

    @property
    def shortfall(self):
        return max(Decimal(0), self.total - self.budget)


def candidates(rows, target):
    if len(rows) <= ROLE_LIMIT:
        return rows
    # Keep affordable portions and explore prices closer to the role's budget.
    cheapest = nsmallest(2, rows, key=lambda row: (row[2], row[0]))
    cheap_ids = {row[0] for row in cheapest}
    return cheapest + nsmallest(
        ROLE_LIMIT - len(cheapest),
        (row for row in rows if row[0] not in cheap_ids),
        key=lambda row: (abs(row[2] - target), row[2], row[0]),
    )


def build_bundles(budget, people, diet, exclude, max_minutes, limit=6, *, point=None, allergens=()):
    """Return the best in-budget bundles and, if needed, the closest over-budget bundle."""
    budget = Decimal(budget)
    limit = max(1, min(limit, 6))
    restaurants = Restaurant.objects.filter(accepting_orders=True).in_bulk()
    terms_by_restaurant = {}
    for restaurant in restaurants.values():
        try:
            terms = delivery_terms(restaurant, point, require_address=True)
        except ValidationError:
            continue
        if max_minutes is None or terms.minutes <= max_minutes:
            terms_by_restaurant[restaurant.pk] = terms

    dishes = MenuItem.objects.filter(
        restaurant_id__in=terms_by_restaurant, is_available=True, lunch_role__in=ROLES,
    ).order_by()
    diet_field = {"vegetarian": "is_vegetarian", "halal": "is_halal"}.get(diet)
    if diet_field:
        dishes = dishes.filter(**{diet_field: True})
    terms = exclusion_terms(exclude)
    allergen_codes = set(allergens)
    fields = ["pk", "restaurant_id", "lunch_role", "price", "servings", "cooking_minutes"]
    if allergen_codes:
        dishes = dishes.exclude(allergens__isnull=True)
        fields.append("allergens")
    if terms:
        fields.extend(EXCLUSION_FIELDS)

    grouped = defaultdict(lambda: defaultdict(list))
    for dish in dishes.values(*fields).iterator(chunk_size=1000):
        if allergen_codes.intersection(dish.get("allergens") or ()):
            continue
        if terms and not matches_text((dish[field] for field in EXCLUSION_FIELDS), terms):
            continue
        restaurant_id = dish["restaurant_id"]
        cooking = dish["cooking_minutes"] or 0
        if max_minutes is not None:
            preparation = restaurants[restaurant_id].preparation_minutes
            travel_time = terms_by_restaurant[restaurant_id].minutes
            if travel_time + max(0, cooking - preparation) > max_minutes:
                continue
        quantity = (people + dish["servings"] - 1) // dish["servings"]
        grouped[restaurant_id][dish["lunch_role"]].append(
            (dish["pk"], quantity, dish["price"] * quantity, cooking)
        )

    best, nearest = [], None
    for restaurant_id, roles in grouped.items():
        if not roles[MenuItem.LunchRole.MAIN]:
            continue
        restaurant = restaurants[restaurant_id]
        delivery = terms_by_restaurant[restaurant_id]
        role_weights = sum(weight for role, weight in zip(ROLES, ROLE_WEIGHTS) if roles[role])
        food_budget = budget
        if budget < settings.FREE_DELIVERY_FROM:
            food_budget -= delivery.fee_below_threshold
        choices = [
            candidates(roles[role], food_budget * weight / role_weights) or [NO_PORTION]
            for role, weight in zip(ROLES, ROLE_WEIGHTS)
        ]
        for main, side, drink in product(*choices):
            subtotal = main[2] + side[2] + drink[2]
            if subtotal < delivery.minimum:
                continue
            fee = delivery.fee(subtotal)
            total = subtotal + fee
            fits = total <= budget
            if fits and len(best) == limit and total < -best[-1][0][0]:
                continue
            if not fits and nearest and total > nearest[0][0]:
                continue
            cooking = max(main[3], side[3], drink[3])
            minutes = delivery.minutes + max(0, cooking - restaurant.preparation_minutes)
            rows = tuple(row for row in (main, side, drink) if row[0])
            tail = (minutes, -len(rows), restaurant_id, tuple(row[0] for row in rows))
            candidate = (restaurant_id, rows, subtotal, fee, minutes)
            if fits:
                score = (-total, *tail)
                if len(best) < limit or score < best[-1][0]:
                    insort(best, (score, candidate))
                    if len(best) > limit:
                        best.pop()
            elif nearest is None or (total, *tail) < nearest[0]:
                nearest = ((total, *tail), candidate)

    selected = [candidate for _, candidate in best]
    if nearest is not None and not selected:
        selected = [nearest[1]]
    items = MenuItem.objects.in_bulk(row[0] for candidate in selected for row in candidate[1])
    fastest = min((candidate[4] for candidate in selected), default=None)
    closest_total = -best[0][0][0] if best else None
    bundles = []
    for restaurant_id, rows, subtotal, fee, minutes in selected:
        if any(row[0] not in items for row in rows):
            continue
        reasons = []
        if subtotal + fee <= budget:
            reasons.append("fits_budget")
        if not fee:
            reasons.append("free_delivery")
        if len(best) > 1 and minutes == fastest:
            reasons.append("fastest")
        if len(best) > 1 and subtotal + fee == closest_total:
            reasons.append("closest_to_budget")
        bundles.append(Bundle(
            restaurants[restaurant_id], tuple((items[pk], quantity) for pk, quantity, _, _ in rows),
            subtotal, fee, minutes, budget, tuple(reasons),
        ))
    if best:
        return bundles, None
    return [], bundles[0] if bundles else None
