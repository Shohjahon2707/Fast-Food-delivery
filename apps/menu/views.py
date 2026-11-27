from django.core.paginator import Paginator
from django.db.models import Avg, Count, F, OuterRef, Q, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.orders.delivery import get_point, saved_point
from apps.orders.models import OrderReview, Restaurant

from .forms import MealFilterForm
from .models import Category, MenuItem
from .search import search
from .smart import recommend, sign_lunch
from .smart_forms import ALLERGEN_CHOICES, SmartLunchForm
from .structured import restaurant_schema


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


def catalog(request, restaurant=None):
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
    items = available_items().annotate(rating=Avg("dish_reviews__score"))
    if restaurant:
        items = items.filter(restaurant=restaurant)
    if form.is_valid():
        data = form.cleaned_data
        if data["q"]:
            items = search(items, data["q"], (
                "name", "name_uz", "name_en", "description", "description_uz", "description_en",
                "restaurant__name",
            ))
        if data["category"]:
            items = items.filter(category=data["category"])
        if data["min_price"] is not None:
            items = items.filter(price__gte=data["min_price"])
        if data["max_price"] is not None:
            items = items.filter(price__lte=data["max_price"])
        if data["diet"] == "vegetarian":
            items = items.filter(is_vegetarian=True)
        if data["sort"] == "rating":
            items = items.order_by(F("rating").desc(nulls_last=True), "pk")
        elif data["sort"] or not data["q"]:
            items = items.order_by(data["sort"] or "pk", "pk")
    else:
        items = items.none()
    page = Paginator(items, 12).get_page(request.GET.get("page"))
    return render(
        request,
        "menu/menu_list.html",
        {
            "form": form,
            "categories": Category.objects.all(),
            "page_obj": page,
            "query": params.get("q", ""),
            "selected_category": params.get("category", ""),
            "restaurant": restaurant,
            "restaurant_schema": restaurant_schema(request, restaurant, page) if restaurant else None,
            "restaurant_rating": restaurant.orders.aggregate(avg=Avg("review__score"))["avg"]
            if restaurant else None,
            "favorite_restaurant": restaurant and request.user.is_authenticated
            and request.user.favorite_restaurants.filter(restaurant=restaurant).exists(),
            "restaurant_count": items.values("restaurant_id").distinct().count(),
        },
    )


def menu_list(request):
    return catalog(request)


def suggestions(request):
    query = request.GET.get("q", "").strip()[:100]
    if len(query) < 2:
        return JsonResponse({"suggestions": []})
    dishes = search(available_items(), query, ("name", "name_uz", "name_en"))
    names = dishes.values_list("name", flat=True)[:18]
    return JsonResponse({"suggestions": list(dict.fromkeys(names))[:6]})


def smart_lunch(request):
    redirect_response = portal_redirect(request)
    if redirect_response:
        return redirect_response
    if "budget" not in request.GET and any(
        key in request.GET for key in ("q", "category", "min_price", "max_price", "sort")
    ):
        return catalog(request)
    preference = request.get_signed_cookie("food_preferences", default="", salt="food-preferences")
    initial = (
        request.user.lunch_preferences if request.user.is_authenticated
        else request.session.get("lunch_preferences", {})
    ).copy()
    initial.setdefault("diet", preference.split(":")[0] or "all")
    point = saved_point(request)
    if point:
        initial.update(latitude=point[0], longitude=point[1])
    params = request.POST if request.method == "POST" else request.GET
    submitted = request.method == "POST" or "budget" in params
    form = SmartLunchForm(params if submitted else None, initial=initial)
    lunches, closest = [], None
    if submitted and form.is_valid():
        criteria = {
            key: form.cleaned_data[key]
            for key in ("budget", "people", "diet", "max_minutes", "allergens")
        }
        criteria["point"] = get_point(form.cleaned_data)
        lunches, closest = recommend(criteria)
        lunches = [(lunch, sign_lunch(lunch, criteria)) for lunch in lunches]
    return render(
        request, "menu/smart_lunch.html",
        {
            "form": form, "lunches": lunches, "closest": closest,
            "searched": submitted and form.is_valid(),
        },
    )


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
    allergen_labels = dict(ALLERGEN_CHOICES)
    return render(
        request,
        "menu/menu_item_detail.html",
        {
            "item": item,
            "options": item.options.filter(active=True),
            "rating": item.dish_reviews.aggregate(avg=Avg("score"))["avg"],
            "favorite_dish": request.user.is_authenticated
            and request.user.favorite_dishes.filter(dish=item).exists(),
            "allergen_labels": [
                allergen_labels[code] for code in (item.allergens or []) if code in allergen_labels
            ],
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
        dish_count=Count("menu_items", filter=Q(menu_items__is_available=True), distinct=True),
        rating=Subquery(
            OrderReview.objects.filter(order__restaurant=OuterRef("pk"))
            .order_by().values("order__restaurant").annotate(avg=Avg("score")).values("avg")
        ),
    )
    if query:
        restaurants = search(
            restaurants, query, (
                "name", "cuisine", "menu_items__name", "menu_items__name_uz", "menu_items__name_en",
            ),
        ).distinct()
    if request.GET.get("sort") == "rating":
        restaurants = restaurants.order_by(F("rating").desc(nulls_last=True), "pk")
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
