"""Queue and deliver guardian/staff broadcast notifications.

The API request only resolves the audience and writes the outbox rows. The
slow work (provider calls) is done later by ``manage.py dispatch_notifications``
from cron, which keeps shared-hosting request times short.
"""
import logging
import math
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import timedelta

from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import Count
from django.utils import timezone

from communications.models import (
    Notification,
    NotificationProvider,
    NotificationRecipient,
    SMSLedgerEntry,
    SMSWallet,
)
from communications.services.contacts import (
    is_valid_email,
    is_valid_phone,
    normalise_phone,
)
from communications.services.email_service import EmailService
from communications.services.sms_service import SMSService

logger = logging.getLogger(__name__)


class BroadcastValidationError(ValueError):
    """The campaign cannot be queued; ``details`` is safe to return to clients."""

    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


@dataclass(frozen=True)
class AudienceMember:
    recipient_type: str
    recipient_id: object
    name: str
    email: str = ""
    phone: str = ""


@dataclass(frozen=True)
class PlannedDelivery:
    member: AudienceMember
    channel: str
    contact: str
    credit_cost: int = 0


@dataclass
class BroadcastPlan:
    members: list
    deliveries: list
    sms_credits: int
    email_count: int
    sms_count: int
    invalid_contacts: list
    unreachable_count: int

    @property
    def deliverable_count(self):
        return len(self.deliveries)


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
    return getattr(settings, "BROADCAST_NOTIFICATIONS", {}) or {}


def sms_segments(message):
    """Number of SMS credits one recipient consumes for ``message``."""
    chars = max(1, int(_settings().get("SMS_CHARS_PER_CREDIT", 160)))
    return max(1, math.ceil(len(message or "") / chars))


