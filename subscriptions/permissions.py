from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from .services.packages import package_has_feature
from .utils import get_active_subscription


class IsPlatformSuperAdmin(BasePermission):
    """
    Platform-level staff gate for Package/Feature management.

    Accepts Django superusers as well as users with the legacy
    ``superadmin`` role so package administration works for both
    existing platform admins and ``createsuperuser`` accounts.
    """
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and (
                request.user.is_superuser
                or (getattr(request.user, "role", "") == "superadmin" and request.user.school_id is None)
            )
        )


class SubscriptionPermission(BasePermission):
    """
    Base subscription-aware permission.
    Enforces lockout and grace period read-only across all views.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        school = request.user.school
        if not school:
            return True  # superusers bypass

        subscription = get_active_subscription(school)

        if not subscription:
            raise PermissionDenied(
                "No active subscription found. "
                "Please contact support to activate your account."
            )

        if subscription.is_locked:
            raise PermissionDenied(
                "Your subscription has expired and your account is locked. "
                "Please renew your subscription to continue."
            )

        if subscription.is_read_only and request.method not in (
            "GET", "HEAD", "OPTIONS"
        ):
            raise PermissionDenied(
                f"Your account is in the grace period "
                f"({subscription.days_remaining} days remaining). "
                f"Please renew to make changes."
            )

        return True


def _make_feature_permission(feature_code: str, message: str):
    """Factory that generates a feature-gated permission class.

    The generated class records the ``feature_code`` it enforces so a view's
    ``permission_classes`` can be introspected (see the wiring tests) and a
    traceback names the feature rather than a generic ``FeaturePermission``.
    """
    class FeaturePermission(SubscriptionPermission):
        enforced_feature_code = feature_code
        denial_message = message

        def has_permission(self, request, view):
            if not super().has_permission(request, view):
                return False

            school = getattr(request.user, "school", None)
            if school is None:
                return True  # platform superusers bypass package entitlements

            subscription = get_active_subscription(school)
            if not package_has_feature(
                subscription.plan if subscription else None, feature_code
            ):
                raise PermissionDenied(message)
            return True

    FeaturePermission.__name__ = "Has" + "".join(
        part.capitalize() for part in feature_code.split("_")
    )
    FeaturePermission.__qualname__ = FeaturePermission.__name__
    return FeaturePermission


# ── Generated permission classes ──────────────────────────────────
# These evaluate against a package's PackageFeature entitlements using
# stable feature codes (see subscriptions/services/packages.py).

HasExportAccess = _make_feature_permission(
    "export",
    "Export is not available on your current package. Upgrade to Advantage or higher.",
)

HasAuditLogAccess = _make_feature_permission(
    "activity_logs",
    "Activity logs are not available on your current package. Upgrade to Advantage or higher.",
)

HasAdvancedFinance = _make_feature_permission(
    "advanced_finance",
    "Advanced finance features require the Advantage package or higher.",
)

HasFinanceAnalytics = _make_feature_permission(
    "finance_analytics",
    "Finance analytics require the Advantage package or higher.",
)

HasIncomeExpenseTracking = _make_feature_permission(
    "income_expense_tracking",
    "Income and expense tracking requires the Advantage package or higher.",
)

HasFinancialReports = _make_feature_permission(
    "financial_reports",
    "Financial reports require the Advantage package or higher.",
)

HasAnnouncementAccess = _make_feature_permission(
    "announcements",
    "Announcements require the Advantage package or higher.",
)

HasStudentPortalAccess = _make_feature_permission(
    "student_portal",
    "Student portal access requires the Advantage package or higher.",
)

HasAdvancedAnalytics = _make_feature_permission(
    "advanced_analytics",
    "Advanced analytics require the Enterprise package.",
)

HasCustomBranding = _make_feature_permission(
    "school_branding",
    "School branding requires the Enterprise package.",
)

HasCustomReportCards = _make_feature_permission(
    "custom_report_cards",
    "Custom report card design requires the Enterprise package.",
)

HasSmsAlerts = _make_feature_permission(
    "sms",
    "SMS alerts are not available on your current package.",
)

HasExtendedSms = _make_feature_permission(
    "extended_sms",
    "Extended SMS alerts require the Advantage package or higher.",
)

HasFullBroadsheet = _make_feature_permission(
    "full_broadsheet",
    "Full broadsheet generation requires the Advantage package or higher.",
)

HasTermComparison = _make_feature_permission(
    "term_comparison",
    "Term-to-term comparison requires the Advantage package or higher.",
)

HasAttendanceModule = _make_feature_permission(
    "attendance",
    "Attendance features are not available on your current package.",
)
