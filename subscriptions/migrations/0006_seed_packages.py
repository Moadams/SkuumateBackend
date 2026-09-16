from django.db import migrations
from django.utils.text import slugify


FEATURE_CATALOG = [
    # ── Core ──────────────────────────────────────────────────────
    ("student_management", "Student Registration & Digital Records", "core"),
    ("class_subject_setup", "Classes, Subjects & Timetable Setup", "core"),
    ("score_entry", "Score Entry", "academics"),
    ("report_cards", "Automated Report Cards", "academics"),
    ("basic_broadsheet", "Basic Broadsheet", "academics"),
    ("fee_billing", "Fee Billing, Payment Tracking & Receipts", "finance"),
    ("debtors_list", "Debtors List & Basic Finance Summary", "finance"),
    ("sms", "SMS Alerts (Attendance & Fee Reminders)", "communication"),
    ("admin_teacher_portal", "Admin & Teacher Portal Access", "access"),
    ("attendance", "Attendance", "core"),
    # ── Advantage ─────────────────────────────────────────────────
    ("advanced_finance", "Advanced Finance Dashboard & Analytics", "finance"),
    ("finance_analytics", "Finance Analytics", "finance"),
    ("income_expense_tracking", "Income, Expense & Revenue Tracking", "finance"),
    ("financial_reports", "Financial Reports", "finance"),
    ("full_broadsheet", "Full Broadsheet & Performance Trends", "academics"),
    ("term_comparison", "Term-to-Term Academic Comparison", "academics"),
    ("export", "Branded Report Exports", "academics"),
    ("activity_logs", "Activity Logs & Role-Based Access", "access"),
    ("announcements", "Announcement Broadcast", "communication"),
    ("extended_sms", "Extended SMS Alerts", "communication"),
    ("student_portal", "Student Portal Access", "access"),
    # ── Enterprise ────────────────────────────────────────────────
    ("advanced_analytics", "Advanced Institutional Analytics", "analytics"),
    ("multi_year_tracking", "Multi-Year Academic & Financial Tracking", "analytics"),
    ("department_access_control", "Hierarchical Admin & Department-Level Access", "access"),
    ("custom_report_cards", "Customized Report Card Design", "academics"),
    ("custom_academic_reports", "Custom Academic Reports", "analytics"),
    ("custom_financial_reports", "Custom Financial Reports", "finance"),
    ("school_branding", "School Branding Across the System", "branding"),
    # ── Future-ready (created now, not assigned to any package) ───
    ("finance", "Finance", "finance"),
    ("parent_portal", "Parent Portal Access", "access"),
    ("ges", "GES Reports", "curriculum"),
    ("eyfs", "EYFS", "curriculum"),
    ("montessori", "Montessori", "curriculum"),
]


# Authoritative configuration for the three standard tiers. This mirrors
# the business proposal and is applied to existing standard-tier rows as
# well as fresh databases.
PACKAGE_CONFIG = {
    "lite": {
        "name": "Lite",
        "tagline": "Control your fees and reports.",
        "description": "Best for small & growing schools. Up to 250 students.",
        "price": "1000.00",
        "setup_fee": "300.00",
        "minimum_students": 0,
        "maximum_students": 250,
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
        "display_order": 2,
        "features": [
            "student_management", "class_subject_setup", "score_entry",
            "report_cards", "basic_broadsheet", "fee_billing",
            "debtors_list", "sms", "admin_teacher_portal", "attendance",
            "advanced_finance", "finance_analytics",
            "income_expense_tracking", "financial_reports",
            "full_broadsheet", "term_comparison", "export",
            "activity_logs", "announcements", "extended_sms",
            "student_portal",
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
            "school_branding",
        ],
        "limits": [
            ("max_students", "Maximum Students", 1000),
            ("monthly_sms", "Monthly SMS", 15000),
            ("storage_mb", "Storage (MB)", 51200),
        ],
    },
}


