"""Deliver queued guardian/staff broadcast notifications.

Intended to run from cPanel cron on shared hosting, where a long-running
worker is not available::

    */5 * * * * cd /home/USER/project && \
      /home/USER/virtualenv/.../python manage.py \
      dispatch_notifications --limit 25 --time-budget 50 \
      >> /home/USER/logs/notification_dispatch.log 2>&1
"""
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from communications.services.broadcast import BroadcastService


class Command(BaseCommand):
    help = "Send queued broadcast notification emails and SMS messages."

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
            "--notification",
            dest="notification_id",
            default=None,
            help="Only process deliveries for this Notification UUID.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count due deliveries without claiming or sending.",
        )

    def handle(self, *args, **options):
        notification_id = options.get("notification_id")
        if notification_id:
            try:
                notification_id = str(UUID(str(notification_id)))
            except ValueError as exc:
                raise CommandError("--notification must be a valid UUID.") from exc

        stats = BroadcastService.dispatch(
            limit=options.get("limit"),
            time_budget=options.get("time_budget"),
            notification_id=notification_id,
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
