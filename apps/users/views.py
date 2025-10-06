# apps/users/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import UserRegisterForm, CourierRegisterForm

def register_user(request):
    if request.method == "POST":
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("home")
    else:
        form = UserRegisterForm()
    return render(request, "users/register_user.html", {"form": form})


def register_courier(request):
    if request.method == "POST":
        form = CourierRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("home")
    else:
        form = CourierRegisterForm()
    return render(request, "users/register_courier.html", {"form": form})
