from django.urls import include, path

urlpatterns = [
    path("health/", include("next_core.platform.health.urls")),
    path("api/v1/audit/", include("next_core.audit.urls")),
]
