from django.utils.deprecation import MiddlewareMixin
from .utils import get_active_subscription


class SubscriptionMiddleware(MiddlewareMixin):
    """
    Attaches the school's active subscription to the request object.
    Access it anywhere as request.subscription.
    """
    def process_request(self, request):
        request.subscription = None

        # User not authenticated yet at middleware stage
        # — we attach lazily so views can use request.subscription
        if hasattr(request, "user") and request.user.is_authenticated:
            school = getattr(request.user, "school", None)
            if school:
                request.subscription = get_active_subscription(school)