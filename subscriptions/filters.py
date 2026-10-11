"""django-filter FilterSets for every subscription list endpoint."""
import django_filters

from subscriptions.models import Feature, Package, Subscription, SubscriptionPayment


class PackageFilter(django_filters.FilterSet):
    """Filter packages for the public catalog and superadmin management."""
    plan_type = django_filters.ChoiceFilter(choices=Package.PlanType.choices)
    billing_period = django_filters.ChoiceFilter(choices=Package.BillingPeriod.choices)
    is_active = django_filters.BooleanFilter()
    is_public = django_filters.BooleanFilter()
    currency = django_filters.CharFilter(lookup_expr="iexact")
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    more_students_than = django_filters.NumberFilter(
        field_name="maximum_students", lookup_expr="gte"
    )

    class Meta:
        model = Package
        fields = (
            "plan_type",
            "billing_period", 
            "currency",
            "is_active",
            "is_public",
            "min_price",
            "max_price",
            "more_students_than",
        )


class FeatureFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()
    category = django_filters.CharFilter(lookup_expr="iexact")

    class Meta:
        model = Feature
        fields = ("is_active", "category")


class SubscriptionFilter(django_filters.FilterSet):
    """Filters used by the superadministrator's cross-school subscription list."""
    school = django_filters.UUIDFilter(field_name="school__id")
    school_name = django_filters.CharFilter(
        field_name="school__name", lookup_expr="icontains"
    )
    school_code = django_filters.CharFilter(
        field_name="school__school_code", lookup_expr="iexact"
    )
    plan = django_filters.UUIDFilter(field_name="plan__id")
    plan_code = django_filters.CharFilter(field_name="plan__code", lookup_expr="iexact")
    status = django_filters.ChoiceFilter(choices=Subscription.Status.choices)
    is_paid = django_filters.BooleanFilter()
    is_current = django_filters.BooleanFilter()
    term = django_filters.UUIDFilter(field_name="term__id")
    start_date_from = django_filters.DateTimeFilter(field_name="start_date", lookup_expr="gte")
    start_date_to = django_filters.DateTimeFilter(field_name="start_date", lookup_expr="lte")
    end_date_from = django_filters.DateTimeFilter(field_name="end_date", lookup_expr="gte")
    end_date_to = django_filters.DateTimeFilter(field_name="end_date", lookup_expr="lte")
    created_from = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_to = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Subscription
        fields = (
            "school",
            "school_name",
            "school_code",
            "plan",
            "plan_code",
            "status",
            "is_paid",
            "is_current",
            "term",
        )


class MySubscriptionFilter(django_filters.FilterSet):
    """Filters a school can use on its own subscription list."""
    plan = django_filters.UUIDFilter(field_name="plan__id")
    plan_code = django_filters.CharFilter(field_name="plan__code", lookup_expr="iexact")
    status = django_filters.ChoiceFilter(choices=Subscription.Status.choices)
    is_paid = django_filters.BooleanFilter()
    is_current = django_filters.BooleanFilter()
    term = django_filters.UUIDFilter(field_name="term__id")
    start_date_from = django_filters.DateTimeFilter(field_name="start_date", lookup_expr="gte")
    start_date_to = django_filters.DateTimeFilter(field_name="start_date", lookup_expr="lte")
    end_date_from = django_filters.DateTimeFilter(field_name="end_date", lookup_expr="gte")
    end_date_to = django_filters.DateTimeFilter(field_name="end_date", lookup_expr="lte")

    class Meta:
        model = Subscription
        fields = (
            "plan",
            "plan_code",
            "status",
            "is_paid",
            "is_current",
            "term",
        )


class SubscriptionPaymentFilter(django_filters.FilterSet):
    """Filters for the superadministrator's payment list."""
    school = django_filters.UUIDFilter(field_name="school__id")
    school_name = django_filters.CharFilter(
        field_name="school__name", lookup_expr="icontains"
    )
    subscription = django_filters.UUIDFilter(field_name="subscription__id")
    plan = django_filters.UUIDFilter(field_name="plan__id")
    status = django_filters.ChoiceFilter(choices=SubscriptionPayment.PaymentStatus.choices)
    payment_mode = django_filters.ChoiceFilter(choices=SubscriptionPayment.PaymentMode.choices)
    provider = django_filters.CharFilter(lookup_expr="iexact")
    min_amount = django_filters.NumberFilter(field_name="amount", lookup_expr="gte")
    max_amount = django_filters.NumberFilter(field_name="amount", lookup_expr="lte")
    created_from = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_to = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = SubscriptionPayment
        fields = (
            "school",
            "school_name",
            "subscription",
            "plan",
            "status",
            "payment_mode",
            "provider",
            "min_amount",
            "max_amount",
        )