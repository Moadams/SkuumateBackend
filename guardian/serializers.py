from rest_framework import serializers

from schools.models import School
from students.models import Student

from .enums import GuardianStudentRelationship
from .models import Guardian, GuardianStudent


def reject_duplicate_students(value):
    student_ids = [item['student'].pk for item in value]
    if len(student_ids) != len(set(student_ids)):
        raise serializers.ValidationError("Each student can only be listed once.")
    return value


class GuardianStudentInputSerializer(serializers.Serializer):
    """A student to link to a guardian, with how they are related."""
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    relationship = serializers.ChoiceField(choices=GuardianStudentRelationship.choices)


class GuardianSerializer(serializers.ModelSerializer):
    students = GuardianStudentInputSerializer(many=True, required=False, write_only=True)
    assigned_students = serializers.SerializerMethodField()

    class Meta:
        model = Guardian
        fields = (
            'id',
            'first_name',
            'last_name',
            'email',
            'phone',
            'address',
            'gender',
            'students',
            'assigned_students',
        )
        read_only_fields = ('id',)

    def get_assigned_students(self, obj):
        return [
            {
                'student': link.student_id,
                'relationship': link.relationship,
            }
            for link in obj.guardian_students.all()
        ]

    def validate_students(self, value):
        return reject_duplicate_students(value)


class GuardianUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guardian
        fields = (
            'first_name',
            'last_name',
            'email',
            'phone',
            'address',
            'gender',
        )


class GuardianLinkedStudentSerializer(serializers.ModelSerializer):
    """A student linked to a guardian, as shown on the guardian detail."""
    student_code = serializers.CharField(source='student.student_id', read_only=True)
    full_name = serializers.CharField(source='student.full_name', read_only=True)

    class Meta:
        model = GuardianStudent
        fields = ('id', 'student', 'student_code', 'full_name', 'relationship')
        read_only_fields = fields


class GuardianDetailSerializer(serializers.ModelSerializer):
    students = GuardianLinkedStudentSerializer(
        source='guardian_students', many=True, read_only=True
    )

    class Meta:
        model = Guardian
        fields = (
            'id',
            'first_name',
            'last_name',
            'email',
            'phone',
            'address',
            'gender',
            'user_account',
            'students',
            'created_at',
            'updated_at',
        )
        read_only_fields = fields


class GuardianLinkStudentsSerializer(serializers.Serializer):
    students = GuardianStudentInputSerializer(many=True, allow_empty=False)

    def validate_students(self, value):
        return reject_duplicate_students(value)


class GuardianUnlinkStudentsSerializer(serializers.Serializer):
    students = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)

    def validate_students(self, value):
        return list(dict.fromkeys(value))


class GuardianChildSchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ('id', 'name')
        read_only_fields = fields


class GuardianChildSerializer(serializers.ModelSerializer):
    """What a guardian sees for each of their linked students."""
    school = GuardianChildSchoolSerializer(read_only=True)
    profile_photo = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = ('id', 'student_id', 'full_name', 'profile_photo', 'school')
        read_only_fields = fields

    def get_profile_photo(self, obj):
        if not obj.profile_photo:
            return None
        request = self.context.get('request')
        url = obj.profile_photo.url
        return request.build_absolute_uri(url) if request else url


class GuardianStudentSerializer(serializers.ModelSerializer):
    model = GuardianStudent
    fields = (
        'id',
        'school',
        'guardian',
        'student',
        'relationship',
        'created_at',
        'updated_at'
    )

    read_only_fields = (
        "id",
        "school",
        'created_at',
        'updated_at'
    )
