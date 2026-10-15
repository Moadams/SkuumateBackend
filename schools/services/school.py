import secrets
from django.db import transaction
from accounts.utils.password_reset import generate_password_setup_link
from core.email import send_welcome_school_email
from schools.models import School
from staff.management.commands.seed_permissions import SYSTEM_POSITIONS
from staff.services import StaffService

class SchoolService:
    @staticmethod
    def _seed_system_positions(school):

        from staff.models import PermissionKey, StaffPosition
        all_keys = list(PermissionKey.objects.values_list("key", flat=True))
        for pos_data in SYSTEM_POSITIONS:
            keys = pos_data["keys"] if pos_data["keys"] is not None else all_keys
            position, created = StaffPosition.objects.get_or_create(
                school=school,
                name=pos_data["name"],
                defaults={
                    "description": pos_data["description"],
                    "is_system": True,
                },
            )
            if created:
                position.is_system = True
            # permissions is a ManyToManyField — assign via .set()
            position.permissions.set(
                PermissionKey.objects.filter(key__in=keys)
            )

    @staticmethod
    @transaction.atomic
    def activate_school_with_admin(school: School, user_data: dict):
        SchoolService._seed_system_positions(school)
        temporary_password = secrets.token_urlsafe(16)
        user_data["password"] = temporary_password
        user = StaffService.create_staff(school, user_data, "Administrator")

        reset_link = generate_password_setup_link(user)
        
        send_welcome_school_email(
            admin_name=f"{user_data['first_name']} {user_data['last_name']}",
            admin_email=user_data['email'],
            reset_link=reset_link,
            school_name=school.name
        )
        return school
