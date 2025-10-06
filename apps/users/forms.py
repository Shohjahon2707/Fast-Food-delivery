# apps/users/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

User = get_user_model()

class UserRegisterForm(UserCreationForm):
    phone = forms.CharField(required=True)

    class Meta:
        model = User
        fields = ("username", "phone", "password1", "password2")


class CourierRegisterForm(UserCreationForm):
    phone = forms.CharField(required=True)
    vehicle = forms.ChoiceField(choices=[("foot", "Пеший"), ("bike", "Велосипед"), ("car", "Машина")])
    shift = forms.ChoiceField(choices=[("day", "День"), ("night", "Ночь")])

    class Meta:
        model = User
        fields = ("username", "phone", "vehicle", "shift", "password1", "password2")
