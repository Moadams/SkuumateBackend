from django.core.management.base import BaseCommand
from django.db import transaction


SYSTEM_POSITIONS = [
    {
        "name": "Administrator",
        "description": "Full access to all school management features.",
        "keys": None,  # all registry keys
    },
    {
        "name": "Teacher",
        "description": (
            "Access to student records, attendance marking, "
            "and score entry for assigned classes."
        ),
        "keys": [
            "school.manage",
            "students.view",
            "attendance.view", "attendance.mark", "attendance.edit",
            "exams.view", "exams.enter_scores",
            "reports.view",
            "announcements.view",
            "academics.view",
            "class.teach",
            "dashboard.teacher",
            "settings.view",
        ],
    },
    {
        "name": "Accountant",
        "description": (
            "Access to finance management, fee structures, "
            "payments, and financial reports."
        ),
        "keys": [
            "school.manage",
            "students.view",
            "finance.view", "finance.manage_fees",
            "finance.record_payments", "finance.export",
            "reports.view", "reports.export",
            "announcements.view",
            "dashboard.finance",
            "settings.view",
        ],
    },
]


class Command(BaseCommand):
    help = (
        "Seed the permission registry and system positions "
        "for all schools. Idempotent."
    )

    @transaction.atomic
    def handle(self, *args, **kwargs):
        from schools.models import School
        from staff.models import PermissionKey
        from staff.permission_registry import PERMISSION_DEFS, PERMISSION_KEYS

        registry_created = 0
        registry_updated = 0
        for definition in PERMISSION_DEFS:
            _, created = PermissionKey.objects.update_or_create(
                key=definition["key"],
                defaults={
                    "module": definition["module"],
                    "label": definition["label"],
                    "description": definition.get("description", ""),
                    "is_system": True,
                },
            )
            if created:
                registry_created += 1
            else:
                registry_updated += 1

        all_keys = PERMISSION_KEYS
        schools = School.objects.filter(
            status=School.SchoolStatus.ACTIVE
        )

        if not schools.exists():
            self.stdout.write(
                self.style.WARNING(
                    "Registry seeded (%d created, %d updated). "
                    "No active schools found — system positions will be "
                    "seeded when schools are created."
                    % (registry_created, registry_updated)
                )
            )
            return

        positions_created = 0
        positions_updated = 0

        for school in schools:
            c, u = self._seed_positions_for_school(school, all_keys)
            positions_created += c
            positions_updated += u

        self.stdout.write(self.style.SUCCESS(
            "Done — permission registry: %d created, %d updated. "
            "Positions: %d created, %d (re)wired across %d school(s)."
            % (
                registry_created,
                registry_updated,
                positions_created,
                positions_updated,
                schools.count(),
            )
        ))

    def _seed_positions_for_school(self, school, all_keys):
        from staff.models import PermissionKey
        from staff.models import StaffPosition

        created_count = 0
        updated_count = 0

        for pos_data in SYSTEM_POSITIONS:
            keys = pos_data["keys"] if pos_data["keys"] is not None else all_keys
            permission_objs = PermissionKey.objects.filter(key__in=keys)
            position_qs = StaffPosition.objects.filter(
                school=school,
                name=pos_data["name"],
            )
            if position_qs.exists():
                position = position_qs.first()
                position.description = pos_data["description"]
                position.is_system = True
                position.save()
                updated_count += 1
            else:
                position = StaffPosition.objects.create(
                    school=school,
                    name=pos_data["name"],
                    description=pos_data["description"],
                    is_system=True,
                )
                created_count += 1
            position.permissions.set(permission_objs)

        return created_count, updated_count