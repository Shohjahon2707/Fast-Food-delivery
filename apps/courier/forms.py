from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import Courier

User = get_user_model()

class CourierRegistrationForm(UserCreationForm):
    name = forms.CharField(max_length=100, label="ФИО")
    phone = forms.CharField(max_length=20, label="Телефон")
    vehicle = forms.ChoiceField(choices=Courier.VEHICLE_CHOICES, label="Транспорт")

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'name', 'phone', 'vehicle']

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            Courier.objects.create(
                user=user,
                name=self.cleaned_data['name'],
                phone=self.cleaned_data['phone'],
                vehicle=self.cleaned_data['vehicle'],
            )
        return user
