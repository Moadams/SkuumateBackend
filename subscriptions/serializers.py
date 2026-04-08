from rest_framework import serializers
from .models import Plan, Subscription


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "id",
            "name",
            "plan_type",
            "tagline",
            "description",
            "price_per_term",
            "setup_fee",
            "min_students",
            "max_students",
            # Core
            "has_student_records",
            "has_class_subject_setup",
            "has_score_entry",
            "has_report_cards",
            "has_basic_broadsheet",
            "has_fee_billing",
            "has_payment_tracking",
            "has_debtors_list",
            "has_sms_alerts",
            "has_admin_teacher_portal",
            # Advantage+
            "has_advanced_finance",
            "has_income_expense_tracking",
            "has_full_broadsheet",
            "has_term_comparison",
            "has_audit_logs",
            "has_announcements",
            "has_extended_sms",
            "has_student_portal",
            "has_export",
            # Enterprise
            "has_advanced_analytics",
            "has_multi_year_tracking",
            "has_department_access_control",
            "has_custom_report_cards",
            "has_custom_report_formats",
            "has_custom_branding",
            "has_data_migration",
            "has_priority_support",
            "is_active",
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    days_remaining = serializers.IntegerField(read_only=True)
    is_read_only = serializers.BooleanField(read_only=True)
    is_locked = serializers.BooleanField(read_only=True)
    term_name = serializers.CharField(
        source="term.get_name_display", read_only=True
    )

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
            "amount_paid",
            "setup_fee_paid",
            "setup_fee_amount",
            "payment_provider",
            "payment_reference",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class ManualActivationSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField()
    term_id = serializers.UUIDField(required=False)
    amount_paid = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False
    )
    setup_fee_paid = serializers.BooleanField(default=False)
    payment_reference = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_plan_id(self, value):
        from .models import Plan
        try:
            Plan.objects.get(id=value, is_active=True)
        except Plan.DoesNotExist:
            raise serializers.ValidationError("Plan not found.")
        return value

    def validate_term_id(self, value):
        from academics.models import Term
        try:
            Term.objects.get(id=value)
        except Term.DoesNotExist:
            raise serializers.ValidationError("Term not found.")
        return value


class InitiatePaymentSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField()
    term_id = serializers.UUIDField(required=False)
    provider = serializers.ChoiceField(choices=["paystack", "momo"])
    include_setup_fee = serializers.BooleanField(default=False)

    def validate_plan_id(self, value):
        from .models import Plan
        try:
            Plan.objects.get(id=value, is_active=True)
        except Plan.DoesNotExist:
            raise serializers.ValidationError("Plan not found.")
        return value