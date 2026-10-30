"""Backfill report deliveries for reports published before this feature.

Examples::

    manage.py enqueue_report_deliveries --school <uuid> --term <uuid>
    manage.py enqueue_report_deliveries --school <uuid> --class <uuid>
    manage.py enqueue_report_deliveries --school <uuid> --report <uuid>
"""
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from communications.services.report_distribution import ReportDistributionService
from exams.models import StudentReport


def _uuid(value, label):
    try:
        return str(UUID(str(value)))
    except ValueError as exc:
        raise CommandError(f"--{label} must be a valid UUID.") from exc


class Command(BaseCommand):
    help = "Queue deliveries for already-published reports (backfill)."

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True, help="School UUID.")
        parser.add_argument("--report", dest="report_id", default=None)
        parser.add_argument("--term", dest="term_id", default=None)
        parser.add_argument("--class", dest="class_id", default=None)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count reports that would be queued without writing rows.",
        )

    def handle(self, *args, **options):
        if not any(
            options.get(key) for key in ("report_id", "term_id", "class_id")
        ):
            raise CommandError("Provide at least one of --report, --term, or --class.")

        school_id = _uuid(options["school"], "school")
        queryset = StudentReport.objects.filter(
            school_id=school_id, status=StudentReport.ReportStatus.PUBLISHED
        )
        if options.get("report_id"):
            queryset = queryset.filter(id=_uuid(options["report_id"], "report"))
        if options.get("term_id"):
            queryset = queryset.filter(term_id=_uuid(options["term_id"], "term"))
        if options.get("class_id"):
            queryset = queryset.filter(
                student_class_id=_uuid(options["class_id"], "class")
            )

        reports = list(
            queryset.select_related(
                "school", "student", "student_class", "term", "academic_year"
            )
        )
        if options.get("dry_run"):
            self.stdout.write(
                f"[dry-run] {len(reports)} published report(s) would be queued."
            )
            return

        queued = ReportDistributionService.enqueue(reports)
        self.stdout.write(
            f"Queued {queued} delivery row(s) for {len(reports)} report(s)."
        )
