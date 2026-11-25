"""Product engine application services: catalog, versioning, maker-checker, simulation.

Lifecycle of a version: DRAFT → (submit) PENDING_APPROVAL → (approve by a different
principal) ACTIVE → SUPERSEDED (when a newer version activates) / RETIRED; or
PENDING_APPROVAL → REJECTED. Accounts are pinned to the version in force at opening, so a
new version never rewrites the behavior of existing accounts (invariant 21).
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction

from next_core.audit.service import record_event
from next_core.ledger.application import gl_account
from next_core.platform import clock
from next_core.platform.actor import Actor
from next_core.platform.errors import (
    ConflictStateError,
    DuplicateResourceError,
    MakerCheckerViolationError,
    NotFoundError,
    ProductNotActiveError,
    ValidationFailedError,
)
from next_core.platform.outbox.service import emit
from next_core.products.definition import BalanceSide, ProductDefinition, parse_definition
from next_core.products.models import Product, ProductVersion, VersionStatus
from next_core.tenancy.context import current_tenant

_cache: dict[tuple[UUID, str], ProductDefinition] = {}


@dataclass(frozen=True, slots=True)
class ResolvedVersion:
    product_id: UUID
    product_code: str
    version_id: UUID
    version: int
    status: str
    definition: ProductDefinition


def _alias() -> str:
    return current_tenant().db_alias


def definition_hash(raw: Any) -> str:
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _audit(
    op: str, version: ProductVersion, actor: Actor, extra: dict[str, Any] | None = None
) -> None:
    record_event(
        operation=op,
        resource_type="product_version",
        resource_id=str(version.id),
        actor=actor.id,
        actor_type=actor.type,
        payload={
            "product_id": str(version.product_id),
            "version": version.version,
            **(extra or {}),
        },
    )


def create_product(
    *, code: str, name: str, description: str, definition: Any, actor: Actor
) -> ProductVersion:
    parsed = parse_definition(definition)
    ctx = current_tenant()
    try:
        with transaction.atomic(using=_alias()):
            product = Product.objects.create(
                tenant_id=ctx.tenant_id,
                code=code.upper(),
                name=name,
                description=description,
                category=parsed.category.value,
            )
            version = ProductVersion.objects.create(
                tenant_id=ctx.tenant_id,
                product=product,
                version=1,
                definition=definition,
                definition_hash=definition_hash(definition),
                created_by=actor.id,
            )
            _audit("product.version.drafted", version, actor)
    except IntegrityError as exc:
        raise DuplicateResourceError(f"Product code '{code.upper()}' already exists.") from exc
    return version


def get_product(product_id: UUID) -> Product:
    try:
        return Product.objects.get(id=product_id)
    except Product.DoesNotExist as exc:
        raise NotFoundError("Product not found.") from exc


def get_version(product_id: UUID, version_no: int) -> ProductVersion:
    try:
        return ProductVersion.objects.select_related("product").get(
            product_id=product_id, version=version_no
        )
    except ProductVersion.DoesNotExist as exc:
        raise NotFoundError("Product version not found.") from exc


def _locked_version(product_id: UUID, version_no: int) -> ProductVersion:
    version = (
        ProductVersion.objects.select_for_update()
        .filter(product_id=product_id, version=version_no)
        .first()
    )
    if version is None:
        raise NotFoundError("Product version not found.")
    return version


def new_version(product_id: UUID, definition: Any, actor: Actor) -> ProductVersion:
    parsed = parse_definition(definition)
    ctx = current_tenant()
    with transaction.atomic(using=_alias()):
        product = Product.objects.select_for_update().filter(id=product_id).first()
        if product is None:
            raise NotFoundError("Product not found.")
        if parsed.category.value != product.category:
            raise ValidationFailedError("A product's category cannot change across versions.")
        last = product.versions.order_by("-version").first()
        try:
            with transaction.atomic(using=_alias()):
                version = ProductVersion.objects.create(
                    tenant_id=ctx.tenant_id,
                    product=product,
                    version=(last.version if last else 0) + 1,
                    definition=definition,
                    definition_hash=definition_hash(definition),
                    created_by=actor.id,
                )
        except IntegrityError as exc:
            raise ConflictStateError(
                "This product already has an open draft or pending version."
            ) from exc
        _audit("product.version.drafted", version, actor)
    return version


def update_draft(
    product_id: UUID, version_no: int, definition: Any, actor: Actor
) -> ProductVersion:
    parse_definition(definition)
    with transaction.atomic(using=_alias()):
        version = _locked_version(product_id, version_no)
        if version.status != VersionStatus.DRAFT:
            raise ConflictStateError("Only DRAFT versions can be edited.")
        version.definition = definition
        version.definition_hash = definition_hash(definition)
        version.created_by = actor.id  # the last editor is the maker
        version.save()
        _audit("product.version.edited", version, actor)
    return version


def submit(product_id: UUID, version_no: int, actor: Actor) -> ProductVersion:
    with transaction.atomic(using=_alias()):
        version = _locked_version(product_id, version_no)
        if version.status != VersionStatus.DRAFT:
            raise ConflictStateError("Only DRAFT versions can be submitted.")
        parse_definition(version.definition)
        version.status = VersionStatus.PENDING_APPROVAL
        version.submitted_by = actor.id
        version.save(update_fields=["status", "submitted_by", "updated_at"])
        _audit("product.version.submitted", version, actor)
    return version


def _check_accounting(defn: ProductDefinition) -> None:
    side = "LIABILITY" if defn.balance_side == BalanceSide.LIABILITY else "ASSET"
    expected_types = {
        "principal": side,
        "accrued_interest": side,
        "cash": "ASSET",
        "fee_income": "INCOME",
        "interest_income": "INCOME",
        "interest_expense": "EXPENSE",
        "tax_payable": "LIABILITY",
    }
    for role, code in defn.gl_mapping.items():
        gl = gl_account(code)
        expected = expected_types[role]
        if gl.type != expected:
            raise ValidationFailedError(
                f"GL '{code}' is {gl.type}; role '{role}' of a {defn.balance_side.value} "
                f"product must map to a {expected} account."
            )


def approve(product_id: UUID, version_no: int, actor: Actor, reason: str = "") -> ProductVersion:
    """Checker approval → ACTIVE. Server-side maker-checker: the approver can be neither
    the submitter nor the last editor (also a DB CHECK)."""
    with transaction.atomic(using=_alias()):
        version = _locked_version(product_id, version_no)
        if version.status != VersionStatus.PENDING_APPROVAL:
            raise ConflictStateError("Only PENDING_APPROVAL versions can be approved.")
        if actor.id in (version.submitted_by, version.created_by):
            raise MakerCheckerViolationError("The maker of a change cannot approve it.")
        defn = parse_definition(version.definition)
        _check_accounting(defn)
        ProductVersion.objects.filter(product_id=product_id, status=VersionStatus.ACTIVE).update(
            status=VersionStatus.SUPERSEDED
        )
        version.status = VersionStatus.ACTIVE
        version.approved_by = actor.id
        version.approved_at = clock.now()
        version.effective_from = clock.business_date()
        version.decision_reason = reason[:500]
        version.save()
        _audit("product.version.approved", version, actor, {"reason": reason[:200]})
        emit(
            "product.version.activated",
            aggregate_type="product",
            aggregate_id=str(product_id),
            payload={"product_id": str(product_id), "version": version.version},
        )
    return version


def reject(product_id: UUID, version_no: int, actor: Actor, reason: str) -> ProductVersion:
    with transaction.atomic(using=_alias()):
        version = _locked_version(product_id, version_no)
        if version.status != VersionStatus.PENDING_APPROVAL:
            raise ConflictStateError("Only PENDING_APPROVAL versions can be rejected.")
        if actor.id in (version.submitted_by, version.created_by):
            raise MakerCheckerViolationError("The maker of a change cannot decide on it.")
        version.status = VersionStatus.REJECTED
        version.decision_reason = reason[:500]
        version.save(update_fields=["status", "decision_reason", "updated_at"])
        _audit("product.version.rejected", version, actor, {"reason": reason[:200]})
    return version


def retire(product_id: UUID, actor: Actor) -> ProductVersion:
    """Stop selling the product: no new accounts; existing accounts keep their version."""
    get_product(product_id)  # 404 (not 409) for unknown / foreign products
    with transaction.atomic(using=_alias()):
        version = (
            ProductVersion.objects.select_for_update()
            .filter(product_id=product_id, status=VersionStatus.ACTIVE)
            .first()
        )
        if version is None:
            raise ConflictStateError("The product has no ACTIVE version.")
        version.status = VersionStatus.RETIRED
        version.save(update_fields=["status", "updated_at"])
        _audit("product.retired", version, actor)
    return version


def bootstrap_activate(version: ProductVersion, maker: Actor, checker: Actor) -> ProductVersion:
    """Provisioning-only path (seed catalog): submit as ``maker`` and approve as ``checker``.
    The maker-checker rule still holds (distinct principals, DB CHECK), and both steps are
    audited."""
    submit(version.product_id, version.version, maker)
    return approve(version.product_id, version.version, checker, "bootstrap seed catalog")


def _resolve(version: ProductVersion) -> ResolvedVersion:
    key = (version.id, version.definition_hash)
    defn = _cache.get(key)
    if defn is None:
        defn = parse_definition(version.definition)
        if version.status != VersionStatus.DRAFT:
            _cache[key] = defn
    return ResolvedVersion(
        product_id=version.product_id,
        product_code=version.product.code,
        version_id=version.id,
        version=version.version,
        status=version.status,
        definition=defn,
    )


def active_version(product_id: UUID) -> ResolvedVersion:
    version = (
        ProductVersion.objects.select_related("product")
        .filter(product_id=product_id, status=VersionStatus.ACTIVE)
        .first()
    )
    if version is None:
        raise ProductNotActiveError("The product has no ACTIVE version.")
    return _resolve(version)


def resolve_version(version_id: UUID) -> ResolvedVersion:
    """Any non-draft version (accounts stay pinned to superseded/retired versions)."""
    version = ProductVersion.objects.select_related("product").filter(id=version_id).first()
    if version is None or version.status in (VersionStatus.DRAFT, VersionStatus.REJECTED):
        raise NotFoundError("Product version not found.")
    return _resolve(version)
