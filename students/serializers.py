import re
import secrets

from django.db import transaction
from rest_framework import serializers

from accounts.models import User
from students.utils import generate_user_email

from .models import Enrollment, Guardian, Promotion, PromotionBatch, Student


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

    def validate_phone(self, value):
        if not re.match(r"^\+?\d{7,15}$", value):
            raise serializers.ValidationError("Phone number must be between 7 and 15 digits, and can start with +.")
        return value

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


class StudentListSerializer(serializers.ModelSerializer):
    student_class = serializers.SerializerMethodField()
    profile_photo = serializers.SerializerMethodField()
    class Meta:
        model = Student
        fields = (
            "id",
            "student_id",
            "full_name",
            "email",
            "gender",
            "profile_photo",
            "status",
            "student_class"
        )

    def get_profile_photo(self, obj):
        request = self.context.get("request")
        if obj.profile_photo and request:
            return request.build_absolute_uri(obj.profile_photo.url)
        return None

    def get_student_class(self, obj):
        enrollment = obj.enrollments.filter(
            academic_year__is_current=True,
            is_active=True,
        ).first()
        if enrollment:
            return enrollment.klass.name
        return None

class StudentSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    guardians = GuardianSerializer(many=True, read_only=True)
    current_enrollment = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = (
            "id",
            "student_id",
            "first_name",
            "last_name",
            "other_names",
            "full_name",
            "date_of_birth",
            "age",
            "email",
            "phone_number",
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
        )
        read_only_fields = ("id", "student_id", "created_at", "updated_at")

    def get_age(self, obj):
        import datetime
        today = datetime.date.today()
        dob = obj.date_of_birth
        if dob is None:
            return None
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
    profile_photo = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = (
            "id",
            "student_id",
            "first_name",
            "last_name",
            "other_names",
            "full_name",
            "profile_photo",
        )
        read_only_fields = ("id", "student_id")

    def get_profile_photo(self, obj):
        request = self.context.get("request")
        if obj.profile_photo and request:
            return request.build_absolute_uri(obj.profile_photo.url)
        return None

class StudentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = [
            "first_name",
            "last_name",
            "other_names",
            "student_id",
            "date_of_birth",
            "gender",
            "profile_photo",
            "address",
            "admission_date",
            "previous_school",
            "status",
            "email",
            "phone_number"
        ]

    def validate_first_name(self, value):
        if not re.match(r"^[A-Za-zÀ-ÿ\s'-]+$", value):
            raise serializers.ValidationError("First name must contain only letters.")
        return value
    
    def validate_last_name(self, value):
        if not re.match(r"^[A-Za-zÀ-ÿ\s'-]+$", value):
            raise serializers.ValidationError("Last name must contain only letters.")
        return value
    
    def validate_other_names(self, value):
        if value and not re.match(r"^[A-Za-zÀ-ÿ\s'-]+$", value):
            raise serializers.ValidationError("Other names must contain only letters.")
        return value

    def validate_phone_number(self, value):
        if value and not re.match(r"^\+?\d{7,15}$", value):
            raise serializers.ValidationError("Phone number must be between 7 and 15 digits, and can start with +.")
        return value

    def validate_date_of_birth(self, value):
        import datetime
        today = datetime.date.today()
        if value > today:
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        
        return value
    
    def validate_admission_date(self, value):
        import datetime
        if value > datetime.date.today():
            raise serializers.ValidationError("Admission date cannot be in the future.")
        return value
    
    def validate_student_id(self, value):
        student = self.instance
        school = self.context["school"]
        if Student.objects.filter(school=school, student_id=value).exclude(id=student.id).exists():
            raise serializers.ValidationError("Student ID must be unique.")
        return value
    
