from django.urls import path

from . import views

urlpatterns = [
    # ─── Platform users ───────────────────────────────────────────
    path("users/", views.PlatformUserListCreateView.as_view(), name="platform-user-list-create"),
    path("users/<uuid:pk>/", views.PlatformUserRetrieveUpdateView.as_view(), name="platform-user-detail"),
    path("users/<uuid:pk>/activate/", views.PlatformUserActivateDeactivateView.as_view(), {"activate": True}, name="platform-user-activate"),
    path("users/<uuid:pk>/deactivate/", views.PlatformUserActivateDeactivateView.as_view(), {"activate": False}, name="platform-user-deactivate"),
    path("users/<uuid:pk>/roles/", views.PlatformUserRolesView.as_view(), name="platform-user-roles"),
    path("users/<uuid:pk>/permissions/", views.PlatformUserPermissionsView.as_view(), name="platform-user-permissions"),
    # ─── Platform roles ─────────────────────────────────────────────
    path("roles/", views.PlatformRoleListCreateView.as_view(), name="platform-role-list-create"),
    path("roles/<uuid:pk>/", views.PlatformRoleRetrieveUpdateView.as_view(), name="platform-role-detail"),
    path("roles/<uuid:pk>/activate/", views.PlatformRoleActivateDeactivateView.as_view(), {"activate": True}, name="platform-role-activate"),
    path("roles/<uuid:pk>/deactivate/", views.PlatformRoleActivateDeactivateView.as_view(), {"activate": False}, name="platform-role-deactivate"),
    path("roles/<uuid:pk>/permissions/", views.PlatformRolePermissionsView.as_view(), name="platform-role-permissions"),
    # ─── Platform permissions (read-only, seeded by the app) ────────
    path("permissions/", views.PlatformPermissionListView.as_view(), name="platform-permission-list"),
    path("permissions/<uuid:pk>/", views.PlatformPermissionRetrieveView.as_view(), name="platform-permission-detail"),
    # ─── Self ────────────────────────────────────────────────────────
    path("me/permissions/", views.PlatformMePermissionsView.as_view(), name="platform-me-permissions"),
]