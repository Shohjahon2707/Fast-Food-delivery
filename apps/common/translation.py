from django.utils.translation import get_language, gettext


def localized(instance, field):
    language = (get_language() or "ru").split("-")[0]
    base = getattr(instance, field)
    if language in ("en", "uz"):
        return getattr(instance, f"{field}_{language}", "") or (gettext(base) if base else "")
    return base
