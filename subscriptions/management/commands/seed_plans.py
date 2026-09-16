from django.core.management.base import BaseCommand
from subscriptions.services.seeding import ensure_feature_catalog, seed_default_packages


class Command(BaseCommand):
    help = "Seed SkuuMate packages (legacy alias for seed_packages)"

    def handle(self, *args, **kwargs):
        ensure_feature_catalog()
        seed_default_packages(reset_entitlements=True)
        self.stdout.write(self.style.SUCCESS("Plans seeded via package configuration."))