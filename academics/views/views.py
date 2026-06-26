from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.views import APIView

from core.mixins import AuditLogMixin
from core.models import AuditLog
from core.permissions import IsAdmin, IsAdminOrTeacher, IsAdminOrTeacherReadOnly
from core.responses import ApiResponse
from core.utils import log_action

from ..models import (
    Class,
    ClassSubject,
    GradeScale,
    GradingSystem,
    SubjectTeacher,
    Term,
    TimeTableSlot,
)
from ..serializers import (
    BulkGradeScaleSerializer,
    BulkSubjectTeacherSerializer,
    ClassSubjectTeacherSummarySerializer,
    GradeResolverSerializer,
    GradeScaleSerializer,
    SubjectTeacherWriteSerializer,
    TimeTableSlotSerializer,
)

# ─── Grade Scales ─────────────────────────────────────────────────

class GradeScaleBulkSetView(APIView):
    """
    Replaces all grade scales for a grading system at once.

    This is the primary way to define grades —
    submit the complete set and we validate the entire
    range for gaps, overlaps and coverage.
    """
    permission_classes = [IsAdmin]

    def get_grading_system(self, pk, school):
        try:
            return GradingSystem.objects.prefetch_related(
                "grade_scales"
            ).get(pk=pk, school=school)
        except GradingSystem.DoesNotExist:
            return None

    def get(self, request, pk):
        """Returns all grade scales for a grading system."""
        system = self.get_grading_system(pk, request.user.school)
        if not system:
            return ApiResponse.error(
                message="Grading system not found.",
                status_code=404,
            )

        scales = system.grade_scales.all().order_by(
            "position", "-min_score"
        )
        return ApiResponse.success(
            data={

                "grade_scales": GradeScaleSerializer(
                    scales, many=True
                ).data,
            }
        )

    def post(self, request, pk):
        """
        Bulk set grade scales — replaces all existing ones.
        Validates the entire range before saving anything.
        """
        system = self.get_grading_system(pk, request.user.school)
        if not system:
            return ApiResponse.error(
                message="Grading system not found.",
                status_code=404,
            )

        serializer = BulkGradeScaleSerializer(
            data=request.data,
            context={"grading_system": system},
        )
        serializer.is_valid(raise_exception=True)

        grades = serializer.validated_data["grades"]

        # All validations passed — replace existing scales
        with transaction.atomic():
            system.grade_scales.all().delete()

            created_scales = []
            for position, grade_data in enumerate(
                sorted(
                    grades,
                    key=lambda x: float(x["min_score"]),
                    reverse=True,
                )
            ):
                grade_data_copy = grade_data.copy()
                grade_data_copy.pop("position", None)  # Remove position if present in request data
                scale = GradeScale.objects.create(
                    grading_system=system,
                    school=request.user.school,
                    position=position,
                    **grade_data_copy,
                )
                created_scales.append(scale)

        log_action(
            action=AuditLog.Action.UPDATE,
            resource="GradingSystem",
            resource_id=str(system.pk),
            description=(
                f"Grade scales updated for '{system.name}' — "
                f"{len(created_scales)} grades defined"
            ),
            request=request,
        )

        return ApiResponse.success(
            data={

                "grade_scales": GradeScaleSerializer(
                    created_scales, many=True
                ).data,
            },
            message=(
                f"{len(created_scales)} grade scales saved successfully."
            ),
        )


