import re

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.orders.models import Restaurant

from .forms import MealFilterForm
from .models import Category, MenuItem


def portal_redirect(request):
    if request.user.is_authenticated and not request.user.is_customer:
        from apps.users.views import landing

        return redirect(landing(request.user))


def available_items():
    return (
        MenuItem.objects.filter(is_available=True)
        .filter(Q(restaurant__accepting_orders=True) | Q(restaurant__isnull=True))
        .select_related("category", "restaurant")
    )


def catalog(request, restaurant=None, smart=False):
    redirect_response = portal_redirect(request)
    if redirect_response:
        return redirect_response
    params = request.GET.copy()
    if "diet" not in params:
        preference = request.get_signed_cookie(
            "food_preferences", default="all:normal", salt="food-preferences"
        ).split(":")[0]
        params["diet"] = preference if preference in ("all", "vegetarian") else "all"
    form = MealFilterForm(params)
    items = available_items()
    if restaurant:
        items = items.filter(restaurant=restaurant)
    if form.is_valid():
        data = form.cleaned_data
        if data["q"]:
            items = items.filter(
                Q(name__iregex=re.escape(data["q"]))
                | Q(description__iregex=re.escape(data["q"]))
                | Q(restaurant__name__iregex=re.escape(data["q"]))
            )
        if data["category"]:
            items = items.filter(category=data["category"])
        if data["min_price"] is not None:
            items = items.filter(price__gte=data["min_price"])
        if data["max_price"] is not None:
            items = items.filter(price__lte=data["max_price"])
        if data["diet"] == "vegetarian":
            items = items.filter(is_vegetarian=True)
        items = items.order_by(data["sort"] or "pk", "pk")
    else:
        items = items.none()
    return render(
        request,
        "menu/menu_list.html",
        {
            "form": form,
            "categories": Category.objects.all(),
            "page_obj": Paginator(items, 12).get_page(request.GET.get("page")),
            "query": params.get("q", ""),
            "selected_category": params.get("category", ""),
            "restaurant": restaurant,
            "smart": smart,
            "restaurant_count": items.values("restaurant_id").distinct().count(),
        },
    )


def menu_list(request):
    return catalog(request)


def smart_lunch(request):
    return catalog(request, smart=True)


def restaurant_detail(request, pk):
    return catalog(request, restaurant=get_object_or_404(Restaurant, pk=pk))


def category_detail(request, category_id):
    get_object_or_404(Category, pk=category_id)
    return redirect("/menu/?category=" + str(category_id))


def menu_item_detail(request, item_id):
    redirect_response = portal_redirect(request)
    if redirect_response:
        return redirect_response
    item = get_object_or_404(available_items(), pk=item_id)
    return render(
        request,
        "menu/menu_item_detail.html",
        {
            "item": item,
            "related": available_items()
            .filter(restaurant_id=item.restaurant_id)
            .exclude(pk=item.pk)[:3],
        },
    )


def home(request):
    redirect_response = portal_redirect(request)
    if redirect_response:
        return redirect_response
    query = request.GET.get("q", "").strip()[:100]
    restaurants = Restaurant.objects.annotate(
        dish_count=Count("menu_items", filter=Q(menu_items__is_available=True))
    )
    if query:
        restaurants = restaurants.filter(
            Q(name__iregex=re.escape(query))
            | Q(cuisine__iregex=re.escape(query))
            | Q(menu_items__name__iregex=re.escape(query))
        ).distinct()
    return render(
        request,
        "home.html",
        {
            "restaurants": restaurants,
            "query": query,
            "categories": Category.objects.filter(items__is_available=True).distinct(),
            "featured_items": available_items().filter(price__gte=40000, price__lte=70000)[:4],
        },
    )
