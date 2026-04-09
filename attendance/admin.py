from django.contrib import admin
from .models import Attendance, AttendanceSummary


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = [
        "student", "klass", "date",
        "status", "recorded_by", "school",
    ]
    list_filter = ["status", "date", "school", "klass"]
    search_fields = [
        "student__first_name",
        "student__last_name",
        "student__student_id",
    ]
    ordering = ["-date"]


@admin.register(AttendanceSummary)
class AttendanceSummaryAdmin(admin.ModelAdmin):
    list_display = [
        "klass", "date", "total_students",
        "present_count", "absent_count",
        "late_count", "attendance_percentage",
    ]
    list_filter = ["date", "school", "klass"]
    ordering = ["-date"]