import django_filters

from exams.models import AssessmentType, StudentReport


class AssessmentTypeFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = AssessmentType
        fields = ('is_active',)

class StudentReportFilter(django_filters.FilterSet):
    status = django_filters.CharFilter()

    class Meta:
        model = StudentReport 
        fields = ('status',)