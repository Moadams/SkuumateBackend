from django.db import transaction

from accounts.models import User
from schools.models import ProspectiveSchool, School
from schools.services.school import SchoolService


class ProspectiveSchoolService:
    @transaction.atomic
    def approve_prospective_school(self, prospective_school: ProspectiveSchool):
        """
        Approve a prospective school and create a new School instance.
        """
        if prospective_school.status != ProspectiveSchool.ProspectiveSchoolStatus.PENDING:
            raise ValueError("Only pending prospective schools can be approved.")

        # Create a new School instance
        new_school = School.objects.create(
            name=prospective_school.name,
            email=prospective_school.email,
            phone=prospective_school.phone,
            status=School.SchoolStatus.ACTIVE,
        )
        
        user_data = {
            "email": prospective_school.admin_email,
            "first_name": prospective_school.admin_first_name,
            "last_name": prospective_school.admin_last_name,
            "role": User.Role.ADMIN,
            "must_change_password": True,
            "school": new_school
        }

        school = SchoolService.activate_school_with_admin(new_school, user_data)
        
        # Update the status of the prospective school
        prospective_school.status = ProspectiveSchool.ProspectiveSchoolStatus.APPROVED
        prospective_school.save()

        return school

    def reject_prospective_school(self, prospective_school: ProspectiveSchool):
        """
        Reject a prospective school.
        """
        if prospective_school.status != ProspectiveSchool.ProspectiveSchoolStatus.PENDING:
            raise ValueError("Only pending prospective schools can be rejected.")

        prospective_school.status = ProspectiveSchool.ProspectiveSchoolStatus.REJECTED
        prospective_school.save()