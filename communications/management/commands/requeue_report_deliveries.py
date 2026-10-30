"""Put skipped or failed report deliveries back on the queue."""
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from communications.models import ReportDelivery
from communications.services.report_distribution import ReportDistributionService


class Command(BaseCommand):
    help = "Requeue report deliveries after fixing a provider or guardian contact."

    def add_arguments(self, parser):
        parser.add_argument(
            "--status",
            choices=["skipped", "failed"],
            default="skipped",
            help="Which rows to requeue (default: skipped).",
        )
        parser.add_argument(
            "--report",
            dest="report_id",
            default=None,
            help="Only requeue deliveries for this StudentReport UUID.",
        )
        parser.add_argument(
            "--channel",
            choices=["email", "sms"],
            default=None,
            help="Only requeue one channel.",
        )

    def handle(self, *args, **options):
        report_id = options.get("report_id")
        if report_id:
            try:
                report_id = str(UUID(str(report_id)))
            except ValueError as exc:
                raise CommandError("--report must be a valid UUID.") from exc

        status = (
            ReportDelivery.Status.SKIPPED
            if options["status"] == "skipped"
            else ReportDelivery.Status.FAILED
        )
        count = ReportDistributionService.requeue(
            status=status,
            report_id=report_id,
            channel=options.get("channel"),
        )
        self.stdout.write(f"Requeued {count} report delivery row(s).")
