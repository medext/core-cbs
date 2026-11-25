"""Operations commands, outbox relay semantics, parties & product lifecycle services."""

import uuid
from collections.abc import Callable
from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from next_core.control_plane.models import Tenant
from next_core.parties import application as parties
from next_core.platform.actor import Actor
from next_core.platform.errors import (
    ConflictStateError,
    DuplicateResourceError,
    MakerCheckerViolationError,
    NotFoundError,
    ValidationFailedError,
)
from next_core.platform.outbox.models import OutboxEvent, OutboxStatus
from next_core.platform.outbox.service import MAX_ATTEMPTS, relay_batch
from next_core.products import application as products
from next_core.products.catalog import SAVINGS
from next_core.products.models import Product
from next_core.tenancy.context import TenantContext, tenant_context
from tests import factories as f
from tests.conftest import TENANT_DBS, ctx_for

pytestmark = [pytest.mark.integration, pytest.mark.django_db(databases=TENANT_DBS)]
MAKER, CHECKER = Actor("maker@alpha"), Actor("checker@alpha")


def test_operations_commands_run_per_tenant(tenants: dict[str, Tenant]) -> None:
    out = StringIO()
    call_command("bootstrap_tenant", stdout=out)
    call_command("bootstrap_tenant", "--tenant", "alpha", "--coa-only", stdout=out)
    assert "products activated: CURRENT" in out.getvalue()
    with tenant_context(ctx_for(tenants["alpha"])):
        acc = f.account({p.code: p.id for p in Product.objects.all()}, "SAVINGS")
        f.deposit(acc, "1000.00")
    call_command("run_eod_steps", "--tenant", "alpha", stdout=out)
    call_command("verify_ledger", stdout=out)
    call_command("relay_outbox", "--tenant", "alpha", stdout=out)
    text = out.getvalue()
    assert "accrued=1" in text and "-> OK" in text and "delivered" in text
    with tenant_context(ctx_for(tenants["alpha"])):
        assert not OutboxEvent.objects.filter(status=OutboxStatus.PENDING).exists()


def test_verify_ledger_command_fails_on_findings(tenants: dict[str, Tenant]) -> None:
    from django.db import connections, transaction

    with tenant_context(ctx_for(tenants["alpha"])):
        prods = f.bootstrap()
        acc = f.account(prods)
        f.deposit(acc, "10.00")
        with transaction.atomic(using="tenant_alpha"), connections["tenant_alpha"].cursor() as c:
            c.execute("SELECT set_config('next_core.ledger_writer','on',true)")
            c.execute(
                "UPDATE ledger_balance SET credit_total = credit_total + 1, book_balance = "
                "book_balance + 1, version = version + 1 WHERE id = %s",
                [str(acc.principal_balance_id)],
            )
    with pytest.raises(CommandError, match="alpha"):
        call_command("verify_ledger", "--tenant", "alpha", stdout=StringIO())


def test_outbox_relay_keeps_per_aggregate_order_and_dead_letters(alpha: TenantContext) -> None:
    from django.db import transaction

    from next_core.platform.outbox.service import emit

    with transaction.atomic(using=alpha.db_alias):
        for i in range(3):
            emit("t.e", aggregate_type="agg", aggregate_id="A", payload={"i": i})
        emit("t.e", aggregate_type="agg", aggregate_id="B", payload={"i": 0})
    delivered: list[tuple[str, int]] = []

    def flaky(msg: dict[str, Any]) -> None:
        if msg["aggregate"]["id"] == "A" and msg["data"]["i"] == 0:
            raise OSError("receiver down")
        delivered.append((msg["aggregate"]["id"], msg["data"]["i"]))

    assert relay_batch(flaky) == 1
    assert delivered == [("B", 0)]  # A1, A2 held back behind failed A0
    for _ in range(MAX_ATTEMPTS):
        relay_batch(flaky)
    assert OutboxEvent.objects.get(payload__i=0, aggregate_id="A").status == OutboxStatus.DEAD


