from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from core.permissions import effective_keys


def needs_teacher_scope(user):
    return user.role == "teacher" and "school.manage" not in effective_keys(user)


def assigned_class_ids(user, term=None):
    from academics.models import ClassTeacher, SubjectTeacher
    profile = getattr(user, "staff_profile", None)
    if profile is None:
        return set()
    classes = ClassTeacher.objects.filter(school_id=user.school_id, teacher=profile, is_active=True)
    subjects = SubjectTeacher.objects.filter(school_id=user.school_id, teacher=profile, is_active=True)
    year_scope = Q(academic_year=term.academic_year) if term else Q(academic_year__is_current=True)
    classes = classes.filter(year_scope | Q(academic_year__isnull=True))
    subjects = subjects.filter(year_scope | Q(academic_year__isnull=True))
    term_scope = Q(term=term) if term else Q(term__is_current=True)
    subjects = subjects.filter(term_scope | Q(term__isnull=True))
    return set(classes.values_list("klass_id", flat=True)) | set(subjects.values_list("klass_id", flat=True))


def ensure_teacher_assignment(user, klass, term=None, subject=None):
    if not needs_teacher_scope(user):
        return
    if subject is None:
        allowed = klass.pk in assigned_class_ids(user, term)
    else:
        from academics.models import SubjectTeacher
        assignments = SubjectTeacher.objects.filter(school_id=user.school_id, teacher__user=user, klass=klass, subject=subject, is_active=True)
        year_scope = Q(academic_year=term.academic_year) if term else Q(academic_year__is_current=True)
        term_scope = Q(term=term) if term else Q(term__is_current=True)
        allowed = assignments.filter(year_scope | Q(academic_year__isnull=True)).filter(term_scope | Q(term__isnull=True)).exists()
    if not allowed:
        raise PermissionDenied("You are not assigned to this class or subject.")


class TeacherScopedQuerysetMixin:
    """Scope list/detail/export querysets, in addition to the action permission."""
    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if not needs_teacher_scope(self.request.user):
            return queryset
        paths = {"Student": "enrollments__klass_id", "Guardian": "student__enrollments__klass_id", "Enrollment": "klass_id", "Class": "pk", "Attendance": "klass_id", "AttendanceSummary": "klass_id", "StudentMark": "student_class_id", "StudentReport": "student_class_id", "StudentReportSubjectScore": "student_report__student_class_id"}
        path = paths.get(queryset.model.__name__)
        if path is None:
            return queryset
        from academics.models import Term
        from uuid import UUID
        term_id = self.kwargs.get("term_id") or self.request.query_params.get("term_id")
        term = None
        if term_id:
            try:
                term = Term.objects.filter(pk=UUID(str(term_id)), school_id=self.request.user.school_id).first()
            except (ValueError, TypeError):
                return queryset.none()
            if term is None:
                return queryset.none()
        filters = {f"{path}__in": assigned_class_ids(self.request.user, term)}
        enrollment_prefix = {"Student": "enrollments__", "Guardian": "student__enrollments__", "Enrollment": ""}.get(queryset.model.__name__)
        if enrollment_prefix is not None:
            filters[f"{enrollment_prefix}is_active"] = True
            if term:
                filters[f"{enrollment_prefix}academic_year_id"] = term.academic_year_id
            else:
                filters[f"{enrollment_prefix}academic_year__is_current"] = True
        return queryset.filter(**filters).distinct()
