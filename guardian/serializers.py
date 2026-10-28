from rest_framework import serializers

from .models import Guardian, GuardianStudent


class GuardianSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guardian
        fields = (
            'first_name',
            'last_name',
            'email',
            'phone',
            'address',
            'gender'
        )


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
