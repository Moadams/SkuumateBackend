from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("accounts.urls")),
    path("api/v1/", include("schools.urls")),
    path("api/v1/", include("core.urls")),   
    path("api/v1/", include("academics.urls")), 
    path("api/v1/", include("students.urls")),
    path("api/v1/", include("subscriptions.urls")), 
    path("api/v1/", include("attendance.urls")),  
    path("api/v1/", include("staff.urls")), 
    path("api/v1/communications/", include("communications.urls")),
    path("api/v1/", include("exams.urls")),
    path("api/v1/finance/", include("finance.urls")),
    path("api/v1/", include("dashboard.urls")),
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT})
] 


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)