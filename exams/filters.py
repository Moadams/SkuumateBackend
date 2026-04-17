import django_filters

from exams.models import AssessmentType


class AssessmentTypeFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = AssessmentType
        fields = ['is_active']