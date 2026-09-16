from django.core.management.base import BaseCommand

from ...sync import seed_platform_permissions


class Command(BaseCommand):
    help = "Seed / refresh the platform permission registry (idempotent)."

    def handle(self, *args, **options):
        result = seed_platform_permissions(verbosity=1)
        self.stdout.write(
            self.style.SUCCESS(
                f"Platform permissions synced: {result['created']} created, {result['updated']} updated."
            )
        )