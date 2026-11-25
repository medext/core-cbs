"""Permission registry and enforcement.

Permissions are Next Core concepts; the IAM asserts identity and coarse roles only
(ADR-0008). Every endpoint names its permission explicitly — "authenticated" is never
sufficient. Role bundles below are seeds; institutions recompose them through
configuration (maker-checker is enforced on product configuration — products context).
"""

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from next_core.iam.principal import AuthenticatedPrincipal

# --- Registry (append-only; mirrored by docs/security/authorization-matrix.md) ---------
AUDIT_READ = "audit:read"
PARTIES_READ = "parties:read"
PARTIES_WRITE = "parties:write"
PRODUCTS_READ = "products:read"
PRODUCTS_WRITE = "products:write"  # maker
PRODUCTS_APPROVE = "products:approve"  # checker (never the maker of the same version)
ACCOUNTS_READ = "accounts:read"
ACCOUNTS_OPEN = "accounts:open"
ACCOUNTS_CONTROL = "accounts:control"  # status, blocks, closure
TRANSACTIONS_READ = "transactions:read"
TRANSACTIONS_POST = "transactions:post"  # deposits, withdrawals, transfers, loans
HOLDS_MANAGE = "holds:manage"
LOANS_DISBURSE = "loans:disburse"  # credit decision: never granted to channel clients
TRANSACTIONS_REVERSE = "transactions:reverse"
LEDGER_READ = "ledger:read"
OPERATIONS_RUN = "operations:run"  # EoD steps, integrity runs

PERMISSIONS: frozenset[str] = frozenset(
    {
        AUDIT_READ,
        PARTIES_READ,
        PARTIES_WRITE,
        PRODUCTS_READ,
        PRODUCTS_WRITE,
        PRODUCTS_APPROVE,
        ACCOUNTS_READ,
        ACCOUNTS_OPEN,
        ACCOUNTS_CONTROL,
        TRANSACTIONS_READ,
        TRANSACTIONS_POST,
        HOLDS_MANAGE,
        LOANS_DISBURSE,
        TRANSACTIONS_REVERSE,
        LEDGER_READ,
        OPERATIONS_RUN,
    }
)

_READS = frozenset(
    {AUDIT_READ, PARTIES_READ, PRODUCTS_READ, ACCOUNTS_READ, TRANSACTIONS_READ, LEDGER_READ}
)
_TELLER = frozenset(
    {
        PARTIES_READ,
        PARTIES_WRITE,
        PRODUCTS_READ,
        ACCOUNTS_READ,
        ACCOUNTS_OPEN,
        TRANSACTIONS_READ,
        TRANSACTIONS_POST,
        HOLDS_MANAGE,
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "auditor": _READS,
    "platform_ops": frozenset({AUDIT_READ}),
    "teller": _TELLER,
    "supervisor": _TELLER | {ACCOUNTS_CONTROL, TRANSACTIONS_REVERSE, LOANS_DISBURSE},
    "loan_officer": frozenset(
        {
            PARTIES_READ,
            PRODUCTS_READ,
            ACCOUNTS_READ,
            ACCOUNTS_OPEN,
            TRANSACTIONS_READ,
            LOANS_DISBURSE,
        }
    ),
    "product_manager": frozenset({PRODUCTS_READ, PRODUCTS_WRITE, LEDGER_READ}),
    "product_approver": frozenset({PRODUCTS_READ, PRODUCTS_APPROVE, LEDGER_READ}),
    "operations": frozenset(
        {OPERATIONS_RUN, LEDGER_READ, ACCOUNTS_READ, TRANSACTIONS_READ, PRODUCTS_READ}
    ),
    "api_client": frozenset(
        {
            PARTIES_READ,
            PRODUCTS_READ,
            ACCOUNTS_READ,
            TRANSACTIONS_READ,
            TRANSACTIONS_POST,
            HOLDS_MANAGE,
        }
    ),
}


def permissions_for(roles: frozenset[str]) -> frozenset[str]:
    granted: set[str] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(granted)


def require_permission(code: str) -> type[BasePermission]:
    """DRF permission class enforcing one registered permission code."""
    if code not in PERMISSIONS:
        raise ValueError(f"Unregistered permission code '{code}'.")

    class _RequirePermission(BasePermission):
        message = "Permission denied."
        required = code

        def has_permission(self, request: Request, view: APIView) -> bool:
            principal: Any = request.user
            if not isinstance(principal, AuthenticatedPrincipal):
                return False
            return code in permissions_for(principal.roles)

    return _RequirePermission
