from academics.services import AcademicsService


class StudentService:
    def bulk_upload_students(self, school, validated_data):
        current_term = AcademicsService._current_term(school)
        if not current_term:
            raise ValueError("No current term found for the school.")

        academic_year = current_term.academic_year

        