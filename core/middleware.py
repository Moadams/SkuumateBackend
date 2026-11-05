"""Request-level guards applied before authentication or upload parsing."""
from django.conf import settings
from django.http import JsonResponse


class RequestSizeLimitMiddleware:
    """Reject request bodies larger than ``MAX_REQUEST_BODY_SIZE``.

    Django spools large uploads to disk, so without a ceiling a single
    authenticated account (or an unauthenticated endpoint) can fill the
    hosting account's disk quota. The limit is checked from
    ``CONTENT_LENGTH``, before any parsing happens.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.limit = int(getattr(settings, "MAX_REQUEST_BODY_SIZE", 0) or 0)

    def __call__(self, request):
        if self.limit:
            try:
                length = int(request.META.get("CONTENT_LENGTH") or 0)
            except (TypeError, ValueError):
                length = 0
            if length > self.limit:
                return JsonResponse(
                    {
                        "success": False,
                        "message": (
                            "Uploaded data is too large. "
                            f"Maximum request size is {self.limit // (1024 * 1024)} MB."
                        ),
                        "errors": {"detail": "request_too_large"},
                        "status_code": 413,
                    },
                    status=413,
                )
        return self.get_response(request)
