from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.filters import OrderingFilter, SearchFilter

from core.permissions import IsGuardian
from core.responses import ApiResponse
from core.school_permissions import school_permission
from guardian.models import Guardian
from guardian.serializers import GuardianSerializer, GuardianStudentSerializer
from guardian.services.guardian_service import GuardianService


class GuardianListCreateView(generics.ListCreateAPIView):
    queryset = Guardian.objects.all()
    serializer_class = GuardianSerializer
    permission_classes = (school_permission(read="guardians.list", write="guardians.create"),)
    filter_backends = (DjangoFilterBackend,  OrderingFilter, SearchFilter)
    filterset_fields = ("gender",)
    search_fields = ("first_name", "last_name", "email", "phone", "address", "gender")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = GuardianService()

    def create(self, request, *args, **kwargs):
        school = request.user.school
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        try:
            self.service.create_guardian(validated_data, school)
            return ApiResponse.created(
                data=serializer.data,
                message="Guardian created successfully"
            )
        except Exception as e:
            return ApiResponse.error(str(e))


class GuardianStudentAssignView(generics.ListCreateAPIView):
    serializer_class = GuardianStudentSerializer
    permission_classes = (school_permission(read="guardians.list", write="guardians.create"))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.service = GuardianService()

    def create(self, request, *args, **kwargs):
        school = request.user.school
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        self.service.assign_student_to_guardian(validated_data, school)
        return ApiResponse.created(
            data=serializer.data,
            message="Student assigned to guardian successfully"
        )


class GuardianStudentView(generics.ListAPIView):
    serializer_class = GuardianStudentSerializer
    permission_classes = (IsGuardian,)
    filter_backends = (
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    )
    search_fields = ('student__first_name', 'student__last_name','guardian__first_name', 'guardian__last_name')
    ordering_fields = ('student__first_name', 'student__last_name', 'guardian__first_name', 'guardian__last_name')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.service = GuardianService()

    def get_queryset(self):
        return self.service.get_guardian_students(self.request.user)
