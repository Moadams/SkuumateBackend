from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = "Seed system staff positions for all schools (delegates to seed_permissions)"

    def handle(self, *args, **kwargs):
        call_command("seed_permissions", verbosity=self.verbosity)