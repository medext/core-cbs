"""Security review M4: every data-plane route with an object id, called by tenant beta with
tenant alpha's ids, must answer 404 RESOURCE_NOT_FOUND without leaking identifiers."""

import json
import uuid

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

from next_core.control_plane.models import Tenant
from next_core.tenancy.context import tenant_context
from tests import factories as f
from tests.conftest import TENANT_DBS, TokenFactory, ctx_for
from tests.e2e.test_api_flows import Api

pytestmark = [pytest.mark.integration, pytest.mark.django_db(databases=TENANT_DBS)]

ALL_ROLES = (
    "teller",
    "supervisor",
    "product_manager",
    "product_approver",
    "operations",
    "auditor",
    "loan_officer",
)


def _routes() -> list[str]:
    out: list[str] = []

    def walk(patterns: list[URLPattern | URLResolver], prefix: str) -> None:
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns, prefix + str(p.pattern))
            else:
                out.append(prefix + str(p.pattern))

    walk(get_resolver().url_patterns, "")
    return [r for r in out if r.startswith("api/v1/") and "<" in r]


def test_every_object_route_masks_foreign_objects(
    tenants: dict[str, Tenant], token_factory: TokenFactory
) -> None:
    with tenant_context(ctx_for(tenants["alpha"])):
        products = f.bootstrap()
        acc, other = f.account(products), f.account(products)
        f.deposit(acc, "100.00")
        from django.db import transaction

        from next_core.ledger.models import JournalEntry
        from next_core.transactions import application as txns
        from next_core.transactions.models import Hold

        with transaction.atomic(using="tenant_alpha"):
            txns.place_hold(acc.id, f.money("1.00"), 3600, txns.CommonFields(), f.TELLER)
        ids = {
            "account_id": acc.id,
            "party_id": acc.party_id,
            "product_id": products["CURRENT"],
            "txn_id": Hold.objects.get().transaction_id,
            "hold_id": Hold.objects.get().id,
            "entry_id": JournalEntry.objects.first().id,  # type: ignore[union-attr]
            "version": 1,
        }
        secrets = {acc.number, other.number}
    with tenant_context(ctx_for(tenants["beta"])):
        f.bootstrap()
    beta = Api(token_factory, "beta", "intruder", *ALL_ROLES)
    routes = _routes()
    assert len(routes) >= 25
    for route in routes:
        path = "/" + route
        for name, value in ids.items():
            path = path.replace(f"<uuid:{name}>", str(value)).replace(f"<int:{name}>", str(value))
        assert "<" not in path, path
        for method in ("get", "post"):
            r = getattr(beta.client, method)(
                path,
                data=json.dumps({}) if method == "post" else None,
                content_type="application/json",
                headers={**beta._headers(str(uuid.uuid4()))},
            )
            if r.status_code == 405:
                continue
            body = r.content.decode()
            assert r.status_code in (400, 404), (method, path, r.status_code, body[:200])
            if r.status_code == 404:
                assert json.loads(body)["code"] == "RESOURCE_NOT_FOUND", (method, path, body)
            for secret in secrets:
                assert secret not in body, (method, path)
