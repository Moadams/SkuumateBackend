from django.utils import timezone

from accounts.models import User
from staff.models import StaffPosition, StaffProfile


class StaffService:
    @staticmethod
    def create_staff(school, user_data, position_name=None):
        """
        Create a new staff member for the given school.
        """
        # Create the user
        user = User.objects.create_user(**user_data)
        position = StaffPosition.objects.filter(school=school, name=position_name).first() if position_name else None
        
        # Assign the user to the school
        staff_data = {
            "first_name": user_data.get("first_name"),
            "last_name": user_data.get("last_name"),
            "user": user,
            "school": school,
            "role": user_data.get("role", User.Role.STAFF),
            "date_joined": user_data.get("date_joined", timezone.now().date()),
        }
        staff_profile = StaffProfile.objects.create(**staff_data)
        staff_profile.positions.add(position) if position else None
        
        return user