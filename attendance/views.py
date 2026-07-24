import datetime

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.views import APIView

from core.mixins import ExportMixin
from core.models import AuditLog
from core.permissions import IsAdminOrTeacher
from core.responses import ApiResponse
from core.utils import log_action
from subscriptions.permissions import HasAttendanceModule

from .filters import AttendanceFilter, AttendanceSummaryFilter
from .models import Attendance, AttendanceSummary
from .serializers import (
    AttendanceRecordSerializer,
    AttendanceSummarySerializer,
    BulkAttendanceSerializer,
    UpdateAttendanceSerializer,
)
from .utils import mark_bulk_attendance

# ─── Bulk Mark Attendance ─────────────────────────────────────────

class BulkMarkAttendanceView(APIView):
    """
    Mark attendance for an entire class in one request.
    Creates new records or updates existing ones for the given date.
    Accessible by both admins and teachers.
    """
    permission_classes = [IsAdminOrTeacher]

    def post(self, request):
        school = request.user.school
        serializer = BulkAttendanceSerializer(
            data=request.data,
            context={"school": school},
        )
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        created, updated = mark_bulk_attendance(
            school=school,
            klass=data["klass"],
            term=data["term"],
            date=data["date"],
            records=data["records"],
            recorded_by=request.user,
        )

        log_action(
            action=AuditLog.Action.CREATE,
            resource="Attendance",
            resource_id=str(data["klass"].id),
            description=(
                f"Attendance marked for {data['klass'].name} "
                f"on {data['date']} — "
                f"{created} created, {updated} updated"
            ),
            request=request,
            metadata = {
                "date": str(data["date"]),
                "class": data["klass"].name,
                "created": created,
                "updated": updated,
                "total_processed": created + updated,
            }
        )

        return ApiResponse.created(
            data={
                "date": str(data["date"]),
                "class": data["klass"].name,
                "created": created,
                "updated": updated,
                "total_processed": created + updated,
            },
            message=(
                f"Attendance marked successfully. "
                f"{created} new, {updated} updated."
            ),
        )


# ─── Attendance List ──────────────────────────────────────────────

class AttendanceListView(ExportMixin, generics.ListAPIView):
    """
    Paginated, filtered list of individual attendance records.
    Useful for viewing a student's attendance history
    or a class's attendance on a specific date.
    """
    permission_classes = [IsAdminOrTeacher]
    serializer_class = AttendanceRecordSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = AttendanceFilter
    search_fields = [
        "student__first_name",
        "student__last_name",
        "student__student_id",
    ]
    ordering_fields = ["date", "status", "created_at"]
    ordering = ["-date"]

    def get_queryset(self):
        return (
            Attendance.objects
            .filter(school=self.request.user.school)
            .select_related(
                "student", "klass", "term", "recorded_by"
            )
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)


class AttendanceExportView(ExportMixin, generics.ListAPIView):
    permission_classes = [IsAdminOrTeacher, HasAttendanceModule]
    serializer_class = AttendanceRecordSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = AttendanceFilter
    search_fields = [
        "student__first_name",
        "student__last_name",
        "student__student_id",
    ]
    ordering = ["-date"]

    def get_queryset(self):
        return (
            Attendance.objects
            .filter(school=self.request.user.school)
            .select_related("student", "klass", "term", "recorded_by")
        )

    def get(self, request, *args, **kwargs):
        return self.export(request, *args, **kwargs)


# ─── Single Attendance Record ─────────────────────────────────────

