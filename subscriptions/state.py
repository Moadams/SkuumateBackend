"""Single source of truth for subscription *state* rules.

Feature entitlements ("does this package include reports?") are enforced by the
generated permission classes in ``subscriptions.permissions``. Subscription
*state* ("is this school allowed to do anything at all right now?") is a
different axis and lives here.

Keeping both the middleware and ``SubscriptionPermission`` on
``evaluate_request_state`` matters: they used to encode the same rules
separately, which is how LOCKED and GRACE came to be enforced for eight
features and silently ignored everywhere else.
"""
from __future__ import annotations

from django.urls import Resolver404, resolve


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Always reachable, whatever the subscription state. Two reasons a path lands
# here: a locked school would otherwise have no way to *pay*, and a 403 the
# client cannot authenticate past is worse than no gate at all. If you add a
# billing or auth endpoint, add it here in the same commit.
ALWAYS_REACHABLE_URL_NAMES = frozenset({
    # Auth and session bootstrap.
    "login",
    "logout",
    "token-refresh",
    "me",
    "forgot-password",
    "reset-password-confirm",
    "change-password",
    "change-user-password",
    # Health checks and public package browsing.
    "health-check",
    "plan-list",
    "plan-features",
    # Billing. A locked or grace-period school must be able to renew.
    "subscription-list",
    "subscription-current",
    "current-subscription",
    "subscription-current-features",
    "current-entitlements",
    "school-subscribe",
    "subscribe",
    "school-subscribe-initiate",
    "initiate-payment",
    "school-webhook",
    "payment-webhook",
    # A school that has not finished registering cannot subscribe yet.
    "school-profile",
    "school-details",
    "school-onboarding",
})

# Path prefixes, as a safety net for endpoints whose URL name is not set and
# for trailing-slash or mount-point variations in the names above.
ALWAYS_REACHABLE_PATH_PREFIXES = (
    "/api/subscriptions/",
    "/api/v1/subscriptions/",
    "/api/v1/subscription/",
    "/api/v1/plans/",
    "/api/schools/me/",
    "/api/v1/schools/me/",
    "/api/auth/",
    "/api/v1/auth/",
    "/api/health/",
    "/api/v1/health/",
)

LOCKED_MESSAGE = (
    "Your subscription has expired and your account is locked. "
    "Please renew your subscription to continue."
)


def is_always_reachable(request) -> bool:
    path = request.path_info or ""
    if any(path.startswith(prefix) for prefix in ALWAYS_REACHABLE_PATH_PREFIXES):
        return True
    try:
        match = resolve(path)
    except Resolver404:
        # Unknown path: let the view layer produce the 404 rather than masking
        # it with a subscription error.
        return True
    return match.url_name in ALWAYS_REACHABLE_URL_NAMES


def is_write_method(request) -> bool:
    return request.method.upper() not in SAFE_METHODS


def evaluate_request_state(request, user, subscription):
    """Return a denial message, or ``None`` when the request may proceed.

    This covers subscription *state* only. Package entitlements are a separate
    check performed by the feature permission classes.

    A school with **no subscription at all** is deliberately allowed through:
    that is the normal state between registration and subscribing, and
    ``SchoolSubscribeView`` grants the free trial from there. Denying it would
    strand new signups with no way to ever obtain a subscription. Feature
    gates still deny the gated features for them, as they always have.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None

    school = getattr(user, "school", None)
    if school is None:
        # Platform staff operate outside any school's subscription.
        return None

    if subscription is None or is_always_reachable(request):
        return None

    if subscription.status == subscription.Status.LOCKED:
        return LOCKED_MESSAGE

    return None
