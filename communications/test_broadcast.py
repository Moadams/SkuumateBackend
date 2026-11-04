from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from academics.models import AcademicYear, Class
from accounts.models import User
from core.test_security import grant_all_features
from guardian.models import Guardian, GuardianStudent
from schools.models import School
from staff.models import StaffProfile
from students.models import Enrollment, Student

from .models import (
    Notification,
    NotificationRecipient,
    SMSBundle,
    SMSLedgerEntry,
    SMSPurchase,
    SMSWallet,
)
from .services.broadcast import BroadcastService, RecipientResolver, sms_segments


class BroadcastTestBase(APITestCase):
    def setUp(self):
        self.school = School.objects.create(name="Alpha School", school_code="ALP")
        self.other = School.objects.create(name="Beta School", school_code="BET")
        self.admin = User.objects.create_user(
            email="admin@alpha.test", password="pw", role="admin", school=self.school
        )
        self.other_admin = User.objects.create_user(
            email="admin@beta.test", password="pw", role="admin", school=self.other
        )
        self.teacher = User.objects.create_user(
            email="teacher@alpha.test", password="pw", role="teacher", school=self.school
        )
        grant_all_features(self.school)
        grant_all_features(self.other)
        self.client.force_authenticate(self.admin)

        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_current=True,
        )
        self.klass = Class.objects.create(school=self.school, name="Primary 1")

        self.student_a = Student.objects.create(
            school=self.school, first_name="Ama", last_name="Mensah", gender="female"
        )
        self.student_b = Student.objects.create(
            school=self.school, first_name="Kofi", last_name="Mensah", gender="male"
        )
        self.withdrawn = Student.objects.create(
            school=self.school,
            first_name="Yaa",
            last_name="Gone",
            gender="female",
            status=Student.Status.WITHDRAWN,
        )
        self.other_student = Student.objects.create(
            school=self.other, first_name="Kojo", last_name="Other", gender="male"
        )
        Enrollment.objects.create(
            school=self.school,
            student=self.student_a,
            klass=self.klass,
            academic_year=self.year,
            is_active=True,
        )

        self.guardian_a = self._guardian(
            self.school, "Efua", "Mensah", "+233201234567", "efua@example.com"
        )
        self.guardian_b = self._guardian(
            self.school, "Kwame", "Mensah", "123", "kwame@example.com"
        )
        # Both guardians belong to student A; guardian A also has student B.
        GuardianStudent.objects.create(
            school=self.school,
            guardian=self.guardian_a,
            student=self.student_a,
            relationship="mother",
        )
        GuardianStudent.objects.create(
            school=self.school,
            guardian=self.guardian_a,
            student=self.student_b,
            relationship="mother",
        )
        GuardianStudent.objects.create(
            school=self.school,
            guardian=self.guardian_b,
            student=self.student_a,
            relationship="father",
        )

        self.staff = StaffProfile.objects.create(
            school=self.school,
            first_name="Esi",
            last_name="Staff",
            user=User.objects.create_user(
                email="esi@alpha.test", password="pw", role="teacher", school=self.school
            ),
            date_joined=date(2026, 1, 5),
            status="active",
            email="esi@alpha.test",
            phone="+233209999999",
        )
        self.other_guardian = self._guardian(
            self.other, "Foreign", "Guardian", "+233207777777", "foreign@example.com"
        )
        GuardianStudent.objects.create(
            school=self.other,
            guardian=self.other_guardian,
            student=self.other_student,
            relationship="father",
        )

        self.wallet = SMSWallet.objects.create(school=self.school, balance=1000)

    def _guardian(self, school, first_name, last_name, phone, email):
        user = User.objects.create_user(
            email=email,
            password="pw",
            role="guardian",
            school=school,
            first_name=first_name,
            last_name=last_name,
        )
        return Guardian.objects.create(
            school=school,
            user_account=user,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            gender="female",
        )

    def payload(self, **overrides):
        data = {
            "title": "School update",
            "message_body": "Hello from Alpha School.",
            "channel": "sms",
            "recipient_type": "all_students",
        }
        data.update(overrides)
        return data


