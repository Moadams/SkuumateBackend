import logging
from datetime import datetime

from django.db import transaction
from django.template import Template, Context

from communications.models import Notification

from .email_service import EmailService
from .sms_service import SMSService

logger = logging.getLogger(__name__)


class NotificationSender:
    """Orchestrates resolving recipients and sending notifications."""

    @staticmethod
    @transaction.atomic
    def send(notification):
        """
        Resolve recipients for a notification and attempt delivery.

        Returns the notification with updated status and recipient records.
        """
        from ..models import NotificationRecipient, NotificationProvider

        school = notification.school
        recipients = NotificationSender._resolve_recipients(notification)

        if not recipients:
            notification.status = Notification.Status.FAILED
            notification.save(update_fields=["status"])
            return notification

        # Get the default active provider for the channel
        channel = notification.channel
        email_provider = None
        sms_provider = None
        if channel == Notification.Channel.BOTH:
            email_provider = NotificationProvider.objects.filter(
                school=school, channel=NotificationProvider.Channel.EMAIL, is_active=True, is_default=True,
            ).first() or NotificationProvider.objects.filter(
                school=school, channel=NotificationProvider.Channel.EMAIL, is_active=True,
            ).first()
            sms_provider = NotificationProvider.objects.filter(
                school=school, channel=NotificationProvider.Channel.SMS, is_active=True, is_default=True,
            ).first() or NotificationProvider.objects.filter(
                school=school, channel=NotificationProvider.Channel.SMS, is_active=True,
            ).first()
        else:
            provider = NotificationProvider.objects.filter(
                school=school, channel=channel, is_active=True, is_default=True,
            ).first() or NotificationProvider.objects.filter(
                school=school, channel=channel, is_active=True,
            ).first()

        if channel != NotificationProvider.Channel.BOTH and not provider:
            notification.status = Notification.Status.FAILED
            notification.save(update_fields=["status"])
            return notification

        sent_count = 0
        failed_count = 0
        
        for recipient_data in recipients:
            contact = recipient_data.get("contact")
            if not contact:
                NotificationRecipient.objects.create(
                    notification=notification,
                    recipient_type=recipient_data["type"],
                    recipient_id=recipient_data.get("id"),
                    recipient_name=recipient_data.get("name", ""),
                    recipient_contact="",
                    status="failed",
                    error_message="No contact info available",
                )
                failed_count += 1
                continue

            recipient = NotificationRecipient.objects.create(
                notification=notification,
                recipient_type=recipient_data["type"],
                recipient_id=recipient_data.get("id"),
                recipient_name=recipient_data.get("name", ""),
                recipient_contact=contact,
                status="pending",
            )

            try:
                if channel == NotificationProvider.Channel.BOTH:
                    # Send email
                    if email_provider and "@" in contact:
                        success, msg = EmailService.send(
                            email_provider, contact,
                            notification.title, notification.message_body,
                            school_name=school.name,
                        )
                        if not success:
                            logger.warning("Email failed for %s: %s", contact, msg)
                    # Send SMS
                    if sms_provider and "@" not in contact:
                        success, msg = SMSService.send(
                            sms_provider, contact, notification.message_body,
                        )
                        if not success:
                            logger.warning("SMS failed for %s: %s", contact, msg)
                    recipient.status = NotificationRecipient.DeliveryStatus.SENT
                elif channel == NotificationProvider.Channel.EMAIL:
                    if not email_provider:
                        email_provider = provider
                    success, msg = EmailService.send(
                        email_provider, contact,
                        notification.title, notification.message_body,
                        school_name=school.name,
                    )
                    recipient.status = NotificationRecipient.DeliveryStatus.SENT if success else NotificationRecipient.DeliveryStatus.FAILED
                    if not success:
                        recipient.error_message = msg
                elif channel == NotificationProvider.Channel.SMS:
                    success, msg = SMSService.send(
                        provider, contact, notification.message_body,
                    )
                    recipient.status = NotificationRecipient.DeliveryStatus.SENT if success else NotificationRecipient.DeliveryStatus.FAILED
                    if not success:
                        recipient.error_message = msg

                recipient.sent_at = datetime.now()
                recipient.save()
                if recipient.status == NotificationRecipient.DeliveryStatus.SENT:
                    sent_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                print("Delivery failed for %s: %s", contact, e)
                logger.exception("Delivery failed for %s: %s", contact, e)
                recipient.status = NotificationRecipient.DeliveryStatus.FAILED
                recipient.error_message = str(e)
                recipient.save()
                failed_count += 1

        notification.sent_at = datetime.now()
        if failed_count == 0:
            notification.status = Notification.Status.SENT
        elif sent_count > 0:
            notification.status = Notification.Status.PARTIAL
        else:
            notification.status = Notification.Status.FAILED
        notification.save(update_fields=["status", "sent_at"])

        return notification

    @staticmethod
    def _resolve_recipients(notification):
        """Return list of recipient dicts based on recipient_type."""
        from students.models import Student, Guardian
        from staff.models import StaffProfile

        school = notification.school
        recipient_type = notification.recipient_type
        metadata = notification.metadata or {}
        recipients = []

        if recipient_type == Notification.RecipientType.ALL_STUDENTS:
            students = Student.objects.filter(school=school, status=Student.Status.ACTIVE)
            for s in students:
                contact = s.email or s.phone_number
                if contact:
                    recipients.append({
                        "type": "student",
                        "id": s.id,
                        "name": s.full_name,
                        "contact": contact,
                    })

        elif recipient_type == Notification.RecipientType.ALL_STAFF:
            staff = StaffProfile.objects.filter(school=school, status="active")
            for s in staff:
                contact = s.email or s.phone
                if contact:
                    recipients.append({
                        "type": "staff",
                        "id": s.id,
                        "name": f"{s.first_name} {s.last_name}",
                        "contact": contact,
                    })

        elif recipient_type == Notification.RecipientType.SPECIFIC_STUDENTS:
            student_ids = metadata.get("recipient_ids", [])
            if student_ids:
                students = Student.objects.filter(id__in=student_ids, school=school)
                for s in students:
                    contact = s.email or s.phone_number
                    if contact:
                        recipients.append({
                            "type": "student",
                            "id": s.id,
                            "name": s.full_name,
                            "contact": contact,
                        })

        elif recipient_type == Notification.RecipientType.SPECIFIC_STAFF:
            staff_ids = metadata.get("recipient_ids", [])
            if staff_ids:
                staff = StaffProfile.objects.filter(id__in=staff_ids, school=school)
                for s in staff:
                    contact = s.email or s.phone
                    if contact:
                        recipients.append({
                            "type": "staff",
                            "id": s.id,
                            "name": f"{s.first_name} {s.last_name}",
                            "contact": contact,
                        })

        elif recipient_type == Notification.RecipientType.CLASS:
            class_id = metadata.get("class_id")
            if class_id:
                students = Student.objects.filter(
                    school=school,
                    status=Student.Status.ACTIVE,
                    enrollments__klass_id=class_id,
                    enrollments__is_active=True,
                ).distinct()
                for s in students:
                    contact = s.email or s.phone_number
                    if contact:
                        recipients.append({
                            "type": "student",
                            "id": s.id,
                            "name": s.full_name,
                            "contact": contact,
                        })

        elif recipient_type == Notification.RecipientType.GUARDIANS_OF:
            student_ids = metadata.get("recipient_ids", [])
            if student_ids:
                guardians = Guardian.objects.filter(
                    student_id__in=student_ids, school=school,
                )
                for g in guardians:
                    contact = g.phone or g.email
                    recipients.append({
                        "type": "guardian",
                        "id": g.id,
                        "name": f"{g.first_name} {g.last_name}",
                        "contact": contact,
                    })

        return recipients

    @staticmethod
    def render_template(template, variables):
        """Render a NotificationTemplate with the given variables."""
        subject_template = Template(template.subject) if template.subject else None
        body_template = Template(template.body)

        context = Context(variables)

        subject = subject_template.render(context) if subject_template else ""
        body = body_template.render(context)
        return subject, body
