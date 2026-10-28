"""Bulk import of students into a single class from an Excel workbook.

``ClassBulkImportService`` owns the whole workflow (class/term resolution,
file parsing, per-row persistence and photo attachment) and reports what
happened through a ``ClassBulkImportResult``. Views stay responsible for
turning that result into an HTTP response and for audit logging.
"""
from dataclasses import dataclass, field

from django.core.files import File
from django.db import transaction
from rest_framework import serializers

from academics.models import Class
from students.models import Enrollment, Student
from students.services.excel import parse_class_excel
from students.services.photo_archive import extracted_photo_map


@dataclass(frozen=True)
class ClassBulkImportResult:
    """Outcome of a class-bulk import run."""

    class_id: str
    class_name: str
    academic_year: str
    file_name: str
    photos_included: bool
    total_submitted: int
    created: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    all_rows_failed_validation: bool = False

    @property
    def created_count(self):
        return len(self.created)

    @property
    def failed_count(self):
        return len(self.failed)

    @property
    def success_rate(self):
        if self.total_submitted <= 0:
            return "0%"
        return f"{round((self.created_count / self.total_submitted) * 100)}%"

    def success_payload(self):
        return {
            "summary": {
                "class_name": self.class_name,
                "academic_year": self.academic_year,
                "total_submitted": self.total_submitted,
                "created": self.created_count,
                "failed": self.failed_count,
                "success_rate": self.success_rate,
            },
            "created": self.created,
            "failed": self.failed,
        }

    def all_failed_payload(self):
        return {
            "summary": {
                "total_submitted": self.total_submitted,
                "created": 0,
                "failed": self.failed_count,
                "parse_errors": self.failed,
            }
        }

    def status_message(self):
        message = (
            f"{self.created_count} of {self.total_submitted} students imported "
            f"into {self.class_name} successfully."
        )
        if self.failed_count:
            message += f" {self.failed_count} failed — check 'failed' for details."
        return message


class ClassBulkImportService:
    """Orchestrates a class-scoped bulk student import."""

    @staticmethod
    def run(school, *, class_id, file, photos_file=None):
        klass = ClassBulkImportService._resolve_class(school, class_id)
        academic_year = ClassBulkImportService._current_academic_year(school)
        ClassBulkImportService._validate_file(file)
        students_data, parse_errors = ClassBulkImportService._parse(file)

        result_kwargs = {
            "class_id": str(klass.id),
            "class_name": klass.name,
            "academic_year": academic_year.name,
            "file_name": file.name,
            "photos_included": bool(photos_file),
        }

        if not students_data and parse_errors:
            return ClassBulkImportResult(
                total_submitted=len(parse_errors),
                created=[],
                failed=[*parse_errors],
                all_rows_failed_validation=True,
                **result_kwargs,
            )

        created, failed = ClassBulkImportService._persist(
            school, klass, academic_year, students_data, parse_errors, photos_file
        )

        return ClassBulkImportResult(
            total_submitted=len(students_data) + len(parse_errors),
            created=created,
            failed=failed,
            **result_kwargs,
        )

    @staticmethod
    def _resolve_class(school, class_id):
        klass = Class.objects.filter(
            id=class_id, school=school, is_active=True
        ).first()
        if not klass:
            raise serializers.ValidationError("Class not found or inactive.")
        return klass

    @staticmethod
    def _current_academic_year(school):
        current_term = school.terms.filter(is_current=True).first()
        if not current_term:
            raise serializers.ValidationError(
                "No active academic year. Please set up an academic year and "
                "term first."
            )
        return current_term.academic_year

    @staticmethod
    def _validate_file(file):
        if not file:
            raise serializers.ValidationError(
                "No file uploaded. Please upload an .xlsx file."
            )
        if not file.name.endswith(".xlsx"):
            raise serializers.ValidationError(
                "Invalid file type. Only .xlsx files are supported."
            )

    @staticmethod
    def _parse(file):
        try:
            return parse_class_excel(file)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    @staticmethod
    def _persist(school, klass, academic_year, students_data, parse_errors, photos_file):
        created = []
        failed = [*parse_errors]

        with extracted_photo_map(photos_file) as photo_map:
            for student_data in students_data:
                row_num = student_data.pop("_row", None)
                photo_filename = student_data.pop("photo_filename", None)

                try:
                    with transaction.atomic():
                        guardian_data = student_data.pop("guardian", None)

                        student = Student.objects.create(
                            school=school, **student_data
                        )

                        Enrollment.objects.create(
                            school=school,
                            student=student,
                            klass=klass,
                            academic_year=academic_year,
                        )

                        ClassBulkImportService._attach_photo(
                            student, photo_filename, photo_map
                        )

                        created.append({
                            "student_id": str(student.id),
                            "student_id_number": student.student_id,
                            "name": student.full_name,
                        })
                except Exception as exc:
                    failed.append({
                        "row": row_num,
                        "name": (
                            f"{student_data.get('first_name', '')} "
                            f"{student_data.get('last_name', '')}"
                        ).strip(),
                        "errors": [str(exc)],
                    })

        return created, failed

    @staticmethod
    def _attach_photo(student, photo_filename, photo_map):
        if not photo_filename or not photo_map:
            return
        normalized = photo_filename.strip().lower()
        photo_path = photo_map.get(normalized)
        if not photo_path:
            return
        with open(photo_path, "rb") as handle:
            student.profile_photo.save(normalized, File(handle), save=True)
