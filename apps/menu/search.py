import re

from django.db.models import Case, IntegerField, Q, Value, When

CYRILLIC = dict(zip(
    "абвгдеёзийклмнопрстуфхцчшщъыьэюяқғўҳ",
    ("a", "b", "v", "g", "d", "e", "yo", "z", "i", "y", "k", "l", "m", "n",
     "o", "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "",
     "y", "", "e", "yu", "ya", "q", "g", "o", "h"), strict=True,
))
LATIN = {value: key for key, value in CYRILLIC.items() if value}
LATIN.update({"y": "й", "o": "о", "e": "е", "g": "г", "h": "х", "j": "ж"})
LATIN_PATTERN = re.compile("|".join(sorted(LATIN, key=len, reverse=True)))


def variants(query):
    query = query.casefold()
    cleaned = query.replace("‘", "").replace("’", "").replace("'", "")
    transliterated = (
        "".join(CYRILLIC.get(char, char) for char in cleaned)
        if any(char in CYRILLIC for char in cleaned)
        else LATIN_PATTERN.sub(lambda match: LATIN[match[0]], cleaned)
    )
    return {query, cleaned, transliterated} - {""}


def search(queryset, query, fields):
    if not query:
        return queryset
    conditions = Q()
    for word in query.split()[:6]:
        match = Q()
        for variant in variants(word):
            for field in fields:
                match |= Q(**{f"{field}__icontains": variant}) | Q(
                    **{f"{field}__icontains": variant.capitalize()}
                )
        conditions &= match
    exact, prefix = Q(), Q()
    for variant in variants(query):
        for spelling in (variant, variant.capitalize()):
            exact |= Q(**{f"{fields[0]}__iexact": spelling})
            prefix |= Q(**{f"{fields[0]}__istartswith": spelling})
    return queryset.filter(conditions).annotate(search_rank=Case(
        When(exact, then=Value(2)), When(prefix, then=Value(1)),
        default=Value(0), output_field=IntegerField(),
    )).order_by("-search_rank", "pk")
