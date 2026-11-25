"""Remaining API surface: account controls & reports, hold release, loans, simulation
variants, product authoring endpoints, ledger reads, error shapes."""

import pytest

from next_core.control_plane.models import Tenant
from next_core.products.catalog import CURRENT_ACCOUNT
from tests.conftest import TENANT_DBS, TokenFactory
from tests.e2e.test_api_flows import Api, _customer, _open, _product_id

pytestmark = [pytest.mark.integration, pytest.mark.django_db(databases=TENANT_DBS)]


def test_account_controls_reports_and_loans(
    seeded: dict[str, Tenant], token_factory: TokenFactory
) -> None:
    teller = Api(token_factory, "alpha", "t1", "teller")
    sup = Api(token_factory, "alpha", "s1", "supervisor")
    officer = Api(token_factory, "alpha", "lo1", "loan_officer")
    app = Api(token_factory, "alpha", "app1", "api_client")
    party = _customer(teller, "Eve", level=2)
    cur = _open(teller, party, _product_id(teller, "CURRENT"))
    loan = _open(teller, party, _product_id(teller, "PERSONAL_LOAN"))
    sav = _open(teller, party, _product_id(teller, "SAVINGS"))

    body = {"target_account_id": cur["id"], "amount": "1000.00", "currency": "MRU"}
    assert app.write(f"/api/v1/loans/{loan['id']}/disbursements", body)[0] == 403  # H2
    st, d = officer.write(f"/api/v1/loans/{loan['id']}/disbursements", body)
    assert st == 201 and d["type"] == "DISBURSEMENT", d
    st, r = teller.write(
        f"/api/v1/loans/{loan['id']}/repayments",
        {
            "source_account_id": cur["id"],
            "amount": "100.00",
            "currency": "MRU",
            "channel": "BRANCH",
        },
    )
    assert st == 201 and r["type"] == "REPAYMENT"

    st, h = teller.write(
        "/api/v1/holds", {"account_id": cur["id"], "amount": "50.00", "currency": "MRU"}
    )
    assert st == 201
    st, hd = teller.get(f"/api/v1/holds/{h['hold']['id']}")
    assert st == 200 and hd["id"] == h["id"]
    st, rel = teller.write(f"/api/v1/holds/{h['hold']['id']}/release")
    assert st == 201 and rel["state"] == "VOIDED"
    assert teller.write(f"/api/v1/holds/{h['hold']['id']}/release")[1]["code"] == "CONFLICT_STATE"

    for kind, extra in (
        ("DEPOSIT", {"account_id": cur["id"]}),
        ("HOLD", {"account_id": cur["id"]}),
        ("TRANSFER", {"source_account_id": cur["id"], "target_account_id": sav["id"]}),
        ("REPAYMENT", {"source_account_id": cur["id"], "target_account_id": loan["id"]}),
        ("DISBURSEMENT", {"source_account_id": loan["id"], "target_account_id": cur["id"]}),
    ):
        st, sim = teller.post(
            "/api/v1/transactions/simulate",
            {"type": kind, "amount": "10.00", "currency": "MRU", **extra},
        )
        assert st == 200 and sim["outcome"].startswith("WOULD"), (kind, sim)
    st, sim = teller.post(
        "/api/v1/transactions/simulate",
        {"type": "WITHDRAWAL", "account_id": sav["id"], "amount": "99999.00", "currency": "MRU"},
    )
    assert sim["outcome"] == "WOULD_BE_REJECTED" and sim["error"]["code"] == "INSUFFICIENT_FUNDS"
    st, _ = teller.post(
        "/api/v1/transactions/simulate", {"type": "TRANSFER", "amount": "1.00", "currency": "MRU"}
    )
    assert st == 400

    st, lims = teller.get(f"/api/v1/accounts/{cur['id']}/limits")
    assert st == 200 and lims[0]["code"] == "DAILY_OUT" and lims[0]["consumed_count"] >= 1
    st, listing = teller.get(f"/api/v1/transactions?account_id={cur['id']}&state=POSTED")
    assert st == 200 and listing["results"]
    assert teller.get("/api/v1/transactions?account_id=nope")[0] == 400
    st, accs = teller.get(f"/api/v1/accounts?party_id={party}&status=ACTIVE")
    assert len(accs["results"]) == 3
    assert teller.get("/api/v1/accounts?party_id=bad")[0] == 400
    st, _ = teller.get(f"/api/v1/accounts/{loan['id']}/statement?purpose=ACCRUED_INTEREST&limit=5")
    assert st == 200
    assert teller.get(f"/api/v1/accounts/{cur['id']}/statement?purpose=ACCRUED_INTEREST")[0] == 400
    assert teller.get(f"/api/v1/accounts/{cur['id']}/statement?after=x")[0] == 400

    assert (
        sup.post(
            f"/api/v1/accounts/{cur['id']}/blocks",
            {"debit_blocked": True, "credit_blocked": False, "reason": "court"},
        )[0]
        == 200
    )
    assert (
        sup.post(f"/api/v1/accounts/{cur['id']}/status", {"status": "FROZEN", "reason": "inv"})[0]
        == 200
    )
    st, hist = teller.get(f"/api/v1/accounts/{cur['id']}/history")
    assert [x["to"] for x in hist] == ["ACTIVE", "ACTIVE", "FROZEN"]
    assert (
        teller.post(f"/api/v1/accounts/{cur['id']}/status", {"status": "ACTIVE", "reason": "x"})[0]
        == 403
    )

    st, p = teller.patch(f"/api/v1/parties/{party}", {"email": "eve@example.org"})
    assert st == 200 and p["email"] == "eve@example.org"
    assert teller.patch(f"/api/v1/parties/{party}", {"kyc_level": 3})[0] == 400
    assert (
        teller.post(f"/api/v1/parties/{party}/status", {"status": "BLOCKED", "reason": "aml"})[0]
        == 200
    )
    st, plist = teller.get("/api/v1/parties?status=BLOCKED")
    assert [x["id"] for x in plist["results"]] == [party]


