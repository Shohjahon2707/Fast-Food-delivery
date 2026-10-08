from django.contrib import admin

from .models import Courier


@admin.register(Courier)
class CourierAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "vehicle", "is_approved", "shift_status")
    list_filter = ("is_approved", "shift_status", "vehicle")
    search_fields = ("name", "phone")
    readonly_fields = ("user", "is_approved", "shift_status")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
