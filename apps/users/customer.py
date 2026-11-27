from django import forms
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.common.access import customer_required
from apps.menu.models import MenuItem
from apps.menu.smart_forms import PointForm
from apps.orders.models import Restaurant

from .models import FavoriteDish, FavoriteRestaurant, SavedAddress


class AddressForm(PointForm):
    field_order = ["label", "address", "latitude", "longitude"]
    label = forms.CharField(label=_("Название адреса"), max_length=40)
    address = forms.CharField(label=_("Адрес доставки"), min_length=8, max_length=255)


@customer_required
def addresses(request):
    form = AddressForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                SavedAddress.objects.create(user=request.user, **form.cleaned_data)
        except IntegrityError:
            form.add_error("label", _("Адрес с таким названием уже существует."))
        else:
            return redirect("saved_addresses")
    return render(request, "users/addresses.html", {
        "form": form, "addresses": request.user.saved_addresses.all(),
    })


@customer_required
@require_POST
def delete_address(request, pk):
    get_object_or_404(SavedAddress, pk=pk, user=request.user).delete()
    return redirect("saved_addresses")


@customer_required
def favorites(request):
    return render(request, "users/favorites.html", {
        "dishes": request.user.favorite_dishes.select_related("dish__category", "dish__restaurant"),
        "restaurants": request.user.favorite_restaurants.select_related("restaurant"),
    })


@customer_required
@require_POST
def favorite(request, kind, pk):
    if kind == "dish":
        dish = get_object_or_404(MenuItem, pk=pk)
        model, fields = FavoriteDish, {"dish": dish}
        fallback = reverse("menu_item_detail", args=[pk])
    else:
        restaurant = get_object_or_404(Restaurant, pk=pk)
        model, fields = FavoriteRestaurant, {"restaurant": restaurant}
        fallback = reverse("restaurant_detail", args=[pk])
    if request.POST.get("action") == "remove":
        model.objects.filter(user=request.user, **fields).delete()
        messages.success(request, _("Удалено из избранного."))
    else:
        model.objects.get_or_create(user=request.user, **fields)
        messages.success(request, _("Добавлено в избранное."))
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url, {request.get_host()}, require_https=request.is_secure()
    ):
        next_url = fallback
    return redirect(next_url or fallback)
