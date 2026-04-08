from django.core.management.base import BaseCommand
from subscriptions.models import Plan


class Command(BaseCommand):
    help = "Seed SkuuMate subscription plans"

    def handle(self, *args, **kwargs):
        plans = [
            {
                "name": "Lite",
                "plan_type": "lite",
                "tagline": "Control your fees and reports.",
                "description": "Best for small & growing schools. Up to 250 students.",
                "price_per_term": 1000.00,
                "setup_fee": 300.00,
                "min_students": 0,
                "max_students": 250,

                # Core — all True for Lite
                "has_student_records": True,
                "has_class_subject_setup": True,
                "has_score_entry": True,
                "has_report_cards": True,
                "has_basic_broadsheet": True,
                "has_fee_billing": True,
                "has_payment_tracking": True,
                "has_debtors_list": True,
                "has_sms_alerts": True,
                "has_admin_teacher_portal": True,

                # Advantage+ — all False for Lite
                "has_advanced_finance": False,
                "has_income_expense_tracking": False,
                "has_full_broadsheet": False,
                "has_term_comparison": False,
                "has_audit_logs": False,
                "has_announcements": False,
                "has_extended_sms": False,
                "has_student_portal": False,
                "has_export": False,

                # Enterprise — all False for Lite
                "has_advanced_analytics": False,
                "has_multi_year_tracking": False,
                "has_department_access_control": False,
                "has_custom_report_cards": False,
                "has_custom_report_formats": False,
                "has_custom_branding": False,
                "has_data_migration": False,
                "has_priority_support": False,
            },
            {
                "name": "Advantage",
                "plan_type": "advantage",
                "tagline": "Gain financial and operational intelligence.",
                "description": "Best for structured & expanding schools. 251–500 students.",
                "price_per_term": 1800.00,
                "setup_fee": 500.00,
                "min_students": 251,
                "max_students": 500,

                # Core — all True
                "has_student_records": True,
                "has_class_subject_setup": True,
                "has_score_entry": True,
                "has_report_cards": True,
                "has_basic_broadsheet": True,
                "has_fee_billing": True,
                "has_payment_tracking": True,
                "has_debtors_list": True,
                "has_sms_alerts": True,
                "has_admin_teacher_portal": True,

                # Advantage+ — all True
                "has_advanced_finance": True,
                "has_income_expense_tracking": True,
                "has_full_broadsheet": True,
                "has_term_comparison": True,
                "has_audit_logs": True,
                "has_announcements": True,
                "has_extended_sms": True,
                "has_student_portal": True,
                "has_export": True,

                # Enterprise — all False
                "has_advanced_analytics": False,
                "has_multi_year_tracking": False,
                "has_department_access_control": False,
                "has_custom_report_cards": False,
                "has_custom_report_formats": False,
                "has_custom_branding": False,
                "has_data_migration": False,
                "has_priority_support": False,
            },
            {
                "name": "Enterprise",
                "plan_type": "enterprise",
                "tagline": "Run your school like a structured institution.",
                "description": "Best for large, branded, or high-growth schools. 501–1000 students.",
                "price_per_term": 3000.00,
                "setup_fee": 800.00,
                "min_students": 501,
                "max_students": 1000,

                # Core — all True
                "has_student_records": True,
                "has_class_subject_setup": True,
                "has_score_entry": True,
                "has_report_cards": True,
                "has_basic_broadsheet": True,
                "has_fee_billing": True,
                "has_payment_tracking": True,
                "has_debtors_list": True,
                "has_sms_alerts": True,
                "has_admin_teacher_portal": True,

                # Advantage+ — all True
                "has_advanced_finance": True,
                "has_income_expense_tracking": True,
                "has_full_broadsheet": True,
                "has_term_comparison": True,
                "has_audit_logs": True,
                "has_announcements": True,
                "has_extended_sms": True,
                "has_student_portal": True,
                "has_export": True,

                # Enterprise — all True
                "has_advanced_analytics": True,
                "has_multi_year_tracking": True,
                "has_department_access_control": True,
                "has_custom_report_cards": True,
                "has_custom_report_formats": True,
                "has_custom_branding": True,
                "has_data_migration": True,
                "has_priority_support": True,
            },
        ]

        for plan_data in plans:
            plan, created = Plan.objects.update_or_create(
                plan_type=plan_data["plan_type"],
                defaults=plan_data,
            )
            action = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{action}: {plan.name} — "
                    f"GHS {plan.price_per_term}/term "
                    f"(setup: GHS {plan.setup_fee})"
                )
            )