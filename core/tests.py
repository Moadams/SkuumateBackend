from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test import TestCase, override_settings

from core.middleware import RequestSizeLimitMiddleware
from core.models import AuditLog
from core.utils import log_action, sanitize_audit_payload
from schools.models import School


class AuditRedactionTests(TestCase):
    def test_sanitize_redacts_secret_like_keys_at_every_depth(self):
        payload = {
            "password": "hunter2",
            "api_key": "abc",
            "nested": {"token": "t", "safe": 1},
            "items": [{"secret": "s", "name": "ok"}],
        }

        cleaned = sanitize_audit_payload(payload)

        self.assertEqual(cleaned["password"], "[REDACTED]")
        self.assertEqual(cleaned["api_key"], "[REDACTED]")
        self.assertEqual(cleaned["nested"]["token"], "[REDACTED]")
        self.assertEqual(cleaned["nested"]["safe"], 1)
        self.assertEqual(cleaned["items"][0]["secret"], "[REDACTED]")
        self.assertEqual(cleaned["items"][0]["name"], "ok")

    def test_log_action_never_persists_secrets(self):
        school = School.objects.create(
            name="Audit School", school_code="AUD", email="audit@example.com"
        )

        log_action(
            action=AuditLog.Action.CREATE,
            resource="Test",
            school=school,
            metadata={"password": "hunter2", "note": "visible"},
        )

        entry = AuditLog.objects.get(school=school)
        self.assertEqual(entry.metadata["password"], "[REDACTED]")
        self.assertEqual(entry.metadata["note"], "visible")


class RequestSizeLimitMiddlewareTests(TestCase):
    def _request(self, content_length):
        request = Mock()
        request.META = {"CONTENT_LENGTH": str(content_length)}
        return request

    @override_settings(MAX_REQUEST_BODY_SIZE=100)
    def test_rejects_body_over_limit(self):
        middleware = RequestSizeLimitMiddleware(lambda request: HttpResponse("ok"))

        response = middleware(self._request(101))

        self.assertEqual(response.status_code, 413)

    @override_settings(MAX_REQUEST_BODY_SIZE=100)
    def test_allows_body_within_limit(self):
        middleware = RequestSizeLimitMiddleware(lambda request: HttpResponse("ok"))

        response = middleware(self._request(100))

        self.assertEqual(response.status_code, 200)

    @override_settings(MAX_REQUEST_BODY_SIZE=0)
    def test_limit_zero_disables_the_guard(self):
        middleware = RequestSizeLimitMiddleware(lambda request: HttpResponse("ok"))

        response = middleware(self._request(10**9))

        self.assertEqual(response.status_code, 200)


class SettingsLoaderStrictnessTests(TestCase):
    def test_unknown_app_env_fails_loudly(self):
        from skuumate.settings import loader

        with patch.object(loader, "config", return_value="prod-typo"):
            with self.assertRaises(ImproperlyConfigured):
                loader.load()

    def test_blank_app_env_fails_loudly(self):
        from skuumate.settings import loader

        with patch.object(loader, "config", return_value="   "):
            with self.assertRaises(ImproperlyConfigured):
                loader.load()
