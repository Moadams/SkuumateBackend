from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path

from core.media import PublicLogoView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("accounts.urls")),
    path("api/v1/", include("schools.urls")),
    path("api/v1/", include("core.urls")),   
    path("api/v1/", include("academics.urls")), 
    path("api/v1/", include("students.urls")),
    path("api/v1/", include("subscriptions.urls")), 
    path("api/v1/", include("subscriptions.coupon_urls")),
    path("api/v1/", include("attendance.urls")),  
    path("api/v1/", include("staff.urls")), 
    path("api/v1/communications/", include("communications.urls")),
    path("api/v1/", include("exams.urls")),
    path("api/v1/finance/", include("finance.urls")),
    path("api/v1/", include("dashboard.urls")),
    path("api/v1/platform/", include("platform_rbac.urls")),
    re_path(r'^media/(?P<path>.*)$', PublicLogoView.as_view(), name="public-media")
] 


if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
