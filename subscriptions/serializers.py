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


class ManualActivationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = [
            "school",
            "plan",
            "status",
            "term",
            "amount_paid",
            "setup_fee_paid",
            "setup_fee_amount",
            "payment_reference",
            "payment_provider",
            "notes"
        ]

    def validate(self, attrs):
        plan = attrs.get("plan_id")
        school = attrs.get("school_id")
        term = attrs.get("term_id")

        # Prevent a school from having multiple free trial subscriptions
        status = attrs.get("status", Subscription.Status.TRIAL)
        if status == Subscription.Status.TRIAL:
            if school.subscriptions.filter(status=Subscription.Status.TRIAL).exists():
                raise serializers.ValidationError("This school already has a free trial subscription.")
        
        # Prevent activating a subscription for an inactive plan or mismatched term/school
        if not plan.is_active:
            raise serializers.ValidationError("Selected plan is not active.")

        if term.school != school:
            raise serializers.ValidationError("Term does not belong to the specified school.")

        return attrs
    
    def create(self, validated_data):
        subscription = Subscription.objects.create(**validated_data)
        subscription.activate(activated_by=self.context["request"].user)
        return subscription
    

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
    amount_paid = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
    )

    def validate_plan_id(self, value):
        try:
            plan = Plan.objects.get(id=value, is_active=True)
        except Plan.DoesNotExist:
            raise serializers.ValidationError("Plan not found or inactive.")
        return plan

    def validate_term_id(self, value):
        from academics.models import Term
        school = self.context["school"]
        try:
            term = Term.objects.get(id=value, school=school)
        except Term.DoesNotExist:
            raise serializers.ValidationError(
                "Term not found or does not belong to this school."
            )
        return term

    def validate(self, attrs):
        plan = attrs.get("plan_id")  # already resolved to Plan instance
        school = self.context["school"]

        # Rename keys to resolved instances for the view
        attrs["plan"] = attrs.pop("plan_id")
        if "term_id" in attrs:
            attrs["term"] = attrs.pop("term_id")

        # Validate student count against plan limits
        if plan.max_students is not None:
            current_students = school.students.filter(
                status="active"
            ).count()
            if current_students > plan.max_students:
                raise serializers.ValidationError({
                    "plan_id": (
                        f"Your school currently has {current_students} active students "
                        f"which exceeds the {plan.name} plan limit of "
                        f"{plan.max_students} students. "
                        f"Please choose a higher plan."
                    )
                })

        return attrs