def _uuid_list(values):
    result = []
    for value in values or []:
        try:
            result.append(uuid.UUID(str(value)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"Invalid identifier: {value}") from exc
    return list(dict.fromkeys(result))


class RecipientResolver:
    """Resolve an audience selection into distinct guardian/staff contacts."""

    @classmethod
    def resolve(
        cls,
        school,
        recipient_type,
        *,
        recipient_ids=None,
        student_ids=None,
        staff_ids=None,
        class_id=None,
    ):
        from staff.models import StaffProfile
        from students.models import Student

        if school is None:
            raise ValueError("No school context available.")

        if recipient_type == Notification.RecipientType.ALL_STUDENTS:
            students = Student.objects.filter(
                school=school, status=Student.Status.ACTIVE
            )
            return cls._guardians_for_students(school, students)

        if recipient_type == Notification.RecipientType.ALL_STAFF:
            staff = StaffProfile.objects.filter(school=school, status="active")
            return cls._staff_members(staff)

        if recipient_type in (
            Notification.RecipientType.SPECIFIC_STUDENTS,
            Notification.RecipientType.GUARDIANS_OF,
        ):
            ids = _uuid_list(student_ids or recipient_ids)
            if not ids:
                raise ValueError("Select at least one student.")
            students = Student.objects.filter(school=school, id__in=ids)
            if students.count() != len(ids):
                raise ValueError(
                    "One or more selected students do not belong to this school."
                )
            return cls._guardians_for_students(school, students)

        if recipient_type == Notification.RecipientType.SPECIFIC_STAFF:
            ids = _uuid_list(staff_ids or recipient_ids)
            if not ids:
                raise ValueError("Select at least one staff member.")
            staff = StaffProfile.objects.filter(school=school, id__in=ids)
            if staff.count() != len(ids):
                raise ValueError(
                    "One or more selected staff do not belong to this school."
                )
            return cls._staff_members(staff)

        if recipient_type == Notification.RecipientType.SPECIFIC_RECIPIENTS:
            selected_students = _uuid_list(student_ids)
            selected_staff = _uuid_list(staff_ids)
            if not selected_students and not selected_staff:
                raise ValueError("Select at least one student or staff member.")

            members = []
            if selected_students:
                students = Student.objects.filter(
                    school=school, id__in=selected_students
                )
                if students.count() != len(selected_students):
                    raise ValueError(
                        "One or more selected students do not belong to this school."
                    )
                members.extend(cls._guardians_for_students(school, students))
            if selected_staff:
                staff = StaffProfile.objects.filter(
                    school=school, id__in=selected_staff
                )
                if staff.count() != len(selected_staff):
                    raise ValueError(
                        "One or more selected staff do not belong to this school."
                    )
                members.extend(cls._staff_members(staff))
            return cls._dedupe_members(members)

        if recipient_type == Notification.RecipientType.CLASS:
            from academics.models import Class

            if not class_id:
                raise ValueError("Select a class.")
            klass = Class.objects.filter(school=school, id=class_id).first()
            if klass is None:
                raise ValueError("Class not found in this school.")
            students = Student.objects.filter(
                school=school,
                status=Student.Status.ACTIVE,
                enrollments__klass=klass,
                enrollments__is_active=True,
            ).distinct()
            return cls._guardians_for_students(school, students)

        raise ValueError(f"Unsupported recipient type: {recipient_type}")

    @classmethod
    def _guardians_for_students(cls, school, students):
        from guardian.models import GuardianStudent

        links = (
            GuardianStudent.objects.filter(
                school=school, student_id__in=students.values("id")
            )
            .select_related("guardian__user_account")
            .order_by("created_at")
        )
        members = []
        seen = set()
        for link in links:
            guardian = link.guardian
            if guardian.id in seen:
                continue
            seen.add(guardian.id)
            user = guardian.user_account
            members.append(
                AudienceMember(
                    recipient_type=NotificationRecipient.RecipientType.GUARDIAN,
                    recipient_id=guardian.id,
                    name=f"{guardian.first_name} {guardian.last_name}".strip(),
                    email=(guardian.email or (user.email if user else "") or "").strip(),
                    phone=(guardian.phone or (user.phone if user else "") or "").strip(),
                )
            )
        return members

    @classmethod
    def _staff_members(cls, staff):
        members = []
        for profile in staff.select_related("user").order_by("last_name", "first_name"):
            user = profile.user
            members.append(
                AudienceMember(
                    recipient_type=NotificationRecipient.RecipientType.STAFF,
                    recipient_id=profile.id,
                    name=f"{profile.first_name} {profile.last_name}".strip(),
                    email=(profile.email or (user.email if user else "") or "").strip(),
                    phone=(profile.phone or (user.phone if user else "") or "").strip(),
                )
            )
        return members

    @staticmethod
    def _dedupe_members(members):
        deduped = []
        seen = set()
        for member in members:
            key = (member.recipient_type, member.recipient_id)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(member)
        return deduped


class BroadcastPlanner:
    """Turn an audience selection into concrete, deduplicated deliveries."""

    @classmethod
    def build(
        cls,
        school,
        *,
        channel,
        recipient_type,
        message_body,
        recipient_ids=None,
        student_ids=None,
        staff_ids=None,
        class_id=None,
    ):
        members = RecipientResolver.resolve(
            school,
            recipient_type,
            recipient_ids=recipient_ids,
            student_ids=student_ids,
            staff_ids=staff_ids,
            class_id=class_id,
        )

        requested = (
            {NotificationRecipient.Channel.EMAIL, NotificationRecipient.Channel.SMS}
            if channel == Notification.Channel.BOTH
            else {channel}
        )
        segments = sms_segments(message_body)

        deliveries = []
        invalid = []
        reachable = set()
        seen_contacts = set()

        for member in members:
            member_key = (member.recipient_type, member.recipient_id)
            if NotificationRecipient.Channel.EMAIL in requested:
                email = (member.email or "").strip()
                if is_valid_email(email):
                    key = (NotificationRecipient.Channel.EMAIL, email.lower())
                    if key not in seen_contacts:
                        seen_contacts.add(key)
                        deliveries.append(
                            PlannedDelivery(
                                member=member,
                                channel=NotificationRecipient.Channel.EMAIL,
                                contact=email,
                            )
                        )
                    reachable.add(member_key)
                elif email:
                    invalid.append(
                        {
                            "name": member.name,
                            "channel": "email",
                            "contact": email,
                            "reason": "Invalid email address",
                        }
                    )
                else:
                    invalid.append(
                        {
                            "name": member.name,
                            "channel": "email",
                            "contact": "",
                            "reason": "No email address",
                        }
                    )

            if NotificationRecipient.Channel.SMS in requested:
                raw_phone = (member.phone or "").strip()
                phone = normalise_phone(raw_phone)
                if is_valid_phone(phone):
                    key = (NotificationRecipient.Channel.SMS, phone)
                    if key not in seen_contacts:
                        seen_contacts.add(key)
                        deliveries.append(
                            PlannedDelivery(
                                member=member,
                                channel=NotificationRecipient.Channel.SMS,
                                contact=phone,
                                credit_cost=segments,
                            )
                        )
                    reachable.add(member_key)
                elif raw_phone:
                    invalid.append(
                        {
                            "name": member.name,
                            "channel": "sms",
                            "contact": raw_phone,
                            "reason": "Invalid phone number",
                        }
                    )
                else:
                    invalid.append(
                        {
                            "name": member.name,
                            "channel": "sms",
                            "contact": "",
                            "reason": "No phone number",
                        }
                    )

        email_count = sum(
            1 for row in deliveries if row.channel == NotificationRecipient.Channel.EMAIL
        )
        sms_count = sum(
            1 for row in deliveries if row.channel == NotificationRecipient.Channel.SMS
        )

        return BroadcastPlan(
            members=members,
            deliveries=deliveries,
            sms_credits=sms_count * segments,
            email_count=email_count,
            sms_count=sms_count,
            invalid_contacts=invalid,
            unreachable_count=len(members) - len(reachable),
        )


class BroadcastService:
    """Queue, deliver and account for guardian/staff broadcasts."""

    # ── Preview / validation ───────────────────────────────────────
    @classmethod
    def preview(
        cls,
        school,
        *,
        channel,
        recipient_type,
        message_body,
        recipient_ids=None,
        student_ids=None,
        staff_ids=None,
        class_id=None,
    ):
        plan = BroadcastPlanner.build(
            school,
            channel=channel,
            recipient_type=recipient_type,
            message_body=message_body,
            recipient_ids=recipient_ids,
            student_ids=student_ids,
            staff_ids=staff_ids,
            class_id=class_id,
        )

        wallet = SMSWallet.objects.filter(school=school).first()
        balance = wallet.balance if wallet else 0

        reasons = []
        warnings = []
        sms_requested = channel in (
            Notification.Channel.SMS,
            Notification.Channel.BOTH,
        )

        if plan.deliverable_count == 0:
            reasons.append("No valid recipients were found for the selected audience.")

        if sms_requested and plan.sms_count:
            if not cls._sms_provider_available(school):
                reasons.append(
                    "No SMS provider is configured. Add a school provider or set "
                    "SMS_PROVIDER before sending."
                )
            if not cls._sms_feature_enabled(school):
                reasons.append(
                    "SMS alerts are not available on your current package."
                )
            if plan.sms_credits > balance:
                reasons.append(
                    f"Not enough SMS credits: {plan.sms_credits} required, "
                    f"{balance} available."
                )
        elif sms_requested:
            warnings.append("None of the selected recipients has a valid phone number.")

        if channel in (Notification.Channel.EMAIL, Notification.Channel.BOTH):
            if plan.email_count == 0:
                warnings.append("None of the selected recipients has a valid email address.")

        if plan.invalid_contacts:
            warnings.append(
                f"{len(plan.invalid_contacts)} contact(s) were skipped because they "
                "are missing or invalid."
            )

        return {
            "channel": channel,
            "recipient_type": recipient_type,
            "audience_count": len(plan.members),
            "delivery_count": plan.deliverable_count,
            "email": {
                "deliverable": plan.email_count,
            },
            "sms": {
                "deliverable": plan.sms_count,
                "segments_per_recipient": sms_segments(message_body),
                "credits_required": plan.sms_credits,
                "credits_available": balance,
                "provider_configured": cls._sms_provider_available(school),
                "sufficient_credits": plan.sms_credits <= balance,
            },
            "unreachable_count": plan.unreachable_count,
            "invalid_contacts": plan.invalid_contacts[:100],
            "invalid_contact_count": len(plan.invalid_contacts),
            "can_send": not reasons,
            "reasons": reasons,
            "warnings": warnings,
        }

    # ── Queueing ──────────────────────────────────────────────────
    @classmethod
    def enqueue(
        cls,
        school,
        *,
        user,
        title,
        message_body,
        channel,
        recipient_type,
        recipient_ids=None,
        student_ids=None,
        staff_ids=None,
        class_id=None,
        template=None,
        template_variables=None,
    ):
        plan = BroadcastPlanner.build(
            school,
            channel=channel,
            recipient_type=recipient_type,
            message_body=message_body,
            recipient_ids=recipient_ids,
            student_ids=student_ids,
            staff_ids=staff_ids,
            class_id=class_id,
        )

        sms_requested = channel in (
            Notification.Channel.SMS,
            Notification.Channel.BOTH,
        )

        reasons = []
        if plan.deliverable_count == 0:
            reasons.append("No valid recipients were found for the selected audience.")
        if sms_requested and plan.sms_count:
            if not cls._sms_provider_available(school):
                reasons.append(
                    "No SMS provider is configured. Add a school provider or set "
                    "SMS_PROVIDER before sending."
                )
            if not cls._sms_feature_enabled(school):
                reasons.append(
                    "SMS alerts are not available on your current package."
                )

        if reasons:
            raise BroadcastValidationError(
                " ".join(reasons),
                details={"reasons": reasons},
            )

        now = timezone.now()
        metadata = {
            "recipient_ids": [str(value) for value in (recipient_ids or [])],
            "student_ids": [str(value) for value in (student_ids or [])],
            "staff_ids": [str(value) for value in (staff_ids or [])],
            "class_id": str(class_id) if class_id else None,
            "template_variables": template_variables or {},
            "delivery_summary": {
                "audience_count": len(plan.members),
                "deliverable_count": plan.deliverable_count,
                "email_count": plan.email_count,
                "sms_count": plan.sms_count,
                "sms_credits": plan.sms_credits,
                "unreachable_count": plan.unreachable_count,
                "invalid_contact_count": len(plan.invalid_contacts),
            },
        }

        with transaction.atomic():
            wallet, _ = SMSWallet.objects.get_or_create(school=school)
            wallet = SMSWallet.objects.select_for_update().get(pk=wallet.pk)
            if plan.sms_credits > wallet.balance:
                raise BroadcastValidationError(
                    f"Not enough SMS credits: {plan.sms_credits} required, "
                    f"{wallet.balance} available.",
                    details={
                        "credits_required": plan.sms_credits,
                        "credits_available": wallet.balance,
                    },
                )

            if plan.sms_credits:
                wallet.balance -= plan.sms_credits
                wallet.save(update_fields=["balance", "updated_at"])

            notification = Notification.objects.create(
                school=school,
                template=template,
                title=title,
                message_body=message_body,
                channel=channel,
                recipient_type=recipient_type,
                metadata=metadata,
                sent_by=user,
                status=Notification.Status.QUEUED,
                total_recipients=plan.deliverable_count,
                sms_credits_charged=plan.sms_credits,
                queued_at=now,
            )

            NotificationRecipient.objects.bulk_create(
                [
                    NotificationRecipient(
                        notification=notification,
                        recipient_type=row.member.recipient_type,
                        recipient_id=row.member.recipient_id,
                        recipient_name=row.member.name,
                        recipient_contact=row.contact,
                        channel=row.channel,
                        status=NotificationRecipient.DeliveryStatus.PENDING,
                        next_attempt_at=now,
                        credit_cost=row.credit_cost,
                    )
                    for row in plan.deliveries
                ],
                batch_size=200,
            )

            if plan.sms_credits:
                SMSLedgerEntry.objects.create(
                    school=school,
                    kind=SMSLedgerEntry.Kind.USAGE,
                    credits=-plan.sms_credits,
                    balance_after=wallet.balance,
                    description=f"SMS credits for notification '{title}'",
                    notification=notification,
                    created_by=user,
                )

        return notification, plan

    # ── Worker ────────────────────────────────────────────────────
    @classmethod
    def dispatch(
        cls,
        *,
        limit=None,
        time_budget=None,
        notification_id=None,
        dry_run=False,
    ):
        """Claim and deliver a bounded batch of due notification rows."""
        config = _settings()
        limit = max(1, int(limit or config.get("BATCH_SIZE", 25)))
        time_budget = max(1, int(time_budget or config.get("TIME_BUDGET_SECONDS", 50)))
        lock_ttl = int(config.get("LOCK_TTL_MINUTES", 15))
        max_attempts = int(config.get("MAX_ATTEMPTS", 5))
        backoff = list(config.get("BACKOFF_MINUTES", [1, 5, 15, 60, 360]))

        now = timezone.now()
        stats = DispatchStats()

        # Recover rows abandoned by a process killed mid-run.
        NotificationRecipient.objects.filter(
            status=NotificationRecipient.DeliveryStatus.PROCESSING,
            locked_at__lt=now - timedelta(minutes=lock_ttl),
        ).update(
            status=NotificationRecipient.DeliveryStatus.PENDING,
            locked_at=None,
            locked_by="",
        )

        candidates = NotificationRecipient.objects.filter(
            status__in=[
                NotificationRecipient.DeliveryStatus.PENDING,
                NotificationRecipient.DeliveryStatus.FAILED,
            ],
            next_attempt_at__lte=now,
            notification__status__in=[
                Notification.Status.QUEUED,
                Notification.Status.PROCESSING,
            ],
        )
        if notification_id:
            candidates = candidates.filter(notification_id=notification_id)

        ids = list(
            candidates.order_by("next_attempt_at", "created_at").values_list(
                "id", flat=True
            )[:limit]
        )
        stats.claimed = len(ids)
        if dry_run or not ids:
            return stats

        worker_id = uuid.uuid4().hex
        NotificationRecipient.objects.filter(
            id__in=ids,
            status__in=[
                NotificationRecipient.DeliveryStatus.PENDING,
                NotificationRecipient.DeliveryStatus.FAILED,
            ],
        ).update(
            status=NotificationRecipient.DeliveryStatus.PROCESSING,
            locked_at=now,
            locked_by=worker_id,
        )
        claimed = list(
            NotificationRecipient.objects.filter(
                id__in=ids,
                status=NotificationRecipient.DeliveryStatus.PROCESSING,
                locked_by=worker_id,
            )
            .select_related("notification__school")
            .order_by("notification_id", "created_at")
        )
        stats.claimed = len(claimed)
        if not claimed:
            return stats

        processed = set()
        touched_campaigns = set()
        started = time.monotonic()

        by_campaign = defaultdict(list)
        for delivery in claimed:
            by_campaign[delivery.notification_id].append(delivery)

        for notification_id, deliveries in by_campaign.items():
            if time.monotonic() - started > time_budget:
                break
            notification = deliveries[0].notification
            touched_campaigns.add(notification.id)

            Notification.objects.filter(
                pk=notification.id, status=Notification.Status.QUEUED
            ).update(status=Notification.Status.PROCESSING)

            sms_provider = cls._school_provider(
                notification.school_id, NotificationProvider.Channel.SMS
            )
            email_provider = cls._school_provider(
                notification.school_id, NotificationProvider.Channel.EMAIL
            )

            for delivery in deliveries:
                try:
                    if delivery.channel == NotificationRecipient.Channel.SMS:
                        if not sms_provider and not SMSService.system_provider_type():
                            cls._skip(
                                delivery,
                                "No SMS provider configured for this school.",
                                now=now,
                            )
                            cls._refund_sms(delivery, now=now)
                            stats.skipped += 1
                        else:
                            success, message = SMSService.send(
                                sms_provider,
                                delivery.recipient_contact,
                                notification.message_body,
                            )
                            if not success:
                                raise RuntimeError(message)
                            cls._mark_sent(
                                delivery,
                                (
                                    sms_provider.provider_type
                                    if sms_provider
                                    else SMSService.system_provider_type()
                                ),
                                now=now,
                            )
                            stats.sent += 1
                    else:
                        success, message = EmailService.send(
                            provider=email_provider,
                            to_email=delivery.recipient_contact,
                            subject=notification.title,
                            body=notification.message_body,
                            school_name=notification.school.name,
                        )
                        if not success:
                            raise RuntimeError(message)
                        cls._mark_sent(
                            delivery,
                            (
                                email_provider.provider_type
                                if email_provider
                                else "smtp"
                            ),
                            now=now,
                        )
                        stats.sent += 1
                except Exception as exc:
                    logger.warning(
                        "Notification delivery %s failed: %s", delivery.id, exc
                    )
                    terminal = cls._fail(
                        delivery,
                        exc,
                        max_attempts=max_attempts,
                        backoff=backoff,
                        now=now,
                    )
                    if terminal:
                        stats.failed += 1
                        if delivery.channel == NotificationRecipient.Channel.SMS:
                            cls._refund_sms(delivery, now=now)
                    else:
                        stats.deferred += 1
                processed.add(delivery.id)

            cls._sync_campaign_status(notification.id, now=now)
            close_old_connections()

        # Give claimed rows we did not reach back to the next cron run.
        remaining = [delivery.id for delivery in claimed if delivery.id not in processed]
        if remaining:
            NotificationRecipient.objects.filter(
                id__in=remaining,
                status=NotificationRecipient.DeliveryStatus.PROCESSING,
                locked_by=worker_id,
            ).update(
                status=NotificationRecipient.DeliveryStatus.PENDING,
                locked_at=None,
                locked_by="",
            )

        for campaign_id in touched_campaigns:
            cls._sync_campaign_status(campaign_id, now=now)

        return stats

    # ── Configuration helpers ─────────────────────────────────────
    @classmethod
    def _sms_provider_available(cls, school):
        return bool(
            cls._school_provider(school.id, NotificationProvider.Channel.SMS)
            or SMSService.system_provider_type()
        )

    @classmethod
    def _sms_feature_enabled(cls, school):
        from subscriptions.services.packages import package_has_feature
        from subscriptions.utils import get_active_subscription

        subscription = get_active_subscription(school)
        if not subscription or not subscription.plan:
            return False
        return package_has_feature(subscription.plan, "sms")

    @staticmethod
    def _school_provider(school_id, channel):
        return (
            NotificationProvider.objects.filter(
                school_id=school_id,
                channel=channel,
                is_active=True,
            )
            .order_by("-is_default", "name")
            .first()
        )

    # ── State transitions ─────────────────────────────────────────
    @classmethod
    def _mark_sent(cls, delivery, provider_key, *, now):
        delivery.status = NotificationRecipient.DeliveryStatus.SENT
        delivery.sent_at = now
        delivery.attempts += 1
        delivery.error_message = ""
        delivery.provider = provider_key or ""
        delivery.locked_at = None
        delivery.locked_by = ""
        delivery.next_attempt_at = None
        delivery.save(
            update_fields=[
                "status",
                "sent_at",
                "attempts",
                "error_message",
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
        delivery.error_message = str(exc)[:2000]
        delivery.status = NotificationRecipient.DeliveryStatus.FAILED
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
                "error_message",
                "next_attempt_at",
                "locked_at",
                "locked_by",
                "updated_at",
            ]
        )
        return terminal

    @classmethod
    def _skip(cls, delivery, reason, *, now):
        delivery.status = NotificationRecipient.DeliveryStatus.SKIPPED
        delivery.attempts += 1
        delivery.error_message = str(reason)[:2000]
        delivery.next_attempt_at = None
        delivery.locked_at = None
        delivery.locked_by = ""
        delivery.save(
            update_fields=[
                "status",
                "attempts",
                "error_message",
                "next_attempt_at",
                "locked_at",
                "locked_by",
                "updated_at",
            ]
        )

    @classmethod
    def _refund_sms(cls, delivery, *, now):
        """Return this delivery's reserved credits exactly once."""
        if delivery.channel != NotificationRecipient.Channel.SMS:
            return
        if not delivery.credit_cost or delivery.credit_refunded:
            return

        with transaction.atomic():
            updated = NotificationRecipient.objects.filter(
                pk=delivery.pk, credit_refunded=False
            ).update(credit_refunded=True)
            if not updated:
                return

            wallet, _ = SMSWallet.objects.get_or_create(
                school_id=delivery.notification.school_id
            )
            wallet = SMSWallet.objects.select_for_update().get(pk=wallet.pk)
            wallet.balance += delivery.credit_cost
            wallet.save(update_fields=["balance", "updated_at"])
            SMSLedgerEntry.objects.create(
                school_id=delivery.notification.school_id,
                kind=SMSLedgerEntry.Kind.REFUND,
                credits=delivery.credit_cost,
                balance_after=wallet.balance,
                description=(
                    f"Refund for failed SMS to {delivery.recipient_name or 'recipient'}"
                ),
                notification_id=delivery.notification_id,
            )
        delivery.credit_refunded = True

    @classmethod
    def _sync_campaign_status(cls, notification_id, *, now):
        notification = Notification.objects.filter(pk=notification_id).first()
        if notification is None:
            return

        rows = NotificationRecipient.objects.filter(notification_id=notification_id)
        pending = rows.filter(
            status__in=[
                NotificationRecipient.DeliveryStatus.PENDING,
                NotificationRecipient.DeliveryStatus.PROCESSING,
            ]
        ).exists()
        retryable = rows.filter(
            status=NotificationRecipient.DeliveryStatus.FAILED,
            next_attempt_at__isnull=False,
        ).exists()

        if pending or retryable:
            if notification.status != Notification.Status.PROCESSING:
                Notification.objects.filter(pk=notification_id).update(
                    status=Notification.Status.PROCESSING
                )
            return

        counts = {
            row["status"]: row["total"]
            for row in rows.values("status").annotate(total=Count("id"))
        }
        sent = counts.get(NotificationRecipient.DeliveryStatus.SENT, 0)
        total = sum(counts.values())

        if sent and sent == total:
            status = Notification.Status.SENT
        elif sent:
            status = Notification.Status.PARTIAL
        else:
            status = Notification.Status.FAILED

        Notification.objects.filter(pk=notification_id).update(
            status=status,
            sent_at=now,
            completed_at=now,
        )
