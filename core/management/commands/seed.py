from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import transaction


class Command(BaseCommand):
    help = "Run all seeders in the correct order (plans → superadmin)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            default="superadmin@skuumate.com",
            help="Superadmin email (passed to seed_superadmin)",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="Admin@1234",
            help="Superadmin password (passed to seed_superadmin)",
        )
        parser.add_argument(
            "--first-name",
            type=str,
            default="Super",
            help="Superadmin first name",
        )
        parser.add_argument(
            "--last-name",
            type=str,
            default="Admin",
            help="Superadmin last name",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            "\n  SkuuMate Database Seeder"
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        ))

        steps = [
            ("Subscription Plans", self._seed_plans),
            ("Superadmin User", lambda: self._seed_superadmin(options)),
        ]

        for step_name, step_fn in steps:
            self.stdout.write(f"\n▶  Seeding {step_name}...")
            try:
                step_fn()
                self.stdout.write(
                    self.style.SUCCESS(f"✔  {step_name} seeded successfully.")
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"✘  {step_name} failed: {e}")
                )
                raise  # re-raise to trigger transaction rollback

        self.stdout.write(self.style.SUCCESS(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            "\n  All seeders completed successfully! 🎉"
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        ))

    def _seed_plans(self):
        call_command("seed_plans", verbosity=0)

    def _seed_superadmin(self, options):
        call_command(
            "seed_superadmin",
            email=options["email"],
            password=options["password"],
            first_name=options["first_name"],
            last_name=options["last_name"],
            verbosity=0,
        )