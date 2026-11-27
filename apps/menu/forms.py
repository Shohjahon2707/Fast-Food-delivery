from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Category


class MealFilterForm(forms.Form):
    q = forms.CharField(required=False, max_length=100, label=_("Поиск"))
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        empty_label=_("Все категории"),
        label=_("Категория"),
    )
    min_price = forms.IntegerField(
        required=False, min_value=0, max_value=99999999, label=_("Цена от")
    )
    max_price = forms.IntegerField(
        required=False, min_value=0, max_value=99999999, label=_("Цена до")
    )
    diet = forms.ChoiceField(
        required=False, choices=[("all", _("Все блюда")), ("vegetarian", _("Без мяса"))]
    )
    sort = forms.ChoiceField(
        required=False,
        choices=[
            ("", _("Рекомендуем")),
            ("price", _("Сначала дешевле")),
            ("-price", _("Сначала дороже")),
            ("rating", _("Сначала по оценке")),
        ],
    )

    def clean(self):
        data = super().clean()
        low, high = data.get("min_price"), data.get("max_price")
        if low is not None and high is not None and low > high:
            raise forms.ValidationError(_("Цена от не должна быть больше цены до."))
        return data
