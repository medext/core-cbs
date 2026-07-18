from django.urls import path

from next_core.audit.api import AuditEventListView

urlpatterns = [
    path("events", AuditEventListView.as_view(), name="audit-events"),
]
