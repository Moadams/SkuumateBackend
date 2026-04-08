import django_filters
from .models import Student


class StudentFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=Student.Status.choices)
    gender = django_filters.ChoiceFilter(choices=Student.Gender.choices)
    admission_year = django_filters.NumberFilter(
        field_name="admission_date", lookup_expr="year"
    )
    class_id = django_filters.UUIDFilter(
        field_name="enrollments__klass__id",
        label="Class ID",
    )
    academic_year_id = django_filters.UUIDFilter(
        field_name="enrollments__academic_year__id",
        label="Academic Year ID",
    )

    class Meta:
        model = Student
        fields = ["status", "gender", "admission_year", "class_id", "academic_year_id"]