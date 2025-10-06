# apps/menu/views.py
from django.shortcuts import render, get_object_or_404
from .models import Category, MenuItem

def menu_list(request):
    categories = Category.objects.prefetch_related("items").all()
    return render(request, "menu/menu_list.html", {"categories": categories})

def category_detail(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    items = category.items.filter(is_available=True)
    return render(request, "menu/category_detail.html", {"category": category, "items": items})

def menu_item_detail(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id, is_available=True)
    return render(request, "menu/menu_item_detail.html", {"item": item})

def home(request):
    categories = Category.objects.all()
    featured_items = MenuItem.objects.filter(is_available=True)[:6] 
    return render(request, "home.html", {
        "categories": categories,
        "featured_items": featured_items,
    })
