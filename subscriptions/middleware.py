from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from .state import evaluate_request_state
from .utils import get_active_subscription


def resolve_acting_user(request):
    """Return the authenticated user for this request, or None.

    ``AuthenticationMiddleware`` only understands session cookies, but this API
    is stateless JWT (``SchoolJWTAuthentication`` is the sole authenticator).
    At middleware time ``request.user`` is therefore ``AnonymousUser`` for
    every real API call, which is why ``request.subscription`` used to always
    be None in production and the state rules never ran at all.

    So: use the session user when there is one, otherwise authenticate the
    bearer token here. ``SchoolJWTAuthentication`` caches its result on the
    request, so DRF reuses this instead of verifying the token twice.

    Authentication errors are swallowed on purpose. An expired or malformed
    token is a 401 that DRF's authenticator should report with its own error
    shape, not a subscription failure raised from middleware.
    """
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user

    from rest_framework.exceptions import AuthenticationFailed

    from accounts.authentication import SchoolJWTAuthentication

    try:
        result = SchoolJWTAuthentication().authenticate(request)
    except AuthenticationFailed:
        return None
    except Exception:
        # Never let a middleware failure turn into a 500. DRF will re-run the
        # authenticator and produce the authoritative 401.
        return None
    return result[0] if result else None


class SubscriptionMiddleware(MiddlewareMixin):
    """Attach the school's subscription to the request and enforce its state.

    Two responsibilities:

    1. Set ``request.subscription`` so views and permissions can read it.
    2. Deny the request when the subscription is LOCKED, or in GRACE for writes.

    Step 2 was missing entirely. Feature gates cover package entitlements, but
    they are only attached to views that sell a feature, so subscription state
    was enforced for those views and ignored for every other one: a LOCKED
    school could still read students and a GRACE school could still create
    them. Enforcing here means no view can opt out by forgetting to list a
    permission class.
    """

    def process_request(self, request):
        request.subscription = None

        user = resolve_acting_user(request)
        school = getattr(user, "school", None) if user is not None else None
        if school is not None:
            request.subscription = get_active_subscription(school)

        denial = evaluate_request_state(request, user, request.subscription)
        if denial:
            return JsonResponse(
                {"success": False, "message": denial},
                status=403,
            )
        return None
