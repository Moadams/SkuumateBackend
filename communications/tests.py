from django.test import TestCase

from communications.models import NotificationProvider
from communications.serializers import SendTestSerializer
from schools.models import School


class SendTestSerializerScopingTests(TestCase):
    """A school must never be able to send through another tenant's provider."""

    def setUp(self):
        self.school = School.objects.create(
            name="Alpha School", school_code="AL", email="alpha@example.com"
        )
        self.other_school = School.objects.create(
            name="Beta School", school_code="BE", email="beta@example.com"
        )
        self.own_provider = NotificationProvider.objects.create(
            school=self.school,
            name="Own SMTP",
            channel=NotificationProvider.Channel.EMAIL,
            provider_type=NotificationProvider.ProviderType.SMTP,
        )
        self.foreign_provider = NotificationProvider.objects.create(
            school=self.other_school,
            name="Foreign SMTP",
            channel=NotificationProvider.Channel.EMAIL,
            provider_type=NotificationProvider.ProviderType.SMTP,
        )

    def _serializer(self, provider, school):
        return SendTestSerializer(
            data={"provider": str(provider.id), "recipient": "guardian@example.com"},
            context={"school": school},
        )

    def test_accepts_provider_owned_by_the_caller(self):
        serializer = self._serializer(self.own_provider, self.school)

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_rejects_provider_from_another_school(self):
        serializer = self._serializer(self.foreign_provider, self.school)

        self.assertFalse(serializer.is_valid())
        self.assertIn("provider", serializer.errors)

    def test_rejects_every_provider_without_school_context(self):
        serializer = SendTestSerializer(
            data={"provider": str(self.own_provider.id), "recipient": "x@example.com"}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("provider", serializer.errors)