class AttendanceDetailView(APIView):
    """Retrieve or update a single attendance record."""
    permission_classes = [IsAdminOrTeacher, HasAttendanceModule]

    def get_object(self, pk, school):
        try:
            return Attendance.objects.select_related(
                "student", "klass", "term", "recorded_by"
            ).get(pk=pk, school=school)
        except Attendance.DoesNotExist:
            return None

    def get(self, request, pk):
        record = self.get_object(pk, request.user.school)
        if not record:
            return ApiResponse.error(
                message="Attendance record not found.",
                status_code=404,
            )
        return ApiResponse.success(
            data=AttendanceRecordSerializer(record).data
        )

    def patch(self, request, pk):
        record = self.get_object(pk, request.user.school)
        if not record:
            return ApiResponse.error(
                message="Attendance record not found.",
                status_code=404,
            )
        serializer = UpdateAttendanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        record.status = serializer.validated_data["status"]
        record.remarks = serializer.validated_data.get(
            "remarks", record.remarks
        )
        record.recorded_by = request.user
        record.save()

        # Refresh the summary for this class/date
        from .models import AttendanceSummary
        try:
            summary = AttendanceSummary.objects.get(
                school=request.user.school,
                klass=record.klass,
                date=record.date,
            )
            summary.recompute()
        except AttendanceSummary.DoesNotExist:
            pass

        log_action(
            action=AuditLog.Action.UPDATE,
            resource="Attendance",
            resource_id=str(record.pk),
            description=(
                f"Attendance updated for {record.student.full_name} "
                f"on {record.date} → {record.status}"
            ),
            request=request,
        )

        return ApiResponse.success(
            data=AttendanceRecordSerializer(record).data,
            message="Attendance record updated successfully.",
        )


# ─── Class Attendance Sheet ───────────────────────────────────────

class ClassAttendanceSheetView(APIView):
    """
    Returns a full attendance sheet for a class on a given date.
    Includes all enrolled students with their status for that day.
    Useful for the teacher's attendance marking screen.
    """
    permission_classes = [IsAdminOrTeacher, HasAttendanceModule]

    def get(self, request, class_id):
        from academics.models import Class
        from students.models import Enrollment, Student

        school = request.user.school
        date_str = request.query_params.get("date")
        term_id = request.query_params.get("term_id")

        # Default to today if no date given
        try:
            date = (
                datetime.date.fromisoformat(date_str)
                if date_str
                else datetime.date.today()
            )
        except ValueError:
            return ApiResponse.error(
                message="Invalid date format. Use YYYY-MM-DD.",
                status_code=400,
            )

        # Validate class
        try:
            klass = Class.objects.get(
                id=class_id, school=school, is_active=True
            )
        except Class.DoesNotExist:
            return ApiResponse.error(
                message="Class not found.", status_code=404
            )

        # Get all active enrollments for this class
        enrollments = Enrollment.objects.filter(
            school=school,
            klass=klass,
            is_active=True,
        ).select_related("student")

        if term_id:
            enrollments = enrollments.filter(
                academic_year__terms__id=term_id
            )

        # Fetch existing attendance records for this class/date
        existing_records = {
            str(a.student_id): a
            for a in Attendance.objects.filter(
                school=school,
                klass=klass,
                date=date,
            )
        }

        # Build sheet — one row per student
        sheet = []
        for enrollment in enrollments:
            student = enrollment.student
            record = existing_records.get(str(student.id))
            sheet.append({
                "student_id": str(student.id),
                "student_name": student.full_name,
                "student_id_number": student.student_id,
                "status": record.status if record else None,
                "remarks": record.remarks if record else "",
                "attendance_id": str(record.id) if record else None,
                "marked": record is not None,
            })

        # Sort by student name
        sheet.sort(key=lambda x: x["student_name"])

        # Fetch summary for this class/date
        try:
            summary = AttendanceSummary.objects.get(
                school=school, klass=klass, date=date
            )
            summary_data = AttendanceSummarySerializer(summary).data
        except AttendanceSummary.DoesNotExist:
            summary_data = None

        return ApiResponse.success(
            data={
                "class_id": str(klass.id),
                "class_name": klass.name,
                "date": str(date),
                "is_marked": bool(existing_records),
                "summary": summary_data,
                "students": sheet,
            }
        )


# ─── Attendance Summary List ──────────────────────────────────────

class AttendanceSummaryListView(ExportMixin, generics.ListAPIView):
    """
    Daily attendance summaries per class.
    Useful for admin overview and dashboard.
    """
    permission_classes = [IsAdminOrTeacher]
    serializer_class = AttendanceSummarySerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = AttendanceSummaryFilter
    ordering_fields = [
        "date", "attendance_percentage",
        "present_count", "absent_count",
    ]
    ordering = ["-date"]

    def get_queryset(self):
        return (
            AttendanceSummary.objects
            .filter(school=self.request.user.school)
            .select_related("klass", "term")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)


