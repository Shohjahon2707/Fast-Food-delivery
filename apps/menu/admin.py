from django.contrib import admin

from .models import Category, DishOption, MenuItem


class DishOptionInline(admin.TabularInline):
    model = DishOption
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    inlines = [DishOptionInline]
    list_display = ("name", "restaurant", "category", "price", "is_available", "is_vegetarian")
    list_editable = ("price", "is_available")
    list_filter = ("restaurant", "category", "is_available", "is_vegetarian")
    search_fields = ("name",)
    list_select_related = ("category", "restaurant")
