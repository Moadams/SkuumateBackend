from django.db.models import Count, Q
from rest_framework.views import APIView
from rest_framework.response import Response

from core.permissions import IsSuperAdmin
from core.responses import ApiResponse
from schools.models import School
from schools.serializers.superadmin_serializers import SchoolDetailSerializer


class SuperSchoolDetailView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request, school_id=None):    
        # Fetch specific school details
        try:
            school = School.objects.annotate(
                total_users=Count('users', distinct=True),
                total_active_users=Count('users', filter=Q(users__is_active=True), distinct=True),
                total_students=Count('students', distinct=True),
                total_staff=Count('staff_profiles', distinct=True)
            ).get(id=school_id)
            serializer = SchoolDetailSerializer(school)
            return ApiResponse.success(data = serializer.data)
        except School.DoesNotExist:
            return ApiResponse.error(message="School not found", status_code=404)
    