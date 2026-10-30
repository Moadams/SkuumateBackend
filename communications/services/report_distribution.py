"""Queue, deliver and retry published student reports for guardians.

The web request only writes ``ReportDelivery`` rows inside the publish
transaction. ``manage.py dispatch_report_deliveries`` (run from cPanel cron)
does the slow work: rendering the PDF and calling the email/SMS providers.
"""
import logging
import re
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import timedelta
from itertools import groupby

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from communications.models import NotificationProvider, ReportDelivery
from communications.services.email_service import EmailService
from communications.services.sms_service import SMSService
from exams.services.report_pdf import build_report_pdf

logger = logging.getLogger(__name__)


class DeliverySkipped(Exception):
    """The delivery cannot run until configuration or data changes."""


class DeliveryFailed(Exception):
    """The provider rejected the delivery; it may be retried."""


@dataclass
class DispatchStats:
    claimed: int = 0
    sent: int = 0
    deferred: int = 0
    failed: int = 0
    skipped: int = 0

    def as_dict(self):
        return asdict(self)


def _settings():
    return getattr(settings, "REPORT_DISTRIBUTION", {}) or {}


def _normalise_phone(value):
    """Keep digits and a single leading ``+`` so providers accept the number."""
    cleaned = re.sub(r"[^\d+]", "", value or "")
    if cleaned.count("+") > 1:
        cleaned = "+" + cleaned.replace("+", "")
    return cleaned


def _score(value):
    if value is None or value == "":
        return "-"
    try:
        return f"{value:.2f}"
    except (TypeError, ValueError):
        return str(value)


