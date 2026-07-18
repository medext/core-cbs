"""Routing determinism under concurrent mixed-tenant load (gate item).

Parallel workers write audit events for interleaved tenants; afterwards every event must
sit in exactly its tenant's database. Synchronization uses a barrier, not sleeps.
"""

import threading
import uuid

import pytest

from next_core.audit.models import AuditEvent
from next_core.control_plane.models import Tenant
from next_core.tenancy.context import TenantContext, tenant_context
from tests.conftest import TENANT_DBS

pytestmark = pytest.mark.integration

WORKERS_PER_TENANT = 4
EVENTS_PER_WORKER = 5


@pytest.mark.django_db(databases=TENANT_DBS, transaction=True)
def test_concurrent_mixed_tenant_writes_do_not_cross_contaminate(
    tenants: dict[str, Tenant],
) -> None:
    contexts = {
        slug: TenantContext(tenant_id=t.id, slug=t.slug, db_alias=t.db_alias)
        for slug, t in tenants.items()
    }
    barrier = threading.Barrier(WORKERS_PER_TENANT * len(contexts))
    errors: list[Exception] = []

    def worker(slug: str, worker_id: int) -> None:
        try:
            barrier.wait(timeout=30)
            with tenant_context(contexts[slug]):
                for i in range(EVENTS_PER_WORKER):
                    AuditEvent(
                        tenant_id=contexts[slug].tenant_id,
                        actor=f"w{worker_id}",
                        actor_type="SYSTEM",
                        operation=f"conc.{slug}",
                        resource_type="test",
                        resource_id=f"{worker_id}-{i}",
                        correlation_id=str(uuid.uuid4()),
                    ).save()
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(slug, n))
        for slug in contexts
        for n in range(WORKERS_PER_TENANT)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors, errors

    expected = WORKERS_PER_TENANT * EVENTS_PER_WORKER
    for slug, other in (("alpha", "beta"), ("beta", "alpha")):
        db = f"tenant_{slug}"
        own = AuditEvent._base_manager.using(db).filter(operation=f"conc.{slug}").count()
        foreign = AuditEvent._base_manager.using(db).filter(operation=f"conc.{other}").count()
        assert own == expected, f"{db}: expected {expected} own events, got {own}"
        assert foreign == 0, f"{db}: found {foreign} events belonging to {other}"
        # tenant_id column agrees with the database the row lives in (belt and braces)
        mismatched = (
            AuditEvent._base_manager.using(db)
            .filter(operation__startswith="conc.")
            .exclude(tenant_id=contexts[slug].tenant_id)
            .count()
        )
        assert mismatched == 0
