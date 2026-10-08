import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User


def clean_phone(value):
    value = re.sub(r"[\s()\-]", "", value)
    if not re.fullmatch(r"\+?[1-9]\d{8,14}", value):
        raise forms.ValidationError("Введите телефон с кодом страны, например +998 90 123 45 67.")
    return "+" + value.lstrip("+")


class UserRegisterForm(UserCreationForm):
    first_name = forms.CharField(label="Как вас зовут", max_length=150)
    phone = forms.CharField(label="Телефон", max_length=20)
    email = forms.EmailField(label="Электронная почта", help_text="Для восстановления доступа.")

    class Meta:
        model = User
        fields = ("first_name", "username", "email", "phone", "password1", "password2")

    def clean_phone(self):
        return clean_phone(self.cleaned_data["phone"])

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Эта почта уже зарегистрирована. Войдите или восстановите пароль."
            )
        return email


class CustomerLoginForm(AuthenticationForm):
    remember_me = forms.BooleanField(required=False, label="Запомнить меня на 30 дней")

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_customer:
            raise forms.ValidationError(
                "Используйте отдельный вход для курьеров или администратора.", code="invalid_role"
            )


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "phone", "address")
        labels = {"first_name": "Имя", "phone": "Телефон", "address": "Адрес по умолчанию"}
        widgets = {"address": forms.Textarea(attrs={"rows": 3, "maxlength": 255})}

    def clean_phone(self):
        return clean_phone(self.cleaned_data["phone"] or "")

    def clean_address(self):
        address = (self.cleaned_data.get("address") or "").strip()
        if len(address) > 255:
            raise forms.ValidationError("Не более 255 символов.")
        return address
