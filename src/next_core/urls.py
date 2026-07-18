from django.urls import include, path

urlpatterns = [
    path("health/", include("next_core.platform.health.urls")),
]
