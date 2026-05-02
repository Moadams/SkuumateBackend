from functools import wraps
from django.core.cache import cache


def _school_key(school_id, suffix):
    return f"skuumate:school:{school_id}:{suffix}"


def invalidate_school_cache(school_id):
    patterns = [
        f"skuumate:school:{school_id}:dashboard",
        f"skuumate:school:{school_id}:onboarding",
        f"skuumate:school:{school_id}:students_count",
        f"skuumate:school:{school_id}:attendance_summary",
        f"skuumate:school:{school_id}:revenue",
    ]
    cache.delete_many(patterns)


class CacheKeys:
    SUPERADMIN_DASHBOARD = "skuumate:superadmin:dashboard"
    PLAN_LIST = "skuumate:plans:list"
    PLAN_FEATURES = "skuumate:plans:features"
    PERMISSION_LIST = "skuumate:permissions:list"

    @staticmethod
    def school_dashboard(school_id):
        return _school_key(school_id, "dashboard")

    @staticmethod
    def school_onboarding(school_id):
        return _school_key(school_id, "onboarding")

    @staticmethod
    def school_students_count(school_id):
        return _school_key(school_id, "students_count")

    @staticmethod
    def school_revenue(school_id):
        return _school_key(school_id, "revenue")


def cache_response(key_func, timeout=60 * 15):
    def decorator(view_method):
        @wraps(view_method)
        def wrapper(self, request, *args, **kwargs):
            key = key_func(self, request, *args, **kwargs)
            cached = cache.get(key)
            if cached is not None:
                from core.responses import ApiResponse
                return ApiResponse.success(data=cached)

            response = view_method(self, request, *args, **kwargs)
            if hasattr(response, "data") and response.data:
                payload = response.data.get("data") if isinstance(response.data, dict) else response.data
                if payload is not None:
                    cache.set(key, payload, timeout)
            return response
        return wrapper
    return decorator
