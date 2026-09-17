import hashlib
import hmac
import io
import json
import sys
import types
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from schools.models import School
from subscriptions.models import Package

from integrations.email import (
    NullEmailProvider,
    SendGridEmailProvider,
    SimulatedEmailProvider,
    SMTPEmailProvider,
)
from integrations.email.base import BaseEmailProvider
from integrations.email.mailgun import MailgunEmailProvider
from integrations.payments.base import BasePaymentProvider
from integrations.payments.paystack import PaystackPaymentProvider
from integrations.payments.simulate import SimulatedPaymentProvider
from integrations.payments.stripe import StripePaymentProvider
from integrations.registry import get_email_provider, get_payment_provider, get_sms_provider
from integrations.sms.africas_talking import AfricasTalkingSMSProvider
from integrations.sms.arkesel import ArkeselSMSProvider
from integrations.sms.base import BaseSMSProvider
from integrations.sms.mnotify import MNotifySMSProvider
from integrations.sms.simulate import SimulatedSMSProvider
from integrations.sms.twilio import TwilioSMSProvider


class AbstractClassContractTests(TestCase):
    def test_payment_base_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            BasePaymentProvider()

    def test_sms_base_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            BaseSMSProvider()

    def test_email_base_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            BaseEmailProvider()

    def test_real_providers_inherit_abstract_bases(self):
        self.assertTrue(issubclass(PaystackPaymentProvider, BasePaymentProvider))
        self.assertTrue(issubclass(StripePaymentProvider, BasePaymentProvider))
        self.assertTrue(issubclass(SimulatedPaymentProvider, BasePaymentProvider))
        for cls in (TwilioSMSProvider, AfricasTalkingSMSProvider, MNotifySMSProvider, ArkeselSMSProvider):
            self.assertTrue(issubclass(cls, BaseSMSProvider))
        for cls in (SMTPEmailProvider, SendGridEmailProvider, MailgunEmailProvider, NullEmailProvider):
            self.assertTrue(issubclass(cls, BaseEmailProvider))


class SimulatedProviderBehaviourTests(TestCase):
    def capture(self, callable):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            result = callable()
        return result, buffer.getvalue()

    def test_payment_initiate_prints_and_returns_reference(self):
        provider = SimulatedPaymentProvider()

        result, output = self.capture(
            lambda: provider.initiate("a@b.com", 250.0, "GHS", {"school_id": "1"})
        )
        self.assertTrue(result.success)
        self.assertTrue(result.reference.startswith("SIM-"))
        self.assertEqual(result.amount, 250.0)
        self.assertEqual(result.provider, "simulate")
        self.assertIn("SIMULATED PAYMENT", output)
        self.assertIn(result.reference, output)

    def test_payment_webhook_prints_and_verifies(self):
        provider = SimulatedPaymentProvider()
        result, output = self.capture(
            lambda: provider.verify_webhook({"reference": "SIM-X", "status": "success"})
        )
        self.assertTrue(result.success)
        self.assertEqual(result.reference, "SIM-X")
        self.assertEqual(result.status, "success")
        self.assertIn("SIMULATED PAYMENT", output)

    def test_sms_send_prints_and_succeeds(self):
        provider = SimulatedSMSProvider()
        result, output = self.capture(lambda: provider.send("+233240000000", "Hello"))
        self.assertTrue(result.success)
        self.assertIn("SIMULATED SMS", output)
        self.assertIn("Hello", output)
        self.assertIn("+233240000000", output)

    def test_email_send_prints_and_succeeds(self):
        provider = SimulatedEmailProvider()
        result, output = self.capture(
            lambda: provider.send("x@y.com", "Subject", "Body", html_body="<p>Body</p>", from_email="n@n.com")
        )
        self.assertTrue(result.success)
        self.assertIn("SIMULATED EMAIL", output)
        self.assertIn("Subject", output)