class StudentCreateSerializer(serializers.ModelSerializer):
    """
    Used for creating a student — accepts guardian data
    and optional enrollment inline.
    """
    guardians = GuardianSerializer(many=True, required=False)
    class_id = serializers.UUIDField(write_only=True, required=False)

    class Meta:
        model = Student
        fields = [
            "first_name",
            "last_name",
            "other_names",
            "student_id",
            "date_of_birth",
            "gender",
            "profile_photo",
            "email",
            "phone_number",
            "address",
            "admission_date",
            "previous_school",
            "guardians",
            "class_id"
        ]

    def validate(self, attrs):
        class_id = attrs.get("class_id")
        student_id = attrs.get("student_id")
        email = attrs.get("email", None)
        first_name = attrs.get("first_name", "")
        last_name = attrs.get("last_name", "")
        if not email:
            email = generate_user_email(first_name, last_name, domain=self.context["school"].school_email_domain or "school.com")

        if not student_id:
            if not self.context["school"].school_code:
                raise serializers.ValidationError({
                    "student_id": (
                        "Student ID is required if school does not have a "
                        "school code for auto-generation."
                    )
                })
        # Validate class_id if provided
        if class_id is not None:
            if not class_id:
                raise serializers.ValidationError({
                    "class_id": "If provided, class_id cannot be empty."
                })

            school = self.context["school"]

            # Check for active academic year
            active_academic_term = school.terms.filter(
                is_current=True
            ).first()

            active_academic_year = active_academic_term.academic_year if active_academic_term else None
            if not active_academic_year:
                raise serializers.ValidationError({
                    "class_id": (
                        "Cannot enroll student because there is no active "
                        "academic year. Please create and activate an "
                        "academic year first."
                    )
                })

            # Validate class existence and status
            school_class = school.classes.filter(
                id=class_id,
                is_active=True
            ).first()

            if not school_class:
                raise serializers.ValidationError({
                    "class_id": "Class not found or inactive."
                })

            # Optional: attach validated class object
            attrs["school_class"] = school_class
            attrs["academic_year"] = active_academic_year
            attrs["email"] = email

        return attrs

    def validate_first_name(self, value):
        if not re.match(r"^[A-Za-zÀ-ÿ\s'-]+$", value):
            raise serializers.ValidationError("First name must contain only letters.")
        return value

    def validate_last_name(self, value):
        if not re.match(r"^[A-Za-zÀ-ÿ\s'-]+$", value):
            raise serializers.ValidationError("Last name must contain only letters.")
        return value

    def validate_other_names(self, value):
        if value and not re.match(r"^[A-Za-zÀ-ÿ\s'-]+$", value):
            raise serializers.ValidationError("Other names must contain only letters.")
        return value

    def validate_phone_number(self, value):
        if value and not re.match(r"^\+?\d{7,15}$", value):
            raise serializers.ValidationError("Phone number must be between 7 and 15 digits, and can start with +.")
        return value
    
    def validate_admission_date(self, value):
        import datetime
        if value > datetime.date.today():
            raise serializers.ValidationError("Admission date cannot be in the future.")
        return value
    
    def validate_student_id(self, value):
        if Student.objects.filter(school=self.context["school"], student_id=value).exists():
            raise serializers.ValidationError("Student ID must be unique.")
        return value
    
    def validate_date_of_birth(self, value):
        import datetime
        today = datetime.date.today()
        if value > today:
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        
        return value

    @transaction.atomic
    def create(self, validated_data):
        guardians_data = validated_data.pop("guardians", [])
        validated_data.pop("class_id", None) 
        school = self.context["school"]
        school_class = validated_data.pop("school_class", None)
        academic_year = validated_data.pop("academic_year", None)

        # User account
        temporary_password = secrets.token_urlsafe(16)

        # 2. Create the first admin user
        user = User.objects.create_user(
            email=validated_data.get("email"),
            password=temporary_password,
            first_name=validated_data.get("first_name"),
            last_name=validated_data.get("last_name"),
            role=User.Role.STUDENT,
            must_change_password=True,
            school=school
        )

        # Create the student
        student = Student.objects.create(school=school, user_account = user, **validated_data)

        # Create guardians
        for guardian_data in guardians_data:
            Guardian.objects.create(
                student=student,
                school=school,
                **guardian_data,
            )

        # Optionally enroll immediately
        if school_class and academic_year:
            Enrollment.objects.create(
                school=school,
                student=student,
                klass=school_class,
                academic_year=academic_year,
            )
           
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


class BulkStudentUploadSerializer(serializers.Serializer):
    class_id = serializers.UUIDField(required=True)

    def validate_class_id(self, value):
        from academics.models import Class
        school = self.context["school"]
        try:
            klass = Class.objects.get(id=value, school=school, is_active=True)
        except Class.DoesNotExist:
            raise serializers.ValidationError("Class not found or inactive.")
        return value


class IDCardRequestSerializer(serializers.Serializer):
    """Body for a bulk ID-card generation request.

    ``student_ids`` (explicit selection) or ``class_id`` (a whole class) narrow
    the run; when neither is given, every active student in the school is used
    (subject to the view's batch cap).
    """

    student_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=True
    )
    class_id = serializers.UUIDField(required=False)
    term_id = serializers.UUIDField(required=False)


class StudentVerificationSerializer(serializers.Serializer):
    """Public projection returned by the QR verification endpoint.

    Deliberately limited to what a card would carry: no date of birth, address,
    guardians, email or phone. The photo is only exposed to authenticated staff
    of the same school (or platform superusers).
    """

    def to_representation(self, obj):
        from .services.id_cards import resolve_card_context

        context = resolve_card_context(obj)
        request = self.context.get("request")
        school = obj.school

        logo_url = None
        if school.logo and request is not None:
            logo_url = request.build_absolute_uri(school.logo.url)

        photo_url = None
        user = getattr(request, "user", None)
        if (
            request is not None
            and obj.profile_photo
            and getattr(user, "is_authenticated", False)
            and (
                getattr(user, "is_superuser", False)
                or getattr(user, "school_id", None) == obj.school_id
            )
        ):
            photo_url = request.build_absolute_uri(obj.profile_photo.url)

        return {
            "student_id": obj.student_id,
            "full_name": obj.full_name,
            "gender": obj.get_gender_display(),
            "status": obj.status,
            "is_active": obj.status == Student.Status.ACTIVE,
            "class_name": context["class_name"],
            "academic_year": context["academic_year"],
            "term_name": context["term_name"],
            "school": {"name": school.name, "logo_url": logo_url},
            "photo_url": photo_url,
        }


