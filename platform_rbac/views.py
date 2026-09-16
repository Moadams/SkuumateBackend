from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from accounts.models import User
from core.mixins import AuditLogMixin
from core.models import AuditLog
from core.pagination import StandardPagination
from core.responses import ApiResponse
from core.utils import log_action

from .models import (
    PlatformPermission,
    PlatformRole,
    PlatformRolePermission,
    PlatformUserRole,
)
from .permissions import HasPlatformPermission, require_platform_permission
from .serializers import (
    CodesPayloadSerializer,
    PlatformPermissionSerializer,
    PlatformRoleCreateUpdateSerializer,
    PlatformRoleSerializer,
    PlatformUserCreateSerializer,
    PlatformUserSerializer,
    PlatformUserUpdateSerializer,
)
from .services import (
    PLATFORM_STAFF_ROLE,
    get_user_platform_permissions,
    get_user_platform_roles,
    self_modification_blocked,
    validate_assignable_permissions,
    validate_assignable_roles,
)


def _require_object_or_404(model, code):
    obj = model.objects.filter(code=code).first()
    if obj is None:
        raise NotFound(f"Unknown code: {code}.")
    return obj


def _guard_assignable(fn, *args):
    try:
        fn(*args)
    except PermissionError as exc:
        raise PermissionDenied(str(exc))


def _platform_user_or_404(pk):
    user = get_object_or_404(User, pk=pk)
    if not (user.is_superuser or user.role == PLATFORM_STAFF_ROLE):
        raise NotFound("Platform user not found.")
    return user


class PlatformUserListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    audit_resource = "PlatformUser"
    serializer_class = PlatformUserSerializer
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["is_active"]
    search_fields = ["email", "first_name", "last_name", "phone"]

    def get_queryset(self):
        return User.objects.filter(
            Q(role=PLATFORM_STAFF_ROLE) | Q(is_superuser=True)
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PlatformUserCreateSerializer
        return super().get_serializer_class()

    def get_permissions(self):
        code = "platform_users.create" if self.request.method == "POST" else "platform_users.view"
        return [require_platform_permission(code)()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = self.perform_create(serializer)
        return ApiResponse.created(
            data=PlatformUserSerializer(user).data,
            message="Platform user created successfully.",
        )


class PlatformUserRetrieveUpdateView(AuditLogMixin, generics.RetrieveUpdateAPIView):
    audit_resource = "PlatformUser"
    serializer_class = PlatformUserSerializer

    def get_queryset(self):
        return User.objects.filter(
            Q(role=PLATFORM_STAFF_ROLE) | Q(is_superuser=True)
        )

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return PlatformUserUpdateSerializer
        return super().get_serializer_class()

    def get_permissions(self):
        code = "platform_users.update" if self.request.method in ("PATCH", "PUT") else "platform_users.view"
        return [require_platform_permission(code)()]

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", self.request.method == "PATCH")
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        user = self.perform_update(serializer)
        return ApiResponse.success(
            data=PlatformUserSerializer(user).data,
            message="Platform user updated successfully.",
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return ApiResponse.success(
            data=serializer.data,
            message="Platform user retrieved successfully.",
        )


class PlatformUserActivateDeactivateView(AuditLogMixin, APIView):
    """POST /users/{id}/activate/ or /users/{id}/deactivate/."""

    audit_resource = "PlatformUser"

    def get_permissions(self):
        return [require_platform_permission("platform_users.deactivate")()]

    def post(self, request, pk, activate=False):
        target = _platform_user_or_404(pk)

        if activate and target.is_active:
            return ApiResponse.success(data=PlatformUserSerializer(target).data, message="Platform user is already active.")
        if not activate and not target.is_active:
            return ApiResponse.success(data=PlatformUserSerializer(target).data, message="Platform user is already inactive.")

        if target.is_superuser and not activate:
            raise ValidationError({"detail": "Root superusers cannot be deactivated."})
        if self_modification_blocked(request.user, target):
            raise PermissionDenied("You cannot deactivate your own platform account.")

        target.is_active = activate
        target.save(update_fields=["is_active", "updated_at"])
        log_action(
            action=AuditLog.Action.UPDATE,
            resource=self.audit_resource,
            resource_id=str(target.pk),
            description=f"{request.user.full_name} {'activated' if activate else 'deactivated'} platform user {target.email}",
            request=request,
            metadata={"is_active": activate},
        )
        message = "Platform user activated successfully." if activate else "Platform user deactivated successfully."
        return ApiResponse.success(data=PlatformUserSerializer(target).data, message=message)


class PlatformUserRolesView(AuditLogMixin, APIView):
    """GET list roles / POST assign roles / DELETE remove roles for a user."""
    audit_resource = "PlatformUserRole"

    def get_permissions(self):
        if self.request.method == "GET":
            return [require_platform_permission("platform_users.view")()]
        return [require_platform_permission("platform_users.assign_roles")()]

    def get(self, request, pk):
        target = _platform_user_or_404(pk)
        return ApiResponse.success(
            data={"roles": get_user_platform_roles(target)},
            message="Platform user roles retrieved successfully.",
        )

    def post(self, request, pk):
        target = _platform_user_or_404(pk)
        codes = self._validated_codes()
        if target.is_superuser:
            raise ValidationError({"detail": "Root superusers already have all permissions; role assignment is not needed."})
        roles = [self._resolve_role(code) for code in codes]
        inactive = [r.code for r in roles if not r.is_active]
        if inactive:
            raise ValidationError({"detail": f"Cannot assign inactive roles: {', '.join(inactive)}."})
        _guard_assignable(validate_assignable_roles, request.user, roles)

        existing = set(
            PlatformUserRole.objects.filter(user=target, role__in=roles)
            .values_list("role__code", flat=True)
        )
        duplicate = set(codes) & existing
        if duplicate:
            raise ValidationError({"detail": f"Role(s) already assigned: {', '.join(sorted(duplicate))}."})

        with transaction.atomic():
            for role in roles:
                PlatformUserRole.objects.create(user=target, role=role)
                log_action(
                    action=AuditLog.Action.UPDATE,
                    resource=self.audit_resource,
                    resource_id=str(role.pk),
                    description=f"{request.user.full_name} assigned role {role.code} to {target.email}",
                    request=request,
                )
        return ApiResponse.success(
            data={"roles": get_user_platform_roles(target)},
            message="Role(s) assigned successfully.",
        )

    def delete(self, request, pk):
        target = _platform_user_or_404(pk)
        codes = self._validated_codes()
        if self_modification_blocked(request.user, target):
            raise PermissionDenied("You cannot change your own platform roles.")
        roles = list(PlatformRole.objects.filter(code__in=codes))
        self._reject_unknown(codes, roles)

        assigned = {
            row.role_id: row
            for row in PlatformUserRole.objects.filter(user=target, role__in=roles)
        }
        unassigned = [r.code for r in roles if r.pk not in assigned]
        if unassigned:
            raise ValidationError({"detail": f"Role(s) are not assigned to this user: {', '.join(unassigned)}."})

        with transaction.atomic():
            for role in roles:
                row = assigned[role.pk]
                row.delete()
                log_action(
                    action=AuditLog.Action.UPDATE,
                    resource=self.audit_resource,
                    resource_id=str(role.pk),
                    description=f"{request.user.full_name} removed role {role.code} from {target.email}",
                    request=request,
                )
        return ApiResponse.success(
            data={"roles": get_user_platform_roles(target)},
            message="Role(s) removed successfully.",
        )

    def _validated_codes(self):
        serializer = CodesPayloadSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data["codes"]

    def _resolve_role(self, code):
        return _require_object_or_404(PlatformRole, code)

    def _reject_unknown(self, codes, roles):
        found = {role.code for role in roles}
        missing = set(codes) - found
        if missing:
            raise NotFound(f"Unknown role code(s): {', '.join(sorted(missing))}.")


class PlatformUserPermissionsView(APIView):
    """GET effective platform permissions for a user."""

    def get_permissions(self):
        return [require_platform_permission("platform_users.view")()]

    def get(self, request, pk):
        target = _platform_user_or_404(pk)
        if target.is_superuser:
            permissions = ["*"]
        else:
            permissions = sorted(get_user_platform_permissions(target))
        return ApiResponse.success(
            data={
                "user": PlatformUserSerializer(target).data,
                "permissions": permissions,
            },
            message="Effective platform permissions retrieved successfully.",
        )


class PlatformRoleListCreateView(AuditLogMixin, generics.ListCreateAPIView):
    audit_resource = "PlatformRole"
    pagination_class = StandardPagination
    filter_backends = [SearchFilter]
    search_fields = ["name", "code", "description"]
    queryset = PlatformRole.objects.all()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PlatformRoleCreateUpdateSerializer
        return PlatformRoleSerializer

    def get_permissions(self):
        code = "roles.create" if self.request.method == "POST" else "roles.view"
        return [require_platform_permission(code)()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = self.perform_create(serializer)
        return ApiResponse.created(
            data=PlatformRoleSerializer(role).data,
            message="Platform role created successfully.",
        )


class PlatformRoleRetrieveUpdateView(AuditLogMixin, generics.RetrieveUpdateAPIView):
    audit_resource = "PlatformRole"
    queryset = PlatformRole.objects.all()

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return PlatformRoleCreateUpdateSerializer
        return PlatformRoleSerializer

    def get_permissions(self):
        code = "roles.update" if self.request.method in ("PATCH", "PUT") else "roles.view"
        return [require_platform_permission(code)()]

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", self.request.method == "PATCH")
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        if instance.is_system_role and "code" in serializer.validated_data:
            raise ValidationError({"detail": "The code of a system role cannot be changed."})

        role = self.perform_update(serializer)
        return ApiResponse.success(
            data=PlatformRoleSerializer(role).data,
            message="Platform role updated successfully.",
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return ApiResponse.success(
            data=serializer.data,
            message="Platform role retrieved successfully.",
        )


class PlatformRoleActivateDeactivateView(AuditLogMixin, APIView):
    """POST /roles/{id}/activate/ or /roles/{id}/deactivate/."""

    audit_resource = "PlatformRole"

    def get_permissions(self):
        return [require_platform_permission("roles.deactivate")()]

    def post(self, request, pk, activate=False):
        role = get_object_or_404(PlatformRole, pk=pk)

        if not activate and role.is_system_role:
            raise ValidationError({"detail": "System roles cannot be deactivated."})
        if activate and role.is_active:
            return ApiResponse.success(data=PlatformRoleSerializer(role).data, message="Platform role is already active.")
        if not activate and not role.is_active:
            return ApiResponse.success(data=PlatformRoleSerializer(role).data, message="Platform role is already inactive.")

        role.is_active = activate
        role.save(update_fields=["is_active", "updated_at"])
        log_action(
            action=AuditLog.Action.UPDATE,
            resource=self.audit_resource,
            resource_id=str(role.pk),
            description=f"{request.user.full_name} {'activated' if activate else 'deactivated'} role {role.code}",
            request=request,
        )
        message = "Platform role activated successfully." if activate else "Platform role deactivated successfully."
        return ApiResponse.success(data=PlatformRoleSerializer(role).data, message=message)


class PlatformRolePermissionsView(AuditLogMixin, APIView):
    """GET list permissions / POST assign permissions / DELETE remove permissions."""

    audit_resource = "PlatformRolePermission"

    def get_permissions(self):
        if self.request.method == "GET":
            return [require_platform_permission("roles.view")()]
        return [require_platform_permission("roles.assign_permissions")()]

    def get(self, request, pk):
        role = get_object_or_404(PlatformRole, pk=pk)
        return self._role_payload(role)

    def post(self, request, pk):
        role = get_object_or_404(PlatformRole, pk=pk)
        serializer = CodesPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        codes = serializer.validated_data["codes"]

        permissions = self._resolve_permissions(codes)
        inactive = [p.code for p in permissions if not p.is_active]
        if inactive:
            raise ValidationError({"detail": f"Cannot assign inactive permissions: {', '.join(inactive)}."})
        _guard_assignable(validate_assignable_permissions, request.user, codes)

        existing = set(
            PlatformRolePermission.objects.filter(role=role, permission__in=permissions)
            .values_list("permission__code", flat=True)
        )
        duplicate = set(codes) & existing
        if duplicate:
            raise ValidationError({"detail": f"Permission(s) already assigned to this role: {', '.join(sorted(duplicate))}."})

        with transaction.atomic():
            for permission in permissions:
                PlatformRolePermission.objects.create(role=role, permission=permission)
                log_action(
                    action=AuditLog.Action.UPDATE,
                    resource=self.audit_resource,
                    resource_id=str(permission.pk),
                    description=f"{request.user.full_name} granted permission {permission.code} to role {role.code}",
                    request=request,
                )
        return ApiResponse.success(data=self._role_payload(role), message="Permission(s) assigned successfully.")

    def delete(self, request, pk):
        role = get_object_or_404(PlatformRole, pk=pk)
        serializer = CodesPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        codes = serializer.validated_data["codes"]
        permissions = self._resolve_permissions(codes)

        rows = {
            row.permission_id: row
            for row in PlatformRolePermission.objects.filter(role=role, permission__in=permissions)
        }
        not_assigned = [p.code for p in permissions if p.pk not in rows]
        if not_assigned:
            raise ValidationError({"detail": f"Permission(s) not assigned to this role: {', '.join(not_assigned)}."})

        with transaction.atomic():
            for permission in permissions:
                row = rows[permission.pk]
                row.delete()
                log_action(
                    action=AuditLog.Action.UPDATE,
                    resource=self.audit_resource,
                    resource_id=str(permission.pk),
                    description=f"{request.user.full_name} removed permission {permission.code} from role {role.code}",
                    request=request,
                )
        return ApiResponse.success(data=self._role_payload(role), message="Permission(s) removed successfully.")

    def _role_payload(self, role):
        return {"roles": PlatformRoleSerializer(role).data}

    def _resolve_permissions(self, codes):
        permissions = list(PlatformPermission.objects.filter(code__in=codes))
        found = {p.code for p in permissions}
        missing = set(codes) - found
        if missing:
            raise NotFound(f"Unknown permission code(s): {', '.join(sorted(missing))}.")
        return permissions


class PlatformPermissionListView(generics.ListAPIView):
    serializer_class = PlatformPermissionSerializer
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["module", "is_active"]
    search_fields = ["code", "name", "description"]
    queryset = PlatformPermission.objects.all()

    def get_permissions(self):
        return [require_platform_permission("roles.view")()]


class PlatformPermissionRetrieveView(generics.RetrieveAPIView):
    serializer_class = PlatformPermissionSerializer
    queryset = PlatformPermission.objects.all()

    def get_permissions(self):
        return [require_platform_permission("roles.view")()]

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return ApiResponse.success(
            data=serializer.data,
            message="Platform permission retrieved successfully.",
        )


class PlatformMePermissionsView(APIView):
    """GET /platform/me/permissions/ — current platform user's effective access."""

    permission_classes = [HasPlatformPermission]

    def get(self, request):
        user = request.user
        if user.is_superuser:
            permissions = ["*"]
        else:
            permissions = sorted(get_user_platform_permissions(user))
        return ApiResponse.success(
            data={
                "is_superuser": user.is_superuser,
                "roles": get_user_platform_roles(user),
                "permissions": permissions,
            }
        )