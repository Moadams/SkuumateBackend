"""Report-card distribution: outbox queueing, worker, PDF/email and SMS."""
from datetime import date, timedelta
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from academics.models import AcademicYear, Class, Subject, Term
from accounts.models import User
from communications.models import NotificationProvider, ReportDelivery
from communications.services.email_service import EmailService
from communications.services.report_distribution import ReportDistributionService
from communications.services.sms_service import SMSService
from core.models import AuditLog
from core.test_security import grant_all_features
from exams.models import (
    AssessmentType,
    ReportScheme,
    StudentReport,
    StudentReportSubjectScore,
)
from guardian.models import GuardianStudent
from guardian.services.guardian_service import GuardianService
from integrations.common import MessageSendResult
from integrations.email.smtp import SMTPEmailProvider
from schools.models import School
from students.models import Student


def _school(name, code, email):
    return School.objects.create(name=name, school_code=code, email=email)


def _academics(school):
    year = AcademicYear.objects.create(
        school=school,
        name="2026",
        is_current=True,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    term = Term.objects.create(
        school=school,
        academic_year=year,
        name=Term.TermName.TERM_1,
        start_date=date(2026, 1, 5),
        end_date=date(2026, 4, 10),
    )
    klass = Class.objects.create(school=school, name="Primary 3")
    assessment = AssessmentType.objects.create(
        school=school, name="End of term exam", max_score=100
    )
    scheme = ReportScheme.objects.create(
        school=school, name="Primary scheme", main_exam=assessment
    )
    return year, term, klass, scheme


def _student(school, first_name, last_name="Mensah"):
    return Student.objects.create(
        school=school, first_name=first_name, last_name=last_name, gender="female"
    )


def _report(
    *,
    school,
    student,
    term,
    klass,
    scheme,
    report_status=StudentReport.ReportStatus.READY,
    **overrides,
):
    fields = {
        "school": school,
        "student": student,
        "academic_year": term.academic_year,
        "term": term,
        "student_class": klass,
        "report_scheme": scheme,
        "overall_score": "82.50",
        "overall_position": 2,
        "overall_attendance": 55,
        "total_school_days": 60,
        "teacher_remarks": "A steady term.",
        "headteacher_remarks": "Well done.",
        "status": report_status,
    }
    fields.update(overrides)
    return StudentReport.objects.create(**fields)


def _guardian(school, students, *, first_name="Efua", email="efua@example.com"):
    return GuardianService().create_guardian(
        {
            "first_name": first_name,
            "last_name": "Mensah",
            "email": email,
            "phone": "024 000 0000",
            "gender": "female",
            "students": [
                {"student": student, "relationship": "mother"} for student in students
            ],
        },
        school,
    )


def _distribution_config(**overrides):
    config = dict(getattr(settings, "REPORT_DISTRIBUTION", {}))
    config.update(overrides)
    return config


class ReportEnqueueTests(TestCase):
    def setUp(self):
        self.school = _school("Test School", "TST", "test@example.com")
        self.other_school = _school("Other School", "OTH", "other@example.com")
        self.year, self.term, self.klass, self.scheme = _academics(self.school)
        self.ama = _student(self.school, "Ama")
        self.kofi = _student(self.school, "Kofi")
        self.foreign = _student(self.other_school, "Esi")
        self.guardian = _guardian(self.school, [self.ama, self.kofi])
        self.ama_report = _report(
            school=self.school,
            student=self.ama,
            term=self.term,
            klass=self.klass,
            scheme=self.scheme,
        )
        self.kofi_report = _report(
            school=self.school,
            student=self.kofi,
            term=self.term,
            klass=self.klass,
            scheme=self.scheme,
            overall_score="70.00",
        )

    def test_queues_email_and_sms_for_every_linked_guardian(self):
        queued = ReportDistributionService.enqueue(
            [self.ama_report, self.kofi_report]
        )

        self.assertEqual(queued, 4)
        rows = ReportDelivery.objects.filter(guardian=self.guardian)
        self.assertEqual(rows.count(), 4)
        self.assertEqual(
            set(rows.values_list("channel", flat=True)),
            {ReportDelivery.Channel.EMAIL, ReportDelivery.Channel.SMS},
        )
        # The phone number is normalised before being stored.
        self.assertEqual(
            set(
                rows.filter(channel=ReportDelivery.Channel.SMS).values_list(
                    "recipient", flat=True
                )
            ),
            {"0240000000"},
        )
        self.assertEqual(
            set(
                rows.filter(channel=ReportDelivery.Channel.EMAIL).values_list(
                    "recipient", flat=True
                )
            ),
            {"efua@example.com"},
        )
        self.assertEqual(
            set(rows.values_list("student_report_id", flat=True)),
            {self.ama_report.id, self.kofi_report.id},
        )

    def test_enqueue_is_idempotent(self):
        ReportDistributionService.enqueue([self.ama_report])
        ReportDistributionService.enqueue([self.ama_report])

        self.assertEqual(ReportDelivery.objects.count(), 2)

    def test_guardian_links_belonging_to_another_school_are_ignored(self):
        foreign_student = _student(self.other_school, "Esi")
        foreign_guardian = _guardian(
            self.other_school,
            [foreign_student],
            first_name="Away",
            email="away@example.com",
        )
        # A malformed cross-school link must not leak a report outside its tenant.
        GuardianStudent.objects.create(
            school=self.other_school,
            guardian=foreign_guardian,
            student=self.ama,
            relationship="mother",
        )

        ReportDistributionService.enqueue([self.ama_report])

        self.assertFalse(
            ReportDelivery.objects.filter(guardian=foreign_guardian).exists()
        )
        self.assertEqual(
            ReportDelivery.objects.filter(guardian=self.guardian).count(), 2
        )

    def test_guardian_without_a_phone_only_gets_email(self):
        guardian = _guardian(
            self.school,
            [self.ama],
            first_name="NoPhone",
            email="nophone@example.com",
        )
        guardian.phone = ""
        guardian.save(update_fields=["phone"])
        guardian.user_account.phone = ""
        guardian.user_account.save(update_fields=["phone"])

        ReportDistributionService.enqueue([self.ama_report])

        self.assertEqual(
            ReportDelivery.objects.filter(guardian=guardian).count(), 1
        )
        self.assertTrue(
            ReportDelivery.objects.filter(
                guardian=guardian, channel=ReportDelivery.Channel.EMAIL
            ).exists()
        )


class ReportDispatchTests(TestCase):
    def setUp(self):
        self.school = _school("Test School", "TST", "test@example.com")
        self.year, self.term, self.klass, self.scheme = _academics(self.school)
        self.student = _student(self.school, "Ama")
        self.guardian = _guardian(self.school, [self.student])
        self.report = _report(
            school=self.school,
            student=self.student,
            term=self.term,
            klass=self.klass,
            scheme=self.scheme,
            report_status=StudentReport.ReportStatus.PUBLISHED,
        )
        self.sms_provider = NotificationProvider.objects.create(
            school=self.school,
            name="School SMS",
            channel=NotificationProvider.Channel.SMS,
            provider_type=NotificationProvider.ProviderType.ARKESEL,
            config={},
            is_default=True,
        )
        ReportDistributionService.enqueue([self.report])

    def _delivery(self, channel):
        return ReportDelivery.objects.get(channel=channel)

    def test_sends_the_email_with_a_pdf_and_the_sms_summary(self):
        with patch(
            "communications.services.report_distribution.EmailService.send",
            return_value=(True, "ok"),
        ) as email_send:
            stats = ReportDistributionService.dispatch()

        self.assertEqual(stats.claimed, 2)
        self.assertEqual(stats.sent, 2)
        self.assertEqual(stats.failed, 0)

        email_row = self._delivery(ReportDelivery.Channel.EMAIL)
        sms_row = self._delivery(ReportDelivery.Channel.SMS)
        self.assertEqual(email_row.status, ReportDelivery.Status.SENT)
        self.assertEqual(sms_row.status, ReportDelivery.Status.SENT)
        self.assertIsNotNone(email_row.sent_at)
        self.assertEqual(email_row.provider, "smtp")  # global fallback
        self.assertEqual(sms_row.provider, "arkesel")

        attachments = email_send.call_args.kwargs["attachments"]
        self.assertEqual(len(attachments), 1)
        filename, payload, mimetype = attachments[0]
        self.assertTrue(filename.endswith(".pdf"))
        self.assertTrue(payload.startswith(b"%PDF"))
        self.assertEqual(mimetype, "application/pdf")

    @override_settings(SMS_PROVIDER="twilio")
    def test_school_provider_takes_precedence_over_the_system_provider(self):
        stats = ReportDistributionService.dispatch(channel="sms")

        self.assertEqual(stats.sent, 1)
        # The school's Arkesel row wins over the system-level Twilio default.
        self.assertEqual(
            self._delivery(ReportDelivery.Channel.SMS).provider, "arkesel"
        )

    @override_settings(SMS_PROVIDER="mnotify")
    def test_inactive_school_provider_falls_back_to_the_system_provider(self):
        self.sms_provider.is_active = False
        self.sms_provider.save(update_fields=["is_active"])

        stats = ReportDistributionService.dispatch(channel="sms")

        self.assertEqual(stats.sent, 1)
        self.assertEqual(
            self._delivery(ReportDelivery.Channel.SMS).provider, "mnotify"
        )

    @override_settings(SMS_PROVIDER="arkesel")
    def test_sms_falls_back_to_the_system_provider(self):
        self.sms_provider.delete()

        stats = ReportDistributionService.dispatch(channel="sms")

        self.assertEqual(stats.sent, 1)
        self.assertEqual(stats.skipped, 0)
        sms_row = self._delivery(ReportDelivery.Channel.SMS)
        self.assertEqual(sms_row.status, ReportDelivery.Status.SENT)
        self.assertEqual(sms_row.provider, "arkesel")

    @override_settings(INTEGRATION_MODE="live", SMS_PROVIDER="")
    def test_sms_is_skipped_when_no_school_or_system_provider_exists(self):
        self.sms_provider.delete()

        stats = ReportDistributionService.dispatch(channel="sms")

        self.assertEqual(stats.sent, 0)
        self.assertEqual(stats.skipped, 1)
        sms_row = self._delivery(ReportDelivery.Channel.SMS)
        self.assertEqual(sms_row.status, ReportDelivery.Status.SKIPPED)
        self.assertIn("No SMS provider configured", sms_row.last_error)

    def test_provider_failure_is_retried_with_backoff(self):
        with patch(
            "communications.services.report_distribution.SMSService.send",
            return_value=(False, "gateway down"),
        ):
            stats = ReportDistributionService.dispatch(channel="sms")

        self.assertEqual(stats.deferred, 1)
        sms_row = self._delivery(ReportDelivery.Channel.SMS)
        self.assertEqual(sms_row.status, ReportDelivery.Status.FAILED)
        self.assertEqual(sms_row.attempts, 1)
        self.assertEqual(sms_row.last_error, "gateway down")
        self.assertGreater(sms_row.next_attempt_at, timezone.now())

        sms_row.next_attempt_at = timezone.now() - timedelta(seconds=1)
        sms_row.save(update_fields=["next_attempt_at"])
        with patch(
            "communications.services.report_distribution.SMSService.send",
            return_value=(True, "ok"),
        ):
            stats = ReportDistributionService.dispatch(channel="sms")

        sms_row.refresh_from_db()
        self.assertEqual(stats.sent, 1)
        self.assertEqual(sms_row.status, ReportDelivery.Status.SENT)
        self.assertEqual(sms_row.attempts, 2)

    @override_settings(REPORT_DISTRIBUTION={"MAX_ATTEMPTS": 1, "BACKOFF_MINUTES": [1]})
    def test_failure_becomes_terminal_after_max_attempts(self):
        with patch(
            "communications.services.report_distribution.SMSService.send",
            return_value=(False, "gateway down"),
        ):
            stats = ReportDistributionService.dispatch(channel="sms")

        self.assertEqual(stats.failed, 1)
        sms_row = self._delivery(ReportDelivery.Channel.SMS)
        self.assertEqual(sms_row.status, ReportDelivery.Status.FAILED)
        self.assertIsNone(sms_row.next_attempt_at)

        self.assertEqual(
            ReportDistributionService.dispatch(channel="sms").claimed, 0
        )

    def test_stale_processing_lock_is_recovered(self):
        ReportDelivery.objects.filter(channel=ReportDelivery.Channel.EMAIL).update(
            status=ReportDelivery.Status.PROCESSING,
            locked_at=timezone.now() - timedelta(minutes=30),
            locked_by="dead-worker",
        )

        stats = ReportDistributionService.dispatch(channel="email")

        self.assertEqual(stats.sent, 1)
        self.assertEqual(
            self._delivery(ReportDelivery.Channel.EMAIL).status,
            ReportDelivery.Status.SENT,
        )

    def test_dry_run_counts_due_rows_without_claiming_them(self):
        stats = ReportDistributionService.dispatch(dry_run=True)

        self.assertEqual(stats.claimed, 2)
        self.assertEqual(stats.sent, 0)
        self.assertEqual(
            set(ReportDelivery.objects.values_list("status", flat=True)),
            {ReportDelivery.Status.PENDING},
        )

    def test_channel_filter_leaves_the_other_channel_queued(self):
        stats = ReportDistributionService.dispatch(channel="email")

        self.assertEqual(stats.sent, 1)
        self.assertEqual(
            self._delivery(ReportDelivery.Channel.EMAIL).status,
            ReportDelivery.Status.SENT,
        )
        self.assertEqual(
            self._delivery(ReportDelivery.Channel.SMS).status,
            ReportDelivery.Status.PENDING,
        )

    def test_report_filter_only_processes_the_requested_report(self):
        other_student = _student(self.school, "Kofi")
        other_report = _report(
            school=self.school,
            student=other_student,
            term=self.term,
            klass=self.klass,
            scheme=self.scheme,
            report_status=StudentReport.ReportStatus.PUBLISHED,
        )
        _guardian(self.school, [other_student], first_name="Other", email="o@example.com")
        ReportDistributionService.enqueue([other_report])

        stats = ReportDistributionService.dispatch(report_id=self.report.id)

        self.assertEqual(stats.claimed, 2)
        self.assertEqual(
            ReportDelivery.objects.filter(
                student_report=other_report, status=ReportDelivery.Status.PENDING
            ).count(),
            2,
        )

    def test_requeue_returns_skipped_rows_to_pending(self):
        ReportDelivery.objects.filter(channel=ReportDelivery.Channel.SMS).update(
            status=ReportDelivery.Status.SKIPPED,
            attempts=3,
            last_error="No active SMS provider",
            next_attempt_at=None,
        )

        count = ReportDistributionService.requeue()

        self.assertEqual(count, 1)
        sms_row = self._delivery(ReportDelivery.Channel.SMS)
        self.assertEqual(sms_row.status, ReportDelivery.Status.PENDING)
        self.assertEqual(sms_row.attempts, 0)
        self.assertEqual(sms_row.last_error, "")
        self.assertIsNotNone(sms_row.next_attempt_at)


class ReportEmailTests(TestCase):
    def test_smtp_provider_attaches_the_pdf(self):
        provider = SMTPEmailProvider({})

        result = provider.send(
            to_email="guardian@example.com",
            subject="Report card",
            body="Attached.",
            attachments=[("report.pdf", b"%PDF-1.4 test", "application/pdf")],
        )

        self.assertTrue(result.success)
        self.assertEqual(len(mail.outbox), 1)
        filename, content, mimetype = mail.outbox[0].attachments[0]
        self.assertEqual(filename, "report.pdf")
        self.assertEqual(content, b"%PDF-1.4 test")
        self.assertEqual(mimetype, "application/pdf")

    def test_email_service_falls_back_to_global_smtp_with_attachments(self):
        class FakeProvider:
            def __init__(self):
                self.captured = None

            def send(self, **kwargs):
                self.captured = kwargs
                return MessageSendResult(True, "fake", "ok")

        fake = FakeProvider()
        attachments = [("report.pdf", b"%PDF", "application/pdf")]
        with patch(
            "communications.services.email_service.get_email_provider",
            return_value=fake,
        ) as factory:
            success, _message = EmailService.send(
                provider=None,
                to_email="guardian@example.com",
                subject="Report card",
                body="Attached.",
                attachments=attachments,
            )

        self.assertTrue(success)
        factory.assert_called_once_with("smtp", config={})
        self.assertEqual(fake.captured["attachments"], attachments)


class SmsServiceFallbackTests(TestCase):
    @override_settings(INTEGRATION_MODE="simulate", SMS_PROVIDER="")
    def test_simulate_mode_works_without_configuration(self):
        success, _message = SMSService.send(None, "0244000000", "Hello")

        self.assertTrue(success)
        self.assertEqual(SMSService.system_provider_type(), "simulate")

    @override_settings(INTEGRATION_MODE="live", SMS_PROVIDER="")
    def test_live_mode_without_a_provider_fails_clearly(self):
        success, message = SMSService.send(None, "0244000000", "Hello")

        self.assertFalse(success)
        self.assertIn("SMS_PROVIDER", message)

    @override_settings(INTEGRATION_MODE="live", SMS_PROVIDER="bogus")
    def test_live_mode_unknown_provider_does_not_fake_a_send(self):
        success, message = SMSService.send(None, "0244000000", "Hello")

        self.assertFalse(success)
        self.assertIn("No SMS provider configured", message)

    @override_settings(
        INTEGRATION_MODE="live", SMS_PROVIDER="arkesel", ARKESEL_API_KEY=""
    )
    def test_live_arkesel_without_credentials_fails_without_network(self):
        success, message = SMSService.send(None, "0244000000", "Hello")

        self.assertFalse(success)
        self.assertIn("Arkesel API key not configured", message)


class ReportSmsBodyTests(TestCase):
    def setUp(self):
        self.school = _school("Sunrise Academy", "SUN", "sun@example.com")
        self.year, self.term, self.klass, self.scheme = _academics(self.school)
        self.student = _student(self.school, "Ama")
        self.report = _report(
            school=self.school,
            student=self.student,
            term=self.term,
            klass=self.klass,
            scheme=self.scheme,
            report_status=StudentReport.ReportStatus.PUBLISHED,
            teacher_remarks="A very long remark. " * 40,
        )
        subject = Subject.objects.create(
            school=self.school, name="Mathematics", code="MTH"
        )
        StudentReportSubjectScore.objects.create(
            student_report=self.report,
            student=self.student,
            subject=subject,
            total_score=88,
            grade="A",
        )

    def test_body_contains_the_summary_and_the_deep_link(self):
        body = ReportDistributionService.build_sms_body(self.report)

        self.assertIn("Sunrise Academy", body)
        self.assertIn("Ama Mensah", body)
        self.assertIn("Overall: 82.50%", body)
        self.assertIn("Mathematics 88.00", body)
        self.assertIn("Full report: http", body)
        self.assertLessEqual(len(body), 320)

    @override_settings(REPORT_DISTRIBUTION=_distribution_config(SMS_MAX_LENGTH=400))
    def test_long_remarks_are_truncated_but_scores_and_link_remain(self):
        body = ReportDistributionService.build_sms_body(self.report)

        self.assertLessEqual(len(body), 400)
        self.assertIn("Mathematics 88.00", body)
        self.assertIn("Full report:", body)

    def test_every_subject_is_included_without_a_more_suffix(self):
        for index in range(1, 9):
            subject = Subject.objects.create(
                school=self.school, name=f"Subject {index}", code=f"S{index:02d}"
            )
            StudentReportSubjectScore.objects.create(
                student_report=self.report,
                student=self.student,
                subject=subject,
                total_score=60 + index,
                grade="B",
            )

        body = ReportDistributionService.build_sms_body(self.report)

        for index in range(1, 9):
            self.assertIn(f"Subject {index} ", body)
        self.assertNotIn("more", body)
        # The link comes after the scores, so it proves nothing was cut off.
        self.assertIn("Full report:", body)

    @override_settings(
        REPORT_DISTRIBUTION=_distribution_config(SMS_INCLUDE_REMARKS=False)
    )
    def test_remarks_can_be_omitted(self):
        body = ReportDistributionService.build_sms_body(self.report)

        self.assertNotIn("Remarks:", body)
        self.assertIn("Full report:", body)

    @override_settings(REPORT_DISTRIBUTION=_distribution_config(REPORT_CARD_URL_TEMPLATE=""))
    def test_missing_url_template_omits_the_link(self):
        body = ReportDistributionService.build_sms_body(self.report)

        self.assertNotIn("Full report:", body)
        self.assertIn("Ama Mensah", body)


class PublishReportsApiTests(APITestCase):
    def setUp(self):
        self.school = _school("Test School", "TST", "test@example.com")
        self.other_school = _school("Other School", "OTH", "other@example.com")
        self.year, self.term, self.klass, self.scheme = _academics(self.school)
        self.student = _student(self.school, "Ama")
        self.other_student = _student(self.school, "Kofi")
        self.guardian = _guardian(self.school, [self.student, self.other_student])
        self.report = _report(
            school=self.school,
            student=self.student,
            term=self.term,
            klass=self.klass,
            scheme=self.scheme,
        )
        self.other_report = _report(
            school=self.school,
            student=self.other_student,
            term=self.term,
            klass=self.klass,
            scheme=self.scheme,
        )

        oth_year, oth_term, oth_klass, oth_scheme = _academics(self.other_school)
        foreign_student = _student(self.other_school, "Esi")
        self.foreign_report = _report(
            school=self.other_school,
            student=foreign_student,
            term=oth_term,
            klass=oth_klass,
            scheme=oth_scheme,
        )

        self.admin = User.objects.create_user(
            email="admin@example.com", password="secret-pass", role="admin"
        )
        self.admin.school = self.school
        self.admin.save()
        grant_all_features(self.school)

        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.url = reverse("publish-reports")

    def test_publishes_ready_reports_and_queues_guardian_delivery(self):
        response = self.client.post(
            self.url, {"reports": [str(self.report.id)]}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(
            response.data["data"], {"published": 1, "queued": 2}
        )
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, StudentReport.ReportStatus.PUBLISHED)
        self.assertEqual(
            ReportDelivery.objects.filter(student_report=self.report).count(), 2
        )
        self.assertTrue(
            AuditLog.objects.filter(resource="StudentReport").exists()
        )

    def test_one_invalid_report_rolls_back_the_whole_publish(self):
        response = self.client.post(
            self.url,
            {"reports": [str(self.report.id), str(self.foreign_report.id)]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, StudentReport.ReportStatus.READY)
        self.assertEqual(ReportDelivery.objects.count(), 0)

    def test_non_ready_reports_are_rejected(self):
        draft = _report(
            school=self.school,
            student=_student(self.school, "Yaw"),
            term=self.term,
            klass=self.klass,
            scheme=self.scheme,
            report_status=StudentReport.ReportStatus.DRAFT,
            teacher_remarks="",
            headteacher_remarks="",
        )

        response = self.client.post(
            self.url, {"reports": [str(draft.id)]}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        draft.refresh_from_db()
        self.assertEqual(draft.status, StudentReport.ReportStatus.DRAFT)
        self.assertEqual(ReportDelivery.objects.count(), 0)

    def test_guardian_cannot_publish_reports(self):
        self.client.force_authenticate(self.guardian.user_account)

        response = self.client.post(
            self.url, {"reports": [str(self.report.id)]}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, StudentReport.ReportStatus.READY)

    def test_empty_and_malformed_payloads_are_rejected(self):
        empty = self.client.post(self.url, {"reports": []}, format="json")
        malformed = self.client.post(
            self.url, {"reports": ["not-a-uuid"]}, format="json"
        )

        self.assertEqual(empty.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(malformed.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ReportDelivery.objects.count(), 0)
