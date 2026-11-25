"""Base class for data-plane API views: OIDC authentication + one registered permission per
HTTP method. "Authenticated" alone never grants access."""

from typing import Any, ClassVar

from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

from next_core.iam.authentication import OIDCAuthentication
from next_core.iam.permissions import require_permission


class _DenyAll(BasePermission):
    def has_permission(self, request: Any, view: Any) -> bool:
        return False


class DataPlaneView(APIView):
    authentication_classes = (OIDCAuthentication,)
    method_permissions: ClassVar[dict[str, str]] = {}

    def get_permissions(self) -> list[BasePermission]:
        method = self.request.method or ""
        code = self.method_permissions.get(method)
        if code is None:
            # Unsupported method → let DRF answer 405; a handler without a mapped
            # permission is denied (never "authenticated is enough").
            return [] if not hasattr(self, method.lower()) else [_DenyAll()]
        return [require_permission(code)()]
