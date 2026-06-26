from rest_framework import serializers
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True)
    actor_email = serializers.CharField(source="actor.email", read_only=True)
    school_name = serializers.CharField(source="school.name", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "action",
            "resource",
            "school_name",
            "resource_id",
            "description",
            "metadata",
            "actor_name",
            "actor_email",
            "ip_address",
            "timestamp",
        ]