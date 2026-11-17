from django.contrib import admin
from django.urls import path

from config.health import health

admin.site.site_header = "Creator Campaign Platform"
admin.site.site_title = "Creator Campaign Platform"
admin.site.index_title = "Creators and campaigns"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
]
