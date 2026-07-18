"""Audit read API — the first tenant-scoped data-plane endpoint.

Access itself is audited (viewing the audit trail is an auditable operation).
"""

from typing import Any, ClassVar

from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from next_core.audit.models import AuditEvent
from next_core.audit.service import record_event
from next_core.iam.authentication import OIDCAuthentication
from next_core.iam.permissions import AUDIT_READ, require_permission
from next_core.platform.api import BoundedPageNumberPagination


class AuditEventSerializer(serializers.ModelSerializer[AuditEvent]):
    class Meta:
        model = AuditEvent
        # Explicit allow-list (never __all__): tenant_id and source_ip stay internal.
        fields = (
            "id",
            "occurred_at",
            "actor",
            "actor_type",
            "operation",
            "resource_type",
            "resource_id",
            "correlation_id",
            "payload",
        )
        read_only_fields = fields


class AuditEventListView(ListAPIView[AuditEvent]):
    authentication_classes = (OIDCAuthentication,)
    permission_classes = (require_permission(AUDIT_READ),)
    pagination_class = BoundedPageNumberPagination
    serializer_class = AuditEventSerializer
    # Explicit filter allow-list; arbitrary ORM lookups from the client are prohibited.
    allowed_filters: ClassVar[frozenset[str]] = frozenset({"operation", "resource_type"})

    def get_queryset(self) -> Any:
        qs = AuditEvent.objects.all()  # tenant-scoped manager + tenant-routed database
        for name in self.allowed_filters:
            value = self.request.query_params.get(name)
            if value:
                qs = qs.filter(**{name: value[:100]})
        return qs

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        response = super().list(request, *args, **kwargs)
        principal = request.user
        record_event(
            operation="audit.trail.viewed",
            resource_type="audit_event",
            resource_id="*",
            actor=str(principal),
            actor_type="SERVICE" if getattr(principal, "is_service", False) else "USER",
            request=request._request,
        )
        return response
