"""
timesdojo/urls.py
-----------------
Root URL configuration.
All app URLs are delegated to dojo/urls.py via include().
Django admin is kept at /django-admin/ for emergency superuser access.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Django's built-in admin at a non-obvious path
    path("django-admin/", admin.site.urls),

    # Everything else lives in the dojo app
    path("", include("dojo.urls")),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
