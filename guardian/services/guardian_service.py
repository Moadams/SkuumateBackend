
from django.db import transaction

from accounts.models import User
from accounts.services import AccountService
from guardian.models import Guardian, GuardianStudent
from guardian.serializers import GuardianStudentSerializer
from schools.models import School


class GuardianService:
    def __init__(self):
        self.account_service = AccountService()

    @transaction.atomic
    def create_guardian(self, data, school: School):
        try:

            data["role"] = User.Role.GUARDIAN
            data["school"] = school
            user = self.account_service.create_account(data, school)
            data.pop("role")
            data['user_account'] = user
            if Guardian.objects.filter(**data).exists():
                raise ValueError("Guardian already exists")
            guardian = Guardian.objects.create(**data)

            return guardian
        except Exception as e:
            raise ValueError(str(e))

    @transaction.atomic
    def assign_student(self, data:GuardianStudentSerializer, school: School):
        data['school'] = school
        if GuardianStudent.objects.filter(**data).exists():
            raise ValueError("Student is already assigned to this guardian")
        return GuardianStudent.objects.create(**data)

    def get_guardian_students(self, user: User):
        try:
            guardian = Guardian.objects.get(user_account=user)
            return GuardianStudent.objects.filter(guardian=guardian)
        except Guardian.DoesNotExist:
            return GuardianStudent.objects.none()
