# Phase 0 Architecture Review — Formal Summary

| | |
|---|---|
| **Purpose** | The formal Phase 0 gate document: what was decided, what needs approval, and the exact Phase 1 proposal. |
| **Audience** | The human approver. |
| **Status** | **Awaiting approval** — Phase 1 must not start before it. |

## 1. Executive summary

Phase 0 delivered the complete architecture blueprint for **Next Core**, a bank-grade
lightweight core banking system, as version-controlled documentation plus the Claude Code
development operating system — with zero production code, per the phase mandate. The
recommended architecture is a **Django modular monolith** over **PostgreSQL-per-tenant**,
with an **immutable double-entry ledger kernel** guarded by 25 explicitly enforced
invariants, **database-arbitrated idempotency**, **transactional-outbox events**, external
**OIDC identity**, and one artifact set serving shared-SaaS, dedicated-SaaS, and on-premise
(air-gapped) editions. The design adopts BLNK's strongest ledger ideas (immutability,
balance reconstruction, inflight→holds) and extends them with the constructs real banks
require (CoA, posting rules, business dates, EoD, reconciliation, maker-checker).

## 2. Most important architectural decisions (all Proposed, needing approval)

| ADR | Decision | Why it matters |
|---|---|---|
| [0001](../decisions/adr/0001-modular-monolith.md) | Modular monolith first | Keeps ledger invariants inside single DB transactions; extraction stays possible |
| [0002](../decisions/adr/0002-django-primary-framework.md) | Django+DRF primary; FastAPI only by future ADR | One stack; domain kept out of framework |
| [0003](../decisions/adr/0003-postgresql-authority.md) | PostgreSQL sole financial authority | Constraints/grants as backstop; Redis never decides |
| [0004](../decisions/adr/0004-money-representation.md) | Integer minor units + ISO-4217; round-half-even; decimal-string APIs | Exact money, no float, deterministic rounding |
| [0005](../decisions/adr/0005-multi-tenancy-model.md) | DB-per-tenant + separate control-plane DB | Physical isolation; on-prem = single-tenant case |
| [0006](../decisions/adr/0006-idempotency-design.md) | DB-arbitrated scoped idempotency w/ response replay | At-most-once posting under retries & races |
| [0007](../decisions/adr/0007-transactional-outbox.md) | Outbox + inbox dedup; signed webhooks | Events only after commit (invariant 25) |
| [0008](../decisions/adr/0008-external-iam.md) | External OIDC (Keycloak ref); authz in-product | No credential liability; bring-your-own-IAM on-prem |

## 3. Critical risks (register in [PRD §9](../product/prd.md))

Ledger-correctness defect (mitigated: kernel-first, hostile suite, DB backstops) ·
hot-account contention (lock ordering + hierarchical sub-balances, benchmark-gated) ·
tenant leakage (physical isolation + mandatory cross-tenant suites) · configuration engine
drifting toward code execution (declarative-only, non-negotiable) · discipline erosion
(gates, reviewers, hooks).

## 4. Documents created (this repository)

Claude Code operating system: `CLAUDE.md`, `.claude/rules/`(7), `.claude/agents/`(6),
`.claude/commands/`(4), `.claude/hooks/`(5+settings). Authored docs: PRD, scope, roadmap
w/ gates, development workflow, glossary, domain model, transaction lifecycle, ledger
architecture, accounting model, invariant matrix, balance semantics, idempotency &
concurrency, tenancy & deployment, repo structure, C4 (context+container), 8 ADRs +
template + index, BLNK adoption matrix, open-decisions register (18), threat model
(8 trust boundaries), test strategy, API standards + error catalog, capacity hypotheses,
executive overview. Structured skeletons with owner phases: events, security architecture,
authorization matrix, control readiness, deployment guides, observability, backup/DR,
runbooks, migrations, CoA.

## 5. Validation performed

Internal consistency review across docs (terms per glossary, invariants↔matrix↔rules,
lifecycle↔balance semantics); every master-prompt §16 document exists (authored or
structured skeleton with owner); Mermaid diagrams syntax-checked; all links relative and
resolving within the repo. **Limitations honestly stated:** BLNK live documentation was
unreachable from the build environment (network policy) — the adoption matrix uses
Jan-2026 project knowledge and its re-validation is registered as OD-16, due before the
Phase 3 gate. No code executed (none exists — per phase mandate); hooks are written
defensively but only guard hooks are active pre-Phase-1.

## 6. Decisions requiring human approval now

1. **Accept ADRs 0001–0008** (or amend) — they gate all implementation.
2. **Approve the Phase 0 gate** in [roadmap](../product/roadmap.md) (records approver+date).
3. Confirm or correct: target markets/currencies (OD-1), MVP FX depth (OD-4, recommended:
   same-currency only), licensing (OD-12) — none block Phase 1 but OD-1 shapes Phase 4 seeds.

## 7. Exact proposed scope for Phase 1

Per [roadmap Phase 1](../product/roadmap.md): repository skeleton per
[repository-structure](../architecture/repository-structure.md); uv+pyproject; Django LTS
project with profile-driven settings; compose stack (PostgreSQL 16, Redis, Keycloak dev);
Makefile (`lint/typecheck/format/test/check/docs`); CI with lint+mypy-strict+pytest+docs+
migration check+secret/dependency scans; pre-commit; structured JSON logging; OTel bootstrap;
health endpoints; MkDocs site building this tree; worker-framework ADR (OD-5); CLAUDE.md
command sections finalized. **Explicitly excluded from Phase 1:** any domain model, any
financial logic, any tenancy code (Phase 2), any API beyond health.

**Requested action:** review this blueprint; record approval (or change requests) for the
gate and the ADRs. Phase 1 will not begin until then.
