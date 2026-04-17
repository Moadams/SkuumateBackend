from exams.models import AssessmentType
from rest_framework import serializers


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

        

    def validate_name(self, value):
        school = self.context["request"].user.school
        if AssessmentType.objects.filter(school = school, name = value.title()).exists():
            raise serializers.ValidationError("An assessment type with this name already exists")
        return value
    
    def create(self, validated_data):
        if 'name' in validated_data:
            validated_data['name'] = validated_data['name'].title()
        return super().create(validated_data)