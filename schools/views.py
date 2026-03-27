from django.db import transaction
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from core.responses import ApiResponse
from core.permissions import IsAdmin

from .models import School
from .serializers import SchoolSerializer, SchoolCreateSerializer


class SchoolOnboardView(APIView):
    """
    Public endpoint — creates a new school + first admin user.
    Called once during signup. No auth required.
    """
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        serializer = SchoolCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        school = serializer.save()
        return ApiResponse.created(
            data=SchoolSerializer(school).data,
            message="School created successfully. You can now log in.",
        )


class SchoolDetailView(APIView):
    """
    Authenticated endpoint — retrieve or update the current user's school.
    Only admins can update.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self, request):
        return request.user.school

    def get(self, request):
        school = self.get_object(request)
        if not school:
            return ApiResponse.error(
                message="No school associated with this account.",
                status_code=404,
            )
        return ApiResponse.success(data=SchoolSerializer(school).data)

    def patch(self, request):
        if request.user.role != "admin":
            return ApiResponse.error(
                message="Only admins can update school details.",
                status_code=403,
            )
        school = self.get_object(request)
        serializer = SchoolSerializer(school, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return ApiResponse.success(
            data=serializer.data,
            message="School updated successfully.",
        )