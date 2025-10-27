from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

User = get_user_model()

class UserRegisterForm(UserCreationForm):
    phone = forms.CharField(required=True, label="Телефон")

    class Meta:
        model = User
        fields = ("username", "email", "phone", "password1", "password2")


class CourierRegisterForm(UserCreationForm):
    phone = forms.CharField(required=True, label="Телефон")
    vehicle = forms.ChoiceField(
        choices=[("foot", "Пеший"), ("bike", "Велосипед"), ("car", "Машина")],
        label="Транспорт"
    )

    class Meta:
        model = User
        fields = ("username", "email", "phone", "vehicle", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = "courier"
        if commit:
            user.save()
        return user
