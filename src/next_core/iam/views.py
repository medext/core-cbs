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
        code = self.method_permissions.get(self.request.method or "")
        if code is None:
            return [_DenyAll()]
        return [require_permission(code)()]