class GradeScaleUpdateView(APIView):
    """Update or delete a single grade scale."""
    permission_classes = [IsAdmin]

    def get_scale(self, pk, school):
        try:
            return GradeScale.objects.select_related(
                "grading_system"
            ).get(pk=pk, school=school)
        except GradeScale.DoesNotExist:
            return None

    def patch(self, request, pk):
        scale = self.get_scale(pk, request.user.school)
        if not scale:
            return ApiResponse.error(
                message="Grade scale not found.", status_code=404
            )

        serializer = GradeScaleSerializer(
            scale, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)

        # After updating this scale, verify the whole system
        # still has no gaps or overlaps
        updated_data = serializer.validated_data
        other_scales = scale.grading_system.grade_scales.exclude(
            pk=scale.pk
        ).values(
            "grade", "min_score", "max_score",
        )

        # Build a temporary full list to validate against
        temp_grades = list(other_scales) + [{
            "grade": updated_data.get("grade", scale.grade),
            "min_score": updated_data.get("min_score", scale.min_score),
            "max_score": updated_data.get("max_score", scale.max_score),
        }]

        bulk_serializer = BulkGradeScaleSerializer(
            data={"grades": temp_grades},
            context={"grading_system": scale.grading_system},
        )
        if not bulk_serializer.is_valid():
            return ApiResponse.error(
                message="This update would create gaps or overlaps.",
                errors=bulk_serializer.errors,
                status_code=400,
            )

        serializer.save()

        log_action(
            action=AuditLog.Action.UPDATE,
            resource="GradeScale",
            resource_id=str(scale.pk),
            description=(
                f"Grade '{scale.grade}' updated in "
                f"'{scale.grading_system.name}'"
            ),
            request=request,
        )

        return ApiResponse.success(
            data=GradeScaleSerializer(scale).data,
            message="Grade scale updated successfully.",
        )

    def delete(self, request, pk):
        scale = self.get_scale(pk, request.user.school)
        if not scale:
            return ApiResponse.error(
                message="Grade scale not found.", status_code=404
            )

        # Must have at least 2 grades
        total = scale.grading_system.grade_scales.count()
        if total <= 2:
            return ApiResponse.error(
                message=(
                    "Cannot delete — a grading system must have "
                    "at least 2 grade bands."
                ),
                status_code=400,
            )

        scale.delete()
        return ApiResponse.success(
            message=f"Grade '{scale.grade}' removed successfully."
        )


class GradeResolverView(APIView):
    """
    Test endpoint — given a score, returns the matching grade.
    Useful for the frontend to preview grading before saving.
    """
    permission_classes = [IsAdminOrTeacher]

    def post(self, request, pk):
        from ..utils import resolve_grade

        try:
            system = GradingSystem.objects.get(
                pk=pk, school=request.user.school
            )
        except GradingSystem.DoesNotExist:
            return ApiResponse.error(
                message="Grading system not found.",
                status_code=404,
            )

        serializer = GradeResolverSerializer(
            data=request.data,
            context={"grading_system": system},
        )
        serializer.is_valid(raise_exception=True)

        score = serializer.validated_data["score"]
        grade = resolve_grade(system, score)

        if not grade:
            return ApiResponse.error(
                message=(
                    f"No grade found for score {score} in "
                    f"'{system.name}'. Check your grade ranges."
                ),
                status_code=404,
            )

        return ApiResponse.success(
            data={
                "score": float(score),
                "grade": grade.grade,
                "label": grade.label,
                "is_passing": grade.is_passing,
                "range": {
                    "min": float(grade.min_score),
                    "max": float(grade.max_score),
                },
            }
        )

class BulkSubjectTeacherAssignView(APIView):
    """
    Bulk assign teachers to class subjects in a single request.
    All items share the same academic year and optional term.

    Validates ALL items before saving ANY of them —
    so either the entire batch succeeds or nothing is saved.
    """
    permission_classes = [IsAdmin]

    def post(self, request):
        school = request.user.school
        serializer = BulkSubjectTeacherSerializer(
            data=request.data,
            context={"school": school},
        )
        serializer.is_valid(raise_exception=True)

        assignments_data = serializer.validated_data[
            "validated_assignments"
        ]

        created_list = []
        updated_list = []

        with transaction.atomic():
            for item in assignments_data:
                assignment, created = (
                    SubjectTeacher.objects.update_or_create(
                        school=school,
                        klass=item["klass"],
                        subject=item["subject"],
                        academic_year=item["academic_year"],
                        term=item["term"],
                        defaults={
                            "teacher": item["teacher"],
                            "is_active": True,
                        },
                    )
                )
                if created:
                    created_list.append(assignment)
                else:
                    updated_list.append(assignment)

        all_assignments = created_list + updated_list

        log_action(
            action=AuditLog.Action.CREATE,
            resource="SubjectTeacher",
            description=(
                f"Bulk assignment: {len(created_list)} created, "
                f"{len(updated_list)} updated"
            ),
            request=request,
            metadata={
                "created": len(created_list),
                "updated": len(updated_list),
            },
        )

        return ApiResponse.created(
            data={
                "summary": {
                    "total": len(all_assignments),
                    "created": len(created_list),
                    "updated": len(updated_list),
                },

            },
            message=(
                f"Bulk assignment complete — "
                f"{len(created_list)} created, "
                f"{len(updated_list)} updated."
            ),
        )


