# apps/users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "role", "is_staff", "is_superuser")
    list_filter = ("role", "is_staff", "is_superuser")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Личные данные", {"fields": ("email", "phone", "address", "role")}),
        ("Права доступа", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Важные даты", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "phone", "address", "role", "password1", "password2", "is_staff", "is_superuser"),
        }),
    )
    search_fields = ("username", "email", "phone")
    ordering = ("username",)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
