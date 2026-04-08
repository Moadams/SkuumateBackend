from django.core.management.base import BaseCommand
from accounts.models import User
from django.db import transaction


class Command(BaseCommand):
    help = "Seed a superadmin user"

    def add_arguments(self, parser):
        parser.add_argument("--email", type=str, required=True, default="superadmin@skuumate.com", help="Email of the superadmin")
        parser.add_argument("--password", type=str, default = "Admin@1234", required=True, help="Password for the superadmin")
        parser.add_argument("--first_name", type=str, default="Super", help="First name of the superadmin")
        parser.add_argument("--last_name", type=str, default="Admin", help="Last name of the superadmin")

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["email"]
        password = options["password"]
        first_name = options["first_name"]
        last_name = options["last_name"]

        if User.objects.filter(email=email).exists():
            self.stdout.write(self.style.WARNING(f"Superadmin with email {email} already exists. Skipping."))
            return
        
        User.objects.create_superuser(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=User.Role.SUPERADMIN
        )

        self.stdout.write(self.style.SUCCESS(f"Superadmin {email} created successfully."))

        