class RecipientResolutionTests(BroadcastTestBase):
    def test_all_students_resolve_guardians_once_and_skip_withdrawn(self):
        members = RecipientResolver.resolve(
            self.school, Notification.RecipientType.ALL_STUDENTS
        )

        self.assertEqual(len(members), 2)
        self.assertEqual(
            {member.recipient_id for member in members},
            {self.guardian_a.id, self.guardian_b.id},
        )

    def test_class_resolves_only_guardians_of_enrolled_students(self):
        members = RecipientResolver.resolve(
            self.school,
            Notification.RecipientType.CLASS,
            class_id=self.klass.id,
        )

        self.assertEqual(
            {member.recipient_id for member in members},
            {self.guardian_a.id, self.guardian_b.id},
        )

    def test_specific_recipients_combines_students_and_staff(self):
        members = RecipientResolver.resolve(
            self.school,
            Notification.RecipientType.SPECIFIC_RECIPIENTS,
            student_ids=[self.student_b.id],
            staff_ids=[self.staff.id],
        )

        self.assertEqual(
            {member.recipient_id for member in members},
            {self.guardian_a.id, self.staff.id},
        )

    def test_foreign_student_is_rejected(self):
        with self.assertRaisesMessage(ValueError, "do not belong to this school"):
            RecipientResolver.resolve(
                self.school,
                Notification.RecipientType.SPECIFIC_STUDENTS,
                student_ids=[self.other_student.id],
            )

    def test_sms_segments_rounds_up(self):
        self.assertEqual(sms_segments("a" * 160), 1)
        self.assertEqual(sms_segments("a" * 161), 2)


