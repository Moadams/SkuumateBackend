from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from .utils import get_active_subscription


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


def _make_feature_permission(feature_flag: str, message: str):
    """Factory that generates a feature permission class."""
    class FeaturePermission(SubscriptionPermission):
        def has_permission(self, request, view):
            super().has_permission(request, view)
            sub = get_active_subscription(request.user.school)
            if not getattr(sub.plan, feature_flag, False):
                raise PermissionDenied(message)
            return True
    return FeaturePermission


# ── Generated permission classes ─────────────────────────────────

HasExportAccess = _make_feature_permission(
    "has_export",
    "Export is not available on your current plan. Upgrade to Advantage or higher.",
)

HasAuditLogAccess = _make_feature_permission(
    "has_audit_logs",
    "Audit logs are not available on your current plan. Upgrade to Advantage or higher.",
)

HasAdvancedFinance = _make_feature_permission(
    "has_advanced_finance",
    "Advanced finance features require the Advantage plan or higher.",
)

HasAnnouncementAccess = _make_feature_permission(
    "has_announcements",
    "Announcements require the Advantage plan or higher.",
)

HasStudentPortalAccess = _make_feature_permission(
    "has_student_portal",
    "Student portal access requires the Advantage plan or higher.",
)

HasAdvancedAnalytics = _make_feature_permission(
    "has_advanced_analytics",
    "Advanced analytics require the Enterprise plan.",
)

HasCustomBranding = _make_feature_permission(
    "has_custom_branding",
    "Custom branding requires the Enterprise plan.",
)

HasCustomReportCards = _make_feature_permission(
    "has_custom_report_cards",
    "Custom report card design requires the Enterprise plan.",
)

HasSmsAlerts = _make_feature_permission(
    "has_sms_alerts",
    "SMS alerts are not available on your current plan.",
)

HasExtendedSms = _make_feature_permission(
    "has_extended_sms",
    "Extended SMS alerts require the Advantage plan or higher.",
)

HasFullBroadsheet = _make_feature_permission(
    "has_full_broadsheet",
    "Full broadsheet generation requires the Advantage plan or higher.",
)

HasTermComparison = _make_feature_permission(
    "has_term_comparison",
    "Term-to-term comparison requires the Advantage plan or higher.",
)