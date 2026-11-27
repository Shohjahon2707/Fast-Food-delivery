from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from itertools import product
from re import split
from unicodedata import normalize

from django.core import signing
from django.core.exceptions import ValidationError

from apps.orders.delivery import delivery_terms, quote_delivery
from apps.orders.models import Restaurant

from .models import MenuItem

TOKEN_SALT = "teplo-smart-lunch"
ROLE_LIMIT = 5
EXCLUSION_FIELDS = ("name", "name_uz", "name_en", "description", "description_uz", "description_en")


@dataclass(frozen=True)
class Lunch:
    restaurant: object
    lines: tuple
    subtotal: Decimal
    fee: Decimal
    minutes: int
    budget: int

    @property
    def total(self):
        return self.subtotal + self.fee

    @property
    def extra(self):
        return max(0, self.total - self.budget)


def calculate_lunch(items, criteria):
    restaurant = items[0].restaurant
    if restaurant is None or any(
        not item.is_available or item.restaurant_id != restaurant.pk for item in items
    ):
        raise ValidationError("Недоступный набор.")
    if any(not matches_preferences(item, criteria) for item in items):
        raise ValidationError("Состав набора изменился.")
    lines = tuple(
        (item, (criteria["people"] + item.servings - 1) // item.servings) for item in items
    )
    subtotal = sum(item.price * quantity for item, quantity in lines)
    delivery = quote_delivery(restaurant, subtotal, criteria.get("point"), require_address=True)
    preparation = max((item.cooking_minutes or 0 for item in items), default=0)
    minutes = delivery.minutes + max(0, preparation - restaurant.preparation_minutes)
    return Lunch(restaurant, lines, subtotal, delivery.fee, minutes, criteria["budget"])


def matches_preferences(item, criteria):
    diet = criteria.get("diet")
    if diet == "vegetarian" and not item.is_vegetarian:
        return False
    if diet == "halal" and item.is_halal is not True:
        return False
    if diet == "mild" and item.spice_level != 0:
        return False
    exclusions = set(criteria.get("allergens", ()))
    if exclusions and (item.allergens is None or exclusions.intersection(item.allergens)):
        return False
    terms = exclusion_terms(criteria.get("exclude", ""))
    return not terms or matches_text((getattr(item, field) for field in EXCLUSION_FIELDS), terms)


def exclusion_terms(text):
    return tuple(normalize("NFKC", part.strip()).casefold() for part in split(r"[,;\n]", text)
                 if part.strip())


def matches_text(fields, exclusions):
    searchable = normalize("NFKC", "\n".join(fields)).casefold()
    return not any(term in searchable for term in exclusions)


def recommend(criteria):
    by_restaurant = defaultdict(lambda: defaultdict(list))
    items = MenuItem.objects.filter(
        is_available=True, restaurant__accepting_orders=True
    ).exclude(lunch_role__in=("", "dessert"))
    if criteria.get("diet") == "vegetarian":
        items = items.filter(is_vegetarian=True)
    elif criteria.get("diet") == "halal":
        items = items.filter(is_halal=True)
    elif criteria.get("diet") == "mild":
        items = items.filter(spice_level=0)
    exclusions = set(criteria.get("allergens", ()))
    rows = items.order_by("price", "pk").values_list(
        "pk", "restaurant_id", "lunch_role", "allergens", "price", "servings", "cooking_minutes",
    )
    for pk, restaurant_id, role, allergens, price, servings, cooking in rows.iterator(chunk_size=1000):
        group = by_restaurant[restaurant_id][role]
        if len(group) >= ROLE_LIMIT or (
            exclusions and (allergens is None or exclusions.intersection(allergens))
        ):
            continue
        quantity = (criteria["people"] + servings - 1) // servings
        group.append((pk, quantity, price * quantity, cooking or 0))

    best, closest = [], None
    restaurants = Restaurant.objects.in_bulk(by_restaurant)
    budget, maximum_time = criteria["budget"], criteria["max_minutes"]
    for restaurant_id, roles in by_restaurant.items():
        restaurant = restaurants.get(restaurant_id)
        if restaurant is None or not roles["main"]:
            continue
        try:
            terms = delivery_terms(restaurant, criteria.get("point"), require_address=True)
        except ValidationError:
            continue
        for main, side, drink in product(
            roles["main"], [None, *roles["side"]], [None, *roles["drink"]]
        ):
            rows = tuple(row for row in (main, side, drink) if row)
            subtotal = sum(row[2] for row in rows)
            if subtotal < terms.minimum:
                continue
            preparation = max(row[3] for row in rows)
            minutes = terms.minutes + max(0, preparation - restaurant.preparation_minutes)
            if maximum_time and minutes > maximum_time:
                continue
            fee = terms.fee(subtotal)
            lines = tuple((row[0], row[1]) for row in rows)
            total = subtotal + fee
            candidate = (restaurant_id, lines, subtotal, fee, minutes)
            if total > budget:
                distance = (total - budget, minutes)
                if closest is None or distance < closest[0]:
                    closest = (distance, candidate)
            else:
                score = (-len(lines), budget - total, minutes, lines)
                best.append((score, candidate))

    ranked = [candidate for _, candidate in sorted(best)]
    chosen, seen = [], set()
    for candidate in ranked:
        if candidate[0] not in seen:
            seen.add(candidate[0])
            chosen.append(candidate)
            if len(chosen) == 6:
                break
    if len(chosen) < 6:
        selected = set(chosen)
        for candidate in ranked:
            if candidate not in selected:
                chosen.append(candidate)
                if len(chosen) == 6:
                    break

    nearest = closest[1] if closest and not chosen else None
    displayed = chosen or ([nearest] if nearest else [])
    dishes = MenuItem.objects.in_bulk(pk for row in displayed for pk, _ in row[1])

    def render_lunch(candidate):
        restaurant_id, lines, subtotal, fee, minutes = candidate
        portions = tuple((dishes[pk], quantity) for pk, quantity in lines if pk in dishes)
        if len(portions) != len(lines):
            return None
        return Lunch(restaurants[restaurant_id], portions, subtotal, fee, minutes, budget)

    return [lunch for row in chosen if (lunch := render_lunch(row))], (
        render_lunch(nearest) if nearest else None
    )


def sign_lunch(lunch, criteria):
    details = dict(criteria)
    if details.get("point"):
        details["point"] = list(map(str, details["point"]))
    return signing.dumps(
        {
            "ids": [item.pk for item, _ in lunch.lines],
            "criteria": details,
            "fee": str(lunch.fee),
            "subtotal": str(lunch.subtotal),
        },
        salt=TOKEN_SALT,
    )


def load_lunch(token):
    data = signing.loads(token, salt=TOKEN_SALT, max_age=1800)
    criteria = data["criteria"]
    if criteria.get("point"):
        criteria["point"] = tuple(map(Decimal, criteria["point"]))
    items = MenuItem.objects.select_related("restaurant").in_bulk(data["ids"])
    if len(items) != len(data["ids"]):
        raise ValidationError("Недоступный набор.")
    lunch = calculate_lunch([items[key] for key in data["ids"]], criteria)
    if (
        lunch.extra or (criteria["max_minutes"] and lunch.minutes > criteria["max_minutes"])
        or lunch.fee != Decimal(data["fee"]) or lunch.subtotal != Decimal(data["subtotal"])
    ):
        raise ValidationError("Условия набора изменились.")
    return lunch, criteria
