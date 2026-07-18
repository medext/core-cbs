"""Control-plane tenant registry (control database only — never financial data).

The control plane manages tenant lifecycle, routing, and entitlements. It has NO code path
that reads or mutates tenant financial data; the registry stores only routing/lifecycle
metadata. The DSN field carries connection routing for the tenant database; production
deployments are expected to reference secret-manager material rather than embed passwords
(tracked as OD-19).
"""

import uuid

from django.core.validators import RegexValidator
from django.db import models

SLUG_VALIDATOR = RegexValidator(
    regex=r"^[a-z][a-z0-9_]{1,30}$",
    message="Tenant slug must be 2-31 chars: lowercase letter first, then [a-z0-9_].",
)


class TenantStatus(models.TextChoices):
    PROVISIONING = "PROVISIONING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DECOMMISSIONED = "DECOMMISSIONED"


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=31, unique=True, validators=[SLUG_VALIDATOR])
    name = models.CharField(max_length=200)
    status = models.CharField(
        max_length=16, choices=TenantStatus.choices, default=TenantStatus.PROVISIONING
    )
    db_alias = models.CharField(max_length=64, unique=True)
    database_dsn = models.CharField(max_length=500)
    deployment_profile = models.CharField(max_length=16, default="shared")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cp_tenant"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(db_alias__startswith="tenant_"),
                name="cp_tenant_alias_prefix",
            )
        ]

    def __str__(self) -> str:
        return f"{self.slug} ({self.status})"
