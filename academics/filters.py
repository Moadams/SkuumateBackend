import django_filters
from .models import AcademicYear, SubjectTeacher, Term, Subject, Class


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

class SubjectTeacherFilter(django_filters.FilterSet):
    class_id = django_filters.UUIDFilter(field_name="klass__id")
    subject_id = django_filters.UUIDFilter(field_name="subject__id")
    teacher_id = django_filters.UUIDFilter(field_name="teacher__id")
    academic_year_id = django_filters.UUIDFilter(
        field_name="academic_year__id"
    )
    term_id = django_filters.UUIDFilter(field_name="term__id")
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = SubjectTeacher
        fields = [
            "class_id", "subject_id", "teacher_id",
            "academic_year_id", "term_id", "is_active",
        ]