"""Parties application services. Other contexts use ``party_for_account_opening`` only."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction

from next_core.parties.models import KycStatus, Party, PartyIdentifier, PartyStatus
from next_core.platform.errors import (
    ConflictStateError,
    DuplicateResourceError,
    NotFoundError,
    ValidationFailedError,
)
from next_core.platform.outbox.service import emit
from next_core.tenancy.context import current_tenant

# Legal status transitions (closed/deceased are terminal).
_TRANSITIONS: dict[str, set[str]] = {
    PartyStatus.ACTIVE: {PartyStatus.BLOCKED, PartyStatus.DECEASED, PartyStatus.CLOSED},
    PartyStatus.BLOCKED: {PartyStatus.ACTIVE, PartyStatus.DECEASED, PartyStatus.CLOSED},
    PartyStatus.DECEASED: set(),
    PartyStatus.CLOSED: set(),
}

UPDATABLE_FIELDS = (
    "display_name",
    "given_name",
    "family_name",
    "legal_name",
    "registration_number",
    "birth_date",
    "nationality",
    "residence_country",
    "email",
    "phone",
    "risk_rating",
    "external_ref",
)


@dataclass(frozen=True, slots=True)
class PartyEligibility:
    id: UUID
    status: str
    kyc_status: str
    kyc_level: int


def _alias() -> str:
    return current_tenant().db_alias


def create_party(data: dict[str, Any], identifiers: list[dict[str, str]]) -> Party:
    ctx = current_tenant()
    if data["type"] == "INDIVIDUAL" and not (data.get("given_name") or data.get("family_name")):
        raise ValidationFailedError("Individuals require given_name or family_name.")
    if data["type"] == "ORGANIZATION" and not data.get("legal_name"):
        raise ValidationFailedError("Organizations require legal_name.")
    try:
        with transaction.atomic(using=_alias()):
            party = Party.objects.create(tenant_id=ctx.tenant_id, **data)
            for ident in identifiers:
                PartyIdentifier.objects.create(tenant_id=ctx.tenant_id, party=party, **ident)
            emit(
                "party.created",
                aggregate_type="party",
                aggregate_id=str(party.id),
                payload={"party_id": str(party.id), "type": party.type},
            )
    except IntegrityError as exc:
        raise DuplicateResourceError(
            "A party with this external reference or identifier already exists."
        ) from exc
    return party


def get_party(party_id: UUID) -> Party:
    try:
        return Party.objects.get(id=party_id)
    except Party.DoesNotExist as exc:
        raise NotFoundError("Party not found.") from exc


def update_party(party_id: UUID, changes: dict[str, Any]) -> Party:
    with transaction.atomic(using=_alias()):
        party = Party.objects.select_for_update().filter(id=party_id).first()
        if party is None:
            raise NotFoundError("Party not found.")
        for key, value in changes.items():
            if key not in UPDATABLE_FIELDS:
                raise ValidationFailedError(f"Field '{key}' is not updatable.")
            setattr(party, key, value)
        party.version += 1
        try:
            party.save()
        except IntegrityError as exc:
            raise DuplicateResourceError("external_ref already in use.") from exc
        emit(
            "party.updated",
            aggregate_type="party",
            aggregate_id=str(party.id),
            payload={"party_id": str(party.id), "fields": sorted(changes)},
        )
    return party


def change_status(party_id: UUID, new_status: str, reason: str) -> Party:
    with transaction.atomic(using=_alias()):
        party = Party.objects.select_for_update().filter(id=party_id).first()
        if party is None:
            raise NotFoundError("Party not found.")
        if new_status not in _TRANSITIONS[party.status]:
            raise ConflictStateError(f"Party cannot move from {party.status} to {new_status}.")
        old = party.status
        party.status = new_status
        party.version += 1
        party.save(update_fields=["status", "version", "updated_at"])
        emit(
            "party.status.changed",
            aggregate_type="party",
            aggregate_id=str(party.id),
            payload={"party_id": str(party.id), "from": old, "to": new_status, "reason": reason},
        )
    return party


def record_kyc(party_id: UUID, *, status: str, level: int, reference: str) -> Party:
    """KYC orchestration is external; we record its outcome (status, tier, reference)."""
    if status == KycStatus.VERIFIED and level < 1:
        raise ValidationFailedError("A VERIFIED outcome requires kyc_level >= 1.")
    if status != KycStatus.VERIFIED and level != 0:
        raise ValidationFailedError("Only a VERIFIED outcome may carry a kyc_level > 0.")
    with transaction.atomic(using=_alias()):
        party = Party.objects.select_for_update().filter(id=party_id).first()
        if party is None:
            raise NotFoundError("Party not found.")
        party.kyc_status, party.kyc_level, party.kyc_reference = status, level, reference
        party.version += 1
        party.save(
            update_fields=["kyc_status", "kyc_level", "kyc_reference", "version", "updated_at"]
        )
        emit(
            "party.kyc.recorded",
            aggregate_type="party",
            aggregate_id=str(party.id),
            payload={"party_id": str(party.id), "kyc_status": status, "kyc_level": level},
        )
    return party


def party_for_account_opening(party_id: UUID) -> PartyEligibility:
    """Port used by accounts: eligibility facts only (no PII crosses the boundary)."""
    party = get_party(party_id)
    return PartyEligibility(party.id, party.status, party.kyc_status, party.kyc_level)
