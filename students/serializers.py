from rest_framework import serializers
from .models import Student, Guardian, Enrollment


class GuardianSerializer(serializers.ModelSerializer):

    class Meta:
        model = Guardian
        fields = [
            "id",
            "first_name",
            "last_name",
            "relationship",
            "phone",
            "email",
            "address",
            "is_primary",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class EnrollmentSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source="klass.name", read_only=True)
    academic_year_name = serializers.CharField(
        source="academic_year.name", read_only=True
    )

    class Meta:
        model = Enrollment
        fields = [
            "id",
            "klass",
            "class_name",
            "academic_year",
            "academic_year_name",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class StudentSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    guardians = GuardianSerializer(many=True, read_only=True)
    current_enrollment = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            "id",
            "student_id",
            "first_name",
            "last_name",
            "other_names",
            "full_name",
            "date_of_birth",
            "age",
            "gender",
            "profile_photo",
            "address",
            "status",
            "admission_date",
            "previous_school",
            "guardians",
            "current_enrollment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "student_id", "created_at", "updated_at"]

    def get_age(self, obj):
        import datetime
        today = datetime.date.today()
        dob = obj.date_of_birth
        return today.year - dob.year - (
            (today.month, today.day) < (dob.month, dob.day)
        )

    def get_current_enrollment(self, obj):
        enrollment = obj.enrollments.filter(
            academic_year__is_current=True,
            is_active=True,
        ).first()
        if enrollment:
            return EnrollmentSerializer(enrollment).data
        return None

class StudentMinimalSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Student
        fields = [
            "id",
            "student_id",
            "first_name",
            "last_name",
            "other_names",
            "full_name",
        ]
        read_only_fields = ["id", "student_id"]

class StudentCreateSerializer(serializers.ModelSerializer):
    """
    Used for creating a student — accepts guardian data
    and optional enrollment inline.
    """
    guardians = GuardianSerializer(many=True, required=False)
    class_id = serializers.UUIDField(write_only=True, required=False)
    academic_year_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = Student
        fields = [
            "first_name",
            "last_name",
            "other_names",
            "date_of_birth",
            "gender",
            "profile_photo",
            "address",
            "admission_date",
            "previous_school",
            "guardians",
            "class_id",
            "academic_year_id",
        ]

    

    def create(self, validated_data):
        from academics.models import Class, AcademicYear

        guardians_data = validated_data.pop("guardians", [])
        class_id = validated_data.pop("class_id", None)
        school = self.context["school"]

        # Create the student
        student = Student.objects.create(school=school, **validated_data)

        # Create guardians
        for guardian_data in guardians_data:
            Guardian.objects.create(
                student=student,
                school=school,
                **guardian_data,
            )

        # Optionally enroll immediately
        if class_id:
            try:
                klass = Class.objects.get(id=class_id, school=school)
                academic_year = AcademicYear.objects.get(
                    school=school, is_current=True
                )
                Enrollment.objects.create(
                    school=school,
                    student=student,
                    klass=klass,
                    academic_year=academic_year,
                )
            except (Class.DoesNotExist, AcademicYear.DoesNotExist):
                pass  # enrollment is optional — don't block student creation

        return student


class EnrollStudentSerializer(serializers.Serializer):
    """Enroll or transfer a student to a class."""
    class_id = serializers.UUIDField()
    academic_year_id = serializers.UUIDField()

    def validate(self, attrs):
        from academics.models import Class, AcademicYear
        school = self.context["school"]

        try:
            klass = Class.objects.get(
                id=attrs["class_id"], school=school, is_active=True
            )
        except Class.DoesNotExist:
            raise serializers.ValidationError({
                "class_id": "Class not found or inactive."
            })

        try:
            academic_year = AcademicYear.objects.get(
                id=attrs["academic_year_id"], school=school
            )
        except AcademicYear.DoesNotExist:
            raise serializers.ValidationError({
                "academic_year_id": "Academic year not found."
            })

        # Check if already enrolled for this academic year
        student = self.context.get("student")
        if student:
            existing = Enrollment.objects.filter(
                student=student,
                academic_year=academic_year,
                school=school,
                is_active=True,
            ).first()
            if existing:
                raise serializers.ValidationError(
                    f"Student is already enrolled in "
                    f"{existing.klass.name} for {academic_year.name}. "
                    f"Withdraw first before re-enrolling."
                )

        attrs["klass"] = klass
        attrs["academic_year"] = academic_year
        return attrs