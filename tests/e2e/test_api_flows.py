"""End-to-end business flows through the public HTTP API (real PostgreSQL, real OIDC token
validation against a locally-generated key — mocked only at the IAM boundary).

open customer + account → fund → transfer (fee) → hold → capture → reverse → statement →
EoD interest → integrity → close; product maker-checker; idempotency; cross-tenant isolation.
"""

import json
import uuid
from typing import Any

import pytest
from django.test import Client

from next_core.control_plane.models import Tenant
from next_core.products.catalog import SAVINGS
from next_core.products.management.commands.bootstrap_tenant import bootstrap_current_tenant
from next_core.tenancy.context import tenant_context
from tests.conftest import TENANT_DBS, TokenFactory, ctx_for

pytestmark = [pytest.mark.integration, pytest.mark.django_db(databases=TENANT_DBS)]


class Api:
    def __init__(self, tokens: TokenFactory, tenant: str, subject: str, *roles: str) -> None:
        self.client = Client()
        self.tenant = tenant
        self.token = tokens.mint(tenant, subject=subject, roles=roles)

    def _headers(self, key: str | None) -> dict[str, str]:
        h = {"X-Tenant-ID": self.tenant, "Authorization": f"Bearer {self.token}"}
        if key:
            h["Idempotency-Key"] = key
        return h

    def get(self, path: str) -> tuple[int, Any]:
        r = self.client.get(path, headers=self._headers(None))
        return r.status_code, json.loads(r.content or b"null")

    def post(
        self, path: str, body: dict[str, Any] | None = None, key: str | None = None
    ) -> tuple[int, Any]:
        r = self.client.post(
            path,
            data=json.dumps(body or {}),
            content_type="application/json",
            headers=self._headers(key),
        )
        if r.status_code >= 500 or not r.content.strip().startswith((b"{", b"[")):
            raise AssertionError(f"{path} -> {r.status_code}: {r.content[:300]!r}")
        return r.status_code, json.loads(r.content or b"null")

    def write(self, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        return self.post(path, body, key=str(uuid.uuid4()))


@pytest.fixture()
def seeded(tenants: dict[str, Tenant]) -> dict[str, Tenant]:
    for t in tenants.values():
        with tenant_context(ctx_for(t)):
            bootstrap_current_tenant()
    return tenants


def _product_id(api: Api, code: str) -> str:
    status, body = api.get("/api/v1/products")
    assert status == 200, body
    return str(next(p["id"] for p in body["results"] if p["code"] == code))


def _customer(teller: Api, name: str, level: int = 2) -> str:
    status, party = teller.post(
        "/api/v1/parties",
        {"type": "INDIVIDUAL", "display_name": name, "given_name": name, "nationality": "MR"},
    )
    assert status == 201, party
    status, party = teller.post(
        f"/api/v1/parties/{party['id']}/kyc",
        {"status": "VERIFIED", "level": level, "reference": "ext-1"},
    )
    assert status == 200 and party["kyc_level"] == level
    return str(party["id"])


def _open(teller: Api, party_id: str, product_id: str, **extra: Any) -> dict[str, Any]:
    status, acc = teller.post(
        "/api/v1/accounts",
        {"party_id": party_id, "product_id": product_id, "currency": "MRU", **extra},
    )
    assert status == 201, acc
    return dict(acc)


def test_full_banking_flow(seeded: dict[str, Tenant], token_factory: TokenFactory) -> None:
    teller = Api(token_factory, "alpha", "teller-1", "teller")
    supervisor = Api(token_factory, "alpha", "super-1", "supervisor")
    ops = Api(token_factory, "alpha", "ops-1", "operations")
    current = _product_id(teller, "CURRENT")
    savings = _product_id(teller, "SAVINGS")

    alice, bob = _customer(teller, "Alice"), _customer(teller, "Bob")
    a = _open(teller, alice, current)
    b = _open(teller, bob, current)
    s = _open(teller, alice, savings)
    assert len(a["number"]) == 12 and int(a["number"]) % 97 == 1  # mod-97 check digits
    assert {x["purpose"] for x in s["balances"]} == {"PRINCIPAL", "ACCRUED_INTEREST"}

    # Fund — idempotent replay returns the same transaction
    body = {"account_id": a["id"], "amount": "5000.00", "currency": "MRU", "channel": "BRANCH"}
    st1, dep1 = teller.post("/api/v1/transactions/deposits", body, key="dep-1")
    st2, dep2 = teller.post("/api/v1/transactions/deposits", body, key="dep-1")
    assert (st1, st2) == (201, 201) and dep1["id"] == dep2["id"]
    st3, conflict = teller.post(
        "/api/v1/transactions/deposits", {**body, "amount": "5000.01"}, key="dep-1"
    )
    assert st3 == 409 and conflict["code"] == "IDEMPOTENCY_CONFLICT"
    st4, missing = teller.post("/api/v1/transactions/deposits", body)
    assert st4 == 400 and missing["code"] == "IDEMPOTENCY_KEY_REQUIRED"

    # Transfer with product fee
    st, t = teller.write(
        "/api/v1/transactions/transfers",
        {
            "source_account_id": a["id"],
            "target_account_id": b["id"],
            "amount": "1000.00",
            "currency": "MRU",
        },
    )
    assert st == 201 and t["state"] == "POSTED" and t["total_fees"] == "5.80", t

    # Over-spend is a recorded, replayable rejection
    over = {
        "source_account_id": a["id"],
        "target_account_id": b["id"],
        "amount": "9999.00",
        "currency": "MRU",
    }
    st, rej = teller.post("/api/v1/transactions/transfers", over, key="over-1")
    assert st == 422 and rej["code"] == "INSUFFICIENT_FUNDS" and rej["retryable"] is False
    st, rej2 = teller.post("/api/v1/transactions/transfers", over, key="over-1")
    assert st == 422 and rej2["transaction_id"] == rej["transaction_id"]
    st, rejected_txn = teller.get(f"/api/v1/transactions/{rej['transaction_id']}")
    assert (
        rejected_txn["state"] == "REJECTED"
        and rejected_txn["rejection"]["code"] == "INSUFFICIENT_FUNDS"
    )

    # Hold → partial capture
    st, h = teller.write(
        "/api/v1/holds",
        {"account_id": a["id"], "amount": "300.00", "currency": "MRU", "expires_in_seconds": 3600},
    )
    assert st == 201 and h["state"] == "HELD" and h["funds_reserved"]
    st, acc = teller.get(f"/api/v1/accounts/{a['id']}/balances")
    principal = next(x for x in acc if x["purpose"] == "PRINCIPAL")
    assert principal["held_amount"] == "300.00" and principal["available_balance"] == "3694.20"
    st, cap = teller.write(
        f"/api/v1/holds/{h['hold']['id']}/capture",
        {"target_account_id": b["id"], "amount": "250.00", "currency": "MRU"},
    )
    assert st == 201 and cap["state"] == "POSTED" and cap["hold"]["status"] == "CAPTURED"

    # Reversal needs the supervisor permission
    st, _ = teller.write(f"/api/v1/transactions/{t['id']}/reversal", {"reason": "dispute"})
    assert st == 403
    st, rev = supervisor.write(f"/api/v1/transactions/{t['id']}/reversal", {"reason": "dispute"})
    assert st == 201 and rev["type"] == "REVERSAL" and rev["reversal_of"] == t["id"]
    st, orig = teller.get(f"/api/v1/transactions/{t['id']}")
    assert orig["state"] == "REVERSED" and orig["reversed_by"] == rev["id"]
    st, hist = teller.get(f"/api/v1/transactions/{t['id']}/transitions")
    assert [x["to"] for x in hist] == ["RECEIVED", "VALIDATING", "AUTHORIZED", "POSTED", "REVERSED"]

    # Statement with running book balance
    st, stmt = teller.get(f"/api/v1/accounts/{a['id']}/statement")
    assert st == 200 and stmt["lines"][-1]["running_book_balance"] == "4750.00"

    # Simulation: exact outcome, nothing persisted
    st, sim = teller.post(
        "/api/v1/transactions/simulate",
        {"type": "WITHDRAWAL", "account_id": a["id"], "amount": "100.00", "currency": "MRU"},
    )
    assert (
        st == 200
        and sim["outcome"] == "WOULD_POST"
        and sim["balances_after"][0]["book_balance"] == "4626.80"
    )
    st, acc = teller.get(f"/api/v1/accounts/{a['id']}")
    assert (
        next(x for x in acc["balances"] if x["purpose"] == "PRINCIPAL")["book_balance"] == "4750.00"
    )

    # Savings interest via EoD (idempotent)
    teller.write(
        "/api/v1/transactions/deposits",
        {"account_id": s["id"], "amount": "36500.00", "currency": "MRU"},
    )
    st, eod = ops.post("/api/v1/operations/eod", {})
    assert st == 200 and eod["interest"]["accrued"] == 1
    st, eod2 = ops.post("/api/v1/operations/eod", {})
    assert eod2["interest"]["accrued"] == 0
    st, sb = teller.get(f"/api/v1/accounts/{s['id']}/balances")
    assert next(x for x in sb if x["purpose"] == "ACCRUED_INTEREST")["book_balance"] == "3.00"

    # Ledger integrity & trial balance
    st, run = ops.post("/api/v1/operations/integrity-runs")
    assert st == 201 and run["ok"], run
    st, tb = ops.get("/api/v1/ledger/trial-balance")
    assert tb["totals"]["MRU"]["balanced"] is True

    # Closure rules
    st, err = supervisor.post(
        f"/api/v1/accounts/{b['id']}/status", {"status": "CLOSED", "reason": "x"}
    )
    assert st == 422 and err["code"] == "ACCOUNT_STATE_INVALID"


def test_product_maker_checker_via_api(
    seeded: dict[str, Tenant], token_factory: TokenFactory
) -> None:
    maker = Api(token_factory, "alpha", "pm-1", "product_manager")
    checker = Api(token_factory, "alpha", "pa-1", "product_approver")
    both = Api(token_factory, "alpha", "pm-2", "product_manager", "product_approver")

    bad = {
        "code": "BROKEN",
        "name": "Broken",
        "definition": {**SAVINGS, "currencies": ["MRU", "ZZZ"]},
    }
    st, err = maker.post("/api/v1/products", bad)
    assert st == 400 and err["code"] == "VALIDATION_ERROR" and err["errors"]

    evil = json.loads(json.dumps(SAVINGS))
    evil["operation_rules"] = [
        {"code": "X", "operations": ["DEPOSIT"], "condition": "__import__('os').system('id')"}
    ]
    st, err = maker.post("/api/v1/products/validate", {"definition": evil})
    assert st == 400 and any(e["code"] == "invalid_expression" for e in err["errors"])

    st, v1 = both.post(
        "/api/v1/products", {"code": "SAVINGS_PLUS", "name": "Savings+", "definition": SAVINGS}
    )
    assert st == 201 and v1["status"] == "DRAFT"
    pid = v1["product_id"]
    st, _ = both.post(f"/api/v1/products/{pid}/versions/1/submit")
    assert st == 200
    st, err = both.post(f"/api/v1/products/{pid}/versions/1/approve")
    assert st == 403 and err["code"] == "MAKER_CHECKER_VIOLATION"
    st, err = maker.post(f"/api/v1/products/{pid}/versions/1/approve")
    assert st == 403 and err["code"] == "PERMISSION_DENIED"
    st, active = checker.post(f"/api/v1/products/{pid}/versions/1/approve", {"reason": "ok"})
    assert st == 200 and active["status"] == "ACTIVE" and active["approved_by"] == "pa-1@alpha"

    st, sim = maker.post(
        f"/api/v1/products/{pid}/simulate",
        {"operation": "WITHDRAWAL", "amount": "100.00", "currency": "MRU"},
    )
    assert st == 200 and sim["allowed"] and sim["limits"][0]["code"] == "MONTHLY_WITHDRAWALS"

    # A new version never alters accounts pinned to v1 (invariant 21)
    teller = Api(token_factory, "alpha", "teller-1", "teller")
    acc = _open(teller, _customer(teller, "Carol"), pid)
    v2_def = {
        **SAVINGS,
        "parameters": {
            **SAVINGS["parameters"],
            "interest_rate": {**SAVINGS["parameters"]["interest_rate"], "default": "0.0100"},
        },
    }
    st, v2 = maker.post(f"/api/v1/products/{pid}/versions", {"definition": v2_def})
    assert st == 201 and v2["version"] == 2
    maker.post(f"/api/v1/products/{pid}/versions/2/submit")
    st, _ = checker.post(f"/api/v1/products/{pid}/versions/2/approve")
    assert st == 200
    st, still = teller.get(f"/api/v1/accounts/{acc['id']}")
    assert still["product_version_id"] == v1["id"]
    st, versions = maker.get(f"/api/v1/products/{pid}/versions")
    assert [v["status"] for v in versions] == ["SUPERSEDED", "ACTIVE"]


def test_cross_tenant_access_is_impossible(
    seeded: dict[str, Tenant], token_factory: TokenFactory
) -> None:
    alpha = Api(token_factory, "alpha", "teller-1", "teller")
    beta = Api(token_factory, "beta", "teller-1", "teller")
    acc = _open(alpha, _customer(alpha, "Dan"), _product_id(alpha, "CURRENT"))
    party_id = acc["party_id"]

    for path in (
        f"/api/v1/accounts/{acc['id']}",
        f"/api/v1/parties/{party_id}",
        f"/api/v1/accounts/{acc['id']}/statement",
    ):
        st, body = beta.get(path)
        assert st == 404 and body["code"] == "RESOURCE_NOT_FOUND", (path, body)
        assert acc["number"] not in json.dumps(body)
    st, body = beta.write(
        "/api/v1/transactions/deposits",
        {"account_id": acc["id"], "amount": "1.00", "currency": "MRU"},
    )
    assert st == 404 and body["code"] == "RESOURCE_NOT_FOUND"
    st, listing = beta.get("/api/v1/accounts")
    assert listing["results"] == []
    # alpha token presented to beta → 401 (issuer binding)
    r = Client().get(
        "/api/v1/accounts",
        headers={"X-Tenant-ID": "beta", "Authorization": f"Bearer {alpha.token}"},
    )
    assert r.status_code == 401 and json.loads(r.content)["code"] == "AUTHENTICATION_REQUIRED"


def test_authorization_matrix_denies_by_default(
    seeded: dict[str, Tenant], token_factory: TokenFactory
) -> None:
    auditor = Api(token_factory, "alpha", "aud-1", "auditor")
    client_app = Api(token_factory, "alpha", "app-1", "api_client")
    st, _ = auditor.get("/api/v1/accounts")
    assert st == 200
    for path, body in (
        ("/api/v1/parties", {"type": "INDIVIDUAL", "display_name": "x", "given_name": "x"}),
        ("/api/v1/operations/eod", {}),
        ("/api/v1/products/validate", {"definition": {}}),
    ):
        assert client_app.post(path, body)[0] == 403 or path.endswith("validate")
    st, err = auditor.write(
        "/api/v1/transactions/deposits",
        {"account_id": str(uuid.uuid4()), "amount": "1.00", "currency": "MRU"},
    )
    assert st == 403 and err["code"] == "PERMISSION_DENIED"
    st, err = auditor.post(
        "/api/v1/parties", {"type": "INDIVIDUAL", "display_name": "x", "unknown": 1}
    )
    assert st == 403


def test_openapi_schema_is_public_and_versioned(seeded: dict[str, Tenant]) -> None:
    r = Client().get("/api/schema/openapi.json")
    assert r.status_code == 200
    schema = json.loads(r.content)
    assert schema["openapi"].startswith("3.1")
    assert "/api/v1/transactions/transfers" in schema["paths"]
