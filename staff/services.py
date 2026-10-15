from django.db.utils import IntegrityError
from django.utils import timezone

from accounts.models import User
from accounts.utils.password_reset import generate_password_setup_link
from core.email import send_staff_welcome_mail
from staff.enums.employment_type import EmploymentType
from staff.models import StaffPosition, StaffProfile


class StaffService:
    @staticmethod
    def create_staff(school, user_data, position_name=None):
        """
        Create a new staff member for the given school.
        """
        # Create the user
        try:
            user = User.objects.create_user(
                email=user_data.get("email"),
                phone=user_data.get("phone"),
                first_name=user_data.get("first_name"),
                last_name=user_data.get("last_name"),
                role=user_data.get("role", User.Role.STAFF),
                must_change_password=user_data.get("must_change_password", True),
                school=school,
            )
        except IntegrityError as e:
            message = "A user with this email already exists." if "email" in str(e).lower() else f"Failed to create user: {str(e)}"
            raise ValueError(message)

        if position_name is None:
            if user_data.get("role") == User.Role.TEACHER:
                position_name = "Teacher"
            elif user_data.get("role") == User.Role.ADMIN:
                position_name = "Administrator"
            elif user_data.get("role") == User.Role.STAFF:
                position_name = "Staff"
            elif user_data.get("role") == User.Role.FINANCE_MANAGER:
                position_name = "Accountant"

        position = StaffPosition.objects.filter(school=school, name=position_name).first() if position_name else None
        
        # Assign the user to the school
        staff_data = {
            "first_name": user_data.get("first_name"),
            "last_name": user_data.get("last_name"),
            "user": user,
            "school": school,
            "role": user_data.get("role", User.Role.STAFF),
            "date_joined": user_data.get("date_joined", timezone.now().date()),
            "employee_id": user_data.get("employee_id",None),
            "employment_type": user_data.get("employment_type", EmploymentType.FULL_TIME),
            "email": user_data.get("email",None),
            "phone": user_data.get("phone",None),
            "address": user_data.get("address",None),
            "profile_photo": user_data.get("profile_photo",None),
        }
        staff_profile = StaffProfile.objects.create(**staff_data)
        staff_profile.positions.add(position) if position else None

        send_staff_welcome_mail(
            staff_name=staff_profile.first_name,
            staff_email=staff_profile.email,
            reset_link=generate_password_setup_link(user),
            school_name=school.name
        )
        return user

    @staticmethod
    def delete_staff(staff):
        if staff.user and staff.user.is_root_admin:
            raise ValueError("Cannot delete a root administrator account.")
        if staff.user:
            staff.user.delete()
        staff.delete()
        return True