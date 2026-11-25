"""Error taxonomy + RFC 9457 problem-details rendering (docs/api/error-catalog.md).

Domain and application code raise ``DomainError`` subclasses carrying a *stable* catalog
code. The DRF exception handler renders every error — domain or framework — in one shape:
``type, title, status, code, detail, retryable, correlation_id[, errors]``. Unknown
exceptions become ``INTERNAL_ERROR`` without leaking internals.

Every code raised here must exist in the catalog (contract-tested).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Final

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exc
from rest_framework.response import Response

from next_core.platform.logging import logger

ERROR_TYPE_BASE: Final = "https://docs.nextcore.example/errors/"


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    status: int
    title: str
    retryable: bool


# Source of truth for codes the code base can emit (mirrors docs/api/error-catalog.md).
ERROR_CATALOG: Final[dict[str, CatalogEntry]] = {
    "VALIDATION_ERROR": CatalogEntry(400, "Validation error", False),
    "IDEMPOTENCY_KEY_REQUIRED": CatalogEntry(400, "Idempotency-Key header required", False),
    "TENANT_RESOLUTION_FAILED": CatalogEntry(400, "Tenant resolution failed", False),
    "AUTHENTICATION_REQUIRED": CatalogEntry(401, "Authentication required", False),
    "PERMISSION_DENIED": CatalogEntry(403, "Permission denied", False),
    "MAKER_CHECKER_VIOLATION": CatalogEntry(403, "Maker-checker violation", False),
    "RESOURCE_NOT_FOUND": CatalogEntry(404, "Resource not found", False),
    "METHOD_NOT_ALLOWED": CatalogEntry(405, "Method not allowed", False),
    "UNSUPPORTED_MEDIA_TYPE": CatalogEntry(415, "Unsupported media type", False),
    "IDEMPOTENCY_CONFLICT": CatalogEntry(409, "Idempotency conflict", False),
    "REQUEST_IN_PROGRESS": CatalogEntry(409, "Request in progress", True),
    "CONFLICT_STATE": CatalogEntry(409, "Illegal state transition", False),
    "DUPLICATE_RESOURCE": CatalogEntry(409, "Duplicate resource", False),
    "INSUFFICIENT_FUNDS": CatalogEntry(422, "Insufficient funds", False),
    "ACCOUNT_STATE_INVALID": CatalogEntry(422, "Account state invalid", False),
    "LIMIT_EXCEEDED": CatalogEntry(422, "Limit exceeded", False),
    "CREDIT_LIMIT_EXCEEDED": CatalogEntry(422, "Credit limit exceeded", False),
    "AMOUNT_EXCEEDS_OUTSTANDING": CatalogEntry(422, "Amount exceeds outstanding", False),
    "CURRENCY_MISMATCH": CatalogEntry(422, "Currency mismatch", False),
    "OPERATION_NOT_ALLOWED": CatalogEntry(422, "Operation not allowed by product", False),
    "PRODUCT_RULE_VIOLATION": CatalogEntry(422, "Product rule violation", False),
    "KYC_LEVEL_INSUFFICIENT": CatalogEntry(422, "KYC level insufficient", False),
    "PARTY_STATE_INVALID": CatalogEntry(422, "Party state invalid", False),
    "PRODUCT_NOT_ACTIVE": CatalogEntry(422, "Product not active", False),
    "UNBALANCED_ENTRY": CatalogEntry(422, "Unbalanced journal entry", False),
    "RATE_LIMITED": CatalogEntry(429, "Rate limited", True),
    "INTERNAL_ERROR": CatalogEntry(500, "Internal error", True),
    "DEPENDENCY_UNAVAILABLE": CatalogEntry(503, "Dependency unavailable", True),
}


@dataclass(frozen=True, slots=True)
class FieldError:
    field: str
    code: str
    message: str


class DomainError(Exception):
    """Base for all expected, classified failures. ``code`` must be in ERROR_CATALOG."""

    code: ClassVar[str] = "VALIDATION_ERROR"

    def __init__(
        self,
        detail: str,
        *,
        errors: list[FieldError] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        if self.code not in ERROR_CATALOG:  # pragma: no cover - programming error guard
            raise RuntimeError(f"Error code '{self.code}' is not in the catalog.")
        self.detail = detail
        self.errors = errors or []
        self.extra = extra or {}

    @property
    def entry(self) -> CatalogEntry:
        return ERROR_CATALOG[self.code]

    def to_problem(self, correlation_id: str) -> dict[str, Any]:
        return problem(self.code, self.detail, correlation_id, self.errors, self.extra)


class ValidationFailedError(DomainError):
    code = "VALIDATION_ERROR"


class IdempotencyKeyRequiredError(DomainError):
    code = "IDEMPOTENCY_KEY_REQUIRED"


class NotFoundError(DomainError):
    code = "RESOURCE_NOT_FOUND"


class IdempotencyConflictError(DomainError):
    code = "IDEMPOTENCY_CONFLICT"


class RequestInProgressError(DomainError):
    code = "REQUEST_IN_PROGRESS"


class ConflictStateError(DomainError):
    code = "CONFLICT_STATE"


class DuplicateResourceError(DomainError):
    code = "DUPLICATE_RESOURCE"


class InsufficientFundsError(DomainError):
    code = "INSUFFICIENT_FUNDS"


class AccountStateInvalidError(DomainError):
    code = "ACCOUNT_STATE_INVALID"


class LimitExceededError(DomainError):
    code = "LIMIT_EXCEEDED"


class CreditLimitExceededError(DomainError):
    code = "CREDIT_LIMIT_EXCEEDED"


class AmountExceedsOutstandingError(DomainError):
    code = "AMOUNT_EXCEEDS_OUTSTANDING"


class CurrencyMismatchError(DomainError):
    code = "CURRENCY_MISMATCH"


class OperationNotAllowedError(DomainError):
    code = "OPERATION_NOT_ALLOWED"


class ProductRuleViolationError(DomainError):
    code = "PRODUCT_RULE_VIOLATION"


class KycLevelInsufficientError(DomainError):
    code = "KYC_LEVEL_INSUFFICIENT"


class PartyStateInvalidError(DomainError):
    code = "PARTY_STATE_INVALID"


class ProductNotActiveError(DomainError):
    code = "PRODUCT_NOT_ACTIVE"


class UnbalancedEntryError(DomainError):
    code = "UNBALANCED_ENTRY"


class MakerCheckerViolationError(DomainError):
    code = "MAKER_CHECKER_VIOLATION"


def problem(
    code: str,
    detail: str,
    correlation_id: str,
    errors: list[FieldError] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = ERROR_CATALOG[code]
    body: dict[str, Any] = {
        "type": ERROR_TYPE_BASE + code,
        "title": entry.title,
        "status": entry.status,
        "code": code,
        "detail": detail,
        "retryable": entry.retryable,
        "correlation_id": correlation_id,
    }
    if errors:
        body["errors"] = [{"field": e.field, "code": e.code, "message": e.message} for e in errors]
    if extra:
        body.update({k: v for k, v in extra.items() if k not in body})
    return body


def _flatten_drf_errors(data: Any, prefix: str = "") -> list[FieldError]:
    out: list[FieldError] = []
    if isinstance(data, dict):
        for key, value in data.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            out.extend(_flatten_drf_errors(value, name))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            if isinstance(value, dict | list):
                out.extend(_flatten_drf_errors(value, f"{prefix}[{index}]"))
            else:
                out.extend(_flatten_drf_errors(value, prefix))
    else:
        code = getattr(data, "code", "invalid")
        out.append(FieldError(prefix or "non_field_errors", str(code), str(data)))
    return out


def problem_response(body: dict[str, Any]) -> Response:
    response = Response(body, status=body["status"], content_type="application/problem+json")
    return response


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF EXCEPTION_HANDLER: one problem-details shape for everything (OD-27)."""
    request = context.get("request")
    correlation_id = str(getattr(getattr(request, "_request", request), "correlation_id", ""))

    if isinstance(exc, DomainError):
        return problem_response(exc.to_problem(correlation_id))

    mapping: list[tuple[type[Exception], str]] = [
        (drf_exc.NotAuthenticated, "AUTHENTICATION_REQUIRED"),
        (drf_exc.AuthenticationFailed, "AUTHENTICATION_REQUIRED"),
        (drf_exc.PermissionDenied, "PERMISSION_DENIED"),
        (DjangoPermissionDenied, "PERMISSION_DENIED"),
        (drf_exc.NotFound, "RESOURCE_NOT_FOUND"),
        (Http404, "RESOURCE_NOT_FOUND"),
        (drf_exc.MethodNotAllowed, "METHOD_NOT_ALLOWED"),
        (drf_exc.UnsupportedMediaType, "UNSUPPORTED_MEDIA_TYPE"),
        (drf_exc.Throttled, "RATE_LIMITED"),
    ]
    if isinstance(exc, drf_exc.ValidationError | drf_exc.ParseError):
        errors = _flatten_drf_errors(exc.detail) if isinstance(exc, drf_exc.ValidationError) else []
        detail = "The request is invalid." if errors else str(getattr(exc, "detail", exc))
        return problem_response(problem("VALIDATION_ERROR", detail, correlation_id, errors))
    for exc_type, code in mapping:
        if isinstance(exc, exc_type):
            detail = str(getattr(exc, "detail", "")) or ERROR_CATALOG[code].title
            response = problem_response(problem(code, detail, correlation_id))
            if code == "AUTHENTICATION_REQUIRED":
                response["WWW-Authenticate"] = 'Bearer realm="next-core"'
            wait = getattr(exc, "wait", None)
            if isinstance(exc, drf_exc.Throttled) and wait:
                response["Retry-After"] = str(int(wait))
            return response

    # Unclassified: log with type only (no payload/PII), respond generically.
    logger.error("api.unhandled_exception", exc_type=type(exc).__name__, exc_info=exc)
    return problem_response(
        problem("INTERNAL_ERROR", "An internal error occurred.", correlation_id)
    )
