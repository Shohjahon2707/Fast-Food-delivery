from django import forms
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.common.access import partner_required
from apps.menu.models import MenuItem
from apps.users.views import RoleBasedLoginView

from .models import Restaurant


class PartnerLoginForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.role != "partner" or user.is_staff:
            raise ValidationError(_("Этот вход предназначен для партнёров ресторанов."))


class PartnerLoginView(RoleBasedLoginView):
    template_name = "orders/partner_login.html"
    authentication_form = PartnerLoginForm
    redirect_authenticated_user = False

    def get_success_url(self):
        return reverse("partner_dashboard")


class RestaurantForm(forms.ModelForm):
    class Meta:
        model = Restaurant
        fields = ("accepting_orders", "opens_at", "closes_at", "minimum_subtotal")
        labels = {
            "accepting_orders": _("Принимать заказы"), "opens_at": _("Открытие"),
            "closes_at": _("Закрытие"), "minimum_subtotal": _("Минимальная сумма блюд"),
        }
        widgets = {
            "opens_at": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
            "closes_at": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
        }


class DishForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ("name", "description", "category", "price", "is_available", "is_vegetarian",
                  "lunch_role", "servings", "cooking_minutes")
        labels = {
            "name": _("Название"), "description": _("Описание"),
            "category": _("Категория"), "price": _("Цена"),
            "is_available": _("Доступно для заказа"), "is_vegetarian": _("Без мяса"),
            "lunch_role": _("Роль в наборе"), "servings": _("Число порций"),
            "cooking_minutes": _("Приготовление"),
        }


@partner_required
def dashboard(request):
    restaurant = get_object_or_404(Restaurant, partner=request.user)
    form = RestaurantForm(request.POST if request.method == "POST" else None, instance=restaurant)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Настройки ресторана сохранены."))
        return redirect("partner_dashboard")
    orders = restaurant.orders.prefetch_related("items").order_by("-created_at")
    return render(request, "orders/partner.html", {
        "restaurant": restaurant, "form": form,
        "dishes": restaurant.menu_items.select_related("category"),
        "page_obj": Paginator(orders, 15).get_page(request.GET.get("page")),
    })


@partner_required
def edit_dish(request, pk=None):
    restaurant = get_object_or_404(Restaurant, partner=request.user)
    dish = get_object_or_404(restaurant.menu_items, pk=pk) if pk else MenuItem(restaurant=restaurant)
    form = DishForm(request.POST if request.method == "POST" else None, instance=dish)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("partner_dashboard")
    return render(request, "orders/partner_dish.html", {"form": form, "dish": dish})
