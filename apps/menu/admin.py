from django.contrib import admin

from .models import Category, MenuItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "is_available", "is_vegetarian")
    list_editable = ("price", "is_available")
    list_filter = ("category", "is_available", "is_vegetarian")
    search_fields = ("name",)
    list_select_related = ("category",)
