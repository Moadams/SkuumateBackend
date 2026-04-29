import django_filters

from staff.enums.employment_type import EmploymentType
from staff.enums.staff_status import StaffStatus
from .models import StaffProfile


class StaffProfileFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        choices=StaffStatus.choices
    )
    employment_type = django_filters.ChoiceFilter(
        choices=EmploymentType.choices
    )
    position_id = django_filters.UUIDFilter(
        field_name="positions__id",
        label="Position ID",
    )
    role = django_filters.CharFilter(
        field_name = "user__role",
        label="User Role",
    )

    class Meta:
        model = StaffProfile
        fields = ["status", "employment_type", "position_id", "role"]