from django.urls import path
from .views.views import AdminDashboardView, SchoolListExportView, MySchoolRetrieveUpdateView
from .views.superadmin_views import SuperSchoolDetailView, SchoolListCreateView

urlpatterns = [
    # Superadmin — school management
    path("schools/", SchoolListCreateView.as_view(), name="school-list"),
    path("schools/<uuid:school_id>/", SuperSchoolDetailView.as_view(), name="school-detail"),
    path("schools/export/", SchoolListExportView.as_view(), name="school-list-export"),
    
    path("schools/me/", MySchoolRetrieveUpdateView.as_view(), name="school-detail"),
    # path("dashboard/admin/", AdminDashboardView.as_view(), name="admin-dashboard"),
]