class ClassSubjectTeacherSummaryView(APIView):
    """
    Returns all subjects in a class along with their
    assigned teacher for a given academic year/term.

    Shows unassigned subjects too so the admin can see
    what still needs a teacher.
    """
    permission_classes = [IsAdminOrTeacher]

    def get(self, request, class_id):
        school = request.user.school
        academic_year_id = request.query_params.get("academic_year_id")
        term_id = request.query_params.get("term_id")

        # Validate class
        try:
            klass = Class.objects.get(
                id=class_id, school=school, is_active=True
            )
        except Class.DoesNotExist:
            return ApiResponse.error(
                message="Class not found.", status_code=404
            )

        # Get all subjects assigned to this class
        class_subjects = (
            ClassSubject.objects
            .filter(school=school, klass=klass)
            .select_related("subject")
        )

        if not class_subjects.exists():
            return ApiResponse.success(
                data={
                    "class_id": str(klass.id),
                    "class_name": klass.name,
                    "total_subjects": 0,
                    "assigned": 0,
                    "unassigned": 0,
                    "subjects": [],
                }
            )

        # Build teacher lookup for this class
        teacher_qs = SubjectTeacher.objects.filter(
            school=school,
            klass=klass,
            is_active=True,
        ).select_related("teacher__user", "subject")

        if academic_year_id:
            teacher_qs = teacher_qs.filter(
                academic_year_id=academic_year_id
            )
        if term_id:
            teacher_qs = teacher_qs.filter(term_id=term_id)

        # Build lookup dict: subject_id → assignment
        teacher_map = {
            str(st.subject_id): st
            for st in teacher_qs
        }

        # Build summary
        subjects = []
        for cs in class_subjects:
            subject = cs.subject
            assignment = teacher_map.get(str(subject.id))
            subjects.append({
                "subject": subject,
                "teacher": (
                    assignment.teacher if assignment else None
                ),
                "assignment_id": (
                    assignment.id if assignment else None
                ),
            })

        serializer = ClassSubjectTeacherSummarySerializer(
            subjects, many=True
        )

        assigned_count = sum(
            1 for s in subjects if s["teacher"] is not None
        )

        return ApiResponse.success(
            data={
                "class_id": str(klass.id),
                "class_name": klass.name,
                "total_subjects": len(subjects),
                "assigned": assigned_count,
                "unassigned": len(subjects) - assigned_count,
                "subjects": serializer.data,
            }
        )



class TimeTableSlotListCreateView(
    AuditLogMixin, generics.ListCreateAPIView
):
    """List or create timetable slots for a class."""
    permission_classes = [IsAdminOrTeacherReadOnly]
    serializer_class = TimeTableSlotSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = [
        "subject__name",
        "teacher__user__first_name",
        "teacher__user__last_name",
    ]
    ordering_fields = ["start_time", "end_time", "created_at"]
    ordering = ["start_time"]
    audit_resource = "TimeTableSlot"
    pagination_class = None

    def get_queryset(self):
        return (
            TimeTableSlot.objects
            .filter(school=self.request.user.school, klass_id=self.kwargs["class_id"])
            .select_related(
                "klass", "subject", "teacher__user", "term"
            )
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)

    def perform_create(self, serializer):
        current_term = Term.objects.filter(school=self.request.user.school, is_current=True).first()
        serializer.save(school=self.request.user.school, term=current_term)

    def get_audit_description(self, instance):
        return f"Timetable slot created for {instance.klass.name}"

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["school"] = self.request.user.school
        current_term = Term.objects.filter(school=self.request.user.school, is_current=True).first()
        ctx["term"] = current_term
        return ctx

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return ApiResponse.created(
            data=serializer.data,
            message="Timetable slot created successfully"
        )
