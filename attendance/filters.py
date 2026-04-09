import django_filters
from .models import Attendance, AttendanceSummary


class AttendanceFilter(django_filters.FilterSet):
    date = django_filters.DateFilter()
    date_from = django_filters.DateFilter(
        field_name="date", lookup_expr="gte"
    )
    date_to = django_filters.DateFilter(
        field_name="date", lookup_expr="lte"
    )
    status = django_filters.ChoiceFilter(
        choices=Attendance.Status.choices
    )
    class_id = django_filters.UUIDFilter(field_name="klass__id")
    term_id = django_filters.UUIDFilter(field_name="term__id")
    student_id = django_filters.UUIDFilter(field_name="student__id")

    class Meta:
        model = Attendance
        fields = [
            "date",
            "date_from",
            "date_to",
            "status",
            "class_id",
            "term_id",
            "student_id",
        ]


class AttendanceSummaryFilter(django_filters.FilterSet):
    date = django_filters.DateFilter()
    date_from = django_filters.DateFilter(
        field_name="date", lookup_expr="gte"
    )
    date_to = django_filters.DateFilter(
        field_name="date", lookup_expr="lte"
    )
    class_id = django_filters.UUIDFilter(field_name="klass__id")
    term_id = django_filters.UUIDFilter(field_name="term__id")

    class Meta:
        model = AttendanceSummary
        fields = ["date", "date_from", "date_to", "class_id", "term_id"]