class ReportDistributionService:
    """Transactional-outbox queue for guardian report delivery."""

    # ── Queueing ──────────────────────────────────────────────────
    @classmethod
    def enqueue(cls, reports):
        """Create one email and one SMS delivery per linked guardian.

        Called inside the publish transaction, so either the reports are
        marked published *and* queued, or neither happens. The unique
        constraint makes republishing safe.
        """
        from guardian.models import GuardianStudent

        reports = list(reports)
        if not reports:
            return 0

        school_ids = {report.school_id for report in reports}
        student_ids = {report.student_id for report in reports}
        links = (
            GuardianStudent.objects.filter(
                school_id__in=school_ids, student_id__in=student_ids
            )
            .select_related("guardian__user_account")
            .order_by("created_at")
        )
        links_by_student = defaultdict(list)
        for link in links:
            links_by_student[link.student_id].append(link)

        now = timezone.now()
        rows = []
        for report in reports:
            for link in links_by_student.get(report.student_id, ()):
                guardian = link.guardian
                email = (guardian.email or guardian.user_account.email or "").strip()
                phone = _normalise_phone(
                    guardian.phone or guardian.user_account.phone or ""
                )
                common = {
                    "school_id": report.school_id,
                    "student_report": report,
                    "guardian": guardian,
                    "next_attempt_at": now,
                }
                if email:
                    rows.append(
                        ReportDelivery(
                            channel=ReportDelivery.Channel.EMAIL,
                            recipient=email,
                            **common,
                        )
                    )
                if phone:
                    rows.append(
                        ReportDelivery(
                            channel=ReportDelivery.Channel.SMS,
                            recipient=phone,
                            **common,
                        )
                    )

        if rows:
            ReportDelivery.objects.bulk_create(
                rows, ignore_conflicts=True, batch_size=200
            )
        return len(rows)

    # ── Worker ────────────────────────────────────────────────────
    @classmethod
    def dispatch(
        cls,
        *,
        limit=None,
        time_budget=None,
        channel=None,
        report_id=None,
        dry_run=False,
    ):
        """Claim and deliver a bounded batch of due rows.

        Returns ``DispatchStats`` so the management command can log a summary.
        Safe to run two workers at once: rows are claimed with a conditional
        ``UPDATE`` and only the worker that transitioned a row to
        ``PROCESSING`` processes it.
        """
        config = _settings()
        limit = max(1, int(limit or config.get("BATCH_SIZE", 25)))
        time_budget = max(1, int(time_budget or config.get("TIME_BUDGET_SECONDS", 50)))
        lock_ttl = int(config.get("LOCK_TTL_MINUTES", 15))
        max_attempts = int(config.get("MAX_ATTEMPTS", 5))
        backoff = list(config.get("BACKOFF_MINUTES", [1, 5, 15, 60, 360]))

        now = timezone.now()
        stats = DispatchStats()

        # Recover rows abandoned by a process killed mid-run.
        ReportDelivery.objects.filter(
            status=ReportDelivery.Status.PROCESSING,
            locked_at__lt=now - timedelta(minutes=lock_ttl),
        ).update(status=ReportDelivery.Status.PENDING, locked_at=None, locked_by="")

        # ``next_attempt_at`` is the due-time guard: retries wait for their
        # backoff, and terminal failures have it cleared so they are never
        # claimed again.
        candidates = ReportDelivery.objects.filter(
            status__in=[ReportDelivery.Status.PENDING, ReportDelivery.Status.FAILED],
            next_attempt_at__lte=now,
        )
        if channel:
            candidates = candidates.filter(channel=channel)
        if report_id:
            candidates = candidates.filter(student_report_id=report_id)

        ids = list(
            candidates.order_by("next_attempt_at", "created_at").values_list(
                "id", flat=True
            )[:limit]
        )
        stats.claimed = len(ids)
        if dry_run or not ids:
            return stats

        worker_id = uuid.uuid4().hex
        ReportDelivery.objects.filter(
            id__in=ids,
            status__in=[ReportDelivery.Status.PENDING, ReportDelivery.Status.FAILED],
        ).update(
            status=ReportDelivery.Status.PROCESSING,
            locked_at=now,
            locked_by=worker_id,
        )
        claimed = list(
            ReportDelivery.objects.filter(
                id__in=ids,
                status=ReportDelivery.Status.PROCESSING,
                locked_by=worker_id,
            )
            .select_related(
                "student_report__school",
                "student_report__student",
                "student_report__student_class",
                "student_report__term",
                "student_report__academic_year",
                "guardian__user_account",
            )
            .prefetch_related("student_report__subject_scores__subject")
            .order_by("student_report_id", "channel")
        )
        stats.claimed = len(claimed)
        if not claimed:
            return stats

        processed = set()
        started = time.monotonic()

        for _report_id, grouped in groupby(
            claimed, key=lambda delivery: delivery.student_report_id
        ):
            if time.monotonic() - started > time_budget:
                break
            deliveries = list(grouped)
            report = deliveries[0].student_report
            email_rows = [
                row for row in deliveries if row.channel == ReportDelivery.Channel.EMAIL
            ]
            sms_rows = [
                row for row in deliveries if row.channel == ReportDelivery.Channel.SMS
            ]

            pdf_bytes = None
            if email_rows:
                try:
                    # Build once per report, reuse for every guardian.
                    pdf_bytes = build_report_pdf(report).getvalue()
                except Exception as exc:
                    logger.exception(
                        "Could not render report PDF for report %s", report.id
                    )
                    for delivery in email_rows:
                        cls._fail(
                            delivery,
                            exc,
                            max_attempts=max_attempts,
                            backoff=backoff,
                            now=now,
                        )
                        stats.deferred += 1
                        processed.add(delivery.id)
                    email_rows = []

            for delivery in email_rows:
                try:
                    provider_key = cls._send_email(report, delivery, pdf_bytes)
                except DeliverySkipped as exc:
                    cls._skip(delivery, exc)
                    stats.skipped += 1
                except Exception as exc:
                    if cls._fail(
                        delivery,
                        exc,
                        max_attempts=max_attempts,
                        backoff=backoff,
                        now=now,
                    ):
                        stats.failed += 1
                    else:
                        stats.deferred += 1
                else:
                    cls._mark_sent(delivery, provider_key, now=now)
                    stats.sent += 1
                    logger.info(
                        "Sent report email for report %s to delivery %s",
                        report.id,
                        delivery.id,
                    )
                processed.add(delivery.id)

            for delivery in sms_rows:
                try:
                    provider_key = cls._send_sms(report, delivery)
                except DeliverySkipped as exc:
                    cls._skip(delivery, exc)
                    stats.skipped += 1
                except Exception as exc:
                    if cls._fail(
                        delivery,
                        exc,
                        max_attempts=max_attempts,
                        backoff=backoff,
                        now=now,
                    ):
                        stats.failed += 1
                    else:
                        stats.deferred += 1
                else:
                    cls._mark_sent(delivery, provider_key, now=now)
                    stats.sent += 1
                    logger.info(
                        "Sent report SMS for report %s to delivery %s",
                        report.id,
                        delivery.id,
                    )
                processed.add(delivery.id)

            close_old_connections()

        # Give claimed rows we did not reach back to the next cron run.
        remaining = [delivery.id for delivery in claimed if delivery.id not in processed]
        if remaining:
            ReportDelivery.objects.filter(
                id__in=remaining,
                status=ReportDelivery.Status.PROCESSING,
                locked_by=worker_id,
            ).update(
                status=ReportDelivery.Status.PENDING,
                locked_at=None,
                locked_by="",
            )

        return stats

    @classmethod
    def requeue(cls, *, status=None, report_id=None, channel=None):
        """Reset matching rows to ``PENDING`` so the next run picks them up."""
        queryset = ReportDelivery.objects.filter(
            status=status or ReportDelivery.Status.SKIPPED
        )
        if report_id:
            queryset = queryset.filter(student_report_id=report_id)
        if channel:
            queryset = queryset.filter(channel=channel)
        return queryset.update(
            status=ReportDelivery.Status.PENDING,
            next_attempt_at=timezone.now(),
            attempts=0,
            last_error="",
            locked_at=None,
            locked_by="",
        )

    # ── Channels ──────────────────────────────────────────────────
    @classmethod
    def _provider(cls, school, channel):
        return (
            NotificationProvider.objects.filter(
                school=school,
                channel__in=[channel, NotificationProvider.Channel.BOTH],
                is_active=True,
            )
            .order_by("-is_default", "name")
            .first()
        )

    @classmethod
    def _send_email(cls, report, delivery, pdf_bytes):
        provider = cls._provider(report.school, NotificationProvider.Channel.EMAIL)
        subject = (
            f"{report.term.get_name_display()} Report Card - "
            f"{report.student.full_name}"
        )
        success, message = EmailService.send(
            provider=provider,
            to_email=delivery.recipient,
            subject=subject,
            body=cls._email_body(report, delivery),
            school_name=report.school.name,
            attachments=[(cls._pdf_filename(report), pdf_bytes, "application/pdf")],
        )
        if not success:
            raise DeliveryFailed(message)
        return provider.provider_type if provider else "smtp"

    @classmethod
    def _send_sms(cls, report, delivery):
        provider = cls._provider(report.school, NotificationProvider.Channel.SMS)
        provider_type = (
            provider.provider_type if provider else SMSService.system_provider_type()
        )
        if not provider_type:
            raise DeliverySkipped(
                "No SMS provider configured for this school or the system."
            )
        success, message = SMSService.send(
            provider,
            delivery.recipient,
            cls.build_sms_body(report),
        )
        if not success:
            raise DeliveryFailed(message)
        return provider_type

    # ── Message building ──────────────────────────────────────────
    @classmethod
    def _email_body(cls, report, delivery):
        guardian = delivery.guardian
        name = f"{guardian.first_name} {guardian.last_name}".strip() or "Guardian"
        term = report.term.get_name_display()
        student = report.student.full_name

        lines = [
            f"Dear {name},",
            "",
            (
                f"Please find attached {student}'s {term} report card for "
                f"{report.academic_year.name}."
            ),
            "",
            f"Overall score: {_score(report.overall_score)}%",
        ]
        if report.overall_position:
            lines.append(f"Position in class: {report.overall_position}")
        if report.total_school_days:
            lines.append(
                f"Attendance: {report.overall_attendance}/"
                f"{report.total_school_days} days"
            )

        url = cls.report_url(report)
        if url:
            lines.extend(["", f"View the report online: {url}"])

        lines.extend(["", "Regards,", report.school.name])
        return "\n".join(lines)

    @classmethod
    def build_sms_body(cls, report):
        """Compact, readable SMS summary that always keeps every subject score.

        All subject results and the report link are mandatory, so the message
        may run past ``SMS_MAX_LENGTH`` for pupils with many subjects. Only the
        optional teacher's remark is shortened or dropped to fit the configured
        budget; nothing else is ever cut.
        """
        config = _settings()
        max_length = int(config.get("SMS_MAX_LENGTH", 320))
        include_remarks = bool(config.get("SMS_INCLUDE_REMARKS", True))

        header = [
            report.school.name,
            (
                f"{report.term.get_name_display()} Report - "
                f"{report.student.full_name} ({report.student_class.name})"
            ),
        ]
        summary = f"Overall: {_score(report.overall_score)}%"
        if report.overall_position:
            summary += f" | Position: {report.overall_position}"
        header.append(summary)
        if report.total_school_days:
            header.append(
                f"Attendance: {report.overall_attendance}/"
                f"{report.total_school_days} days"
            )

        url = cls.report_url(report)
        footer = [f"Full report: {url}"] if url else []
        lines = list(header)

        def length_with(extra_lines=()):
            return len("\n".join(lines + list(extra_lines) + footer))

        # Every subject is shown; never replace the tail with "+N more".
        lines.extend(
            f"{score.subject.name} {_score(score.total_score)}"
            f" ({score.grade or '-'})"
            for score in report.subject_scores.all()
        )

        if include_remarks and report.teacher_remarks:
            prefix = "Remarks: "
            available = max_length - length_with() - 1
            if available > len(prefix) + 8:
                text = " ".join(report.teacher_remarks.split())
                allowed = available - len(prefix)
                if len(text) > allowed:
                    text = text[: max(1, allowed - 1)].rstrip() + "…"
                lines.append(prefix + text)

        lines.extend(footer)
        return "\n".join(lines)

    @classmethod
    def report_url(cls, report):
        template = _settings().get("REPORT_CARD_URL_TEMPLATE")
        if not template:
            return ""
        try:
            return template.format(
                frontend_url=str(getattr(settings, "FRONTEND_URL", "")).rstrip("/")
            )
        except (KeyError, IndexError, ValueError):
            logger.warning("Invalid REPORT_CARD_URL_TEMPLATE setting", exc_info=True)
            return ""

    @staticmethod
    def _pdf_filename(report):
        raw = (
            f"ReportCard_{report.student.student_id}_"
            f"{report.term.get_name_display()}_{report.academic_year.name}.pdf"
        )
        return re.sub(r"[^A-Za-z0-9._-]+", "_", raw)

    # ── State transitions ─────────────────────────────────────────
    @classmethod
    def _mark_sent(cls, delivery, provider_key, *, now):
        delivery.status = ReportDelivery.Status.SENT
        delivery.sent_at = now
        delivery.attempts += 1
        delivery.last_error = ""
        delivery.provider = provider_key or ""
        delivery.locked_at = None
        delivery.locked_by = ""
        delivery.next_attempt_at = None
        delivery.save(
            update_fields=[
                "status",
                "sent_at",
                "attempts",
                "last_error",
                "provider",
                "locked_at",
                "locked_by",
                "next_attempt_at",
                "updated_at",
            ]
        )

    @classmethod
    def _fail(cls, delivery, exc, *, max_attempts, backoff, now):
        """Record a failure; return ``True`` when the row is terminal."""
        attempts = delivery.attempts + 1
        delivery.attempts = attempts
        delivery.last_error = str(exc)[:2000]
        delivery.status = ReportDelivery.Status.FAILED
        delivery.locked_at = None
        delivery.locked_by = ""

        terminal = attempts >= max_attempts
        if terminal:
            delivery.next_attempt_at = None
        else:
            index = min(attempts - 1, len(backoff) - 1) if backoff else 0
            minutes = backoff[index] if backoff else 1
            delivery.next_attempt_at = now + timedelta(minutes=minutes)

        delivery.save(
            update_fields=[
                "status",
                "attempts",
                "last_error",
                "next_attempt_at",
                "locked_at",
                "locked_by",
                "updated_at",
            ]
        )
        return terminal

    @classmethod
    def _skip(cls, delivery, exc):
        delivery.status = ReportDelivery.Status.SKIPPED
        delivery.last_error = str(exc)[:2000]
        delivery.next_attempt_at = None
        delivery.locked_at = None
        delivery.locked_by = ""
        delivery.save(
            update_fields=[
                "status",
                "last_error",
                "next_attempt_at",
                "locked_at",
                "locked_by",
                "updated_at",
            ]
        )