# ─── Promotion ────────────────────────────────────────────────────────


class PromotionRequestSerializer(serializers.Serializer):
    """Body for a single or bulk promotion.

    Either ``student_ids`` (explicit selection) or ``from_class_id`` (a whole
    class) is required. ``to_class_id`` and ``to_academic_year_id`` are the
    target; ``to_term_id`` is informational only.
    """

    student_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=True
    )
    from_class_id = serializers.UUIDField(required=False)
    from_academic_year_id = serializers.UUIDField(required=False)
    to_class_id = serializers.UUIDField()
    to_academic_year_id = serializers.UUIDField()
    to_term_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        from academics.models import AcademicYear, Class, Term

        school = self.context["school"]

        if not attrs.get("student_ids") and not attrs.get("from_class_id"):
            raise serializers.ValidationError(
                "Provide 'student_ids' or 'from_class_id'."
            )

        to_class = Class.objects.filter(
            id=attrs["to_class_id"], school=school, is_active=True
        ).first()
        if to_class is None:
            raise serializers.ValidationError(
                {"to_class_id": "Class not found or inactive."}
            )

        to_year = AcademicYear.objects.filter(
            id=attrs["to_academic_year_id"], school=school
        ).first()
        if to_year is None:
            raise serializers.ValidationError(
                {"to_academic_year_id": "Academic year not found."}
            )

        from_year = None
        if attrs.get("from_academic_year_id"):
            from_year = AcademicYear.objects.filter(
                id=attrs["from_academic_year_id"], school=school
            ).first()
            if from_year is None:
                raise serializers.ValidationError(
                    {"from_academic_year_id": "Academic year not found."}
                )

        from_class = None
        if attrs.get("from_class_id"):
            from_class = Class.objects.filter(
                id=attrs["from_class_id"], school=school
            ).first()
            if from_class is None:
                raise serializers.ValidationError(
                    {"from_class_id": "Class not found."}
                )

        to_term = None
        if attrs.get("to_term_id"):
            to_term = Term.objects.filter(
                id=attrs["to_term_id"], school=school
            ).first()
            if to_term is None:
                raise serializers.ValidationError({"to_term_id": "Term not found."})
            if to_term.academic_year_id != to_year.id:
                raise serializers.ValidationError(
                    {
                        "to_term_id": (
                            "Term does not belong to the target academic year."
                        )
                    }
                )

        attrs["to_class"] = to_class
        attrs["to_academic_year"] = to_year
        attrs["to_term"] = to_term
        attrs["from_class"] = from_class
        attrs["from_academic_year"] = from_year
        return attrs


class PromotionItemSerializer(serializers.ModelSerializer):
    student_code = serializers.CharField(source="student.student_id", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = Promotion
        fields = (
            "id",
            "student",
            "student_code",
            "student_name",
            "outcome",
            "message",
            "from_enrollment",
            "resulting_enrollment",
            "created_at",
        )


class PromotionBatchSerializer(serializers.ModelSerializer):
    from_class_name = serializers.SerializerMethodField()
    from_academic_year_name = serializers.SerializerMethodField()
    to_class_name = serializers.CharField(source="to_class.name", read_only=True)
    to_academic_year_name = serializers.CharField(
        source="to_academic_year.name", read_only=True
    )
    to_term_name = serializers.SerializerMethodField()
    promoted_by_name = serializers.SerializerMethodField()
    counts = serializers.SerializerMethodField()
    items = PromotionItemSerializer(many=True, read_only=True)

    class Meta:
        model = PromotionBatch
        fields = (
            "id",
            "from_academic_year",
            "from_academic_year_name",
            "from_class",
            "from_class_name",
            "to_academic_year",
            "to_academic_year_name",
            "to_class",
            "to_class_name",
            "to_term",
            "to_term_name",
            "status",
            "notes",
            "promoted_by_name",
            "counts",
            "items",
            "reversed_at",
            "created_at",
        )

    def get_from_class_name(self, obj):
        return obj.from_class.name if obj.from_class else None

    def get_from_academic_year_name(self, obj):
        return obj.from_academic_year.name if obj.from_academic_year else None

    def get_to_term_name(self, obj):
        return obj.to_term.get_name_display() if obj.to_term else None

    def get_promoted_by_name(self, obj):
        user = obj.promoted_by
        if user is None:
            return None
        return f"{user.first_name} {user.last_name}".strip()

    def get_counts(self, obj):
        return obj.outcome_counts()