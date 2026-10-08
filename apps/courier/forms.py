from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction

from apps.users.forms import UserRegisterForm

from .models import Courier


class CourierRegistrationForm(UserRegisterForm):
    name = forms.CharField(max_length=100, label="Полное имя")
    first_name = None
    vehicle = forms.ChoiceField(choices=Courier.VEHICLE_CHOICES, label="Как будете доставлять")

    class Meta(UserRegisterForm.Meta):
        fields = ("name", "username", "email", "phone", "vehicle", "password1", "password2")

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = "courier"
        user.first_name = self.cleaned_data["name"]
        if commit:
            user.save()
            Courier.objects.create(
                user=user,
                name=self.cleaned_data["name"],
                phone=user.phone,
                vehicle=self.cleaned_data["vehicle"],
            )
        return user


class CourierLoginForm(AuthenticationForm):
    remember_me = forms.BooleanField(required=False, label="Запомнить меня на 30 дней")

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_courier:
            raise forms.ValidationError("Здесь вход только для курьеров.", code="invalid_role")
