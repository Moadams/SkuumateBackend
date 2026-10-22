from django.db import transaction

from academics.models import ClassTeacher, SubjectTeacher


class AcademicsService:

    @staticmethod
    def _current_term(school):
        from academics.models import Term
        return Term.objects.filter(school=school, is_current=True).first()


# Ghana Education Service BECE "Stanine" (Standard Nine) scale. Grades run 1–9
# with *lower* grades being better; BECE results are aggregated over the best
# six subjects (6 is the best possible aggregate). A score of 50 and above
# (grades 1–6) is treated as a pass.
GES_BECE_GRADING_SYSTEM_NAME = "GES BECE"

GES_BECE_GRADE_SCALES = [
    {"grade": "1", "label": "Highest", "min_score": "90.00", "max_score": "100.00", "is_passing": True},
    {"grade": "2", "label": "Higher", "min_score": "80.00", "max_score": "89.00", "is_passing": True},
    {"grade": "3", "label": "High", "min_score": "70.00", "max_score": "79.00", "is_passing": True},
    {"grade": "4", "label": "High Average", "min_score": "60.00", "max_score": "69.00", "is_passing": True},
    {"grade": "5", "label": "Average", "min_score": "55.00", "max_score": "59.00", "is_passing": True},
    {"grade": "6", "label": "Low Average", "min_score": "50.00", "max_score": "54.00", "is_passing": True},
    {"grade": "7", "label": "Low", "min_score": "45.00", "max_score": "49.00", "is_passing": False},
    {"grade": "8", "label": "Lower", "min_score": "40.00", "max_score": "44.00", "is_passing": False},
    {"grade": "9", "label": "Lowest", "min_score": "0.00", "max_score": "39.00", "is_passing": False},
]


class GradingSystemService:
    """Default grading systems seeded for a school."""

    @staticmethod
    def seed_ges_bece(school):
        """Create the GES BECE grading system (and its nine bands) for ``school``.

        Idempotent: safe to call more than once for the same school.
        """
        from django.db import transaction

        from academics.models import GradeScale, GradingSystem

        with transaction.atomic():
            grading_system, _ = GradingSystem.objects.get_or_create(
                school=school,
                name=GES_BECE_GRADING_SYSTEM_NAME,
                defaults={
                    "description": (
                        "Ghana Education Service BECE (Standard Nine) grading "
                        "scale."
                    ),
                    "max_score": 100,
                    "pass_mark": 50,
                },
            )
            for position, scale in enumerate(GES_BECE_GRADE_SCALES, start=1):
                GradeScale.objects.get_or_create(
                    grading_system=grading_system,
                    grade=scale["grade"],
                    defaults={
                        "school": school,
                        "label": scale["label"],
                        "min_score": scale["min_score"],
                        "max_score": scale["max_score"],
                        "is_passing": scale["is_passing"],
                        "position": position,
                    },
                )
        return grading_system


class ClassTeacherService:
    @staticmethod
    @transaction.atomic
    def assign_teacher_to_class(klass, teacher, assign_subjects=False):
        from academics.models import ClassTeacher
        school = klass.school

        # check whether the teacher is already assigned to this class
        if ClassTeacher.objects.filter(
            klass=klass,
            teacher=teacher
        ).exists():
            raise ValueError("This teacher is already assigned to this class.")

        # Get all the class subjects and assign to the teacher if that is confirmed by the user
        if assign_subjects:
            subject_ids = list (
                klass.class_subjects.values_list("subject_id", flat=True)
            )
            if subject_ids:
                already_assigned_subjects = set(
                    klass.class_subjects.filter(
                        subject_id__in=subject_ids
                    ).values_list("subject_id", flat=True)
                )
                to_assign_subjects = [s for s in klass.class_subjects.filter(subject_id__in=subject_ids) if s.subject_id not in already_assigned_subjects]
                SubjectTeacher.objects.bulk_create([
                    SubjectTeacher(
                        klass=klass,
                        subject=class_subject.subject,
                        teacher=teacher,
                        school=school
                    ) for class_subject in to_assign_subjects
                ])

        # Create a new assignment
        return ClassTeacher.objects.create(
            klass=klass,
            teacher=teacher,
            school = klass.school
        )
    

class ClassSubjectService:
    @staticmethod
    @transaction.atomic
    def assign_teacher_to_class_subject(class_subject, teacher):
        from academics.models import SubjectTeacher

        if SubjectTeacher.objects.filter(
            klass=class_subject.klass,
            subject=class_subject.subject,
            teacher=teacher,
            school=class_subject.klass.school
        ).exists():
            raise ValueError("This teacher is already assigned to this class subject.")

        return SubjectTeacher.objects.create(
            klass=class_subject.klass,
            subject=class_subject.subject,
            teacher=teacher,
            school=class_subject.klass.school
        )

    @staticmethod
    @transaction.atomic
    def assign_subjects_to_class(klass, subjects, assign_teacher=None):
        from academics.models import ClassSubject
        school = klass.school

        subjects_by_id = {subject.id: subject for subject in subjects}
        unique_subject_ids = list(subjects_by_id.values())
        if not unique_subject_ids:
            return {
                "class": str(klass.id),
                "created": 0,
                "skipped": 0,
                "assigned_subjects": [],
            }, "0 subject(s) assigned successfully."

        
        already_assigned = set(
            ClassSubject.objects.filter(
                school=klass.school,
                klass=klass,
                subject__in=subjects,
            ).values_list("subject_id", flat=True)
        )

        to_create = [s for s in subjects if s.id not in already_assigned]

        created = []
        if to_create:
            objs = [
                ClassSubject(school=klass.school, klass=klass, subject=subject)
                for subject in to_create
            ]
            created = ClassSubject.objects.bulk_create(objs)
        

        if assign_teacher and created:
            class_teacher_ids = list(
                ClassTeacher.objects.filter(
                    klass=klass,
                    school=school
                ).values_list("teacher_id", flat=True).distinct()
            )
            if class_teacher_ids:
                subject_ids = [cs.subject_id for cs in created]
                SubjectTeacher.objects.bulk_create([
                    SubjectTeacher(
                        klass=klass,
                        subject_id = subject_id,
                        teacher_id = teacher_id,
                        school = school
                    )
                    for subject_id in subject_ids
                    for teacher_id in class_teacher_ids
                ])
            
        data = {
            "class": str(klass.id),
            "created": len(created),
            "skipped": len(already_assigned),
            "assigned_subjects": [
                {
                    "id": str(cs.subject_id),
                    "name": cs.subject.name,
                }
                for cs in created
            ],
        }

        message = f"{len(created)} subject(s) assigned successfully."

        if already_assigned:
            message += f" {len(already_assigned)} already assigned."

        return data, message


    @staticmethod
    @transaction.atomic
    def delete_class_subject(class_subject):
        from academics.models import SubjectTeacher

        # Delete all subject teacher assignments for this class subject
        SubjectTeacher.objects.filter(
            klass=class_subject.klass,
            subject=class_subject.subject
        ).delete()

        # Delete the class subject itself
        class_subject.delete()
        return True