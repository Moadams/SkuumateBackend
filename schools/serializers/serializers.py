from rest_framework import serializers
from ..models import School


class SchoolListSerializer(serializers.ModelSerializer):
    """
    Optimized serializer for the schools list page.
    Flat structure matching exactly what the frontend expects.
    """
    school_id = serializers.UUIDField(source="id", read_only=True)
    school_name = serializers.CharField(source="name", read_only=True)
    school_email = serializers.CharField(source="email", read_only=True)
    school_logo = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    joined = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    package_name = serializers.SerializerMethodField()
    subscription_status = serializers.SerializerMethodField()

    class Meta:
        model = School
        fields = [
            "school_id",
            "school_name",
            "school_email",
            "school_logo",
            "location",
            "joined",
            "status",
            "package_name",
            "subscription_status",
        ]

    def get_school_logo(self, obj):
        request = self.context.get("request")
        if obj.logo and request:
            return request.build_absolute_uri(obj.logo.url)
        return None

    def get_location(self, obj):
        parts = [p for p in [obj.city, obj.country] if p]
        return ", ".join(parts) if parts else "N/A"

    def get_joined(self, obj):
        return obj.created_at.strftime("%b %d, %Y")

    def get_status(self, obj):
        # School is active if it has an accessible subscription
        sub = self.context.get("subscriptions", {}).get(str(obj.id))
        if not sub:
            return "Pending"
        if sub.is_locked:
            return "Inactive"
        if sub.is_accessible:
            return "Active"
        return "Inactive"

    def get_package_name(self, obj):
        sub = self.context.get("subscriptions", {}).get(str(obj.id))
        if sub:
            return sub.plan.name
        return "No Plan"

    def get_subscription_status(self, obj):
        sub = self.context.get("subscriptions", {}).get(str(obj.id))
        if sub:
            return sub.status
        return None


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


