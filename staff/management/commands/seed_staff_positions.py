from django.core.management.base import BaseCommand


SYSTEM_POSITIONS = [
    {
        "name": "Administrator",
        "description": "Full access to all school management features.",
        "permissions": [
            "students.view", "students.create",
            "students.edit", "students.delete", "students.export",
            "attendance.view", "attendance.mark",
            "attendance.edit", "attendance.export",
            "exams.view", "exams.manage",
            "exams.enter_scores", "exams.export",
            "finance.view", "finance.manage_fees",
            "finance.record_payments", "finance.export",
            "staff.view", "staff.manage",
            "academics.view", "academics.manage",
            "reports.view", "reports.export",
            "announcements.view", "announcements.manage",
            "settings.view", "settings.manage",
            "dashboard.admin",
        ],
    },
    {
        "name": "Teacher",
        "description": (
            "Access to student records, attendance marking, "
            "and score entry."
        ),
        "permissions": [
            "students.view",
            "attendance.view", "attendance.mark",
            "exams.view", "exams.enter_scores",
            "reports.view",
            "announcements.view",
            "academics.view",
            "dashboard.teacher",
        ],
    },
    {
        "name": "Accountant",
        "description": (
            "Access to finance management, fee structures, "
            "payments, and financial reports."
        ),
        "permissions": [
            "students.view",
            "finance.view", "finance.manage_fees",
            "finance.record_payments", "finance.export",
            "reports.view", "reports.export",
            "announcements.view",
            "dashboard.finance",
        ],
    },
]


class Command(BaseCommand):
    help = "Seed system staff positions for all schools"

    def handle(self, *args, **kwargs):
        from schools.models import School
        from staff.models import StaffPosition

        schools = School.objects.filter(is_active=True)

        if not schools.exists():
            self.stdout.write(
                self.style.WARNING(
                    "No active schools found. "
                    "Positions will be seeded when schools are created."
                )
            )
            return

        total_created = 0
        total_skipped = 0

        for school in schools:
            for pos_data in SYSTEM_POSITIONS:
                _, created = StaffPosition.objects.get_or_create(
                    school=school,
                    name=pos_data["name"],
                    defaults={
                        "description": pos_data["description"],
                        "permissions": pos_data["permissions"],
                        "is_system": True,
                    },
                )
                if created:
                    total_created += 1
                else:
                    total_skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done — {total_created} positions created, "
            f"{total_skipped} already existed."
        ))