"""Serve registered uploads only; private file paths are never public URLs."""
from pathlib import PurePosixPath

from django.http import FileResponse, Http404
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle

from core.access import school_access_allowed
from core.permissions import effective_keys
from core.teacher_scope import assigned_class_ids, needs_teacher_scope
from schools.models import School
from staff.models import StaffProfile
from students.models import Student


def image_response(field, private=False):
    content_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
    content_type = content_types.get(PurePosixPath(field.name).suffix.lower())
    if not content_type:
        raise Http404
    try:
        response = FileResponse(field.open("rb"), content_type=content_type)
    except (FileNotFoundError, OSError, ValueError):
        raise Http404
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store" if private else "public, max-age=300"
    if private:
        response["Vary"] = "Authorization"
    return response


def valid_path(path):
    return not ("\\" in path or path.startswith("/") or any(part in (".", "..", "") for part in path.split("/")))


class PublicLogoView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request, path):
        if not valid_path(path) or not path.startswith("schools/logos/"):
            raise Http404
        school = School.objects.filter(logo=path).first()
        if school is None:
            raise Http404
        return image_response(school.logo)


class PrivateMediaView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "private_media"

    def get(self, request, path):
        user = request.user
        if not valid_path(path):
            raise Http404
        if not user.is_superuser and not school_access_allowed(user):
            raise Http404
        if path.startswith("students/photos/"):
            records = Student.objects.filter(profile_photo=path)
            if not user.is_superuser:
                records = records.filter(school_id=user.school_id)
                keys = effective_keys(user)
                if user.role != "admin" and not {"school.manage", "students.view"}.intersection(keys):
                    records = records.filter(user_account=user)
                elif needs_teacher_scope(user):
                    records = records.filter(enrollments__klass_id__in=assigned_class_ids(user), enrollments__is_active=True)
        elif path.startswith("staff/photos/"):
            records = StaffProfile.objects.filter(profile_photo=path)
            if not user.is_superuser:
                records = records.filter(school_id=user.school_id)
                keys = effective_keys(user)
                if user.role != "admin" and not {"school.manage", "staff.view"}.intersection(keys):
                    records = records.filter(user=user)
        else:
            raise Http404
        record = records.first()
        if record is None:
            raise Http404
        return image_response(record.profile_photo, private=True)
