from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .models import Category, MenuItem


def portal_redirect(request):
    if request.user.is_authenticated and not request.user.is_customer:
        from apps.users.views import landing

        return redirect(landing(request.user))


def menu_list(request):
    redirect_response = portal_redirect(request)
    if redirect_response:
        return redirect_response
    items = MenuItem.objects.filter(is_available=True).select_related("category")
    query = request.GET.get("q", "").strip()[:100]
    category = request.GET.get("category", "")
    if query:
        items = items.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if category.isdigit():
        items = items.filter(category_id=int(category))
    preference = request.get_signed_cookie(
        "food_preferences", default="all:normal", salt="food-preferences"
    )
    diet = request.GET.get("diet", preference.split(":")[0])
    if diet == "vegetarian":
        items = items.filter(is_vegetarian=True)
    sort = request.GET.get("sort", "")
    items = items.order_by({"price": "price", "-price": "-price"}.get(sort, "id"), "pk")
    return render(
        request,
        "menu/menu_list.html",
        {
            "categories": Category.objects.all(),
            "page_obj": Paginator(items, 12).get_page(request.GET.get("page")),
            "query": query,
            "selected_category": category,
            "diet": diet,
            "sort": sort,
        },
    )


def category_detail(request, category_id):
    get_object_or_404(Category, pk=category_id)
    return redirect("/menu/?category=" + str(category_id))


def menu_item_detail(request, item_id):
    redirect_response = portal_redirect(request)
    if redirect_response:
        return redirect_response
    item = get_object_or_404(
        MenuItem.objects.select_related("category"), pk=item_id, is_available=True
    )
    return render(
        request,
        "menu/menu_item_detail.html",
        {
            "item": item,
            "related": MenuItem.objects.filter(category=item.category, is_available=True).exclude(
                pk=item.pk
            )[:3],
        },
    )


def home(request):
    redirect_response = portal_redirect(request)
    if redirect_response:
        return redirect_response
    return render(
        request,
        "home.html",
        {
            "featured_items": MenuItem.objects.filter(is_available=True).select_related("category")[
                :4
            ],
            "categories": Category.objects.all(),
        },
    )
