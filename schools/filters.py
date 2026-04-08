import django_filters
from .models import School


class SchoolFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(
        method="filter_by_status",
        label="Subscription status (Active, Inactive, Pending)",
    )
    plan = django_filters.CharFilter(
        method="filter_by_plan",
        label="Plan type (lite, advantage, enterprise)",
    )

    class Meta:
        model = School
        fields = ["status", "plan"]

    def filter_by_status(self, queryset, name, value):
        """
        Filter schools by derived subscription status.
        Active   = has accessible subscription
        Inactive = locked or cancelled subscription
        Pending  = no subscription at all
        """
        from subscriptions.models import Subscription
        from django.utils import timezone

        value = value.lower()

        if value == "active":
            school_ids = Subscription.objects.filter(
                status__in=["active", "trial", "grace"]
            ).values_list("school_id", flat=True)
            return queryset.filter(id__in=school_ids)

        elif value == "inactive":
            school_ids = Subscription.objects.filter(
                status__in=["locked", "cancelled", "expired"]
            ).values_list("school_id", flat=True)
            return queryset.filter(id__in=school_ids)

        elif value == "pending":
            # Schools with no subscription at all
            subscribed_ids = Subscription.objects.values_list(
                "school_id", flat=True
            ).distinct()
            return queryset.exclude(id__in=subscribed_ids)

        return queryset

    def filter_by_plan(self, queryset, name, value):
        from subscriptions.models import Subscription
        school_ids = Subscription.objects.filter(
            plan__plan_type__iexact=value,
            status__in=["active", "trial", "grace"],
        ).values_list("school_id", flat=True)
        return queryset.filter(id__in=school_ids)