from rest_framework import serializers

from .models import (
    Feature,
    Package,
    Subscription,
    SubscriptionPayment,
)
from .services.packages import PackageService


class FeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = [
            "id",
            "name",
            "code",
            "description",
            "category",
            "is_active",
            "created_at",
            "updated_at",
        ]
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
    """One entitlement row used for both read and write payloads.

    Write payloads send ``code`` + ``enabled``; responses additionally
    include the feature ``name`` (filled by PackageSerializer).
    """
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
    """Super administrator package payload with nested entitlements.

    ``features`` accepts ``[{code, enabled}, ...]`` and ``limits`` accepts
    ``[{key, name, value, description}, ...]`` on create/update. Responses
    include the resolved configuration for convenience.
    """
    features = PackageFeatureAssignmentSerializer(many=True, required=False, write_only=True)
    limits = PackageLimitAssignmentSerializer(many=True, required=False, write_only=True)

    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    setup_fee = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)

    class Meta:
        model = Package
        fields = [
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
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "code": {"required": True},
            "billing_period": {"required": True},
        }

    def validate(self, attrs):
        minimum = attrs.get("minimum_students", getattr(self.instance, "minimum_students", 0))
        maximum = attrs.get("maximum_students", getattr(self.instance, "maximum_students", None))
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
            for row in instance.package_features
            .select_related("feature")
            .order_by("feature__category", "feature__name")
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


class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPayment
        fields = [
            "id",
            "amount",
            "payment_reference",
            "provider",
            "status",
            "created_at",
        ]
        read_only_fields = fields


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PackageSerializer(read_only=True)
    days_remaining = serializers.IntegerField(read_only=True)
    is_read_only = serializers.BooleanField(read_only=True)
    is_locked = serializers.BooleanField(read_only=True)
    term_name = serializers.CharField(
        source="term.get_name_display", read_only=True
    )
    payments = SubscriptionPaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan",
            "status",
            "term",
            "term_name",
            "start_date",
            "end_date",
            "grace_end_date",
            "days_remaining",
            "is_read_only",
            "is_locked",
            "is_paid",
            "payments",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class ManualActivationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = [
            "school",
            "plan",
            "status",
            "term",
            "is_paid",
            "notes"
        ]

    def validate(self, attrs):
        plan = attrs.get("plan")
        school = attrs.get("school")
        term = attrs.get("term")

        # Prevent a school from having multiple free trial subscriptions
        status = attrs.get("status", Subscription.Status.TRIAL)
        if status == Subscription.Status.TRIAL:
            if school and school.subscriptions.filter(status=Subscription.Status.TRIAL).exists():
                raise serializers.ValidationError("This school already has a free trial subscription.")

        # Prevent activating a subscription for an inactive plan or mismatched term/school
        if plan is not None and not plan.is_active:
            raise serializers.ValidationError("Selected package is not active.")

        if term is not None and school is not None and term.school_id != school.id:
            raise serializers.ValidationError("Term does not belong to the specified school.")

        return attrs

    def create(self, validated_data):
        subscription = Subscription.objects.create(
            activated_by=self.context["request"].user,
            **validated_data,
        )
        subscription.activate
        return subscription


class InitiatePaymentSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField()
    term_id = serializers.UUIDField(required=False)
    provider = serializers.ChoiceField(choices=["paystack", "momo"])
    include_setup_fee = serializers.BooleanField(default=False)

    def validate_plan_id(self, value):
        from .models import Package
        try:
            Package.objects.get(id=value, is_active=True)
        except Package.DoesNotExist:
            raise serializers.ValidationError("Package not found.")
        return value


class SubscribeSchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = [
            "school",
            "plan",
            "status",
            "term"
        ]

    def validate_status(self, value):
        if value not in [Subscription.Status.TRIAL, Subscription.Status.ACTIVE]:
            raise serializers.ValidationError("Status must be either 'trial' or 'active'.")
        return value


class SubscribeToPlanSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField()
    term_id = serializers.UUIDField(required=False)
    payment_reference = serializers.CharField(required=False, allow_blank=True)
    payment_provider = serializers.ChoiceField(
        choices=["paystack", "momo", "manual", "trial"],
        required=False,
        allow_blank=True,
    )

    def validate_plan_id(self, value):
        package = Package.objects.filter(id=value, is_active=True).first()
        if package is None:
            raise serializers.ValidationError("Package not found or inactive.")
        return package

    def validate_term_id(self, value):
        from academics.models import Term
        school = self.context["school"]
        term = Term.objects.filter(id=value, school=school).first()
        if term is None:
            raise serializers.ValidationError(
                "Term not found or does not belong to this school."
            )
        return term

    def validate(self, attrs):
        package = attrs.get("plan_id")  # already resolved to a Package instance
        school = self.context["school"]

        # Rename keys to resolved instances for the view
        attrs["plan"] = attrs.pop("plan_id")
        if "term_id" in attrs:
            attrs["term"] = attrs.pop("term_id")

        # Validate student count against the package pricing range
        if package is not None and package.maximum_students is not None:
            current_students = school.students.filter(
                status="active"
            ).count()
            if current_students > package.maximum_students:
                raise serializers.ValidationError({
                    "plan_id": (
                        f"Your school currently has {current_students} active students "
                        f"which exceeds the {package.name} package limit of "
                        f"{package.maximum_students} students. "
                        f"Please choose a higher package."
                    )
                })

        return attrs