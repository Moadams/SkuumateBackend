from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["email", "full_name", "role", "school", "is_active"]
    list_filter = ["role", "is_active", "school"]
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["-created_at"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name")}),
        ("Role & School", {"fields": ("role", "school")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "role", "school", "password1", "password2"),
        }),
    )