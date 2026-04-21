from academics.models import Class, GradingSystem, Term
from exams.models import AssessmentType, ReportScheme, StudentMark, StudentReport, StudentReportSubjectScore
from rest_framework import serializers
from students.models import Enrollment
from django.db import transaction

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
        

    def validate_name(self, value):
        school = self.context["request"].user.school
        if AssessmentType.objects.filter(school = school, name = value.title()).exists():
            raise serializers.ValidationError("An assessment type with this name already exists")
        return value
    
    def create(self, validated_data):
        if 'name' in validated_data:
            validated_data['name'] = validated_data['name'].title()
        return super().create(validated_data)
    

class ReportSchemeSerializer(serializers.ModelSerializer):
    sba_component_names = serializers.StringRelatedField(source = "sba_components", read_only = True, many = True)
    main_exam_name = serializers.CharField(source = "main_exam.name", read_only = True)
    assigned_classes_names = serializers.StringRelatedField(many = True, read_only = True)
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
            "assigned_classes",
            "assigned_classes_names",
        ]

        
        
    def validate(self, data):
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

        if sba_components and main_exam:
            if main_exam in sba_components:
                raise serializers.ValidationError({
                    "Conflict":f"{main_exam.name} cannot be the main exam and in the sba components."
                })

        if not self.instance:
            school = self.context['request'].user.school
            term = Term.objects.filter(school=school, is_current=True).first()
            
            if term:
                data['term'] = term
                data['academic_year'] = term.academic_year
                data['school'] = school # Ensure school is also set here
            else:
                raise serializers.ValidationError("Current academic term not found")
            
        assigned_classes = data.get("assigned_classes")
    
        school = self.context['request'].user.school
        if self.instance:
            term = self.instance.term
        else:
            term = Term.objects.filter(school=school, is_current=True).first()

        if assigned_classes and term:
            conflicting_classes = ReportScheme.objects.filter(
                term=term,
                assigned_classes__in=assigned_classes
            )

            if self.instance:
                conflicting_classes = conflicting_classes.exclude(id=self.instance.id)

            if conflicting_classes.exists():
                bad_class_names = conflicting_classes.values_list('assigned_classes__name', flat=True).distinct()
                
                request_class_ids = [c.id for c in assigned_classes]
                actual_conflicts = Class.objects.filter(
                    id__in=request_class_ids, 
                    report_schemes__term=term
                )
                if self.instance:
                    actual_conflicts = actual_conflicts.exclude(report_schemes=self.instance)

                conflict_names = list(actual_conflicts.values_list('name', flat=True))

                if conflict_names:
                    raise serializers.ValidationError({
                        "assigned_classes": f"The following classes are already assigned to a scheme in this term: {', '.join(conflict_names)}"
                    })
                
        return data
    
class StudentMarkSerializer(serializers.ModelSerializer):
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

    class Meta:
        model = StudentReportSubjectScore
        fields = [
            "subject_name",
            "subject_code",
            "sba_score",
            "exam_score",
            "total_score",
            "grade",
            "rank",
        ]


class StudentReportSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name")
    student_id = serializers.CharField(source="student.student_id")
    class_name = serializers.CharField(source="student_class.name")
    term_name = serializers.CharField(source="term.name")
    academic_year_name = serializers.CharField(source="academic_year.name")
    subject_scores = SubjectScoreSerializer(many=True, read_only=True)
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
            "subject_scores",
            "rank",
        ]


class GenerateReportResponseSerializer(serializers.Serializer):
    generated = serializers.IntegerField()
    updated = serializers.IntegerField()
    reports = StudentReportSerializer(many=True)


class StudentReportUpdateSerializer(serializers.ModelSerializer):
    teacher_remarks = serializers.CharField(required=False, allow_blank=True)
    class Meta:
        model = StudentReport
        fields = [
            "teacher_remarks"
        ]