from django.db import transaction
from rest_framework import serializers
from staff.enums.staff_status import StaffStatus
from staff.models import StaffProfile
from students.models import Enrollment
from .models import AcademicYear, GradeScale, GradingSystem, SubjectTeacher, Term, Subject, Class, ClassSubject, ClassTeacher, TimeTableSlot


class TermMinimalSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="get_name_display", read_only=True)
    class Meta:
        model = Term
        fields = ["id", "name"]
        read_only_fields = fields

class AcademicYearSerializer(serializers.ModelSerializer):
    terms_count = serializers.SerializerMethodField()
    terms = TermMinimalSerializer(many=True, read_only=True)

    class Meta:
        model = AcademicYear
        fields = [
            "id",
            "name",
            "start_date",
            "end_date",
            "is_current",
            "terms_count",
            "terms",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_terms_count(self, obj):
        return obj.terms.count()
    
    def validate_name(self, value):
        school = self.context["request"].user.school
        if AcademicYear.objects.filter(name=value, school=school).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("An academic year with this name already exists.")
        return value

    def validate(self, attrs):
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        if start and end and end <= start:
            raise serializers.ValidationError({
                "end_date": "End date must be after start date."
            })
        if AcademicYear.objects.filter(
            school=self.context["request"].user.school,
            is_current=True,
        ).exclude(id=self.instance.id if self.instance else None).exists() and attrs.get("is_current", True):
            raise serializers.ValidationError({
                "is_current": "Another academic year is already marked as current."
            })
        
        if AcademicYear.objects.filter(
            school=self.context["request"].user.school,
            start_date__lte=end,
            end_date__gte=start,
        ).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("Academic year dates overlap with an existing academic year.")
        

        return attrs


class TermSerializer(serializers.ModelSerializer):
    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all(),
        required=True,
        allow_null=True,
    )
    academic_year_name = serializers.CharField(
        source="academic_year.name", read_only=True
    )
    term_name = serializers.CharField(source="get_name_display", read_only=True)

    class Meta:
        model = Term
        fields = [
            "id",
            "academic_year",
            "academic_year_name",
            "name",
            "term_name",
            "start_date",
            "end_date",
            "next_reopening_date",
            "is_current",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "academic_year_name", "term_name"]

    def validate_name(self, value):
        school = self.context["request"].user.school
        academic_year = self.initial_data.get("academic_year") or (self.instance.academic_year.id if self.instance else None)
        if Term.objects.filter(name=value, school=school, academic_year_id=academic_year).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("A term with this name already exists for the selected academic year.")
        return value

    def validate(self, attrs):
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        if start and end and end <= start:
            raise serializers.ValidationError({
                "end_date": "End date must be after start date."
            })
        if Term.objects.filter(
            school=self.context["request"].user.school,
            academic_year_id=attrs.get("academic_year") or (self.instance.academic_year.id if self.instance else None),
            is_current=True,
        ).exclude(id=self.instance.id if self.instance else None).exists() and attrs.get("is_current", False):
            raise serializers.ValidationError({
                "is_current": "Another term is already marked as current for this academic year."
            })
        
        if Term.objects.filter(
            school=self.context["request"].user.school,
            academic_year_id=attrs.get("academic_year") or (self.instance.academic_year.id if self.instance else None),
            start_date__lte=end,
            end_date__gte=start,
        ).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("Term dates overlap with an existing term in the same academic year.")
        
        if attrs.get("next_reopening_date") and attrs["next_reopening_date"] <= end:
            raise serializers.ValidationError({
                "next_reopening_date": "Next reopening date must be after the term end date."
            })
        
        # if start date and end date are not in the academic year date range, raise error
        academic_year = attrs.get("academic_year") or (self.instance.academic_year if self.instance else None)
        if academic_year:
            if start and (start < academic_year.start_date or start > academic_year.end_date):
                raise serializers.ValidationError({
                    "start_date": "Start date must be within the academic year date range."
                })
            if end and (end < academic_year.start_date or end > academic_year.end_date):
                raise serializers.ValidationError({
                    "end_date": f"End date must be within the academic year date range ({academic_year.start_date} to {academic_year.end_date})."
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

class TermUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Term
        fields = [
            "academic_year",
            "name",
            "start_date",
            "end_date",
            "next_reopening_date",
            "is_current",
        ]

    def validate(self, attrs):
        if "start_date" in attrs and "end_date" in attrs:
            start = attrs["start_date"]
            end = attrs["end_date"]
            if end <= start:
                raise serializers.ValidationError({
                    "end_date": "End date must be after start date."
                })
        if "name" in attrs:
            academic_year = attrs.get("academic_year") or self.instance.academic_year
            if Term.objects.filter(name=attrs["name"], school=self.instance.school, academic_year=academic_year).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError({
                    "name": "A term with this name already exists for the selected academic year."
                })
                    
        # if the new value for current is false, check if there is at least one other term marked as current for the same academic year
        if "is_current" in attrs and not attrs["is_current"]:
            academic_year = attrs.get("academic_year") or self.instance.academic_year
            if not Term.objects.filter(
                school=self.instance.school,
                academic_year=academic_year,
                is_current=True,
            ).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError({
                    "is_current": "At least one term must be marked as current for the academic year."
                })
        return attrs


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

    def validate_name(self, value):
        school = self.context["request"].user.school
        if Subject.objects.filter(name=value, school=school).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("A subject with this name already exists.")
        return value
    
    def validate_code(self, value):
        school = self.context["request"].user.school
        if Subject.objects.filter(code=value, school=school).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError("A subject with this code already exists.")
        return value.upper()
    
class ClassSubjectSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    subject_code = serializers.CharField(source="subject.code", read_only=True)

    class Meta:
        model = ClassSubject
        fields = ["id", "klass", "subject", "subject_name", "subject_code"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        school = self.context["request"].user.school
        subject = attrs.get("subject")
        klass = attrs.get("klass")
        if not Subject.objects.filter(id=subject.id, school=school, is_active=True).exists():
            raise serializers.ValidationError({
                "subject": "Subject not found or inactive in this school."
            })
        
        if ClassSubject.objects.filter(
            school=school,
            klass=klass,
            subject=subject,
        ).exists():
            raise serializers.ValidationError("This subject is already assigned to the class.")

        if not Class.objects.filter(
            id=klass.id,
            school=school,
            is_active=True,
        ).exists():
            raise serializers.ValidationError({
                "klass": "Class not found or inactive in this school."
            })
        return attrs

class ClassTeacherSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source="klass.name", read_only=True)
    teacher_name = serializers.CharField(source="teacher.full_name", read_only=True)
    teacher_email = serializers.CharField(source="teacher.email", read_only=True)

    class Meta:
        model = ClassTeacher
        fields = [
            "id",
            "klass",
            "class_name",
            "teacher",
            "teacher_name",
            "teacher_email"
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        klass = attrs.get("klass")
        teacher = attrs.get("teacher")
        if not StaffProfile.objects.filter(
            id=teacher.id,
            school=self.context["school"],
            user__role="teacher",
            user__is_active=True,
            status__in=[StaffStatus.ACTIVE, StaffStatus.ON_LEAVE]
        ).exists():
            raise serializers.ValidationError({
                "teacher": "Invalid teacher. Teacher not found or not active"
            })
        if ClassTeacher.objects.filter(
            school=self.context["school"],
            klass=klass,
            teacher=teacher,
            is_active=True,
        ).exists():
            raise serializers.ValidationError("This teacher is already assigned to this class.")

        return attrs
    
class TeacherClassesListSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source="klass.name", read_only=True)
    students_count = serializers.SerializerMethodField()
    

    class Meta:
        model = ClassTeacher
        fields = [
            "id",
            "klass",
            "class_name",
            "students_count"
        ]
        read_only_fields = ["id", "class_name", "students_count"]

    def get_students_count(self, obj):
        current_year = AcademicYear.objects.filter(school=obj.school, is_current=True).first()
        return Enrollment.objects.filter(
            school=obj.school,
            klass=obj.klass,
            academic_year=current_year,
            is_active=True,
        ).count()
    

    
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


class BulkAssignClassSubjectsSerializer(serializers.Serializer):
    """Bulk assign subjects to a class. Accepts a list of subject UUIDs."""
    subjects = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
    )

    def validate_subjects(self, value):
        school = self.context["school"]
        subjects = Subject.objects.filter(
            id__in=value,
            school=school,
            is_active=True,
        )
        if subjects.count() != len(value):
            raise serializers.ValidationError(
                "One or more subjects are invalid, inactive, or do not belong to this school."
            )
        return list(subjects)


class AssignTeacherSerializer(serializers.Serializer):
    """Assign a teacher to a class for an academic year."""
    teacher_id = serializers.UUIDField()

    def validate(self, attrs):
        from accounts.models import User
        school = self.context["school"]

        try:
            teacher = StaffProfile.objects.get(
                id=attrs["teacher_id"],
                school=school,
                user__role="teacher",
                user__is_active=True,
            )
            
        except StaffProfile.DoesNotExist:
            raise serializers.ValidationError({
                "teacher_id": "Teacher not found in this school."
            })
        
        if ClassTeacher.objects.filter(
            school=school,
            teacher=teacher.user,
            academic_year__is_current=True,
        ).exists():
            raise serializers.ValidationError( "This teacher is already assigned to a class for the current academic year."
            )

        attrs["teacher"] = teacher.user
        return attrs
    

class GradeScaleSerializer(serializers.ModelSerializer):

    class Meta:
        model = GradeScale
        fields = [
            "id",
            "grading_system",
            "grade",
            "label",
            "min_score",
            "max_score",
            "is_passing",
            "position",
        ]
        read_only_fields = ["id"]

        validations = []
    def validate(self, attrs):
        instance = self.instance

        grade = attrs.get(
            "grade",
            getattr(instance, "grade", None)
        )

        grading_system = attrs.get(
            "grading_system",
            getattr(instance, "grading_system", None)
        )

        min_score = attrs.get(
            "min_score",
            getattr(instance, "min_score", None)
        )

        max_score = attrs.get(
            "max_score",
            getattr(instance, "max_score", None)
        )

        # --------------------------------------------------
        # Grade uniqueness within grading system
        # --------------------------------------------------
        duplicate_grade = GradeScale.objects.filter(
            grading_system=grading_system,
            grade__iexact=grade
        )

        if instance:
            duplicate_grade = duplicate_grade.exclude(pk=instance.pk)

        if duplicate_grade.exists():
            raise serializers.ValidationError({
                "grade": (
                    f"Grade '{grade}' already exists in "
                    f"'{grading_system.name}'."
                )
            })

        # --------------------------------------------------
        # Score range validation
        # --------------------------------------------------
        if min_score is not None and max_score is not None:
            if min_score >= max_score:
                raise serializers.ValidationError({
                    "min_score": (
                        "min_score must be less than max_score."
                    )
                })

        # --------------------------------------------------
        # Prevent overlapping ranges
        # Example:
        # A = 80-100
        # B = 70-90 overlaps
        # --------------------------------------------------
        overlapping_ranges = GradeScale.objects.filter(
            grading_system=grading_system,
            min_score__lte=max_score,
            max_score__gte=min_score,
        )

        if instance:
            overlapping_ranges = overlapping_ranges.exclude(
                pk=instance.pk
            )

        if overlapping_ranges.exists():
            overlap = overlapping_ranges.first()

            raise serializers.ValidationError({
                "min_score": (
                    f"Score range overlaps with grade "
                    f"'{overlap.grade}' "
                    f"({overlap.min_score}-{overlap.max_score})."
                )
            })

        return attrs

    def validate_grade(self, value):
        return value.strip().upper()

    def validate_label(self, value):
        return value.strip().title()

    def validate_min_score(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "Min score cannot be negative."
            )
        return value

    def validate_max_score(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "Max score cannot be negative."
            )
        return value
    

class GradingSystemListSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradingSystem
        fields = [
            "id",
            "name",
            "description",
            "max_score",
            "pass_mark"
        ]
class GradingSystemSerializer(serializers.ModelSerializer):
    grade_scales = GradeScaleSerializer(many=True, required=False)
    class Meta:
        model = GradingSystem
        fields = [
            "id",
            "name",
            "description",
            "max_score",
            "pass_mark",
            "grade_scales"
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        name = attrs.get("name", "").strip()
        if GradingSystem.objects.filter(name__iexact=name, school=self.context["school"]).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError({
                "name": "A grading system with this name already exists in this school."
            })
        max_score = attrs.get("max_score")
        pass_mark = attrs.get("pass_mark")

        if pass_mark > max_score:
            raise serializers.ValidationError({
                "pass_mark": "Pass mark cannot exceed max score."
            })
        
        grade_scales = attrs.get("grade_scales", [])

        ranges = []

        for scale in grade_scales:
            start = scale["min_score"]
            end = scale["max_score"]

            for existing_start, existing_end in ranges:
                if start <= existing_end and end >= existing_start:
                    raise serializers.ValidationError(
                        "Grade ranges cannot overlap."
                    )

            ranges.append((start, end))

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        scales_data = validated_data.pop("grade_scales", [])
        grading_system = GradingSystem.objects.create(**validated_data)
        for scale_data in scales_data:
            GradeScale.objects.create(grading_system=grading_system, school=grading_system.school, **scale_data)
        return grading_system
    

class GradingSystemUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradingSystem
        fields = [
            "name",
            "description",
            "max_score",
            "pass_mark"
        ]

    def validate(self, attrs):
        name = attrs.get("name", self.instance.name).strip()
        if GradingSystem.objects.filter(name__iexact=name, school=self.context["school"]).exclude(id=self.instance.id).exists():
            raise serializers.ValidationError({
                "name": "A grading system with this name already exists in this school."
            })
        max_score = attrs.get("max_score", self.instance.max_score)
        pass_mark = attrs.get("pass_mark", self.instance.pass_mark)

        if pass_mark > max_score:
            raise serializers.ValidationError({
                "pass_mark": "Pass mark cannot exceed max score."
            })
        
        return attrs
class BulkGradeScaleSerializer(serializers.Serializer):
    """
    Used to set all grade scales for a grading system at once.
    Replaces all existing scales with the submitted ones.
    """
    grades = GradeScaleSerializer(many=True, allow_empty=False)

    def validate_grades(self, value):
        if len(value) < 2:
            raise serializers.ValidationError(
                "A grading system must have at least 2 grade bands."
            )

        grading_system = self.context.get("grading_system")
        max_score = (
            grading_system.max_score if grading_system else 100
        )

        # ── Check grade labels are unique ─────────────────────────
        grades = [g["grade"].strip().upper() for g in value]
        if len(grades) != len(set(grades)):
            raise serializers.ValidationError(
                "Duplicate grade labels found. "
                "Each grade must be unique."
            )

        # ── Check scores are within system max ────────────────────
        for item in value:
            if float(item["max_score"]) > float(max_score):
                raise serializers.ValidationError(
                    f"Grade '{item['grade']}' max_score "
                    f"({item['max_score']}) exceeds the grading "
                    f"system's max score ({max_score})."
                )
            if float(item["min_score"]) < 0:
                raise serializers.ValidationError(
                    f"Grade '{item['grade']}' min_score "
                    f"cannot be negative."
                )

        # ── Sort by min_score descending for overlap checking ─────
        sorted_grades = sorted(
            value,
            key=lambda x: float(x["min_score"]),
            reverse=True,
        )

        # ── Check for gaps ────────────────────────────────────────
        # Highest max must equal system max_score
        highest_max = float(sorted_grades[0]["max_score"])
        if highest_max != float(max_score):
            raise serializers.ValidationError(
                f"The highest grade's max_score must equal the "
                f"grading system's max score ({max_score}). "
                f"Got {highest_max}."
            )

        # Lowest min must be 0
        lowest_min = float(sorted_grades[-1]["min_score"])
        if lowest_min != 0:
            raise serializers.ValidationError(
                f"The lowest grade's min_score must be 0. "
                f"Got {lowest_min}."
            )

        # ── Check for overlaps and gaps between bands ─────────────
        for i in range(len(sorted_grades) - 1):
            current = sorted_grades[i]
            next_grade = sorted_grades[i + 1]

            current_min = float(current["min_score"])
            next_max = float(next_grade["max_score"])

            # Overlap: next band's max >= current band's min
            if next_max >= current_min:
                raise serializers.ValidationError(
                    f"Grade ranges overlap between "
                    f"'{current['grade']}' "
                    f"({current['min_score']}–{current['max_score']}) "
                    f"and '{next_grade['grade']}' "
                    f"({next_grade['min_score']}–{next_grade['max_score']})."
                )

            # Gap: next band's max is not exactly one step below
            # current band's min
            expected_next_max = current_min - 1
            if next_max != expected_next_max:
                raise serializers.ValidationError(
                    f"Gap detected between '{next_grade['grade']}' "
                    f"(max: {next_grade['max_score']}) and "
                    f"'{current['grade']}' "
                    f"(min: {current['min_score']}). "
                    f"Ranges must be continuous with no gaps. "
                    f"Expected '{next_grade['grade']}' max_score "
                    f"to be {expected_next_max}."
                )

        return value


class GradeResolverSerializer(serializers.Serializer):
    """
    Given a score, returns the matching grade from a grading system.
    Used to test a grading system before applying it.
    """
    score = serializers.DecimalField(max_digits=5, decimal_places=2)

    def validate_score(self, value):
        grading_system = self.context.get("grading_system")
        if grading_system:
            if float(value) < 0:
                raise serializers.ValidationError(
                    "Score cannot be negative."
                )
            if float(value) > float(grading_system.max_score):
                raise serializers.ValidationError(
                    f"Score ({value}) exceeds the grading system's "
                    f"max score ({grading_system.max_score})."
                )
        return value
    
class SubjectTeacherCreationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubjectTeacher
        fields = [
            
            "klass",
            "subject",
            "teacher"
        ]
        read_only_fields = ["id"]

    def validate(self, attr):
        school = self.context["school"]
        teacher = attr.get("teacher")
        klass = attr.get("klass")
        if not Class.objects.filter(
            id=klass.id,
            school=school,
            is_active=True,
        ).exists():
            raise serializers.ValidationError({
                "klass": "Class not found or inactive in this school."
            })
        if not StaffProfile.objects.filter(
            id=teacher.id,
            school=school,
            user__role="teacher",
            user__is_active=True,
            status__in=[StaffStatus.ACTIVE, StaffStatus.ON_LEAVE]
        ).exists():
            raise serializers.ValidationError({
                "teacher": "Invalid teacher. Teacher not found or not active"
            })
        
        if SubjectTeacher.objects.filter(
            school=school,
            klass=klass,
            teacher=teacher,
            is_active=True,
        ).exists():
            raise serializers.ValidationError( "This teacher is already assigned to this subject for this class."
            )

        
        return attr

class SubjectTeacherListSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source="klass.name", read_only=True)
    teacher_name = serializers.CharField(source="teacher.full_name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    class Meta:
        model = SubjectTeacher
        fields = [
            "id",
            "class_name",
            "teacher_name",
            "subject_name",
        ]
class SubjectTeacherWriteSerializer(serializers.Serializer):
    """Assigns a single teacher to a class subject."""
    class_id = serializers.UUIDField()
    subject_id = serializers.UUIDField()
    teacher_id = serializers.UUIDField() 

    def validate(self, attrs):
        from staff.models import StaffProfile
        school = self.context["school"]

        # ── Validate class ────────────────────────────────────────
        try:
            klass = Class.objects.get(
                id=attrs["class_id"],
                school=school,
                is_active=True,
            )
        except Class.DoesNotExist:
            raise serializers.ValidationError({
                "class_id": "Class not found or inactive."
            })

        # ── Validate subject ──────────────────────────────────────
        try:
            subject = Subject.objects.get(
                id=attrs["subject_id"],
                school=school,
                is_active=True,
            )
        except Subject.DoesNotExist:
            raise serializers.ValidationError({
                "subject_id": "Subject not found or inactive."
            })

        # ── Validate subject is assigned to this class ────────────
        if not ClassSubject.objects.filter(
            klass=klass, subject=subject, school=school
        ).exists():
            raise serializers.ValidationError({
                "subject_id": (
                    f"'{subject.name}' is not assigned to "
                    f"'{klass.name}'. Assign the subject to the "
                    f"class first."
                )
            })

        # ── Validate teacher ──────────────────────────────────────
        try:
            teacher = StaffProfile.objects.select_related(
                "user"
            ).get(
                id=attrs["teacher_id"],
                school=school,
                status="active",
            )
        except StaffProfile.DoesNotExist:
            raise serializers.ValidationError({
                "teacher_id": "Teacher not found or inactive."
            })

        # ── Validate teacher has teaching permission ──────────────
        if not teacher.has_permission("exams.enter_scores"):
            raise serializers.ValidationError({
                "teacher_id": (
                    f"{teacher.user.full_name} does not have "
                    f"teaching permissions."
                )
            })

        
        # ── Validate term if provided ─────────────────────────────
        try:
            term = Term.objects.get(
                id=attrs["term_id"],
                school=school,
                is_current = True,
            )
        except Term.DoesNotExist:
            raise serializers.ValidationError({
                "term_id": (
                    "Current term not found. A current term must be set in the "
                    "school to assign teachers to specific terms."    
                )
            })

        attrs["klass"] = klass
        attrs["subject"] = subject
        attrs["teacher"] = teacher
        attrs["academic_year"] = term.academic_year
        attrs["term"] = term

        return attrs


class BulkSubjectTeacherItemSerializer(serializers.Serializer):
    """Single item inside a bulk assignment request."""
    class_id = serializers.UUIDField()
    subject_id = serializers.UUIDField()
    teacher_id = serializers.UUIDField()


class BulkSubjectTeacherSerializer(serializers.Serializer):
    """
    Bulk assign teachers to class subjects.
    All assignments share the same academic year and term.

    Validates every item before saving any of them.
    """
    
    assignments = BulkSubjectTeacherItemSerializer(
        many=True,
        allow_empty=False,
        min_length=1,
        max_length=100,
    )

    def validate_academic_year_id(self, value):
        school = self.context["school"]
        try:
            return AcademicYear.objects.get(
                id=value, school=school
            )
        except AcademicYear.DoesNotExist:
            raise serializers.ValidationError(
                "Academic year not found."
            )

    def validate_term_id(self, value):
        school = self.context["school"]
        if not value:
            return None
        try:
            return Term.objects.get(id=value, school=school)
        except Term.DoesNotExist:
            raise serializers.ValidationError(
                "Term not found."
            )

    def validate(self, attrs):
        from staff.models import StaffProfile
        school = self.context["school"]

        academic_year = attrs["academic_year_id"]
        term = attrs.get("term_id")
        assignments = attrs["assignments"]

        # ── Check for duplicate class+subject pairs ───────────────
        pairs = [
            (str(a["class_id"]), str(a["subject_id"]))
            for a in assignments
        ]
        if len(pairs) != len(set(pairs)):
            raise serializers.ValidationError({
                "assignments": (
                    "Duplicate class + subject combinations found. "
                    "Each class-subject pair can only appear once."
                )
            })

        # ── Validate every assignment item ────────────────────────
        errors = {}
        validated_assignments = []

        for i, item in enumerate(assignments):
            item_errors = {}

            # Validate class
            try:
                klass = Class.objects.get(
                    id=item["class_id"],
                    school=school,
                    is_active=True,
                )
            except Class.DoesNotExist:
                item_errors["class_id"] = "Class not found or inactive."
                klass = None

            # Validate subject
            try:
                subject = Subject.objects.get(
                    id=item["subject_id"],
                    school=school,
                    is_active=True,
                )
            except Subject.DoesNotExist:
                item_errors["subject_id"] = "Subject not found or inactive."
                subject = None

            # Validate class-subject relationship
            if klass and subject:
                if not ClassSubject.objects.filter(
                    klass=klass,
                    subject=subject,
                    school=school,
                ).exists():
                    item_errors["subject_id"] = (
                        f"'{subject.name}' is not assigned to "
                        f"'{klass.name}'."
                    )

            # Validate teacher
            try:
                teacher = StaffProfile.objects.select_related(
                    "user"
                ).get(
                    id=item["teacher_id"],
                    school=school,
                    status="active",
                )
                if not teacher.has_permission("exams.enter_scores"):
                    item_errors["teacher_id"] = (
                        f"{teacher.user.full_name} does not have "
                        f"teaching permissions."
                    )
            except StaffProfile.DoesNotExist:
                item_errors["teacher_id"] = (
                    "Teacher not found or inactive."
                )
                teacher = None

            if item_errors:
                errors[f"assignment_{i}"] = item_errors
            else:
                validated_assignments.append({
                    "klass": klass,
                    "subject": subject,
                    "teacher": teacher,
                    "academic_year": academic_year,
                    "term": term,
                })

        if errors:
            raise serializers.ValidationError(errors)

        attrs["validated_assignments"] = validated_assignments
        return attrs


class ClassSubjectTeacherSummarySerializer(serializers.Serializer):
    """
    Returns all subjects in a class along with their
    assigned teacher for a given academic year/term.
    Used for the class subject-teacher overview screen.
    """
    def to_representation(self, instance):
        return {
            "subject_id": str(instance["subject"].id),
            "subject_name": instance["subject"].name,
            "subject_code": instance["subject"].code,
            "teacher_id": (
                str(instance["teacher"].id)
                if instance["teacher"] else None
            ),
            "teacher_name": (
                instance["teacher"].user.full_name
                if instance["teacher"] else None
            ),
            "teacher_employee_id": (
                instance["teacher"].employee_id
                if instance["teacher"] else None
            ),
            "is_assigned": instance["teacher"] is not None,
            "assignment_id": (
                str(instance["assignment_id"])
                if instance["assignment_id"] else None
            ),
        }

class TimeTableSlotSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source="school.name", read_only=True)
    class_name = serializers.CharField(source="klass.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    teacher_name = serializers.CharField(source="teacher.full_name", read_only=True)
    term_name = serializers.CharField(source="term.get_name_display", read_only=True)

    class Meta:
        model = TimeTableSlot
        fields = [
            "id",
            "start_time",
            "end_time",
            "school",
            "school_name",
            "klass",
            "class_name",
            "subject",
            "subject_name",
            "teacher",
            "teacher_name",
            "day_of_week",
            "term",
            "term_name",
        ]
        read_only_fields = ["id", "school", "school_name", "class_name", "subject_name", "teacher_name", "term", "term_name"]

    def validate(self, attrs):
        start_time = attrs.get("start_time")
        end_time = attrs.get("end_time")
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError({
                "end_time": "End time must be after start time."
            })
        
        school = self.context.get("school")
        term = self.context.get("term")
        
        if TimeTableSlot.objects.filter(
            school=school,
            klass=attrs["klass"],
            term=term,
            start_time__lt=end_time,
            end_time__gt=start_time,
            day_of_week = attrs["day_of_week"]
        ).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError(
                "This class already has a timetable slot that overlaps with the specified time and term."
            )
        
        if not ClassSubject.objects.filter(
            school=school,
            klass=attrs["klass"],
            subject=attrs["subject"]
        ).exists():
            raise serializers.ValidationError(
                "This subject is not assigned to this class"
            )

        return attrs
    
