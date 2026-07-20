from rest_framework import serializers
from ..models import School
import re


class SchoolListSerializer(serializers.ModelSerializer):
    

    class Meta:
        model = School
        fields = [
            "id",
            "name",
            "email",
            "logo",
            "school_code",
            "city",
            "joined",
            "status"
        ]

    

class SchoolSerializer(serializers.ModelSerializer):
    total_students = serializers.SerializerMethodField()
    total_users = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = [
            "id",
            "name",
            "logo",
            "email",
            "phone",
            "address",
            "city",
            "country",
            "status",
            "total_students",
            "total_users",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_total_students(self, obj):
        # return obj.students.filter(status="active").count()
        return 0

    def get_total_users(self, obj):
        return obj.users.filter(is_active=True).count()


class MySchoolUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = [
            "name",
            "school_code",
            "logo",
            "email",
            "phone",
            "address",
            "city",
            "country",
        ]

    def validate_name(self, value):
        if School.objects.filter(name=value).exclude(id=self.instance.id).exists():
            raise serializers.ValidationError("A school with this name already exists.")
        return value
    
    def validate_school_code(self, value):
        if value and School.objects.filter(school_code=value).exclude(id=self.instance.id).exists():
            raise serializers.ValidationError("This school code is already in use.")
        
        if len(value) > 4:
            raise serializers.ValidationError("School code must be at most 4 characters long.")
        return value.upper()
    
    def validate_phone(self, value):
        if value and School.objects.filter(phone=value).exclude(id=self.instance.id).exists():
            raise serializers.ValidationError("This phone number is already in use.")
        
        if re.match(r"^\+?\d{7,15}$", value) is None:
            raise serializers.ValidationError("Enter a valid phone number (7-15 digits, optional leading +).")
        return value
    
    def validate_email(self, value):
        if value and School.objects.filter(email=value).exclude(id=self.instance.id).exists():
            raise serializers.ValidationError("This email is already in use.")
    
        if value and re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", value) is None:
            raise serializers.ValidationError("Enter a valid email address.")
        return value


class SchoolProfileSerializer(serializers.ModelSerializer):
    

    class Meta:
        model = School
        fields = [
            "id",
            "name",
            "school_code",
            "logo",
            "email",
            "school_email_domain",
            "phone",
            "address",
            "city",
            "country",
        ]
        
