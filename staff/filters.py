import django_filters
from .models import StaffProfile


class StaffProfileFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        choices=StaffProfile.Status.choices
    )
    employment_type = django_filters.ChoiceFilter(
        choices=StaffProfile.EmploymentType.choices
    )
    position_id = django_filters.UUIDFilter(
        field_name="positions__id",
        label="Position ID",
    )

    class Meta:
        model = StaffProfile
        fields = ["status", "employment_type", "position_id"]