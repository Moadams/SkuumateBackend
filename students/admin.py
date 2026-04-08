from django.contrib import admin
from .models import Student, Guardian, Enrollment


class GuardianInline(admin.TabularInline):
    model = Guardian
    extra = 1


class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0
    readonly_fields = ["created_at"]


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = [
        "student_id", "full_name", "gender",
        "status", "admission_date", "school",
    ]
    list_filter = ["status", "gender", "school"]
    search_fields = ["first_name", "last_name", "student_id"]
    inlines = [GuardianInline, EnrollmentInline]
    readonly_fields = ["student_id", "created_at", "updated_at"]


@admin.register(Guardian)
class GuardianAdmin(admin.ModelAdmin):
    list_display = ["first_name", "last_name", "relationship", "phone", "student"]
    search_fields = ["first_name", "last_name", "phone"]


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ["student", "klass", "academic_year", "is_active"]
    list_filter = ["is_active", "academic_year"]