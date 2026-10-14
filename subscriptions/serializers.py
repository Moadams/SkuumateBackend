from rest_framework import serializers

from academics.services import AcademicsService
from schools.models import School

from .models import (
    Feature,
    Package,
    Subscription,
    SubscriptionPayment,
)
from .services.packages import PackageService

# ─────────────────────────────────────────────────────────────────────
# Feature & Package serializers
# ─────────────────────────────────────────────────────────────────────

class FeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = (
            "id",
            "name",
            "code",
            "description",
            "category",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_code(self, value):
        queryset = Feature.objects.filter(code=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A feature with this code already exists."
            )
        return value


class PackageFeatureAssignmentSerializer(serializers.Serializer):
    """One entitlement row used for both read and write payloads."""

    code = serializers.CharField(max_length=100)
    enabled = serializers.BooleanField(default=True)

    def validate_code(self, value):
        if not Feature.objects.filter(code=value).exists():
            raise serializers.ValidationError(f"Unknown feature code: {value}")
        return value


class PackageLimitAssignmentSerializer(serializers.Serializer):
    key = serializers.RegexField(r"^[a-z0-9_]+$", max_length=80)
    name = serializers.CharField(max_length=120)
    value = serializers.IntegerField(min_value=0)
    description = serializers.CharField(required=False, allow_blank=True)


class PackageSerializer(serializers.ModelSerializer):
    """Full package payload with nested entitlements (admin + public catalog)."""

    features = PackageFeatureAssignmentSerializer(
        many=True, required=False, write_only=True
    )
    limits = PackageLimitAssignmentSerializer(
        many=True, required=False, write_only=True
    )
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    setup_fee = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)

    class Meta:
        model = Package
        fields = (
            "id",
            "name",
            "code",
            "plan_type",
            "tagline",
            "description",
            "price",
            "setup_fee",
            "billing_period",
            "currency",
            "minimum_students",
            "maximum_students",
            "is_active",
            "is_public",
            "display_order",
            "features",
            "limits",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {
            "code": {"required": True},
            "billing_period": {"required": True},
        }

    def validate_code(self, value):
        queryset = Package.objects.filter(code=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A package with this code already exists."
            )
        return value

    def validate(self, attrs):
        minimum = attrs.get(
            "minimum_students", getattr(self.instance, "minimum_students", 0)
        )
        maximum = attrs.get(
            "maximum_students", getattr(self.instance, "maximum_students", None)
        )
        if maximum is not None and maximum < minimum:
            raise serializers.ValidationError(
                {"maximum_students": "Maximum students cannot be less than minimum students."}
            )
        return attrs

    def create(self, validated_data):
        features = validated_data.pop("features", [])
        limits = validated_data.pop("limits", [])
        package = Package.objects.create(**validated_data)
        if features:
            PackageService.apply_features(package, features)
        if limits:
            PackageService.apply_limits(package, limits)
        return package

    def update(self, instance, validated_data):
        features = validated_data.pop("features", None)
        limits = validated_data.pop("limits", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if features is not None:
            PackageService.apply_features(instance, features)
        if limits is not None:
            PackageService.apply_limits(instance, limits)
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["features"] = [
            {
                "code": row.feature.code,
                "name": row.feature.name,
                "enabled": bool(row.is_enabled),
            }
            for row in (
                instance.package_features
                .select_related("feature")
                .order_by("feature__category", "feature__name")
            )
        ]
        data["limits"] = [
            {
                "key": row.key,
                "name": row.name,
                "value": str(row.value),
                "description": row.description,
            }
            for row in instance.package_limits.order_by("key")
        ]
        return data


class PackageSummarySerializer(serializers.ModelSerializer):
    """Lightweight package representation embedded inside subscriptions."""

    class Meta:
        model = Package
        fields = (
            "id",
            "name",
            "code",
            "plan_type",
            "tagline",
            "description",
            "price",
            "setup_fee",
            "billing_period",
            "currency",
            "minimum_students",
            "maximum_students",
        )


# ─────────────────────────────────────────────────────────────────────
# Subscription & payment serializers
# ─────────────────────────────────────────────────────────────────────

class SchoolSummarySerializer(serializers.ModelSerializer):
    """Lightweight school representation used by superadmin views."""

    class Meta:
        model = School
        fields = (
            "id",
            "name",
            "email",
            "phone",
            "school_code",
            "status",
            "city",
        )


class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    payment_mode_label = serializers.CharField(
        source="get_payment_mode_display", read_only=True
    )
    status_label = serializers.CharField(
        source="get_status_display", read_only=True
    )

    class Meta:
        model = SubscriptionPayment
        fields = [  # noqa: RUF012
            "id",
            "amount",
            "currency",
            "payment_reference",
            "provider",
            "payment_mode",
            "payment_mode_label",
            "status",
            "status_label",
            "created_at",
        ]
        read_only_fields = fields


class AdminSubscriptionPaymentSerializer(SubscriptionPaymentSerializer):
    """Superadmin-facing payment record with school and plan context."""

    school = SchoolSummarySerializer(read_only=True)
    plan = PackageSummarySerializer(read_only=True)
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPayment
        fields = SubscriptionPaymentSerializer.Meta.fields + [
            "subscription",
            "school",
            "plan",
            "recorded_by_name",
        ]
        read_only_fields = fields

    def get_recorded_by_name(self, instance):
        if instance.recorded_by is None:
            return None
        return f"{instance.recorded_by.first_name} {instance.recorded_by.last_name}"


class SubscriptionSerializer(serializers.ModelSerializer):
    """School-facing subscription detail with the data a school needs."""

    plan = PackageSummarySerializer(read_only=True, allow_null=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    term_name = serializers.CharField(source="term.get_name_display", read_only=True)
    days_remaining = serializers.IntegerField(read_only=True)
    payments = SubscriptionPaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Subscription
        fields = (
            "id",
            "plan",
            "plan_name",
            "status",
            "status_label",
            "term",
            "term_name",
            "start_date",
            "end_date",
            "grace_end_date",
            "days_remaining",
            "is_free_trial",
            "is_current",
            "payments",
            "notes",
            "created_at",
        )
        read_only_fields = fields


class SubscriptionListSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source="school.name", read_only=True)
    plan_name = serializers.CharField(source="plan.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    term_name = serializers.CharField(source="term.get_name_display", read_only=True, allow_null=True)

    class Meta:
        model = Subscription
        fields = (
                "id",
                "school_name",
                "plan_name",
                "status_label",
                "term_name",
                "is_paid",
                "start_date",
                "end_date",
                "is_current"
            ,)


class AdminSubscriptionSerializer(SubscriptionSerializer):
    """Superadmin-facing subscription detail with school context."""

    school = SchoolSummarySerializer(read_only=True)
    activated_by_name = serializers.SerializerMethodField()

    class Meta(SubscriptionSerializer.Meta):
        fields = (
            "id",
            "school",
            "plan",
            "plan_name",
            "status",
            "status_label",
            "term",
            "term_name",
            "start_date",
            "end_date",
            "grace_end_date",
            "days_remaining",
            "is_paid",
            "is_current",
            "is_read_only",
            "is_locked",
            "is_accessible",
            "is_on_trial",
            "activated_by_name",
            "payments",
            "notes",
            "created_at",
        )

    def get_activated_by_name(self, instance):
        if instance.activated_by is None:
            return None
        return f"{instance.activated_by.first_name} {instance.activated_by.last_name}"


# ─────────────────────────────────────────────────────────────────────
# Subscribe input serializers
# ─────────────────────────────────────────────────────────────────────

class InitiatePaymentSerializer(serializers.Serializer):
    coupon_code = serializers.CharField(max_length=20, required=False, allow_blank=False)

    """School admin — start a gateway payment before subscribing."""

    plan_id = serializers.UUIDField()
    term_id = serializers.UUIDField(required=False, allow_null=True)
    provider = serializers.ChoiceField(
        choices=["paystack", "stripe", "momo", "simulate"], required=False
    )
    include_setup_fee = serializers.BooleanField(default=False)

    def validate_plan_id(self, value):
        package = Package.objects.filter(id=value, is_active=True).first()
        if package is None:
            raise serializers.ValidationError("Package not found or inactive.")
        return package

    def validate_term_id(self, value):
        if value is None:
            return None
        term = self.context["school"].terms.filter(id=value).first()
        if term is None:
            raise serializers.ValidationError(
                "Term not found or does not belong to this school."
            )
        return term

    def validate(self, attrs):
        attrs["plan"] = attrs.pop("plan_id")
        return attrs

class SchoolSubscribeSerializer(serializers.Serializer):
    plan = serializers.UUIDField()
    is_paid = serializers.BooleanField(required=False, default=True)
    term = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    payment_reference = serializers.CharField(required=False, allow_blank=True)
    payment_method = serializers.ChoiceField(
        choices=SubscriptionPayment.PaymentMode.choices,
        required=False
    )

    def validate_plan(self, value):
        package = Package.objects.filter(id=value, is_active=True).first()
        if package is None:
            raise serializers.ValidationError("Package not found or inactive.")
        self._validate_student_budget(package)
        return package

    def validate_term(self, value):
        if value is None:
            return None
        term = self.context["school"].terms.filter(id=value).first()
        if term is None:
            raise serializers.ValidationError(
                "Term not found or does not belong to this school."
            )
        return term

    def validate(self, attrs):
        
        plan = attrs.get("plan")
        if plan and plan.billing_period == Package.BillingPeriod.TERM and not attrs.get("term"):
            term = AcademicsService._current_term(self.context["school"])
            if term:
                attrs["term"] = term
            else:
                raise serializers.ValidationError(
                    {"term": "A term must be specified for a term-based plan."}
                )

        if attrs.get("is_paid") and not (attrs.get("payment_method") and attrs.get("payment_reference")):
            raise serializers.ValidationError(
                {"payment_method": "A payment method and payment reference are required for paid subscriptions."}
            )
        return attrs

    def _validate_student_budget(self, package):
        if package.maximum_students is None:
            return
        school = self.context["school"]
        active_students = school.students.filter(status="active").count()
        if active_students > package.maximum_students:
            raise serializers.ValidationError(
                {
                    "plan": (
                        f"Your school currently has {active_students} active students "
                        f"which exceeds the {package.name} package limit of "
                        f"{package.maximum_students} students. "
                        f"Please choose a higher package."
                    )
                }
            )


class AdminSubscribeSerializer(serializers.Serializer):
    """
    Superadministrator — subscribe a school.

    Trial subscriptions are free. Any other (paid) subscription requires a
    ``payment_mode`` of ``cash`` or ``virtual``. Virtual payments also need a
    ``payment_reference`` + ``payment_provider`` so the charge can be verified.
    """

    school_id = serializers.UUIDField()
    plan_id = serializers.UUIDField()
    term_id = serializers.UUIDField(required=False, allow_null=True)
    status = serializers.ChoiceField(
        choices=[Subscription.Status.ACTIVE, Subscription.Status.ACTIVE],
        default=Subscription.Status.ACTIVE,
    )
    payment_mode = serializers.ChoiceField(
        choices=SubscriptionPayment.PaymentMode.choices,
        required=False,
        allow_null=True,
    )
    payment_reference = serializers.CharField(required=False, allow_blank=True)
    payment_provider = serializers.ChoiceField(
        choices=["paystack", "stripe", "momo", "cash"],
        required=False,
        allow_blank=True,
    )
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_school_id(self, value):
        from schools.models import School
        school = School.objects.filter(id=value).first()
        if school is None:
            raise serializers.ValidationError("School not found.")
        return school

    def validate_plan_id(self, value):
        package = Package.objects.filter(id=value, is_active=True).first()
        if package is None:
            raise serializers.ValidationError("Package not found or inactive.")
        return package

    def validate_term_id(self, value):
        if value is None:
            return None
        school = self.validated_data.get("school_id")
        if school is None:
            return None
        term = school.terms.filter(id=value).first()
        if term is None:
            raise serializers.ValidationError(
                "Term not found or does not belong to the specified school."
            )
        return term

    def validate(self, attrs):
        attrs["school"] = attrs.pop("school_id")
        attrs["plan"] = attrs.pop("plan_id")
        attrs["term"] = attrs.pop("term_id", None)

        status = attrs.get("status")
        if status != Subscription.Status.ACTIVE:
            payment_mode = attrs.get("payment_mode")
            if not payment_mode:
                raise serializers.ValidationError(
                    {"payment_mode": "Payment mode is required for a paid subscription."}
                )
            if payment_mode == SubscriptionPayment.PaymentMode.VIRTUAL:
                if not attrs.get("payment_reference"):
                    raise serializers.ValidationError(
                        {"payment_reference": "A payment reference is required for virtual payments."}
                    )
                if not attrs.get("payment_provider") or attrs.get("payment_provider") == "cash":
                    raise serializers.ValidationError(
                        {"payment_provider": "A gateway provider is required for virtual payments."}
                    )
        else:
            attrs.pop("payment_reference", None)
            attrs.pop("payment_provider", None)
            attrs.pop("payment_mode", None)

        return attrs