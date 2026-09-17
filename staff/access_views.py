from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.views import APIView

from core.school_permissions import school_permission
from core.responses import ApiResponse
from core.utils import log_action
from core.models import AuditLog
from core.tenant_serializers import SchoolRelatedFieldsMixin
from staff.models import StaffProfile, StaffPosition, PermissionKey


class StaffAccessSerializer(SchoolRelatedFieldsMixin, serializers.ModelSerializer):
    school_related_fields = ("positions",)
    positions = serializers.PrimaryKeyRelatedField(queryset=StaffPosition.objects.all(), many=True)
    permission_grants = serializers.SlugRelatedField(slug_field="key", queryset=PermissionKey.objects.all(), many=True)
    permission_revokes = serializers.SlugRelatedField(slug_field="key", queryset=PermissionKey.objects.all(), many=True)

    class Meta:
        model = StaffProfile
        fields = ["positions", "permission_grants", "permission_revokes"]


class StaffAccessView(APIView):
    permission_classes = [school_permission(read="school.manage", edit="school.manage")]

    def get(self, request, pk):
        profile = get_object_or_404(StaffProfile, pk=pk, school=request.user.school)
        return ApiResponse.success(data=StaffAccessSerializer(profile, context={"request": request}).data)

    @transaction.atomic
    def patch(self, request, pk):
        profile = get_object_or_404(StaffProfile.objects.select_for_update(), pk=pk, school=request.user.school)
        serializer = StaffAccessSerializer(profile, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_action(action=AuditLog.Action.UPDATE, resource="StaffAccess", resource_id=profile.pk, description="Updated staff permissions", metadata=serializer.data, request=request)
        return ApiResponse.success(data=serializer.data, message="Staff access updated.")