def test_party_lifecycle(alpha: TenantContext) -> None:
    p = parties.create_party(
        {
            "type": "ORGANIZATION",
            "display_name": "Acme",
            "legal_name": "Acme SA",
            "external_ref": "X1",
        },
        [{"scheme": "RCCM", "value": "123", "issuing_country": "MR"}],
    )
    with pytest.raises(DuplicateResourceError):
        parties.create_party(
            {"type": "ORGANIZATION", "display_name": "B", "legal_name": "B", "external_ref": "X1"},
            [],
        )
    with pytest.raises(ValidationFailedError):
        parties.create_party({"type": "INDIVIDUAL", "display_name": "no names"}, [])
    with pytest.raises(ValidationFailedError):
        parties.create_party({"type": "ORGANIZATION", "display_name": "no legal"}, [])
    p = parties.update_party(p.id, {"email": "ops@acme.example"})
    assert p.version == 1
    with pytest.raises(ValidationFailedError):
        parties.update_party(p.id, {"kyc_level": 3})
    with pytest.raises(ValidationFailedError):
        parties.record_kyc(p.id, status="VERIFIED", level=0, reference="")
    with pytest.raises(ValidationFailedError):
        parties.record_kyc(p.id, status="PENDING", level=2, reference="")
    parties.change_status(p.id, "BLOCKED", "aml alert")
    parties.change_status(p.id, "CLOSED", "exit")
    with pytest.raises(ConflictStateError):
        parties.change_status(p.id, "ACTIVE", "reopen")
    calls: list[Callable[[], object]] = [
        lambda: parties.get_party(uuid.uuid4()),
        lambda: parties.update_party(uuid.uuid4(), {}),
        lambda: parties.change_status(uuid.uuid4(), "BLOCKED", ""),
        lambda: parties.record_kyc(uuid.uuid4(), status="PENDING", level=0, reference=""),
    ]
    for call in calls:
        with pytest.raises(NotFoundError):
            call()


def test_product_version_lifecycle(alpha: TenantContext) -> None:
    f.bootstrap()
    v1 = products.create_product(
        code="sav2", name="S2", description="", definition=SAVINGS, actor=MAKER
    )
    pid = v1.product_id
    with pytest.raises(DuplicateResourceError):
        products.create_product(
            code="SAV2", name="S2", description="", definition=SAVINGS, actor=MAKER
        )
    with pytest.raises(ConflictStateError):  # only one open draft
        products.new_version(pid, SAVINGS, MAKER)
    products.update_draft(pid, 1, SAVINGS, MAKER)
    with pytest.raises(ConflictStateError):
        products.approve(pid, 1, CHECKER)  # not submitted
    products.submit(pid, 1, MAKER)
    with pytest.raises(ConflictStateError):
        products.update_draft(pid, 1, SAVINGS, MAKER)
    with pytest.raises(MakerCheckerViolationError):
        products.reject(pid, 1, MAKER, "no")
    products.reject(pid, 1, CHECKER, "rates too high")
    with pytest.raises(ConflictStateError):
        products.retire(pid, CHECKER)  # nothing active
    v2 = products.new_version(pid, SAVINGS, MAKER)
    assert v2.version == 2
    products.submit(pid, 2, MAKER)
    products.approve(pid, 2, CHECKER)
    with pytest.raises(ValidationFailedError):  # category is fixed per product
        from next_core.products.catalog import CURRENT_ACCOUNT

        products.new_version(pid, CURRENT_ACCOUNT, MAKER)
    assert products.retire(pid, CHECKER).status == "RETIRED"
    with pytest.raises(NotFoundError):
        products.resolve_version(v1.id)  # rejected versions are not resolvable
    bad_gl = {**SAVINGS, "gl_mapping": {**SAVINGS["gl_mapping"], "fee_income": "2400"}}
    v = products.create_product(
        code="BADGL", name="x", description="", definition=bad_gl, actor=MAKER
    )
    products.submit(v.product_id, 1, MAKER)
    with pytest.raises(ValidationFailedError, match="fee_income"):
        products.approve(v.product_id, 1, CHECKER)