class RegistryFactoryTests(TestCase):
    def test_simulate_mode_default_returns_simulated_providers(self):
        self.assertIsInstance(get_payment_provider("paystack"), SimulatedPaymentProvider)
        self.assertIsInstance(get_payment_provider("momo"), SimulatedPaymentProvider)
        self.assertIsInstance(get_sms_provider("twilio"), SimulatedSMSProvider)
        self.assertIsInstance(get_email_provider("smtp"), SimulatedEmailProvider)

    def test_unknown_providers_also_simulated_in_dev(self):
        self.assertIsInstance(get_payment_provider("bogus"), SimulatedPaymentProvider)
        self.assertIsInstance(get_sms_provider("bogus"), SimulatedSMSProvider)
        self.assertIsInstance(get_email_provider("bogus"), (SimulatedEmailProvider, NullEmailProvider))

    @override_settings(INTEGRATION_MODE="live")
    def test_live_mode_returns_real_providers(self):
        self.assertIsInstance(get_payment_provider("paystack"), PaystackPaymentProvider)
        self.assertIsInstance(get_payment_provider("momo"), PaystackPaymentProvider)
        self.assertIsInstance(get_payment_provider("stripe"), StripePaymentProvider)
        self.assertIsInstance(get_sms_provider("twilio"), TwilioSMSProvider)
        self.assertIsInstance(get_sms_provider("mnotify"), MNotifySMSProvider)
        self.assertIsInstance(get_sms_provider("arkesel"), ArkeselSMSProvider)
        self.assertIsInstance(get_sms_provider("africas_talking"), AfricasTalkingSMSProvider)
        self.assertIsInstance(get_email_provider("smtp"), SMTPEmailProvider)
        self.assertIsInstance(get_email_provider("sendgrid"), SendGridEmailProvider)
        self.assertIsInstance(get_email_provider("mailgun"), MailgunEmailProvider)

    @override_settings(INTEGRATION_MODE="live")
    def test_unknown_email_provider_falls_back_to_null(self):
        provider = get_email_provider("bogus")
        result = provider.send("x@y.com", "t", "b")
        self.assertFalse(result.success)
        self.assertEqual(result.provider, "null")


class PaystackProviderTests(TestCase):
    def test_initiate_success(self):
        with override_settings(PAYSTACK_SECRET_KEY="sk_test_123"):
            provider = PaystackPaymentProvider()
            with patch("requests.post") as mocked:
                mocked.return_value.status_code = 200
                mocked.return_value.json.return_value = {
                    "status": True,
                    "message": "Authorization URL created",
                    "data": {"authorization_url": "https://paystack.com/pay/abc"},
                }
                result = provider.initiate("a@b.com", 100.0, "GHS", {"school_id": "1"})

        self.assertTrue(result.success)
        self.assertEqual(result.payment_url, "https://paystack.com/pay/abc")
        self.assertEqual(result.amount, 100.0)
        payload = mocked.call_args.kwargs["json"]
        self.assertEqual(payload["amount"], 10000)  # cedis -> pesewas
        self.assertEqual(payload["currency"], "GHS")
        self.assertEqual(payload["email"], "a@b.com")
        self.assertTrue(payload["reference"])

    def test_initiate_missing_secret_fails(self):
        provider = PaystackPaymentProvider()
        with override_settings(PAYSTACK_SECRET_KEY=""):
            result = provider.initiate("a@b.com", 100.0, "GHS")
        self.assertFalse(result.success)
        self.assertIn("secret key", result.message.lower())

    def test_initiate_provider_error(self):
        with override_settings(PAYSTACK_SECRET_KEY="sk_test_123"):
            provider = PaystackPaymentProvider()
            with patch("requests.post") as mocked:
                mocked.return_value.status_code = 400
                mocked.return_value.json.return_value = {"status": False, "message": "Bad request"}
                result = provider.initiate("a@b.com", 100.0, "GHS")
        self.assertFalse(result.success)
        self.assertIn("Bad request", result.message)

    def test_webhook_valid_signature(self):
        body = json.dumps({"event": "charge.success", "data": {"reference": "ref1", "status": "success", "amount": 25000}}).encode()
        signature = hmac.new(b"secret", body, hashlib.sha512).hexdigest()
        with override_settings(PAYSTACK_SECRET_KEY="secret"):
            provider = PaystackPaymentProvider()
            result = provider.verify_webhook(
                {"event": "charge.success", "data": {"reference": "ref1", "status": "success", "amount": 25000}, "_raw_body": body},
                {"X-Paystack-Signature": signature},
            )
        self.assertTrue(result.success)
        self.assertEqual(result.reference, "ref1")
        self.assertEqual(result.amount, 250.0)

    def test_webhook_bad_signature(self):
        body = json.dumps({"event": "charge.success"}).encode()
        with override_settings(PAYSTACK_SECRET_KEY="secret"):
            provider = PaystackPaymentProvider()
            result = provider.verify_webhook(
                {"event": "charge.success", "_raw_body": body},
                {"X-Paystack-Signature": "deadbeef"},
            )
        self.assertFalse(result.success)


