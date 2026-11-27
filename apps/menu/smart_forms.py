from django import forms
from django.utils.translation import gettext_lazy as _

ALLERGEN_CHOICES = (
    ("gluten", _("Глютен")), ("milk", _("Молоко")), ("egg", _("Яйца")),
    ("nuts", _("Орехи")), ("peanut", _("Арахис")), ("soy", _("Соя")),
    ("fish", _("Рыба")), ("sesame", _("Кунжут")), ("shellfish", _("Моллюски и ракообразные")),
    ("mustard", _("Горчица")), ("celery", _("Сельдерей")), ("lupin", _("Люпин")),
    ("sulfites", _("Сульфиты")),
)


class PointForm(forms.Form):
    latitude = forms.DecimalField(
        label=_("Широта"), required=False, min_value=-90, max_value=90, decimal_places=6,
    )
    longitude = forms.DecimalField(
        label=_("Долгота"), required=False, min_value=-180, max_value=180, decimal_places=6,
    )

    def clean(self):
        data = super().clean()
        if (data.get("latitude") is None) != (data.get("longitude") is None):
            raise forms.ValidationError(_("Укажите обе координаты доставки."))
        return data


class SmartLunchForm(PointForm):
    field_order = ["budget", "people", "diet", "max_minutes", "allergens", "latitude", "longitude"]
    budget = forms.IntegerField(
        label=_("Весь бюджет, сум"), min_value=1, max_value=100000000,
        initial=60000, localize=False,
    )
    people = forms.IntegerField(label=_("Сколько человек"), min_value=1, max_value=12, initial=2)
    diet = forms.ChoiceField(
        label=_("Предпочтения"), required=False,
        choices=[
            ("all", _("Любые блюда")), ("vegetarian", _("Без мяса")),
            ("halal", _("Подтверждённый халяль")), ("mild", _("Неострое")),
        ],
    )
    max_minutes = forms.TypedChoiceField(
        label=_("Время доставки"), required=False, coerce=int,
        choices=[("", _("Неважно")), (30, _("До 30 минут")), (40, _("До 40 минут")),
                 (50, _("До 50 минут")), (60, _("До 60 минут"))],
    )
    allergens = forms.MultipleChoiceField(
        label=_("Исключить аллергены"), required=False,
        choices=ALLERGEN_CHOICES, widget=forms.CheckboxSelectMultiple,
    )


class SmartLunchV2Form(SmartLunchForm):
    field_order = [
        "people", "budget", "diet", "exclude", "max_minutes", "allergens", "latitude", "longitude",
    ]
    people = forms.IntegerField(label=_("Сколько человек"), min_value=1, max_value=10, initial=2)
    budget = forms.IntegerField(
        label=_("Бюджет с доставкой, сум"), min_value=10000, max_value=2000000, initial=60000,
    )
    diet = forms.ChoiceField(
        label=_("Предпочтения"), required=False, initial="all",
        choices=[
            ("all", _("Любые блюда")), ("vegetarian", _("Без мяса")),
            ("halal", _("Подтверждённый халяль")),
        ],
    )
    exclude = forms.CharField(
        label=_("Что исключить?"), required=False, max_length=100,
        help_text=_("Укажите слова через запятую. Сверим их с названиями и описаниями блюд."),
    )
    max_minutes = forms.IntegerField(
        label=_("Максимальное время доставки, мин"), required=False, min_value=15, max_value=120,
    )