class PreviewTests(BroadcastTestBase):
    def test_preview_reports_deliverable_counts_and_invalid_contacts(self):
        response = self.client.post(
            reverse("notification-preview"),
            self.payload(channel="both"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertTrue(data["can_send"])
        self.assertEqual(data["email"]["deliverable"], 2)
        self.assertEqual(data["sms"]["deliverable"], 1)
        self.assertEqual(data["sms"]["credits_required"], 1)
        self.assertEqual(data["invalid_contact_count"], 1)
        self.assertIn("123", [row["contact"] for row in data["invalid_contacts"]])

    def test_preview_blocks_when_credits_are_insufficient(self):
        self.wallet.balance = 0
        self.wallet.save(update_fields=["balance"])

        response = self.client.post(
            reverse("notification-preview"), self.payload(), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertFalse(data["can_send"])
        self.assertTrue(
            any("Not enough SMS credits" in reason for reason in data["reasons"])
        )


class EnqueueTests(BroadcastTestBase):
    def test_sms_campaign_is_queued_and_credits_are_reserved(self):
        with patch(
            "communications.services.broadcast.SMSService.send"
        ) as sms_send, patch(
            "communications.services.broadcast.EmailService.send"
        ) as email_send:
            response = self.client.post(
                reverse("notification-list"), self.payload(), format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        sms_send.assert_not_called()
        email_send.assert_not_called()

        notification = Notification.objects.get()
        self.assertEqual(notification.status, Notification.Status.QUEUED)
        self.assertEqual(notification.total_recipients, 1)
        self.assertEqual(notification.sms_credits_charged, 1)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 999)
        rows = NotificationRecipient.objects.filter(notification=notification)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().channel, NotificationRecipient.Channel.SMS)
        self.assertEqual(rows.get().next_attempt_at is not None, True)
        self.assertTrue(
            SMSLedgerEntry.objects.filter(
                notification=notification, kind=SMSLedgerEntry.Kind.USAGE
            ).exists()
        )

    def test_both_channels_create_email_and_sms_rows_but_only_sms_costs_credits(self):
        response = self.client.post(
            reverse("notification-list"),
            self.payload(channel="both"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = Notification.objects.get()
        self.assertEqual(notification.total_recipients, 3)
        self.assertEqual(notification.sms_credits_charged, 1)
        self.assertEqual(
            NotificationRecipient.objects.filter(
                notification=notification, channel=NotificationRecipient.Channel.EMAIL
            ).count(),
            2,
        )
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 999)

    def test_long_message_consumes_one_credit_per_segment(self):
        response = self.client.post(
            reverse("notification-list"),
            self.payload(message_body="x" * 161),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Notification.objects.get().sms_credits_charged, 2)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 998)

    def test_insufficient_credits_writes_nothing(self):
        self.wallet.balance = 0
        self.wallet.save(update_fields=["balance"])

        response = self.client.post(
            reverse("notification-list"), self.payload(), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(NotificationRecipient.objects.exists())
        self.assertFalse(SMSLedgerEntry.objects.exists())
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 0)

    def test_foreign_student_id_is_rejected_and_nothing_is_written(self):
        response = self.client.post(
            reverse("notification-list"),
            self.payload(
                recipient_type="specific_students",
                student_ids=[str(self.other_student.id)],
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Notification.objects.exists())
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 1000)

    def test_no_sms_provider_blocks_the_send(self):
        with override_settings(INTEGRATION_MODE="live", SMS_PROVIDER=""):
            response = self.client.post(
                reverse("notification-list"), self.payload(), format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("No SMS provider", response.data["message"])
        self.assertFalse(Notification.objects.exists())

    def test_teacher_without_announcements_manage_cannot_send(self):
        self.client.force_authenticate(self.teacher)

        response = self.client.post(
            reverse("notification-list"), self.payload(), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class DispatchTests(BroadcastTestBase):
    def _enqueue_sms(self):
        notification, _plan = BroadcastService.enqueue(
            self.school,
            user=self.admin,
            title="Queued",
            message_body="Hello",
            channel=Notification.Channel.SMS,
            recipient_type=Notification.RecipientType.ALL_STUDENTS,
        )
        return notification

    def test_dispatch_marks_rows_and_campaign_sent(self):
        notification = self._enqueue_sms()

        stats = BroadcastService.dispatch(limit=10)

        self.assertEqual(stats.sent, 1)
        delivery = NotificationRecipient.objects.get(notification=notification)
        self.assertEqual(delivery.status, NotificationRecipient.DeliveryStatus.SENT)
        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.Status.SENT)

    @override_settings(
        BROADCAST_NOTIFICATIONS={
            "MAX_ATTEMPTS": 1,
            "BACKOFF_MINUTES": [1],
            "BATCH_SIZE": 25,
            "LOCK_TTL_MINUTES": 15,
            "TIME_BUDGET_SECONDS": 50,
            "SMS_CHARS_PER_CREDIT": 160,
        }
    )
    def test_terminal_failure_refunds_the_reserved_credit_once(self):
        notification = self._enqueue_sms()

        with patch(
            "communications.services.broadcast.SMSService.send",
            return_value=(False, "gateway down"),
        ):
            stats = BroadcastService.dispatch(limit=10)

        self.assertEqual(stats.failed, 1)
        delivery = NotificationRecipient.objects.get(notification=notification)
        self.assertEqual(delivery.status, NotificationRecipient.DeliveryStatus.FAILED)
        self.assertTrue(delivery.credit_refunded)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 1000)
        self.assertEqual(
            SMSLedgerEntry.objects.filter(
                notification=notification, kind=SMSLedgerEntry.Kind.REFUND
            ).count(),
            1,
        )

        # A second refund attempt must not credit the wallet again.
        BroadcastService._refund_sms(delivery, now=delivery.updated_at)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 1000)
        self.assertEqual(
            SMSLedgerEntry.objects.filter(kind=SMSLedgerEntry.Kind.REFUND).count(),
            1,
        )

    @override_settings(
        BROADCAST_NOTIFICATIONS={
            "MAX_ATTEMPTS": 2,
            "BACKOFF_MINUTES": [60],
            "BATCH_SIZE": 25,
            "LOCK_TTL_MINUTES": 15,
            "TIME_BUDGET_SECONDS": 50,
            "SMS_CHARS_PER_CREDIT": 160,
        }
    )
    def test_first_failure_is_retried_without_refund(self):
        notification = self._enqueue_sms()

        with patch(
            "communications.services.broadcast.SMSService.send",
            return_value=(False, "temporary"),
        ):
            stats = BroadcastService.dispatch(limit=10)

        self.assertEqual(stats.deferred, 1)
        delivery = NotificationRecipient.objects.get(notification=notification)
        self.assertEqual(delivery.status, NotificationRecipient.DeliveryStatus.FAILED)
        self.assertIsNotNone(delivery.next_attempt_at)
        self.assertFalse(delivery.credit_refunded)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 999)
        self.assertFalse(
            SMSLedgerEntry.objects.filter(
                kind=SMSLedgerEntry.Kind.REFUND
            ).exists()
        )

    def test_missing_provider_skips_and_refunds(self):
        notification = self._enqueue_sms()

        with override_settings(INTEGRATION_MODE="live", SMS_PROVIDER=""):
            stats = BroadcastService.dispatch(limit=10)

        self.assertEqual(stats.skipped, 1)
        delivery = NotificationRecipient.objects.get(notification=notification)
        self.assertEqual(delivery.status, NotificationRecipient.DeliveryStatus.SKIPPED)
        self.assertTrue(delivery.credit_refunded)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 1000)