def test_product_authoring_endpoints(
    seeded: dict[str, Tenant], token_factory: TokenFactory
) -> None:
    pm = Api(token_factory, "alpha", "pm", "product_manager")
    pa = Api(token_factory, "alpha", "pa", "product_approver")
    st, tpl = pm.get("/api/v1/products/templates")
    assert st == 200 and len(tpl) == 5
    st, ok = pm.post("/api/v1/products/validate", {"definition": CURRENT_ACCOUNT})
    assert st == 200 and ok["valid"]
    pid = _product_id(pm, "CURRENT")
    st, prod = pm.get(f"/api/v1/products/{pid}")
    assert prod["active_version"] == 1
    st, _ = pm.post(f"/api/v1/products/{pid}/versions", {"definition": CURRENT_ACCOUNT})
    assert st == 201
    assert (
        pm.put_json(f"/api/v1/products/{pid}/versions/2", {"definition": CURRENT_ACCOUNT})[0] == 200
    )
    assert pm.get(f"/api/v1/products/{pid}/versions/2")[1]["status"] == "DRAFT"
    pm.post(f"/api/v1/products/{pid}/versions/2/submit")
    assert pa.post(f"/api/v1/products/{pid}/versions/2/reject", {})[0] == 400  # reason required
    assert (
        pa.post(f"/api/v1/products/{pid}/versions/2/reject", {"reason": "no"})[1]["status"]
        == "REJECTED"
    )
    st, sim = pm.post(
        f"/api/v1/products/{pid}/simulate",
        {
            "operation": "TRANSFER_OUT",
            "amount": "1000.00",
            "currency": "EUR",
            "version": 1,
            "parameter_overrides": {"overdraft_limit": "10.00"},
            "book_balance": "5.00",
        },
    )
    assert st == 200 and sim["fees"][0]["code"] == "TRANSFER_FEE"
    assert (
        pm.post(
            f"/api/v1/products/{pid}/simulate",
            {"operation": "DEPOSIT", "amount": "1", "currency": "XXX"},
        )[0]
        == 400
    )
    assert (
        pm.post(
            f"/api/v1/products/{pid}/simulate",
            {"operation": "DEPOSIT", "amount": "1", "currency": "MRU", "book_balance": "1.234"},
        )[0]
        == 400
    )
    assert pa.post(f"/api/v1/products/{pid}/retire")[1]["status"] == "RETIRED"
    st, plist = pm.get("/api/v1/products?category=WALLET")
    assert [x["code"] for x in plist["results"]] == ["WALLET"]

    ops = Api(token_factory, "alpha", "ops", "operations")
    st, coa = ops.get("/api/v1/ledger/gl-accounts")
    assert st == 200 and any(g["code"] == "2110" for g in coa)
    assert ops.get("/api/v1/ledger/entries/00000000-0000-0000-0000-000000000000")[0] == 404
    st, err = ops.post("/api/v1/operations/eod", {"business_date": "2999-01-01"})
    assert st == 400 and err["code"] == "VALIDATION_ERROR"


def test_error_shapes(seeded: dict[str, Tenant], token_factory: TokenFactory) -> None:
    teller = Api(token_factory, "alpha", "t1", "teller")
    r = teller.client.generic(
        "POST",
        "/api/v1/parties",
        "not-json",
        content_type="text/plain",
        headers=teller._headers(None),
    )
    assert r.status_code == 415
    r = teller.client.generic(
        "POST",
        "/api/v1/parties",
        "{bad",
        content_type="application/json",
        headers=teller._headers(None),
    )
    assert r.status_code == 400
    st, body = teller.post("/api/v1/parties", {"type": "ALIEN", "display_name": "x"})
    assert st == 400 and body["errors"][0]["field"] == "type"
    st, body = teller.write(
        "/api/v1/transactions/deposits", {"account_id": "x", "amount": "1.001", "currency": "EUR"}
    )
    assert st == 400 and {e["field"] for e in body["errors"]} >= {"account_id"}
    deep = "[" * 100_000 + "]" * 100_000
    r = teller.client.generic(
        "POST",
        "/api/v1/parties",
        deep,
        content_type="application/json",
        headers=teller._headers(None),
    )
    assert r.status_code == 400
    assert teller.client.delete("/api/v1/parties", headers=teller._headers(None)).status_code == 405
