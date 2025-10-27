# apps/users/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from .forms import UserRegisterForm, CourierRegisterForm
from apps.orders.models import Order
from django.shortcuts import render, redirect
from django.contrib.auth import login
from apps.courier.models import Courier 
from .forms import UserRegisterForm, CourierRegisterForm

def register_user(request):
    if request.method == "POST":
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = "customer"
            user.save()
            login(request, user)
            return redirect("home")
    else:
        form = UserRegisterForm()
    return render(request, "users/register_user.html", {"form": form})


def register_courier(request):
    if request.method == "POST":
        form = CourierRegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = "courier"  
            user.save()


            Courier.objects.create(
                user=user,
                name=user.username,
                phone=form.cleaned_data.get("phone"),
                vehicle=form.cleaned_data.get("vehicle", "foot")
            )

            login(request, user)
            return redirect("courier_orders")
    else:
        form = CourierRegisterForm()
    return render(request, "couriers/register.html", {"form": form})


class RoleBasedLoginView(LoginView):
    template_name = "users/login.html"

    def get_success_url(self):
        user = self.request.user
        if user.is_superuser or user.role == "admin":
            return "/admin/"
        elif user.role == "courier":
            return "/couriers/orders/"
        else:
            return "/"  # клиент


@login_required
def home_view(request):
    user = request.user
    if user.role == "courier":
        return redirect("courier_orders")
    elif user.is_superuser or user.role == "admin":
        return redirect("/admin/")
    return render(request, "users/home.html")
