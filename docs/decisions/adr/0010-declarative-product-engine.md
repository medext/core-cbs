# ADR-0010 — Declarative product engine with a restricted expression language

- **Status:** Proposed
- **Date:** 2026-11-25
- **Deciders:** pending human approval (product owner) — resolves OD-11
- **Supersedes:** —

## Context

The PRD requires a product engine able to configure any financial product (deposits, wallets,
term deposits, loans) per tenant without code changes, comparable in ambition to Mambu and
Thought Machine. Master-prompt §13 and the security rules forbid executing tenant-supplied
code; invariant 21 forbids configuration changes from rewriting historical behavior; the
maker-checker rule applies to all configuration changes. OD-11 asked for the formalism.

## Decision

We will model products as **versioned, immutable, declarative JSON definitions** (schema v1,
`src/next_core/products/definition.py`) validated into typed objects and interpreted by the
transactions orchestrator:

- typed parameters with bounds and account-level overrides (Mambu-style);
- declared GL mapping per role, checked against the chart of accounts at approval;
- fees (FLAT / PERCENTAGE / TIERED / EXPRESSION), limits (TRANSACTION / DAILY / MONTHLY with
  locked counters), operation guards, interest (day count, capitalization), credit line /
  overdraft, lifecycle;
- logic is expressed only in a **restricted expression language**: Python `ast` parsing plus
  a whitelist interpreter (no `eval`/`exec`), Decimal-only numbers built from literal source
  text, `min`/`max`/`abs` as the only functions, ≤ 500 chars / ≤ 120 nodes;
- version lifecycle DRAFT → PENDING_APPROVAL → ACTIVE → SUPERSEDED/RETIRED (or REJECTED),
  activation at approval, maker ≠ checker enforced in application code **and** by a database
  CHECK; non-draft definitions immutable by trigger; accounts pinned to their version.

Full reference: [product engine](../../products/product-engine.md).

## Alternatives considered

- **Executable product contracts (Thought Machine "smart contracts" in Python)** — maximal
  expressiveness, but executing tenant-supplied code inside the core breaks the prohibition
  on arbitrary code execution, needs a sandbox we would have to secure and operate (CPU,
  memory, I/O, determinism), and makes product behavior hard to review in maker-checker.
  Rejected.
- **Hard-coded product classes per category** — simplest, but every new product becomes a
  release, and tenant-specific code forks are prohibited. Rejected.
- **Third-party rules engine / DSL (e.g. JSON-logic, CEL)** — viable; rejected for now to
  avoid a new dependency and because the needed grammar is small. Revisit by superseding ADR
  if expressions outgrow the whitelist.

## Consequences

- **Positive:** products are data — reviewable, diffable (definition hash), simulatable
  (`/products/{id}/simulate`, `/transactions/simulate`), auditable; no deploy per product;
  historical behavior protected by pinning + DB immutability.
- **Negative / accepted costs:** expressiveness is bounded (no loops, no state, no schedules);
  new behaviors need a schema extension (versioned `schema_version`); evaluator correctness is
  security-critical and must stay heavily tested.
- **Neutral / follow-ups:** future-dated activation (OD-33), account migration between
  versions, amortization schedules, schema v2 evolution policy.

## Compliance & security impact

Removes a whole class of code-injection risk from configuration (threat model: tenant-admin
abuse). Maker-checker evidence is captured in audit events and immutable version rows.

## Reversibility

Moderate: the definition parser isolates the format; a future engine can read v1 documents
or migrate them into a v2 schema without touching accounts (they reference version ids).
