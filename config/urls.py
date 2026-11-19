from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from config.health import health

admin.site.site_header = "Creator Campaign Platform"
admin.site.site_title = "Creator Campaign Platform"
admin.site.index_title = "Creators and campaigns"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="admin:login", permanent=False)),
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
