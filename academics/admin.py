from django.contrib import admin
from .models import AcademicYear, Term, Subject, Class, ClassSubject, ClassTeacher


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ["name", "school", "start_date", "end_date", "is_current"]
    list_filter = ["is_current", "school"]
    search_fields = ["name"]


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ["name", "academic_year", "start_date", "end_date", "is_current"]
    list_filter = ["is_current", "name"]
    search_fields = ["academic_year__name"]


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "school"]
    list_filter = ["is_active", "school"]
    search_fields = ["name", "code"]


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ["name", "school", "capacity"]
    list_filter = ["is_active", "school"]
    search_fields = ["name"]


@admin.register(ClassSubject)
class ClassSubjectAdmin(admin.ModelAdmin):
    list_display = ["klass", "subject", "school"]


@admin.register(ClassTeacher)
class ClassTeacherAdmin(admin.ModelAdmin):
    list_display = ["teacher", "klass", "academic_year", "is_active"]
    list_filter = ["is_active"]