from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

User = get_user_model()

class UserRegisterForm(UserCreationForm):
    phone = forms.CharField(required=True, label="Телефон")

    class Meta:
        model = User
        fields = ("username", "email", "phone", "password1", "password2")
