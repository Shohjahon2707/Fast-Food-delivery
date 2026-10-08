from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from .forms import UserRegisterForm
from apps.courier.views import CourierRegisterView

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



# Preserve the existing customer-facing registration URL.
register_courier = CourierRegisterView.as_view()

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
    return redirect("home")
