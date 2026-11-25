"""Product catalog (data plane): products and immutable, versioned definitions.

DB enforcement (migration 0002):
- a version's ``definition`` can change only while DRAFT; non-draft versions cannot be
  deleted (invariant 21 — historical behavior is never rewritten);
- CHECK: the approver differs from the submitter and the creator (maker-checker backstop);
- partial unique indexes: at most one ACTIVE and one open (DRAFT/PENDING) version per product.
"""

import uuid

from django.db import models
from django.db.models import F, Q

from next_core.platform.persistence import TenantScopedManager


class VersionStatus(models.TextChoices):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True, default="")
    category = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantScopedManager["Product"]()
    all_objects = models.Manager["Product"]()

    class Meta:
        db_table = "product"
        base_manager_name = "all_objects"
        constraints = [
            models.UniqueConstraint(fields=["tenant_id", "code"], name="product_code_uniq")
        ]


class ProductVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=VersionStatus.choices, default="DRAFT")
    definition = models.JSONField()
    definition_hash = models.CharField(max_length=64)
    created_by = models.CharField(max_length=255)
    submitted_by = models.CharField(max_length=255, blank=True, default="")
    approved_by = models.CharField(max_length=255, blank=True, default="")
    approved_at = models.DateTimeField(null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    decision_reason = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantScopedManager["ProductVersion"]()
    all_objects = models.Manager["ProductVersion"]()

    class Meta:
        db_table = "product_version"
        base_manager_name = "all_objects"
        constraints = [
            models.UniqueConstraint(fields=["product", "version"], name="pv_number_uniq"),
            models.UniqueConstraint(
                fields=["product"], condition=Q(status="ACTIVE"), name="pv_one_active"
            ),
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(status__in=["DRAFT", "PENDING_APPROVAL"]),
                name="pv_one_open",
            ),
            models.CheckConstraint(
                condition=Q(approved_by="")
                | (~Q(approved_by=F("submitted_by")) & ~Q(approved_by=F("created_by"))),
                name="pv_maker_checker",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=["ACTIVE", "SUPERSEDED", "RETIRED"])
                | (~Q(approved_by="") & Q(approved_at__isnull=False)),
                name="pv_active_requires_approval",
            ),
        ]
