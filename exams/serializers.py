from this import s

from rest_framework import serializers

from academics.models import Class, Term
from exams.models import (
    AssessmentType,
    ReportScheme,
    StudentMark,
    StudentReport,
    StudentReportSubjectScore,
)
from schools.serializers.superadmin_serializers import (
    SchoolDetailSerializer,
    SchoolInfoSerializer,
)
from students.models import Enrollment


class AssessmentTypeSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source = "school.name", read_only = True)
    class Meta:
        model = AssessmentType
        fields = [
            "id",
            "name",
            "school_name",
            "max_score",
            "is_active"
        ]

        read_only_fields = ['id','school_name']

    def validate(self, attrs):
        school = self.context["request"].user.school
        name = (attrs.get("name") or getattr(self.instance, "name", None))

        if not name:
            raise serializers.ValidationError({
                "name": "Name is required."
            })

        name = name.strip().title()
        attrs["name"] = name

        exists = AssessmentType.objects.filter(
            school=school,
            name__iexact=name
        ).exclude(
            pk=getattr(self.instance, "pk", None)
        ).exists()

        if exists:
            raise serializers.ValidationError({
                "name": "An assessment type with this name already exists."
            })

        return attrs

class ReportSchemeSerializer(serializers.ModelSerializer):
    sba_component_names = serializers.StringRelatedField(source = "sba_components", read_only = True, many = True)
    main_exam_name = serializers.CharField(source = "main_exam.name", read_only = True)
    class Meta:
        model = ReportScheme
        fields = [
            "id",
            "name",
            "sba_components",
            "sba_component_names",
            "main_exam",
            "main_exam_name",
            "sba_scaling",
            "exam_scaling",
        ]

        read_only_fields = ["id"]

    def validate_sba_components(self, value):
        if any(not component.is_active for component in value):
            raise serializers.ValidationError(
                "One or more SBA components are inactive assessment types."
            )

        return value

    def validate_main_exam(self, value):
        if not value.is_active:
            raise serializers.ValidationError("The main exam is inactive")
        return value

    def validate(self, data):
        school = self.context['request'].user.school
        instance = getattr(self, "instance", None)

        name = data.get('name')
        if ReportScheme.objects.filter(name__iexact = name, school = school).exclude(pk = instance.pk if instance else None).exists():
            raise serializers.ValidationError({
                "name": (
                    "Report scheme with this name already exists"
                )
            })
        sba = data.get('sba_scaling')
        if sba is None:
            sba = self.instance.sba_scaling if self.instance else 50

        exam = data.get('exam_scaling')
        if exam is None:
            exam = self.instance.exam_scaling if self.instance else 50

        if (sba + exam) != 100:
            raise serializers.ValidationError("SBA and exam scaling should sum up to 100")

        # check for conflicts
        sba_components = data.get("sba_components")
        main_exam = data.get("main_exam")

        if sba_components is None and self.instance:
            sba_components = self.instance.sba_components.all()
        if main_exam is None and self.instance:
            main_exam = self.instance.main_exam

        if sba_components is None and sba > 0:
            raise serializers.ValidationError({
                "sba_components":"Please select at least one sba component"
            })

        if main_exam is None and exam > 0:
            raise serializers.ValidationError({
                "main_exam":"Please select a main exam"
            })

        if sba_components and main_exam:
            if main_exam in sba_components:
                raise serializers.ValidationError({
                    "Conflict":f"{main_exam.name} cannot be the main exam and in the sba components."
                })

        return data

class StudentMarkSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source = "student.full_name", read_only = True)
    subject_name = serializers.CharField(source = "subject.name", read_only = True)
    assessment_name = serializers.CharField(source = "assessment.name", read_only = True)
    academic_year = serializers.CharField(source = "academic_year.name", read_only=True)
    term = serializers.CharField(source = "term.name", read_only = True)
    student_class = serializers.CharField(source = "student_class.name", read_only = True)
    teacher = serializers.CharField(source = "teacher.full_name", allow_blank=True)
    class Meta:
        model = StudentMark
        fields = [
            "id",
            "student_name",
            "academic_year",
            "term",
            "subject_name",
            "assessment_name",
            "student_class",
            "score",
            "teacher",
            "teacher_remarks",
        ]


class StudentMarkCreationSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source = "student.full_name", read_only = True)
    subject_name = serializers.CharField(source = "subject.name", read_only = True)
    assessment_name = serializers.CharField(source = "assessment.name", read_only = True)
    class Meta:
        model = StudentMark
        fields = [
            "id",
            "student",
            "student_name",
            "academic_year",
            "term",
            "subject",
            "subject_name",
            "assessment",
            "assessment_name",
            "student_class",
            "score",
            "teacher",
            "teacher_remarks",
        ]
        read_only_fields = ['id', 'student_name', 'subject_name', 'assessment_name']

    def validate(self, attrs):
        school = self.context['request'].user.school
        student_class = attrs.get('student_class')
        student = attrs.get("student")
        academic_year = attrs.get("academic_year")


        student_enrollment = Enrollment.objects.filter(school = school, student = student, klass = student_class, academic_year = academic_year ).first()
        if student_enrollment is None:
            raise serializers.ValidationError({
                "student":f"{student.full_name} is not enrolled in this class for the current academic year"
            })

        return attrs

    def validate_score(self, value):
        assessment = self.initial_data.get("assessment")
        if not assessment:
            raise serializers.ValidationError("Assessment is required to validate score")
        try:
            assessment_instance = AssessmentType.objects.get(id = assessment)
        except AssessmentType.DoesNotExist:
            raise serializers.ValidationError("Invalid assessment ID")

        if value < 0 or value > assessment_instance.max_score:
            raise serializers.ValidationError(f"Score must be between 0 and {assessment_instance.max_score}")
        return value


class SubjectScoreSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name")
    subject_code = serializers.CharField(source="subject.code")
    student_name = serializers.CharField(source="student.full_name")
    student_id = serializers.CharField(source="student.student_id")

    class Meta:
        model = StudentReportSubjectScore
        fields = [
            "subject",
            "subject_name",
            "subject_code",
            "sba_score",
            "exam_score",
            "total_score",
            "grade",
            "rank",
            "student_name",
            "student_id",
        ]


class StudentReportSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name")
    student_id = serializers.CharField(source="student.student_id")
    class_name = serializers.CharField(source="student_class.name")
    term_name = serializers.CharField(source="term.get_name_display")
    academic_year_name = serializers.CharField(source="academic_year.name")
    rank = serializers.IntegerField(read_only=True)

    class Meta:
        model = StudentReport
        fields = [
            "id",
            "student_name",
            "student_id",
            "class_name",
            "term_name",
            "academic_year_name",
            "overall_score",
            "overall_attendance",
            "total_school_days",
            "teacher_remarks",
            "status",
            "overall_position",
            "rank",
        ]

class StudentReportDetailSerializer(serializers.ModelSerializer):
    school = SchoolInfoSerializer()
    student_name = serializers.CharField(source="student.full_name")
    student_id = serializers.CharField(source="student.student_id")
    class_name = serializers.CharField(source="student_class.name")
    term_name = serializers.CharField(source="term.get_name_display")
    next_reopening_date = serializers.DateField(source = "term.next_reopening_date", allow_null=True, required = False)
    academic_year_name = serializers.CharField(source="academic_year.name")
    subject_scores = SubjectScoreSerializer(many=True, read_only=True)
    rank = serializers.IntegerField(read_only=True)

    class Meta:
        model = StudentReport
        fields = [
            "id",
            "school",
            "student_name",
            "student_id",
            "class_name",
            "term_name",
            "next_reopening_date",
            "academic_year_name",
            "overall_score",
            "overall_attendance",
            "total_school_days",
            "teacher_remarks",
            "headteacher_remarks",
            "teacher",
            "headteacher",
            "status",
            "overall_position",
            "subject_scores",
            "rank",
        ]


class StudentReportGeneratorSerializer(serializers.Serializer):
    class_id = serializers.UUIDField(required = True)
    report_scheme_id = serializers.UUIDField(required = True)
    grading_system_id = serializers.UUIDField(required = True)


class GenerateReportResponseSerializer(serializers.Serializer):
    generated = serializers.IntegerField()
    updated = serializers.IntegerField()


class ReportTeacherRemarksSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentReport
        fields = [
            "teacher_remarks",
            "teacher"
        ]

class HeadTeacherRemarksSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentReport
        fields = [
            "headteacher_remarks",
            "headteacher"
        ]
