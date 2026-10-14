"""Subscription helpers for cross-app feature gates.

Deprecated lifecycle functions (``create_trial_subscription``, ``record_payment``,
``activate_subscription``) are kept as thin wrappers over the service layer so
existing callers keep working while all state changes go through services.
"""
from django.utils import timezone
from datetime import timedelta
from rest_framework.exceptions import PermissionDenied

from .services.packages import get_package_limit, package_has_feature
from .services.subscriptions import SubscriptionService


def get_active_subscription(school):
    """Return the school's current (live) subscription, if any."""
    return SubscriptionService.get_current(school) if school else None


def check_feature(school, feature_code: str):
    """Raise PermissionDenied if the school's package lacks ``feature_code``."""
    subscription = get_active_subscription(school)

    if not subscription:
        raise PermissionDenied("No active subscription found.")

    if subscription.status__in [subscription.Status.LOCKED, subscription.Status.EXPIRED]:
        raise PermissionDenied(
            "Your subscription has expired. Please renew to continue."
        )

    if not package_has_feature(subscription.plan, feature_code):
        raise PermissionDenied(
            f"This feature is not included in your current package. "
            f"Please upgrade to access it."
        )


# resource -> (PackageLimit key, fallback Package column, usage counter).
# An unrecognised resource is a no-op rather than a silent pass of a known one.
LIMIT_RULES = {
    "students": (
        "max_students",
        "maximum_students",
        lambda school: school.students.filter(status="active").count(),
    ),
}


def check_limit(school, resource: str):
    """Raise PermissionDenied if the school has reached a usage limit.

    ``PackageLimit`` rows are the source of truth. The duplicated
    ``Package.maximum_students`` column is a pricing/display field and is only
    consulted for packages created without an explicit limit row.
    """
    subscription = get_active_subscription(school)

    if not subscription:
        raise PermissionDenied("No active subscription found.")

    if subscription.status__in [subscription.Status.LOCKED, subscription.Status.EXPIRED]:
        raise PermissionDenied(
            "Your subscription has expired. Please renew to continue."
        )

    rule = LIMIT_RULES.get(resource)
    if rule is None or subscription.plan is None:
        return

    limit_key, fallback_attr, count_fn = rule
    limit = get_package_limit(subscription.plan, limit_key)
    if limit is None:
        limit = getattr(subscription.plan, fallback_attr, None)

    if limit is None:
        return  # unlimited

    current_count = count_fn(school)
    if current_count >= limit:
        raise PermissionDenied(
            f"You have reached the {resource} limit ({limit}) "
            f"for your {subscription.plan.name} package. "
            f"Please upgrade to add more."
        )


def create_trial_subscription(school, plan):
    """Called on school signup — starts a trial on the given package."""
    return SubscriptionService.start_trial(
        school=school,
        plan=plan,
        activated_by=None,
    )


def record_payment(subscription, amount, provider="manual",
                   payment_reference="", status="successful"):
    """Persist a payment record against a subscription."""
    from .models import SubscriptionPayment
    from .services.payments import PaymentService

    return PaymentService.record_successful_payment(
        subscription=subscription,
        school=subscription.school if subscription.school_id else None,
        plan=subscription.plan,
        term=subscription.term,
        amount=amount,
        provider=provider or "manual",
        reference=payment_reference,
        payment_mode=SubscriptionPayment.PaymentMode.VIRTUAL,
    )


def activate_subscription(school, plan, term=None, activated_by=None,
                           payment_reference="", payment_provider="manual",
                           is_paid=True, notes=""):
    """
    Activates a term-based subscription for a school.
    Cancels any existing active/trial/grace subscription first.
    End date defaults to term end date if term is provided,
    otherwise one standard term (~ACTIVE_DAYS).
    """
    subscription = SubscriptionService.activate(
        school=school,
        plan=plan,
        term=term,
        activated_by=activated_by,
        is_paid=is_paid,
        notes=notes,
    )
    if is_paid and plan:
        record_payment(
            subscription,
            amount=plan.price,
            provider=payment_provider or "manual",
            payment_reference=payment_reference,
        )
    return subscription