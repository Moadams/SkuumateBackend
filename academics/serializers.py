from rest_framework import serializers
from .models import AcademicYear, Term, Subject, Class, ClassSubject, ClassTeacher


class AcademicYearSerializer(serializers.ModelSerializer):
    terms_count = serializers.SerializerMethodField()

    class Meta:
        model = AcademicYear
        fields = [
            "id",
            "name",
            "start_date",
            "end_date",
            "is_current",
            "terms_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_terms_count(self, obj):
        return obj.terms.count()

    def validate(self, attrs):
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        if start and end and end <= start:
            raise serializers.ValidationError({
                "end_date": "End date must be after start date."
            })
        return attrs


class TermSerializer(serializers.ModelSerializer):
    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all(),
        required=False,
        allow_null=True,
    )
    academic_year_name = serializers.CharField(
        source="academic_year.name", read_only=True
    )

    class Meta:
        model = Term
        fields = [
            "id",
            "academic_year",
            "academic_year_name",
            "name",
            "start_date",
            "end_date",
            "is_current",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "academic_year_name"]

    def validate(self, attrs):
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        if start and end and end <= start:
            raise serializers.ValidationError({
                "end_date": "End date must be after start date."
            })
        return attrs

    def create(self, validated_data):
        # Get school from the authenticated user's school
        school = self.context["request"].user.school
        
        # If academic_year is not provided, use the current academic year for the school
        if validated_data.get("academic_year") is None:
            try:
                current_academic_year = AcademicYear.objects.get(
                    school=school,
                    is_current=True,
                )
                validated_data["academic_year"] = current_academic_year
            except AcademicYear.DoesNotExist:
                raise serializers.ValidationError({
                     "Academic Year is required."
                })
        
        return super().create(validated_data)


class SubjectSerializer(serializers.ModelSerializer):

    class Meta:
        model = Subject
        fields = [
            "id",
            "name",
            "code",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ClassSubjectSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    subject_code = serializers.CharField(source="subject.code", read_only=True)

    class Meta:
        model = ClassSubject
        fields = ["id", "subject", "subject_name", "subject_code"]
        read_only_fields = ["id"]


class ClassTeacherSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="teacher.full_name", read_only=True)
    teacher_email = serializers.CharField(source="teacher.email", read_only=True)
    academic_year_name = serializers.CharField(
        source="academic_year.name", read_only=True
    )

    class Meta:
        model = ClassTeacher
        fields = [
            "id",
            "teacher",
            "teacher_name",
            "teacher_email",
            "academic_year",
            "academic_year_name",
            "is_active",
        ]
        read_only_fields = ["id"]


class ClassSerializer(serializers.ModelSerializer):
    current_student_count = serializers.IntegerField(read_only=True)
    subjects = ClassSubjectSerializer(
        source="class_subjects", many=True, read_only=True
    )
    teachers = ClassTeacherSerializer(
        source="class_teachers", many=True, read_only=True
    )

    class Meta:
        model = Class
        fields = [
            "id",
            "name",
            "description",
            "capacity",
            "is_active",
            "current_student_count",
            "subjects",
            "teachers",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "subjects", "teachers", "current_student_count"]


class AssignSubjectsSerializer(serializers.Serializer):
    """Bulk assign subjects to a class."""
    subject_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
    )

    def validate_subject_ids(self, value):
        school = self.context["school"]
        subjects = Subject.objects.filter(
            id__in=value,
            school=school,
            is_active=True,
        )
        if subjects.count() != len(value):
            raise serializers.ValidationError(
                "One or more subjects are invalid or do not belong to this school."
            )
        return value


class AssignTeacherSerializer(serializers.Serializer):
    """Assign a teacher to a class for an academic year."""
    teacher_id = serializers.UUIDField()
    academic_year_id = serializers.UUIDField()

    def validate(self, attrs):
        from accounts.models import User
        school = self.context["school"]

        try:
            teacher = User.objects.get(
                id=attrs["teacher_id"],
                school=school,
                role="teacher",
                is_active=True,
            )
        except User.DoesNotExist:
            raise serializers.ValidationError({
                "teacher_id": "Teacher not found in this school."
            })

        try:
            academic_year = AcademicYear.objects.get(
                id=attrs["academic_year_id"],
                school=school,
            )
        except AcademicYear.DoesNotExist:
            raise serializers.ValidationError({
                "academic_year_id": "Academic year not found."
            })

        attrs["teacher"] = teacher
        attrs["academic_year"] = academic_year
        return attrs