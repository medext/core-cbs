"""Party registry (data plane). PII lives here and only here — the ledger and accounts
reference parties by opaque id. PII is never logged (security rules)."""

import uuid

from django.db import models
from django.db.models import Q

from next_core.platform.persistence import TenantScopedManager


class PartyType(models.TextChoices):
    INDIVIDUAL = "INDIVIDUAL"
    ORGANIZATION = "ORGANIZATION"


class PartyStatus(models.TextChoices):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    DECEASED = "DECEASED"
    CLOSED = "CLOSED"


class KycStatus(models.TextChoices):
    NOT_STARTED = "NOT_STARTED"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class RiskRating(models.TextChoices):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Party(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    type = models.CharField(max_length=12, choices=PartyType.choices)
    status = models.CharField(max_length=10, choices=PartyStatus.choices, default="ACTIVE")
    external_ref = models.CharField(max_length=64, blank=True, default="")
    display_name = models.CharField(max_length=200)
    given_name = models.CharField(max_length=100, blank=True, default="")
    family_name = models.CharField(max_length=100, blank=True, default="")
    legal_name = models.CharField(max_length=200, blank=True, default="")
    registration_number = models.CharField(max_length=64, blank=True, default="")
    birth_date = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=2, blank=True, default="")
    residence_country = models.CharField(max_length=2, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    kyc_status = models.CharField(max_length=12, choices=KycStatus.choices, default="NOT_STARTED")
    kyc_level = models.PositiveSmallIntegerField(default=0)
    kyc_reference = models.CharField(max_length=128, blank=True, default="")
    risk_rating = models.CharField(max_length=6, choices=RiskRating.choices, default="LOW")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=0)

    objects = TenantScopedManager["Party"]()
    all_objects = models.Manager["Party"]()

    class Meta:
        db_table = "party"
        base_manager_name = "all_objects"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "external_ref"],
                condition=~Q(external_ref=""),
                name="party_external_ref_uniq",
            ),
            models.CheckConstraint(condition=Q(kyc_level__lte=3), name="party_kyc_level_range"),
            models.CheckConstraint(
                condition=~Q(kyc_status="VERIFIED") | Q(kyc_level__gte=1),
                name="party_verified_has_level",
            ),
        ]


class PartyIdentifier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField()
    party = models.ForeignKey(Party, on_delete=models.PROTECT, related_name="identifiers")
    scheme = models.CharField(max_length=30)  # NATIONAL_ID, PASSPORT, NIF, RCCM, ...
    value = models.CharField(max_length=64)
    issuing_country = models.CharField(max_length=2, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantScopedManager["PartyIdentifier"]()
    all_objects = models.Manager["PartyIdentifier"]()

    class Meta:
        db_table = "party_identifier"
        base_manager_name = "all_objects"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "scheme", "issuing_country", "value"],
                name="party_identifier_uniq",
            )
        ]
