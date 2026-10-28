from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from core.permissions import IsGuardian
from core.responses import ApiResponse
from core.school_permissions import school_permission
from guardian.models import Guardian
from guardian.serializers import (
    GuardianChildSerializer,
    GuardianDetailSerializer,
    GuardianLinkStudentsSerializer,
    GuardianSerializer,
    GuardianStudentSerializer,
    GuardianUnlinkStudentsSerializer,
    GuardianUpdateSerializer,
)
from guardian.services.guardian_service import GuardianService


class GuardianListCreateView(generics.ListCreateAPIView):
    queryset = Guardian.objects.prefetch_related("guardian_students")
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
            guardian = self.service.create_guardian(validated_data, school)
            return ApiResponse.created(
                data=self.get_serializer(guardian).data,
                message="Guardian created successfully"
            )
        except Exception as e:
            return ApiResponse.error(str(e))


class GuardianScopedMixin:
    """Resolves a guardian from the URL, limited to the requester's school."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = GuardianService()

    def get_queryset(self):
        return (
            Guardian.objects.filter(school=self.request.user.school)
            .select_related("user_account")
            .prefetch_related("guardian_students__student")
        )


class GuardianDetailView(GuardianScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (
        school_permission(read="guardians.list", edit="guardians.edit", delete="guardians.delete"),
    )

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return GuardianUpdateSerializer
        return GuardianDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        return ApiResponse.success(data=self.get_serializer(self.get_object()).data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        guardian = self.get_object()
        serializer = self.get_serializer(guardian, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        try:
            guardian = self.service.update_guardian(guardian, serializer.validated_data)
        except ValueError as e:
            return ApiResponse.error(str(e))
        return ApiResponse.success(
            data=GuardianDetailSerializer(guardian).data,
            message="Guardian updated successfully",
        )

    def destroy(self, request, *args, **kwargs):
        self.service.delete_guardian(self.get_object())
        return ApiResponse.success(message="Guardian deleted successfully")


class GuardianLinkStudentsView(GuardianScopedMixin, generics.GenericAPIView):
    """POST: link one or more students to the guardian."""
    serializer_class = GuardianLinkStudentsSerializer
    permission_classes = (school_permission(write="guardians.edit"),)

    def post(self, request, *args, **kwargs):
        guardian = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.service.link_students(guardian, serializer.validated_data["students"])
        except ValueError as e:
            return ApiResponse.error(str(e))
        return ApiResponse.created(
            data=GuardianDetailSerializer(self.get_object()).data,
            message="Students linked to guardian successfully",
        )


class GuardianUnlinkStudentsView(GuardianScopedMixin, generics.GenericAPIView):
    """POST: unlink one or more students from the guardian."""
    serializer_class = GuardianUnlinkStudentsSerializer
    permission_classes = (school_permission(write="guardians.edit"),)

    def post(self, request, *args, **kwargs):
        guardian = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.service.unlink_students(guardian, serializer.validated_data["students"])
        except ValueError as e:
            return ApiResponse.error(str(e))
        return ApiResponse.success(
            data=GuardianDetailSerializer(self.get_object()).data,
            message="Students unlinked from guardian successfully",
        )


class GuardianStudentView(generics.ListAPIView):
    """The logged-in guardian's linked students. Not paginated."""
    serializer_class = GuardianChildSerializer
    permission_classes = (IsAuthenticated, IsGuardian)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "guardian_students"
    pagination_class = None
    filter_backends = (SearchFilter, OrderingFilter)
    search_fields = ('first_name', 'last_name', 'other_names', 'student_id')
    ordering_fields = ('first_name', 'last_name', 'student_id')
    ordering = ('first_name', 'last_name')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.service = GuardianService()

    def get_queryset(self):
        return self.service.get_guardian_students(self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse.success(data=serializer.data)