class AttendanceSummaryExportView(ExportMixin, generics.ListAPIView):
    permission_classes = [IsAdminOrTeacher, HasAttendanceModule]
    serializer_class = AttendanceSummarySerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = AttendanceSummaryFilter
    ordering = ["-date"]

    def get_queryset(self):
        return (
            AttendanceSummary.objects
            .filter(school=self.request.user.school)
            .select_related("klass", "term")
        )

    def get(self, request, *args, **kwargs):
        return self.export(request, *args, **kwargs)


# ─── Student Attendance Report ────────────────────────────────────

class StudentAttendanceReportView(APIView):
    """
    Full attendance report for a single student.
    Shows day-by-day records plus summary stats for a term.
    """
    permission_classes = [IsAdminOrTeacher, HasAttendanceModule]

    def get(self, request, student_id):
        from django.db.models import Count

        from students.models import Student

        school = request.user.school
        term_id = request.query_params.get("term_id")

        try:
            student = Student.objects.get(
                id=student_id, school=school
            )
        except Student.DoesNotExist:
            return ApiResponse.error(
                message="Student not found.", status_code=404
            )

        records = Attendance.objects.filter(
            school=school, student=student
        ).select_related("klass", "term").order_by("-date")

        if term_id:
            records = records.filter(term_id=term_id)

        # Aggregate stats
        total = records.count()
        present = records.filter(
            status=Attendance.Status.PRESENT
        ).count()
        absent = records.filter(
            status=Attendance.Status.ABSENT
        ).count()
        late = records.filter(
            status=Attendance.Status.LATE
        ).count()

        attendance_pct = (
            round((present / total) * 100, 1) if total > 0 else 0
        )

        return ApiResponse.success(
            data={
                "student": {
                    "id": str(student.id),
                    "name": student.full_name,
                    "student_id": student.student_id,
                },
                "summary": {
                    "total_days": total,
                    "present": present,
                    "absent": absent,
                    "late": late,
                    "attendance_percentage": attendance_pct,
                },
                "records": AttendanceRecordSerializer(
                    records, many=True
                ).data,
            }
        )


# ─── Class Attendance Summary Report ─────────────────────────────

class ClassAttendanceReportView(APIView):
    """
    Attendance summary report for all students in a class
    for a given term — useful for generating class reports.
    """
    permission_classes = [IsAdminOrTeacher, HasAttendanceModule]

    def get(self, request, class_id):
        from academics.models import Class, Term
        from students.models import Enrollment, Student

        school = request.user.school
        term_id = request.query_params.get("term_id")

        try:
            klass = Class.objects.get(id=class_id, school=school)
        except Class.DoesNotExist:
            return ApiResponse.error(
                message="Class not found.", status_code=404
            )

        # Get enrolled students
        enrollments = Enrollment.objects.filter(
            school=school,
            klass=klass,
            is_active=True,
        ).select_related("student")

        if term_id:
            enrollments = enrollments.filter(
                academic_year__terms__id=term_id
            )

        report = []
        for enrollment in enrollments:
            student = enrollment.student
            records = Attendance.objects.filter(
                school=school,
                student=student,
                klass=klass,
            )
            if term_id:
                records = records.filter(term_id=term_id)

            total = records.count()
            present = records.filter(
                status=Attendance.Status.PRESENT
            ).count()
            absent = records.filter(
                status=Attendance.Status.ABSENT
            ).count()
            late = records.filter(
                status=Attendance.Status.LATE
            ).count()

            report.append({
                "student_id": str(student.id),
                "student_name": student.full_name,
                "student_id_number": student.student_id,
                "total_days": total,
                "present": present,
                "absent": absent,
                "late": late,
                "attendance_percentage": (
                    round((present / total) * 100, 1)
                    if total > 0 else 0
                ),
            })

        # Sort by attendance percentage descending
        report.sort(
            key=lambda x: x["attendance_percentage"], reverse=True
        )

        return ApiResponse.success(
            data={
                "class_id": str(klass.id),
                "class_name": klass.name,
                "total_students": len(report),
                "report": report,
            }
        )
