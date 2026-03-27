import django_filters
from .models import AcademicYear, Term, Subject, Class


class AcademicYearFilter(django_filters.FilterSet):
    is_current = django_filters.BooleanFilter()
    start_year = django_filters.NumberFilter(
        field_name="start_date", lookup_expr="year"
    )

    class Meta:
        model = AcademicYear
        fields = ["is_current", "start_year"]


class TermFilter(django_filters.FilterSet):
    academic_year = django_filters.UUIDFilter(field_name="academic_year__id")
    is_current = django_filters.BooleanFilter()
    name = django_filters.ChoiceFilter(choices=Term.TermName.choices)

    class Meta:
        model = Term
        fields = ["academic_year", "is_current", "name"]


class SubjectFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Subject
        fields = ["is_active"]


class ClassFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Class
        fields = ["is_active"]