from django.contrib import admin
from .models import StaffPosition, StaffProfile


@admin.register(StaffPosition)
class StaffPositionAdmin(admin.ModelAdmin):
    list_display = [
        "name", "school", "is_system", "created_at"
    ]
    list_filter = ["is_system", "school"]
    search_fields = ["name"]


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = [
        "employee_id", "user", "school",
        "employment_type", "status", "date_joined",
    ]
    list_filter = ["status", "employment_type", "school"]
    search_fields = [
        "user__first_name", "user__last_name",
        "user__email", "employee_id",
    ]
    filter_horizontal = ["positions"]