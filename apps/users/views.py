import hashlib

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.cart.basket import SESSION_KEY, transfer_guest_basket
from apps.common.access import customer_required
from apps.orders.delivery import POINT_SESSION_KEY

from .forms import CustomerLoginForm, ProfileForm, UserRegisterForm


def landing(user):
    if user.role == "kitchen":
        return "kitchen"
    if user.is_staff:
        return "operations" if user.has_perm("orders.change_order") else "admin:index"
    return "courier_orders" if user.is_courier else "home"


def register_user(request):
    if request.user.is_authenticated:
        return redirect(landing(request.user))
    form = UserRegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        transfer_guest_basket(request)
        messages.success(request, "Добро пожаловать! Самое вкусное уже в меню.")
        return redirect("menu_list")
    return render(request, "users/register_user.html", {"form": form})


class RoleBasedLoginView(LoginView):
    template_name = "users/login.html"
    authentication_form = CustomerLoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or reverse(landing(self.request.user))

    def throttle_key(self):
        identity = self.request.META.get("REMOTE_ADDR", "")
        return "login:" + hashlib.sha256(identity.encode()).hexdigest()

    def post(self, request, *args, **kwargs):
        if cache.get(self.throttle_key(), 0) >= 10:
            form = self.get_form()
            form.add_error(None, "Слишком много попыток. Попробуйте через 10 минут.")
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        key = self.throttle_key()
        cache.set(key, cache.get(key, 0) + 1, 600)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self.throttle_key())
        response = super().form_valid(form)
        self.request.session.set_expiry(2592000 if form.cleaned_data.get("remember_me") else 0)
        transfer_guest_basket(self.request)
        if self.request.user.is_customer and self.request.session.get(SESSION_KEY):
            messages.info(self.request, _("Выберите, какую корзину сохранить."))
            return redirect("cart_detail")
        return response


@login_required
def home_view(request):
    return redirect(landing(request.user))


@customer_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        if "address" in form.changed_data:
            form.instance.address_latitude = form.instance.address_longitude = None
            request.session.pop(POINT_SESSION_KEY, None)
        form.save()
        messages.success(request, "Контакты и адрес сохранены.")
        return redirect("profile")
    return render(request, "users/profile.html", {"form": form})


def preferences(request):
    return render(request, "users/preferences.html")


@require_POST
def save_preferences(request):
    response = redirect("preferences")
    if request.POST.get("action") == "forget":
        response.delete_cookie("food_preferences")
    else:
        diet = "vegetarian" if request.POST.get("diet") == "vegetarian" else "all"
        motion = "reduce" if request.POST.get("motion") == "reduce" else "normal"
        response.set_signed_cookie(
            "food_preferences",
            f"{diet}:{motion}",
            salt="food-preferences",
            max_age=15552000,
            httponly=True,
            secure=request.is_secure(),
            samesite="Lax",
        )
    messages.success(request, "Настройки обновлены.")
    return response
