"""Deliver queued guardian report emails/SMSs.

Intended to run from cPanel cron on shared hosting, where a long-running
worker is not available::

    */5 * * * * cd /home/USER/project && \
      /home/USER/virtualenv/.../python manage.py \
      dispatch_report_deliveries --limit 25 --time-budget 50 \
      >> /home/USER/logs/report_dispatch.log 2>&1
"""
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from communications.services.report_distribution import ReportDistributionService


class Command(BaseCommand):
    help = "Send queued report-card emails (PDF attached) and SMS summaries."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum delivery rows to claim in this run.",
        )
        parser.add_argument(
            "--time-budget",
            type=int,
            default=None,
            help="Stop after roughly this many seconds (shared hosts kill long jobs).",
        )
        parser.add_argument(
            "--channel",
            choices=["email", "sms"],
            default=None,
            help="Only process one channel.",
        )
        parser.add_argument(
            "--report",
            dest="report_id",
            default=None,
            help="Only process deliveries for this StudentReport UUID.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count due deliveries without claiming or sending.",
        )

    def handle(self, *args, **options):
        report_id = options.get("report_id")
        if report_id:
            try:
                report_id = str(UUID(str(report_id)))
            except ValueError as exc:
                raise CommandError("--report must be a valid UUID.") from exc

        stats = ReportDistributionService.dispatch(
            limit=options.get("limit"),
            time_budget=options.get("time_budget"),
            channel=options.get("channel"),
            report_id=report_id,
            dry_run=options.get("dry_run", False),
        )

        if options.get("dry_run"):
            self.stdout.write(
                f"[dry-run] {stats.claimed} delivery row(s) are due."
            )
            return

        self.stdout.write(
            "claimed={claimed} sent={sent} deferred={deferred} "
            "failed={failed} skipped={skipped}".format(**stats.as_dict())
        )
