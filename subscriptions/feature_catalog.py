"""The application's own feature registry.

Every feature anywhere in SkuuMate is declared here **once** — the same way
Django auto-creates permissions from ``Meta.permissions``. ``sync_feature_catalog``
(``subscriptions/sync``) upserts these declarations into the ``Feature`` table
after every ``migrate`` and via ``seed_packages``, so the super administrator
never has to create standard features one by one in the admin UI.

Adding a new platform capability = adding one ``FeatureSpec`` line here + the
enforcement point (``check_feature``/``HasFeature``) in the app that uses it.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureSpec:
    code: str
    name: str
    category: str
    description: str = ""


FEATURES = (
    # ── Core ──────────────────────────────────────────────────────
    FeatureSpec("student_management", "Student Registration & Digital Records",
                "core", "Register students and keep their digital records."),
    FeatureSpec("class_subject_setup", "Classes, Subjects & Timetable Setup",
                "core", "Set up classes, subjects and timetables."),
    FeatureSpec("score_entry", "Score Entry", "academics",
                "Enter and record student scores."),
    FeatureSpec("report_cards", "Automated Report Cards", "academics",
                "Generate automated report cards."),
    FeatureSpec("basic_broadsheet", "Basic Broadsheet", "academics",
                "Basic class performance broadsheet."),
    FeatureSpec("fee_billing", "Fee Billing, Payment Tracking & Receipts",
                "finance", "Invoice fees, track payments and issue receipts."),
    FeatureSpec("debtors_list", "Debtors List & Basic Finance Summary",
                "finance", "List debtors and view basic finance summaries."),
    FeatureSpec("sms", "SMS Alerts (Attendance & Fee Reminders)",
                "communication", "Send SMS alerts for attendance and fee reminders."),
    FeatureSpec("admin_teacher_portal", "Admin & Teacher Portal Access",
                "access", "Access to the admin and teacher portal."),
    FeatureSpec("attendance", "Attendance", "core",
                "Take and manage class attendance."),
    # ── Advantage ─────────────────────────────────────────────────
    FeatureSpec("advanced_finance", "Advanced Finance Dashboard & Analytics",
                "finance", "Advanced finance dashboard and analytics."),
    FeatureSpec("finance_analytics", "Finance Analytics", "finance",
                "Deeper financial analytics."),
    FeatureSpec("income_expense_tracking", "Income, Expense & Revenue Tracking",
                "finance", "Track income, expenses and revenue."),
    FeatureSpec("financial_reports", "Financial Reports", "finance",
                "Generate financial reports."),
    FeatureSpec("full_broadsheet", "Full Broadsheet & Performance Trends",
                "academics", "Full broadsheet with performance trends."),
    FeatureSpec("term_comparison", "Term-to-Term Academic Comparison",
                "academics", "Compare academic performance across terms."),
    FeatureSpec("export", "Branded Report Exports", "academics",
                "Export branded reports."),
    FeatureSpec("activity_logs", "Activity Logs & Role-Based Access",
                "access", "System activity logs and role-based access."),
    FeatureSpec("announcements", "Announcement Broadcast", "communication",
                "Broadcast announcements to the school."),
    FeatureSpec("extended_sms", "Extended SMS Alerts", "communication",
                "Extended SMS alert quota and channels."),
    FeatureSpec("student_portal", "Student Portal Access", "access",
                "Give students access to the portal."),
    # ── Enterprise ────────────────────────────────────────────────
    FeatureSpec("advanced_analytics", "Advanced Institutional Analytics",
                "analytics", "Advanced cross-school analytics."),
    FeatureSpec("multi_year_tracking", "Multi-Year Academic & Financial Tracking",
                "analytics", "Track academic and financial data across years."),
    FeatureSpec("department_access_control", "Hierarchical Admin & Department-Level Access",
                "access", "Fine-grained admin and department-level access."),
    FeatureSpec("custom_report_cards", "Customized Report Card Design",
                "academics", "Design custom report card layouts."),
    FeatureSpec("custom_academic_reports", "Custom Academic Reports",
                "analytics", "Build custom academic reports."),
    FeatureSpec("custom_financial_reports", "Custom Financial Reports",
                "finance", "Build custom financial reports."),
    FeatureSpec("school_branding", "School Branding Across the System",
                "branding", "Apply the school's branding across the system."),
    # ── Enterprise service deliverables ──────────────────────────
    # Display and entitlement only: these are delivered by a human, so nothing
    # in the codebase gates on them. They exist so the sales page and the
    # school's plan record show what the tier includes.
    FeatureSpec("onboarding_support", "Data Migration & Dedicated Onboarding",
                "service", "Data migration of existing records plus dedicated onboarding sessions."),
    FeatureSpec("priority_support", "Priority SLA Support & Operational Reviews",
                "service", "Priority response SLA plus scheduled operational review sessions."),
    # ── Future-ready (created now, not assigned to any package) ───
    FeatureSpec("finance", "Finance", "finance", "Finance module."),
    FeatureSpec("parent_portal", "Parent Portal Access", "access",
                "Give parents access to the portal."),
    FeatureSpec("ges", "GES Reports", "curriculum", "GES reports."),
    FeatureSpec("eyfs", "EYFS", "curriculum", "EYFS support."),
    FeatureSpec("montessori", "Montessori", "curriculum", "Montessori support."),
)


def declared_feature_codes():
    return {spec.code for spec in FEATURES}