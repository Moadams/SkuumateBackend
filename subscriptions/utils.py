from django.utils import timezone
from datetime import timedelta
from rest_framework.exceptions import PermissionDenied


def get_active_subscription(school):
    subscription = (
        school.subscriptions
        .select_related("plan")
        .order_by("-start_date")
        .first()
    )
    if subscription:
        subscription.sync_status()
    return subscription


def check_feature(school, feature: str):
    subscription = get_active_subscription(school)

    if not subscription:
        raise PermissionDenied("No active subscription found.")

    if subscription.is_locked:
        raise PermissionDenied(
            "Your subscription has expired. Please renew to continue."
        )

    if subscription.is_read_only:
        raise PermissionDenied(
            f"Your account is in the grace period "
            f"({subscription.days_remaining} days left). "
            f"Please renew to make changes."
        )

    if not getattr(subscription.plan, feature, False):
        raise PermissionDenied(
            f"This feature is not included in your current plan. "
            f"Please upgrade to access it."
        )


def check_limit(school, resource: str):
    subscription = get_active_subscription(school)

    if not subscription:
        raise PermissionDenied("No active subscription found.")

    if subscription.is_locked:
        raise PermissionDenied(
            "Your subscription has expired. Please renew to continue."
        )

    limit_map = {
        "students": (
            "max_students",
            lambda: school.students.filter(status="active").count(),
        ),
    }

    if resource not in limit_map:
        return

    plan_attr, count_fn = limit_map[resource]
    limit = getattr(subscription.plan, plan_attr, None)

    if limit is None:
        return  # unlimited

    current_count = count_fn()
    if current_count >= limit:
        raise PermissionDenied(
            f"You have reached the {resource} limit ({limit}) "
            f"for your {subscription.plan.name} plan. "
            f"Please upgrade to add more."
        )


def create_trial_subscription(school, plan):
    """Called on school signup — starts a 14-day trial on the Lite plan."""
    from .models import Subscription

    return Subscription.objects.create(
        school=school,
        plan=plan,
        status=Subscription.Status.TRIAL,
        start_date=timezone.now(),
        end_date=timezone.now() + timedelta(days=Subscription.TRIAL_DAYS),
        payment_provider="trial",
        setup_fee_paid=False,
    )


def activate_subscription(school, plan, term=None, activated_by=None,
                           payment_reference="", payment_provider="manual",
                           amount_paid=None, setup_fee_paid=False,
                           setup_fee_amount=None, notes=""):
    """
    Activates a term-based subscription for a school.
    Cancels any existing active/trial/grace subscription first.
    End date defaults to term end date if term is provided,
    otherwise 90 days (one term approx).
    """
    from .models import Subscription

    # Cancel existing subscriptions
    school.subscriptions.filter(
        status__in=[
            Subscription.Status.ACTIVE,
            Subscription.Status.TRIAL,
            Subscription.Status.GRACE,
        ]
    ).update(status=Subscription.Status.CANCELLED)

    now = timezone.now()
    end_date = (
        timezone.make_aware(
            timezone.datetime.combine(term.end_date, timezone.datetime.min.time())
        )
        if term
        else now + timedelta(days=90)
    )

    return Subscription.objects.create(
        school=school,
        plan=plan,
        term=term,
        status=Subscription.Status.ACTIVE,
        start_date=now,
        end_date=end_date,
        activated_by=activated_by,
        payment_reference=payment_reference,
        payment_provider=payment_provider,
        amount_paid=amount_paid or plan.price_per_term,
        setup_fee_paid=setup_fee_paid,
        setup_fee_amount=setup_fee_amount or plan.setup_fee,
        notes=notes,
    )