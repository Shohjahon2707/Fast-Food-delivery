from django import forms

from apps.users.forms import clean_phone


class CheckoutForm(forms.Form):
    customer_name = forms.CharField(label="Ваше имя", max_length=150)
    phone = forms.CharField(
        label="Номер телефона",
        max_length=20,
        widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
    )
    address = forms.CharField(
        label="Адрес доставки",
        min_length=8,
        max_length=255,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "autocomplete": "street-address",
                "placeholder": "Улица, дом, квартира, подъезд",
            }
        ),
    )
    comment = forms.CharField(
        label="Комментарий",
        max_length=500,
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 2, "placeholder": "Например: домофон 24, не звонить в дверь"}
        ),
    )
    payment_method = forms.ChoiceField(
        choices=[("cash", "Наличными при получении")], initial="cash", widget=forms.RadioSelect
    )
    save_address = forms.BooleanField(
        label="Сохранить адрес в профиле", required=False, initial=True
    )
    checkout_token = forms.UUIDField(widget=forms.HiddenInput)

    latitude = forms.DecimalField(
        required=False, min_value=-90, max_value=90, decimal_places=6, widget=forms.HiddenInput
    )
    longitude = forms.DecimalField(
        required=False, min_value=-180, max_value=180, decimal_places=6, widget=forms.HiddenInput
    )

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
