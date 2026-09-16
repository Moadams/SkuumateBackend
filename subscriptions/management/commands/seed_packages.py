from django.core.management.base import BaseCommand
from subscriptions.models import Package
from subscriptions.services.seeding import ensure_feature_catalog, seed_default_packages


class Command(BaseCommand):
    help = "Seed SkuuMate platform features and default packages"

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-entitlements",
            action="store_true",
            help="Only create missing packages; do not reset existing feature/limit configuration.",
        )

    def handle(self, *args, **kwargs):
        features_created = ensure_feature_catalog()
        packages_created = seed_default_packages(
            reset_entitlements=not kwargs["keep_entitlements"]
        )

        self.stdout.write(
            self.style.SUCCESS(f"Features up to date ({features_created} created).")
        )
        for package in Package.objects.filter(is_public=True).order_by("display_order"):
            self.stdout.write(
                self.style.SUCCESS(
                    f"{package.name} — {package.currency} {package.price}/"
                    f"{package.get_billing_period_display().lower()} "
                    f"(setup: {package.currency} {package.setup_fee})"
                )
            )
        if packages_created:
            self.stdout.write(
                self.style.SUCCESS(f"Created {packages_created} new package(s).")
            )