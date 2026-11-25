"""Shared API primitives: pagination, money fields, actor & idempotency extraction,
idempotent-outcome rendering. No business policy."""

from typing import Any

from rest_framework import serializers
from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response

from next_core.platform.actor import Actor
from next_core.platform.errors import IdempotencyKeyRequiredError
from next_core.platform.money import CURRENCIES, AmountFormatError, CurrencyError, Money

IDEMPOTENCY_HEADER = "Idempotency-Key"


class BoundedPageNumberPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class BoundedCursorPagination(CursorPagination):
    """Cursor pagination (API standard for financial collections): stable, opaque cursors."""

    page_size = 50
    page_size_query_param = "limit"
    max_page_size = 200
    ordering = ("-created_at", "-id")


class MoneyInputSerializer(serializers.Serializer[Any]):
    amount = serializers.CharField(max_length=24, help_text='Decimal string, e.g. "100.00".')
    currency = serializers.ChoiceField(choices=sorted(CURRENCIES))

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        try:
            money = Money.from_wire(attrs["amount"], attrs["currency"])
        except (AmountFormatError, CurrencyError, ValueError) as exc:
            raise serializers.ValidationError({"amount": str(exc)}) from exc
        if not money.is_positive:
            raise serializers.ValidationError({"amount": "Amount must be greater than zero."})
        attrs["money"] = money
        return attrs


class StrictSerializer(serializers.Serializer[Any]):
    """Rejects unknown fields (mass-assignment protection; API standards)."""

    def to_internal_value(self, data: Any) -> Any:
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(dict.fromkeys(sorted(unknown), "Unknown field."))
        return super().to_internal_value(data)


def actor_from(request: Request) -> Actor:
    principal = request.user
    is_service = bool(getattr(principal, "is_service", False))
    return Actor(str(principal), "SERVICE" if is_service else "USER")


def idempotency_key(request: Request) -> str:
    key = request.headers.get(IDEMPOTENCY_HEADER, "").strip()
    if not key:
        raise IdempotencyKeyRequiredError(
            f"Financial writes require an {IDEMPOTENCY_HEADER} header (retry with the same key)."
        )
    return key


def outcome_response(status: int, body: dict[str, Any], replayed: bool) -> Response:
    content_type = "application/problem+json" if status >= 400 else "application/json"
    response = Response(body, status=status, content_type=content_type)
    response["Idempotent-Replayed"] = "true" if replayed else "false"
    return response


# Raw OpenAPI schema fragments for responses built from plain dicts.
OBJ: dict[str, Any] = {"type": "object", "additionalProperties": True}
OBJ_LIST: dict[str, Any] = {"type": "array", "items": OBJ}
PROBLEM: dict[str, Any] = {
    "type": "object",
    "description": "RFC 9457 problem details (docs/api/error-catalog.md).",
    "properties": {
        "type": {"type": "string"},
        "title": {"type": "string"},
        "status": {"type": "integer"},
        "code": {"type": "string"},
        "detail": {"type": "string"},
        "retryable": {"type": "boolean"},
        "correlation_id": {"type": "string"},
        "errors": {"type": "array", "items": OBJ},
    },
    "required": ["type", "title", "status", "code", "detail", "retryable", "correlation_id"],
}
