"""Coupon input validation and API representations."""

import re

from django.utils import timezone
from rest_framework import serializers

from subscriptions.models import Coupon, Package


class CouponSerializer(serializers.ModelSerializer):
    code = serializers.CharField(max_length=20)
    target_plan_id = serializers.PrimaryKeyRelatedField(
        source="target_plan",
        queryset=Package.objects.all(),
        required=False,
        allow_null=True,
    )
    target_plan = serializers.SerializerMethodField()
    status = serializers.ChoiceField(choices=Coupon.Status.choices, required=False)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Coupon
        fields = (
            "id",
            "code",
            "description",
            "discount_type",
            "discount_value",
            "duration",
            "target",
            "target_plan_id",
            "target_plan",
            "max_usage",
            "usage_count",
            "expiry_date",
            "status",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "usage_count",
            "created_by",
            "created_at",
            "updated_at",
        )

    def get_target_plan(self, obj):
        return (
            {"id": str(obj.target_plan_id), "name": obj.target_plan.name}
            if obj.target_plan_id
            else None
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["status"] = instance.effective_status
        return data

    def validate_code(self, value):
        value = value.upper()
        if not re.fullmatch(r"[A-Z0-9]{1,20}", value):
            raise serializers.ValidationError(
                "Use only letters and numbers (maximum 20 characters)."
            )
        existing = Coupon.objects.filter(code__iexact=value)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError("A coupon with this code already exists.")
        return value

    def validate_expiry_date(self, value):
        if value is not None and value <= timezone.now():
            raise serializers.ValidationError("Expiry date must be a future date.")
        return value

    def validate_max_usage(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Usage limit must be a positive integer.")
        return value

    def validate(self, attrs):
        def current(key):
            return attrs.get(key, getattr(self.instance, key, None))

        value = current("discount_value")
        if value is not None and (
            value <= 0
            or (current("discount_type") == "percentage" and not 1 <= value <= 100)
        ):
            raise serializers.ValidationError(
                {
                    "discount_value": "Percentage must be between 1 and 100; fixed discounts must be positive."
                }
            )
        if current("target") == "specific_plan" and not current("target_plan"):
            raise serializers.ValidationError(
                {"target_plan_id": "A valid plan is required."}
            )
        if current("target") == "all":
            attrs["target_plan"] = None
        return attrs


class CouponValidationSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20)
    plan_id = serializers.PrimaryKeyRelatedField(
        queryset=Package.objects.filter(is_active=True)
    )
