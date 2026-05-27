from django.contrib import admin
from .models import School


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "city", "country", "status", "created_at"]
    list_filter = ["status", "country"]
    search_fields = ["name", "email"]