class SMSCreditTests(BroadcastTestBase):
    def setUp(self):
        super().setUp()
        self.wallet.balance = 0
        self.wallet.save(update_fields=["balance"])
        self.bundle = SMSBundle.objects.create(
            code="test-bundle-500",
            name="Test 500",
            credits=500,
            price=Decimal("50.00"),
            description="Test bundle",
            display_order=1,
        )

    def purchase(self, reference="PAY-TEST-1", provider="simulate", **kwargs):
        return self.client.post(
            reverse("sms-purchase-list"),
            {
                "bundle": str(self.bundle.id),
                "payment_reference": reference,
                "provider": provider,
                **kwargs,
            },
            format="json",
        )

    def test_wallet_starts_empty_and_lists_active_bundles(self):
        response = self.client.get(reverse("sms-wallet"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["balance"], 0)

        bundles = self.client.get(reverse("sms-bundle-list"))
        self.assertEqual(bundles.status_code, status.HTTP_200_OK)
        codes = [row["code"] for row in bundles.data["data"]]
        self.assertIn("test-bundle-500", codes)

    def test_purchase_credits_wallet_once_even_when_repeated(self):
        first = self.purchase()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 500)

        second = self.purchase()
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertIn("already processed", second.data["message"])
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 500)
        self.assertEqual(SMSPurchase.objects.count(), 1)
        self.assertEqual(
            SMSLedgerEntry.objects.filter(
                kind=SMSLedgerEntry.Kind.PURCHASE
            ).count(),
            1,
        )

    def test_another_school_cannot_reuse_a_payment_reference(self):
        self.purchase()

        self.client.force_authenticate(self.other_admin)
        response = self.purchase()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SMSPurchase.objects.count(), 1)

    def test_inactive_bundle_is_rejected(self):
        self.bundle.is_active = False
        self.bundle.save(update_fields=["is_active"])

        response = self.purchase()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 0)

    def test_purchase_history_is_scoped_to_the_school(self):
        self.purchase(reference="PAY-ALPHA")
        self.client.force_authenticate(self.other_admin)
        self.purchase(reference="PAY-BETA")

        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("sms-purchase-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        references = [
            row["payment_reference"] for row in response.data["data"]["results"]
        ]
        self.assertEqual(references, ["PAY-ALPHA"])

    def test_wallet_summary_reflects_purchase_and_usage(self):
        self.purchase()
        BroadcastService.enqueue(
            self.school,
            user=self.admin,
            title="Usage",
            message_body="Hello",
            channel=Notification.Channel.SMS,
            recipient_type=Notification.RecipientType.ALL_STUDENTS,
        )

        response = self.client.get(reverse("sms-wallet"))

        data = response.data["data"]
        self.assertEqual(data["balance"], 499)
        self.assertEqual(data["total_purchased"], 500)
        self.assertEqual(data["total_used"], 1)

    def test_teacher_cannot_read_the_wallet(self):
        self.client.force_authenticate(self.teacher)

        response = self.client.get(reverse("sms-wallet"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ScopingTests(BroadcastTestBase):
    def test_foreign_notification_detail_is_not_found(self):
        foreign = Notification.objects.create(
            school=self.other,
            title="Foreign",
            message_body="Nope",
            channel=Notification.Channel.SMS,
            recipient_type=Notification.RecipientType.ALL_STAFF,
        )

        response = self.client.get(
            reverse("notification-detail", args=[foreign.id])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_sms_history_excludes_other_schools(self):
        other_notification = Notification.objects.create(
            school=self.other,
            title="Foreign",
            message_body="Nope",
            channel=Notification.Channel.SMS,
            recipient_type=Notification.RecipientType.ALL_STAFF,
        )
        NotificationRecipient.objects.create(
            notification=other_notification,
            recipient_type=NotificationRecipient.RecipientType.STAFF,
            recipient_name="Foreign",
            recipient_contact="+233200000000",
            channel=NotificationRecipient.Channel.SMS,
            status=NotificationRecipient.DeliveryStatus.SENT,
        )

        self._enqueue_sms()

        response = self.client.get(reverse("sms-history"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        contacts = [
            row["recipient_contact"] for row in response.data["data"]["results"]
        ]
        self.assertEqual(contacts, ["+233201234567"])

    def _enqueue_sms(self):
        BroadcastService.enqueue(
            self.school,
            user=self.admin,
            title="Mine",
            message_body="Hello",
            channel=Notification.Channel.SMS,
            recipient_type=Notification.RecipientType.ALL_STUDENTS,
        )
