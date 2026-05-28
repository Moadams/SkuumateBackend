from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import LoginView, LogoutView, MeView, ResetPasswordConfirmView, UserExportView, UserListCreateView, UserDetailView

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("users/export/", UserExportView.as_view(), name="user-export"),
    path("users/", UserListCreateView.as_view(), name="user-list-create"),
    path("users/<uuid:pk>/", UserDetailView.as_view(), name="user-detail"),
     path(
        "auth/reset-password/",
        ResetPasswordConfirmView.as_view(),
        name="reset-password-confirm",
    ),
]