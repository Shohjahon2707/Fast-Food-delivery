from django.contrib import admin

from .models import Order, OrderIssue, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("name", "menu_item", "quantity", "price")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "customer_name", "status", "total_price", "courier", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("id", "phone", "customer_name", "address")
    list_select_related = ("courier",)
    inlines = [OrderItemInline]
    readonly_fields = tuple(field.name for field in Order._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrderIssue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ("order", "author", "created_at", "resolved_at")
    readonly_fields = tuple(field.name for field in OrderIssue._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
