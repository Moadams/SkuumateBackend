from rest_framework import serializers
from .models import Attendance, AttendanceSummary


class AttendanceRecordSerializer(serializers.ModelSerializer):
    """Single attendance record — used for retrieval."""
    student_name = serializers.CharField(
        source="student.full_name", read_only=True
    )
    student_id_number = serializers.CharField(
        source="student.student_id", read_only=True
    )
    class_name = serializers.CharField(
        source="klass.name", read_only=True
    )
    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name", read_only=True
    )

    class Meta:
        model = Attendance
        fields = [
            "id",
            "student",
            "student_name",
            "student_id_number",
            "klass",
            "class_name",
            "term",
            "date",
            "status",
            "remarks",
            "recorded_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "recorded_by_name", "created_at"]


class BulkAttendanceItemSerializer(serializers.Serializer):
    """Single item inside a bulk attendance submission."""
    student_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=Attendance.Status.choices)
    remarks = serializers.CharField(required=False, allow_blank=True)


class BulkAttendanceSerializer(serializers.Serializer):
    """
    Bulk mark attendance for a whole class on a given date.
    One request marks attendance for all students at once.
    """
    class_id = serializers.UUIDField()
    term_id = serializers.UUIDField()
    date = serializers.DateField()
    records = BulkAttendanceItemSerializer(many=True, allow_empty=False)

    def validate_date(self, value):
        import datetime
        if value > datetime.date.today():
            raise serializers.ValidationError(
                "Attendance cannot be marked for a future date."
            )
        return value

    def validate_class_id(self, value):
        from academics.models import Class
        school = self.context["school"]
        try:
            klass = Class.objects.get(
                id=value, school=school, is_active=True
            )
        except Class.DoesNotExist:
            raise serializers.ValidationError(
                "Class not found or inactive."
            )
        return klass

    def validate_term_id(self, value):
        from academics.models import Term
        school = self.context["school"]
        try:
            term = Term.objects.get(id=value, school=school)
        except Term.DoesNotExist:
            raise serializers.ValidationError(
                "Term not found."
            )
        return term

    def validate(self, attrs):
        from students.models import Student

        school = self.context["school"]
        klass = attrs["class_id"]     # already resolved to Class instance
        records = attrs["records"]
        student_ids = [str(r["student_id"]) for r in records]

        # Verify all students belong to this school and class
        valid_students = Student.objects.filter(
            id__in=student_ids,
            school=school,
            status="active",
            enrollments__klass=klass,
            enrollments__is_active=True,
        ).values_list("id", flat=True)

        valid_ids = [str(sid) for sid in valid_students]
        invalid = [
            sid for sid in student_ids if sid not in valid_ids
        ]
        if invalid:
            raise serializers.ValidationError({
                "records": (
                    f"{len(invalid)} student(s) are not enrolled "
                    f"in this class or do not belong to this school."
                )
            })

        # Rename resolved instances
        attrs["klass"] = attrs.pop("class_id")
        attrs["term"] = attrs.pop("term_id")
        return attrs


class AttendanceSummarySerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(
        source="klass.name", read_only=True
    )
    term_name = serializers.CharField(
        source="term.get_name_display", read_only=True
    )

    class Meta:
        model = AttendanceSummary
        fields = [
            "id",
            "klass",
            "class_name",
            "term",
            "term_name",
            "date",
            "total_students",
            "present_count",
            "absent_count",
            "late_count",
            "attendance_percentage",
        ]
        read_only_fields = fields


class UpdateAttendanceSerializer(serializers.Serializer):
    """Update a single student's attendance record."""
    status = serializers.ChoiceField(choices=Attendance.Status.choices)
    remarks = serializers.CharField(required=False, allow_blank=True)