class StripeProviderTests(TestCase):
    def setUp(self):
        # The stripe SDK isn't installed in this environment; register a fake
        # module so the provider's `import stripe` resolves against a mock.
        self.fake_stripe = types.ModuleType("stripe")
        self.fake_stripe.Webhook = types.SimpleNamespace()
        self.webhook_patcher = patch.dict(sys.modules, {"stripe": self.fake_stripe})
        self.webhook_patcher.start()
        self.addCleanup(self.webhook_patcher.stop)

    def test_webhook_construct_event(self):
        with override_settings(STRIPE_WEBHOOK_SECRET="whsec_test", STRIPE_SECRET_KEY="sk_test"):
            provider = StripePaymentProvider()
            fake_event = {
                "type": "checkout.session.completed",
                "data": {"object": {"id": "cs_1", "amount_total": 50000, "metadata": {"school_id": "3"}}},
            }
            self.fake_stripe.Webhook.construct_event = Mock(return_value=fake_event)
            result = provider.verify_webhook(
                {"_raw_body": b"{}"},
                {"Stripe-Signature": "sig"},
            )
        self.assertTrue(result.success)
        self.assertEqual(result.reference, "cs_1")
        self.assertEqual(result.amount, 500.0)
        self.assertEqual(result.metadata, {"school_id": "3"})
        self.fake_stripe.Webhook.construct_event.assert_called_once_with(b"{}", "sig", "whsec_test")

    def test_webhook_rejects_bad_signature(self):
        with override_settings(STRIPE_WEBHOOK_SECRET="whsec_test", STRIPE_SECRET_KEY="sk_test"):
            provider = StripePaymentProvider()
            self.fake_stripe.Webhook.construct_event = Mock(side_effect=ValueError("bad"))
            result = provider.verify_webhook({"_raw_body": b"{}"}, {"Stripe-Signature": "sig"})
        self.assertFalse(result.success)
        self.assertIn("verification failed", result.message.lower())


class InitiatePaymentWiringTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.school = School.objects.create(name="Test School")
        self.admin = user_model.objects.create_user(
            email="admin1@test.com",
            password="pass1234",
            role="admin",
            school=self.school,
        )
        # NOTE: code="advantage" collides with the package seeded in
        # subscriptions.0006_seed_packages, so use a unique fixture code.
        self.package = Package.objects.create(
            name="Advantage",
            code="wiring-test",
            price="250.00",
            is_active=True,
            is_public=True,
        )
        self.client.force_authenticate(self.admin)

    def test_initiate_simulated_returns_payment_url_and_reference(self):
        response = self.client.post(
            reverse("initiate-payment"),
            {"plan_id": self.package.pk, "provider": "paystack"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["provider"], "simulate")
        self.assertTrue(data["reference"].startswith("SIM-"))
        self.assertEqual(float(data["amount"]), 250.0)
        self.assertEqual(data["plan"], "Advantage")

    def test_initiate_momo_goes_through_same_path_in_dev(self):
        response = self.client.post(
            reverse("initiate-payment"),
            {"plan_id": self.package.pk, "provider": "momo"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["provider"], "simulate")

    def test_webhook_accepts_simulated_callback(self):
        response = self.client.post(
            reverse("payment-webhook", kwargs={"provider": "paystack"}),
            {"reference": "SIM-X", "status": "success"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["reference"], "SIM-X")
        self.assertEqual(data["status"], "success")