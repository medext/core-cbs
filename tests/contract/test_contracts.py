"""Contract tests: error catalog ⇄ docs, OpenAPI document ⇄ code, golden dependency rules,
account-number scheme, transaction state machine ⇄ lifecycle spec."""

import ast
import json
import re
from pathlib import Path

import pytest
from drf_spectacular.generators import SchemaGenerator

from next_core.accounts.application import valid_account_number
from next_core.platform.errors import ERROR_CATALOG
from next_core.transactions.application import LEGAL

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "next_core"


def test_every_error_code_is_documented_with_its_status() -> None:
    doc = (ROOT / "docs/api/error-catalog.md").read_text()
    for code, entry in ERROR_CATALOG.items():
        row = re.search(rf"^\|\s*`{code}`\s*\|\s*([^|]+)\|", doc, re.M)
        assert row, f"{code} missing from docs/api/error-catalog.md"
        assert str(entry.status) in row.group(1), f"{code}: documented status != {entry.status}"


def test_committed_openapi_matches_code() -> None:
    gen = SchemaGenerator()  # type: ignore[no-untyped-call]
    generated = gen.get_schema(request=None, public=True)  # type: ignore[no-untyped-call]
    committed = json.loads((ROOT / "docs/api/openapi.json").read_text())
    assert json.loads(json.dumps(generated, default=str)) == committed, (
        "docs/api/openapi.json is stale: run `make openapi`"
    )


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
    return {m for m in found if m.startswith("next_core.")}


def _context_imports(context: str) -> set[str]:
    out: set[str] = set()
    for path in (SRC / context).rglob("*.py"):
        if "migrations" in path.parts:
            continue
        out |= {m.split(".")[1] for m in _imports(path)}
    return out - {context}


# Golden dependency rules (docs/domain/domain-model.md), as built.
ALLOWED: dict[str, set[str]] = {
    "platform": {"tenancy"},  # persistence/outbox need the tenant context type only
    "ledger": {"platform", "tenancy", "iam"},  # iam: API layer only
    "parties": {"platform", "tenancy", "iam"},
    "products": {"platform", "tenancy", "iam", "audit", "ledger", "pricing"},
    "pricing": {"platform", "products"},
    "limits": {"platform", "tenancy", "products"},
    "accounts": {"platform", "tenancy", "iam", "audit", "ledger", "parties", "products", "limits"},
    "transactions": {
        "platform",
        "tenancy",
        "iam",
        "audit",
        "ledger",
        "accounts",
        "products",
        "pricing",
        "limits",
    },
    "control_plane": set(),
}


@pytest.mark.parametrize("context", sorted(ALLOWED))
def test_golden_dependency_rules(context: str) -> None:
    extra = _context_imports(context) - ALLOWED[context]
    assert not extra, f"{context} imports forbidden contexts: {sorted(extra)}"


def test_only_transactions_calls_the_posting_service() -> None:
    offenders = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).parts
        if rel[0] in ("ledger", "transactions"):
            continue
        text = path.read_text()
        if re.search(r"ledger\.post\(|PostingRequest|reversal_specs", text):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, offenders


def test_no_float_in_financial_modules() -> None:
    for context in ("ledger", "transactions", "pricing", "limits", "accounts", "products"):
        for path in (SRC / context).rglob("*.py"):
            text = path.read_text()
            assert "FloatField" not in text and "float(" not in text, path


def test_account_number_check_digits() -> None:
    assert valid_account_number("000000100008")
    assert not valid_account_number("000000100009")


def test_state_machine_matches_lifecycle_spec() -> None:
    spec = (ROOT / "docs/domain/transaction-lifecycle.md").read_text()
    edges = set(re.findall(r"^\s{4}([A-Z]+) --> ([A-Z]+)$", spec, re.M))
    for src, targets in LEGAL.items():
        for dst in targets:
            assert (str(src), str(dst)) in edges, f"{src}->{dst} not in the lifecycle diagram"
