from django import forms
from django.utils.translation import gettext_lazy as _

from apps.payments.payme import enabled as payme_enabled
from apps.users.forms import clean_phone


class CheckoutForm(forms.Form):
    customer_name = forms.CharField(label=_("Ваше имя"), max_length=150)
    phone = forms.CharField(
        label=_("Номер телефона"),
        max_length=20,
        widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
    )
    address = forms.CharField(
        label=_("Адрес доставки"),
        min_length=8,
        max_length=255,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "autocomplete": "street-address",
                "placeholder": _("Улица, дом, квартира, подъезд"),
            }
        ),
    )
    comment = forms.CharField(
        label=_("Комментарий"),
        max_length=500,
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 2, "placeholder": _("Например: домофон 24, не звонить в дверь")}
        ),
    )
    payment_method = forms.ChoiceField(
        choices=[("cash", _("Наличными при получении"))], initial="cash", widget=forms.RadioSelect
    )
    save_address = forms.BooleanField(
        label=_("Сохранить адрес в профиле"), required=False, initial=True
    )
    checkout_token = forms.UUIDField(widget=forms.HiddenInput)
    quoted_fee = forms.DecimalField(required=False, min_value=0, widget=forms.HiddenInput)
    quoted_total = forms.DecimalField(required=False, min_value=0, widget=forms.HiddenInput)
    promo_code = forms.CharField(label=_("Промокод"), max_length=30, required=False)
    scheduled_at = forms.DateTimeField(
        label=_("Доставить к указанному времени"), required=False,
        help_text=_("Время Ташкента. Оставьте пустым для ближайшей доставки."),
        widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
    )

    latitude = forms.DecimalField(
        required=False, min_value=-90, max_value=90, decimal_places=6, widget=forms.HiddenInput
    )
    longitude = forms.DecimalField(
        required=False, min_value=-180, max_value=180, decimal_places=6, widget=forms.HiddenInput
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if payme_enabled():
            field = self.fields["payment_method"]
            field.choices = [*field.choices, ("payme", _("Картой через Payme"))]

    def clean(self):
        data = super().clean()
        if (data.get("latitude") is None) != (data.get("longitude") is None):
            raise forms.ValidationError("Укажите точку доставки заново.")
        return data

    def clean_phone(self):
        return clean_phone(self.cleaned_data["phone"])


class ReasonForm(forms.Form):
    reason = forms.CharField(
        label="Что случилось?",
        min_length=5,
        max_length=500,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Опишите причину. Это поможет быстрее решить вопрос."}
        ),
    )
