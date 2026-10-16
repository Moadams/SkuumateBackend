"""Default SkuuMate package configuration.

Feature declarations live in ``subscriptions.feature_catalog`` (synced
automatically after every ``migrate``); this module only holds package
pricing and entitlements, used by the ``seed_packages`` (and legacy
``seed_plans``) management commands. Application logic never references
these names/codes to make feature or pricing decisions.
"""
from __future__ import annotations

from subscriptions.models import Package
from subscriptions.sync import sync_feature_catalog


# package code → entitlements (feature codes) and usage limits (key/name/value)
PACKAGE_CONFIG = {
    "lite": {
        "name": "Lite",
        "tagline": "Control your fees and reports.",
        "description": "Best for small & growing schools. Up to 250 students.",
        "price": "1000.00",
        "setup_fee": "300.00",
        "minimum_students": 0,
        "maximum_students": 250,
        "plan_type": "lite",
        "display_order": 1,
        "features": [
            "student_management", "class_subject_setup", "score_entry",
            "report_cards", "basic_broadsheet", "fee_billing",
            "debtors_list", "sms", "admin_teacher_portal", "attendance",
        ],
        "limits": [
            ("max_students", "Maximum Students", 250),
            ("max_staff", "Maximum Staff", 50),
            ("monthly_sms", "Monthly SMS", 500),
            ("storage_mb", "Storage (MB)", 2048),
        ],
    },
    "advantage": {
        "name": "Advantage",
        "tagline": "Gain financial and operational intelligence.",
        "description": "Best for structured & expanding schools. 251–500 students.",
        "price": "1800.00",
        "setup_fee": "500.00",
        "minimum_students": 251,
        "maximum_students": 500,
        "plan_type": "advantage",
        "display_order": 2,
        "features": [
            "student_management", "class_subject_setup", "score_entry",
            "report_cards", "basic_broadsheet", "fee_billing",
            "debtors_list", "sms", "admin_teacher_portal", "attendance",
            "advanced_finance", "finance_analytics",
            "income_expense_tracking", "financial_reports",
            "full_broadsheet", "term_comparison", "export",
            "activity_logs", "announcements", "extended_sms",
            "student_portal", "id_cards",
        ],
        "limits": [
            ("max_students", "Maximum Students", 500),
            ("max_staff", "Maximum Staff", 200),
            ("monthly_sms", "Monthly SMS", 5000),
            ("storage_mb", "Storage (MB)", 10240),
        ],
    },
    "enterprise": {
        "name": "Enterprise",
        "tagline": "Run your school like a structured institution.",
        "description": "Best for large, branded, or high-growth schools. 501–1000 students.",
        "price": "3000.00",
        "setup_fee": "800.00",
        "minimum_students": 501,
        "maximum_students": 1000,
        "plan_type": "enterprise",
        "display_order": 3,
        "features": [
            "student_management", "class_subject_setup", "score_entry",
            "report_cards", "basic_broadsheet", "fee_billing",
            "debtors_list", "sms", "admin_teacher_portal", "attendance",
            "advanced_finance", "finance_analytics",
            "income_expense_tracking", "financial_reports",
            "full_broadsheet", "term_comparison", "export",
            "activity_logs", "announcements", "extended_sms",
            "student_portal",
            "advanced_analytics", "multi_year_tracking",
            "department_access_control", "custom_report_cards",
            "custom_academic_reports", "custom_financial_reports",
            "school_branding", "id_cards",
            "onboarding_support", "priority_support",
        ],
        "limits": [
            ("max_students", "Maximum Students", 1000),
            ("monthly_sms", "Monthly SMS", 15000),
            ("storage_mb", "Storage (MB)", 51200),
        ],
    },
}


def ensure_feature_catalog():
    """Sync the platform feature registry from the app's declarations."""
    return sync_feature_catalog(verbosity=0)["created"]


def seed_default_packages(reset_entitlements=True):
    """Create/reconcile the three default packages (idempotent)."""
    ensure_feature_catalog()

    created_count = 0
    for package_code, config in PACKAGE_CONFIG.items():
        package, created = Package.objects.update_or_create(
            code=package_code,
            defaults={
                "name": config["name"],
                "tagline": config["tagline"],
                "description": config["description"],
                "price": config["price"],
                "setup_fee": config["setup_fee"],
                "billing_period": Package.BillingPeriod.TERM,
                "currency": "GHS",
                "minimum_students": config["minimum_students"],
                "maximum_students": config["maximum_students"],
                "plan_type": config["plan_type"],
                "is_active": True,
                "is_public": True,
                "display_order": config["display_order"],
            },
        )
        created_count += int(created)

        if reset_entitlements or created:
            assignments = [{"code": c, "enabled": True} for c in config["features"]]
            limits = [
                {
                    "key": key,
                    "name": name,
                    "value": value,
                    "description": "",
                }
                for key, name, value in config["limits"]
            ]
            _apply_seed_config(package, assignments, limits)

    return created_count


def _apply_seed_config(package, assignments, limits):
    from subscriptions.services.packages import PackageService
    PackageService.apply_features(package, assignments)
    PackageService.apply_limits(package, limits)