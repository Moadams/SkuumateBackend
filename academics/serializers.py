from rest_framework import serializers
from staff.models import StaffProfile
from .models import AcademicYear, GradeScale, GradingSystem, Term, Subject, Class, ClassSubject, ClassTeacher


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
        ).exclude(id=self.instance.id if self.instance else None).exists() and attrs.get("is_current", False):
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
        required=False,
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
            "grade",
            "label",
            "min_score",
            "max_score",
            "remark",
            "is_passing",
            "position",
        ]
        read_only_fields = ["id"]

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

    def validate(self, attrs):
        min_score = attrs.get(
            "min_score",
            getattr(self.instance, "min_score", None)
        )
        max_score = attrs.get(
            "max_score",
            getattr(self.instance, "max_score", None)
        )

        if min_score is not None and max_score is not None:
            if min_score >= max_score:
                raise serializers.ValidationError(
                    "min_score must be less than max_score."
                )

        return attrs


class GradingSystemSerializer(serializers.ModelSerializer):
    grade_scales = GradeScaleSerializer(many=True, read_only=True)
    total_grades = serializers.SerializerMethodField()

    class Meta:
        model = GradingSystem
        fields = [
            "id",
            "name",
            "description",
            "is_default",
            "max_score",
            "pass_mark",
            "total_grades",
            "grade_scales",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_total_grades(self, obj):
        return obj.grade_scales.count()

    def validate_pass_mark(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "Pass mark cannot be negative."
            )
        return value

    def validate(self, attrs):
        max_score = attrs.get(
            "max_score",
            getattr(self.instance, "max_score", None)
        )
        pass_mark = attrs.get(
            "pass_mark",
            getattr(self.instance, "pass_mark", None)
        )
        if max_score and pass_mark and pass_mark >= max_score:
            raise serializers.ValidationError({
                "pass_mark": (
                    f"Pass mark ({pass_mark}) must be "
                    f"less than max score ({max_score})."
                )
            })
        return attrs


class GradingSystemWriteSerializer(GradingSystemSerializer):
    """
    Used for create/update.
    Validates name uniqueness per school.
    """
    def validate_name(self, value):
        school = self.context["school"]
        qs = GradingSystem.objects.filter(
            school=school,
            name__iexact=value,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"A grading system named '{value}' already exists."
            )
        return value


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