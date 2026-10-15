from rest_framework.permissions import BasePermission

from core.access import school_access_allowed
from core.permissions import effective_keys


def school_permission(*, read=None, write=None, create=None, edit=None, delete=None):
    """Explicit action keys; an omitted action is denied, never inferred."""
    class SchoolActionPermission(BasePermission):
        action_keys = {"GET": read, "HEAD": read, "OPTIONS": read,  # noqa: RUF012
                       "POST": create or write, "PUT": edit or write,
                       "PATCH": edit or write, "DELETE": delete or write}

        def has_permission(self, request, view):
            user = request.user
            if not school_access_allowed(user):
                return False
            key = self.action_keys.get(request.method)
            if not key:
                return False
            keys = effective_keys(user)
            allowed = user.role == "admin" or "school.manage" in keys or key in keys
            if allowed:
                self.check_teacher_scope(request, view, key)
            return allowed

        def check_teacher_scope(self, request, view, key):
            from core.teacher_scope import (
                assigned_class_ids,
                ensure_teacher_assignment,
                needs_teacher_scope,
            )
            if not needs_teacher_scope(request.user) or not key.startswith(("students.", "attendance.", "exams.", "reports.")):
                return
            from rest_framework import serializers
            from rest_framework.exceptions import NotFound

            from academics.models import Class, Term
            from students.models import Student
            term_id = view.kwargs.get("term_id") or request.query_params.get("term_id")
            if not term_id and isinstance(request.data, dict):
                term_id = request.data.get("term_id")
            term = None
            if term_id:
                term_id = serializers.UUIDField().run_validation(term_id)
                term = Term.objects.filter(pk=term_id, school_id=request.user.school_id).first()
                if term is None:
                    raise NotFound()
            class_id = view.kwargs.get("class_id") or request.query_params.get("class_id")
            if not class_id and isinstance(request.data, dict):
                class_id = request.data.get("class_id") or request.data.get("student_class")
            if class_id:
                class_id = serializers.UUIDField().run_validation(class_id)
                klass = Class.objects.filter(pk=class_id, school_id=request.user.school_id).first()
                if klass is None:
                    raise NotFound()
                ensure_teacher_assignment(request.user, klass, term)
            student_id = view.kwargs.get("student_id")
            if student_id and not Student.objects.filter(pk=student_id, school_id=request.user.school_id, enrollments__klass_id__in=assigned_class_ids(request.user, term), enrollments__is_active=True).exists():
                raise NotFound()

    return SchoolActionPermission