# Legacy boolean columns → stable feature codes (only used to rebuild a
# custom/non-standard package that predates the entitlement model).
HAS_FIELD_TO_FEATURE = {
    "has_student_records": "student_management",
    "has_class_subject_setup": "class_subject_setup",
    "has_score_entry": "score_entry",
    "has_report_cards": "report_cards",
    "has_basic_broadsheet": "basic_broadsheet",
    "has_fee_billing": "fee_billing",
    "has_payment_tracking": "fee_billing",
    "has_debtors_list": "debtors_list",
    "has_sms_alerts": "sms",
    "has_admin_teacher_portal": "admin_teacher_portal",
    "has_attendance": "attendance",
    "has_advanced_finance": "advanced_finance",
    "has_income_expense_tracking": "income_expense_tracking",
    "has_full_broadsheet": "full_broadsheet",
    "has_term_comparison": "term_comparison",
    "has_audit_logs": "activity_logs",
    "has_announcements": "announcements",
    "has_extended_sms": "extended_sms",
    "has_student_portal": "student_portal",
    "has_export": "export",
    "has_advanced_analytics": "advanced_analytics",
    "has_multi_year_tracking": "multi_year_tracking",
    "has_department_access_control": "department_access_control",
    "has_custom_report_cards": "custom_report_cards",
    "has_custom_report_formats": "custom_academic_reports",
    "has_custom_branding": "school_branding",
    # has_data_migration / has_priority_support are commercial benefits,
    # not application feature gates — deliberately not mapped.
}


def seed_feature_catalog(apps):
    Feature = apps.get_model("subscriptions", "Feature")
    for code, name, category in FEATURE_CATALOG:
        Feature.objects.get_or_create(
            code=code,
            defaults={"name": name, "category": category, "is_active": True},
        )


def apply_package_config(apps, package, config):
    Feature = apps.get_model("subscriptions", "Feature")
    PackageFeature = apps.get_model("subscriptions", "PackageFeature")
    PackageLimit = apps.get_model("subscriptions", "PackageLimit")

    for code in config["features"]:
        feature = Feature.objects.filter(code=code).first()
        if feature is not None:
            PackageFeature.objects.get_or_create(
                package=package,
                feature=feature,
                defaults={"is_enabled": True},
            )

    for key, name, value in config["limits"]:
        PackageLimit.objects.get_or_create(
            package=package,
            key=key,
            defaults={"name": name, "value": value, "description": ""},
        )


def rebuild_custom_package_from_flags(apps, package):
    """Reconstruct entitlements for a non-standard package from legacy has_* flags."""
    Feature = apps.get_model("subscriptions", "Feature")
    PackageFeature = apps.get_model("subscriptions", "PackageFeature")

    for field_name, feature_code in HAS_FIELD_TO_FEATURE.items():
        if not getattr(package, field_name, False):
            continue
        feature = Feature.objects.filter(code=feature_code).first()
        if feature is not None:
            PackageFeature.objects.get_or_create(
                package=package,
                feature=feature,
                defaults={"is_enabled": True},
            )


def backfill_package_metadata(package):
    package.currency = package.currency or "GHS"
    package.billing_period = package.billing_period or "TERM"
    package.is_public = True
    if not package.code:
        candidate = slugify(package.name or package.plan_type or "").replace("-", "_")
        package.code = candidate or str(package.id)
    package.save()


def forward(apps, schema_editor):
    Package = apps.get_model("subscriptions", "Package")

    seed_feature_catalog(apps)

    packages = list(Package.objects.all().order_by("id"))
    if not packages:
        # Fresh database — seed the three default packages.
        for code, config in PACKAGE_CONFIG.items():
            package = Package.objects.create(
                name=config["name"],
                code=code,
                plan_type=code,
                tagline=config["tagline"],
                description=config["description"],
                price=config["price"],
                setup_fee=config["setup_fee"],
                billing_period="TERM",
                currency="GHS",
                minimum_students=config["minimum_students"],
                maximum_students=config["maximum_students"],
                is_active=True,
                is_public=True,
                display_order=config["display_order"],
            )
            apply_package_config(apps, package, config)
        return

    # Existing database — backfill metadata and rebuild entitlements.
    by_price = sorted(packages, key=lambda p: (p.price or 0, p.name or ""))
    for index, package in enumerate(by_price, start=1):
        backfill_package_metadata(package)
        package.display_order = index
        package.save(update_fields=["display_order"])

        config = PACKAGE_CONFIG.get(package.plan_type)
        if config is not None:
            apply_package_config(apps, package, config)
        else:
            rebuild_custom_package_from_flags(apps, package)


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0005_package_module'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]