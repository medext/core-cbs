# Implementation Roadmap & Acceptance Gates

| | |
|---|---|
| **Purpose** | The authoritative phase plan. Each phase ends at a gate requiring executed evidence and explicit human approval. |
| **Audience** | Engineering, product, reviewers. |
| **Owning phase** | Phase 0 (statuses updated continuously). |
| **Related** | [Development workflow](development-workflow.md) · [PRD](prd.md) · `/phase-gate` command |

**Rules:** Work happens only in the current phase. A gate is passed only when every item has
executed evidence and a human has approved (recorded below). Skipping gates is prohibited.

---

## Phase 0 — Discovery & architectural blueprint — **APPROVED 2026-07-18**

**Objective:** Complete architecture blueprint as version-controlled Markdown; no production code.

**Deliverables:** PRD, scope, domain model & bounded contexts, ledger & accounting model,
invariant enforcement matrix, transaction lifecycle, balance semantics, idempotency &
concurrency strategy, tenancy & deployment architecture, BLNK adoption matrix, initial ADRs
(0001–0008), threat model, test strategy, repo structure, Claude Code configuration, roadmap,
open-decisions register, Phase 0 review summary.

**Gate:**
- [x] All Phase 0 documents exist and are internally consistent.
- [x] Every §16 required document exists (authored or structured skeleton with owner phase).
- [x] ADRs 0001–0008 complete with alternatives & consequences — **Accepted 2026-07-18**.
- [x] Open-decisions register labels every assumption.
- [x] **Human approval of the architecture** → approved by mohamed@next.mr, 2026-07-18.

## Phase 1 — Repository & engineering foundation — **APPROVED 2026-07-18**

**Objective:** A running, empty-but-production-shaped Django application with full toolchain.

**Scope:** repo structure per [repository-structure](../architecture/repository-structure.md);
uv + pyproject; Django project skeleton (no domain models); settings system (env-driven,
secure defaults, profiles: local/saas/onprem); compose (PostgreSQL 16, Redis); Makefile; CI
(lint, mypy strict, pytest, docs build, migration check, dependency & image scan); pre-commit;
structured JSON logging; OTel bootstrap; health endpoints (`/health/live`, `/health/ready`);
MkDocs site; CLAUDE.md command sections un-TBD'd.

**Gate:**
- [x] `docker compose up` → app starts; health endpoints green — CI compose-smoke job,
      [run #3](https://github.com/medext/core-cbs/actions/runs/29658380251) (ready 200 +
      `X-Request-ID` asserted against the built image).
- [x] `make check` (lint + mypy + tests + docs) passes locally and in CI — 17 tests on real
      PostgreSQL 16 (+ Redis 7 service in CI), coverage 100% of measured code, mypy strict
      clean, mkdocs strict green.
- [x] `manage.py check --deploy` documented — `docs/deployment/environment-reference.md`
      (saas: 0 issues; onprem: W021 intentional, justified).
- [x] No secrets in repo — gitleaks full-history scan green in CI + guard-secrets hook.
- [x] Human approval: **approved by mohamed@next.mr, 2026-07-18** (incl. ADR-0009: Celery).

## Phase 2 — Tenancy, IAM & audit foundation — **APPROVED 2026-11-25**

**Objective:** Tenant-safe skeleton: no financial code yet, but isolation proven.

**Scope:** control-plane tenant registry (separate DB); `TenantContext` + middleware; tenant→
database routing (ADR-0005) incl. migration fan-out tooling; on-premise single-tenant profile
(control plane absent); OIDC integration boundary (Keycloak dev realm); permission framework +
scope model; audit event foundation; correlation IDs end-to-end; cross-tenant test harness.

**Gate:**
- [x] Cross-tenant access tests fail safely for every data-plane route — tenant A token on
      tenant B → 401 (issuer binding); A's listing never contains B's data (verified with
      unscoped per-database queries); no existence leak in error bodies
      (`tests/integration/test_cross_tenant.py`, anti-enumeration test in
      `tests/contract/test_security_review_fixes.py`).
- [x] No implicit/default tenant possible — router raises on unscoped data-plane access;
      middleware hard-400s on missing/invalid/unknown/inactive tenant; empty registry is a
      command error (`tests/unit/test_router.py`, `test_tenant_middleware.py`).
- [x] Routing deterministic under concurrent mixed-tenant load — barrier-synchronized
      parallel writers, per-database verification incl. tenant_id/database agreement
      (`tests/integration/test_routing_concurrency.py`).
- [x] Audit events emitted with correlation IDs (`test_audit_service.py`; access to the
      audit trail is itself audited).
- [x] On-prem profile boots & serves with control plane absent — CI `onprem-boot` job
      (boot assert + migrate fan-out + health + data-plane 401 probe).
- [x] Security review: APPROVE-WITH-CONDITIONS → all 3 HIGH + 3 MEDIUM findings fixed with
      regression tests; residual risks honestly registered (OD-19..OD-24).
- [x] CI all 6 jobs green — [run #10](https://github.com/medext/core-cbs/actions/runs/29661840687)
      (commit `4d9b962`); local `make check` ALL GATES PASSED (76 tests, coverage 96%).
- [x] Human approval: **approved by mohamed@next.mr, 2026-11-25** (with authorization of the compressed MVP track, Phases 3–6).

## MVP track — Phases 3–6 compressed — **CURRENT** (authorized 2026-11-25)

**Decision (OD-37):** on 2026-11-25 the human owner asked for a first complete, testable
version (ledger, parties, accounts, transactions, product engine, fees, limits) and authorized
building Phases 3→6 sequentially in one track. Invariants, real-PostgreSQL tests, concurrency
tests and the reviewer subagents stayed mandatory; the Phase 3–6 gates below are evaluated
together and need **human approval on the whole**.

**Built** (branch `claude/core-banking-system-mvp-1ryv2t`):

| Phase | Delivered | Not delivered (registered) |
|---|---|---|
| 3 Ledger kernel | Money/currency (MRU XOF EUR USD + TND); GL accounts, ledger balances, journal entries, postings with CHECKs and DB triggers (balanced per currency, append-only, writer session flag, funds floor, born-empty); single posting service with UUID-ordered locks; holds in projections; reversals (one per entry); idempotency records in the posting transaction; outbox + `relay_outbox`; `verify_ledger` reconstruction; trial balance; statements; RFC 9457 errors; OpenAPI 3.1 | Accounting periods (OD-29); snapshots/hash chain (OD-15); DB-role separation (OD-14); webhook delivery + Celery (OD-30) |
| 4 Parties, products, accounts | Party registry + identifiers + KYC outcome; versioned immutable product definitions; accounts pinned to version, lifecycle (ACTIVE/FROZEN/DORMANT/CLOSED), debit/credit blocks, closure controls, mod-97 numbering, append-only history | Account migration between versions; dormancy sweep |
| 5 Transfers, holds, fees, limits | Deposits, withdrawals, transfers, holds (place/capture/partial/release/expiry), loan disbursement/repayment, reversals, fees (flat/percentage/tiered/expression + tax), limits (transaction/daily/monthly, locked counters), transaction simulation, statements, public API v1 | Webhooks (OD-30); rate limiting; cross-currency (OD-38) |
| 6 Product configurability | Declarative definition schema v1, restricted expression language (ADR-0010 Proposed), draft→submit→approve workflow with server-side + DB maker-checker, product simulation, seed catalog of 5 products | Future-dated activation (OD-33); separate fee/limit plan objects; GL/CoA change workflow |

Pre-built pieces of later phases: daily interest accrual and capitalization (Phase 8 scope —
day-by-day, checkpointed per account, value-dated basis, never for a future date), hold expiry,
hold reconciliation and an idempotent EoD step command/API (partial Phase 7 scope — no step
framework).

**Combined gate (Phases 3–6):**
- [ ] All 25 invariants: evidence table in [invariants](../accounting/invariants.md#evidence-mvp-track-2026-11-25) — 22 and 10 partial, period checks deferred.
- [ ] Property suites pass (balance, reversal symmetry, idempotency, reconstruction, money, fees).
- [ ] Hostile concurrency suite passes on real PostgreSQL.
- [x] `ledger-accounting-reviewer`, `postgres-concurrency-reviewer`, `security-reviewer`: findings fixed and **re-verified** — all three APPROVE-WITH-CONDITIONS (see *Review outcomes*); open conditions are registered gate items below.
- [ ] Open reviewer conditions closed or explicitly accepted by the human: OD-40 (TRUNCATE protection / DB-role separation; invariant 24 DB layer Partial), OD-42 (`api_client` scoping), OD-46 (deferred concurrency tests), OD-47 (ledger-level Hypothesis suites for fee entries & holds), OD-48 (route-walk depth).
- [ ] No API path mutates a balance directly (contract test + review).
- [ ] Historical transactions stay linked to the product version in force (e2e).
- [ ] Config changes cannot rewrite historical accounting; no arbitrary code execution (expression-language tests + review).
- [ ] E2E open→fund→transfer→hold→capture→reverse→statement→EoD passes.
- [x] `make check` and CI green — local: 199 passed, coverage 93%; CI all 6 jobs green, [run 45695450049](https://github.com/medext/core-cbs/actions/runs/45695450049) (commit `ad048e2`).
- [ ] Human approval: _pending_.

### Review outcomes (2026-11-25)

**Re-verification (second pass):** ledger-accounting-reviewer **BLOCK lifted ->
APPROVE-WITH-CONDITIONS** (follow-ups fixed: resumable, never-early capitalization with
in-order catch-up; `created_txid` forced by trigger; retryable errors no longer burn
idempotency keys); postgres-concurrency-reviewer **APPROVE-WITH-CONDITIONS** (N1 retryable
errors stored as final -> fixed; N2 per-day accrual commits -> fixed); security-reviewer
**APPROVE-WITH-CONDITIONS** (deep-JSON 500 -> fixed; residuals OD-42, OD-43, OD-48).
Remaining open conditions are listed in the combined gate above. First-pass findings:

| Reviewer | Verdict | Findings → status |
|---|---|---|
| `ledger-accounting-reviewer` | **BLOCK** | **B1** interest accruable/capitalizable for any (future) date on today's balance with wrong value dates → **fixed**: future dates refused, per-account `interest_accrued_through` checkpoint, day-by-day catch-up, value-dated basis (`book_balance_as_of`), value_date = accrual day, accrual stops before maturity. **C1** invariant 15 → DB trigger for `TRANSACTION` sources (transactions migration 0004). **C2** postings appended to committed entries → refused (`created_txid`, ledger migration 0003). **C3** `TRUNCATE` bypass → *deferred* (OD-40, role separation). **C4** GL roles not type-checked → every role checked at approval. **C5** integrity snapshot → REPEATABLE READ READ ONLY. **C6** `held_amount` unreconciled → `reconcile_holds()` in EoD. **C7** reversal overdraw policy → documented exception (balance-semantics, invariant 18). **C8** missing tests → added (simultaneous holds, expiry vs capture, forced deadlock retry, value-dated accrual, holds reconciliation); Hypothesis coverage of fee entries/interest legs still limited. S1 (precision) fixed; S2 (accrual after maturity) fixed. |
| `postgres-concurrency-reviewer` | APPROVE-WITH-CONDITIONS | **C1** reverse-vs-capture lock gap → fixed (re-check after locking; retryable `REQUEST_IN_PROGRESS`). **C2** hot internal balances → `lock_timeout` added; sharding *deferred* (OD-39). **C3** outbox per-aggregate ordering → fixed (single relay per tenant via advisory lock; failed event holds back its aggregate). **C4** missing tests / no jitter → jittered retry + tests added (deadlock retry, simultaneous holds, expiry vs capture, identical replay body); kill-worker and ambiguous-outcome tests still missing. S1 (sweep retries) open. |
| `security-reviewer` | APPROVE-WITH-CONDITIONS | **H1** reversal by its initiator → four-eyes rule in code + DB trigger; full request→approve flow *deferred* (OD-41). **H2** `api_client` breadth → `loans:disburse` split off (not granted to `api_client`); account/channel scoping *open* (OD-42). **M1** expression overflow → bounded literals, bounded context, typed errors. **M2** definition size → bounds (64 KiB, depth 8, 50 items, 20 tiers). **M3** single-actor retire → documented exception (OD-43). **M4** cross-tenant coverage → every object route tested (`tests/e2e/test_cross_tenant_all_routes.py`). **L1** expression source in errors → removed. **L2** public schema → cached; Redoc CDN noted (OD-44). L3 (predictable account numbers — API uses UUIDs) and L4 (`exc_info` logging) noted, no change. |

## Phase 3 — Ledger kernel ⚠️ most critical

**Objective:** Smallest correct ledger vertical slice, hostile-tested.

**Scope:** Currency & Money value objects (ADR-0004); Ledger, LedgerBalance, JournalEntry,
Posting models + DB constraints (balanced-entry trigger/deferred constraint, positive amounts,
idempotency uniques); posting service (single write path, deterministic lock ordering);
idempotency records (ADR-0006); balance projections; reversal; append-only transaction
history; transactional outbox + relay (ADR-0007); integrity-check & reconstruction commands;
minimal internal API.

**Gate:**
- [ ] All 25 invariants: enforcement matrix rows implemented & tested (`/invariant-check`).
- [ ] Property suites pass (balance, reversal symmetry, idempotency, reconstruction).
- [ ] Hostile concurrency suite passes on real PostgreSQL (double spend, duplicate requests,
      races, deadlock recovery, ambiguous-retry).
- [ ] `ledger-accounting-reviewer` + `postgres-concurrency-reviewer` verdicts: APPROVE.
- [ ] No API path mutates a balance directly (test + review evidence).
- [ ] Docs current (ledger architecture, balance semantics match code).
- [ ] Human approval: _pending_.

## Phase 4 — Parties, products & customer accounts

**Scope:** parties; product definitions + versioning (immutable active versions); customer
accounts + lifecycle & blocks; account↔ledger-balance mapping; opening transaction; closure
controls.

**Gate:**
- [ ] Historical transactions remain linked to the product version in force.
- [ ] Closed accounts preserve full history; blocked-account rules atomic (concurrency tests).
- [ ] Tenant isolation re-proven over new surfaces.
- [ ] Human approval: _pending_.

## Phase 5 — Transfers, holds, fees & limits (MVP complete)

**Scope:** internal transfers; holds (place/capture/release/expire); fees (calc + collection);
limits (atomic consumption); reversals of business operations; transaction simulation; basic
statements; public API v1 for all of the above + webhooks.

**Gate:**
- [ ] No double spending under concurrency; limit consumption atomic; hold races tested.
- [ ] Fee calculations deterministic (property tests).
- [ ] All financial writes idempotent (contract + race tests).
- [ ] E2E: open→fund→transfer→hold→capture→fee→reverse→statement passes.
- [ ] Human approval: _pending_.

## Phase 6 — Posting rules & product configurability

**Scope:** versioned posting rules, fee plans, limit plans; effective dating; draft→review→
approve→activate workflow; simulation; maker-checker on all config changes.

**Gate:**
- [ ] No arbitrary runtime code execution (review evidence).
- [ ] Config changes cannot rewrite historical accounting (tests).
- [ ] Every activated configuration traceable & reproducible.
- [ ] Human approval: _pending_.

## Phase 7 — Reconciliation & business-day operations

*MVP note: hold expiry and interest steps exist as an idempotent EoD command/API; the
resumable step framework, periods and trial-balance close remain Phase 7.*

**Scope:** business date; accounting periods; EoD workflow (resumable, idempotent); external
record ingestion; matching rules & engine; exceptions & investigation; maker-checker
adjustments; trial balance; operational reports.

**Gate:**
- [ ] EoD idempotent & resumable (kill-and-resume tests).
- [ ] Reconciliation re-runs deterministic; adjustments require approval.
- [ ] Trial balance validates against ledger.
- [ ] Human approval: _pending_.

## Phase 8 — Interest & advanced capabilities

*MVP note: daily accrual (ACT/365, ACT/360, ACT/ACT) and capitalization (monthly / at
maturity) and term deposits are pre-built; withholding tax, scheduled/standing orders and
dormancy remain.*

**Scope:** interest-rate plans, daily accrual, capitalization, withholding tax; scheduled
transactions; standing orders; dormancy; additional account types (term deposits).

**Gate:** accrual determinism & day-count/property tests; retroactive corrections via
compensating entries only; human approval: _pending_.

## Phase 9 — Production hardening

**Scope:** load & failure testing per capacity model; backup/restore + verification; upgrade/
rollback; zero-/low-downtime migration strategy; security scanning + SBOM (+ image signing if
available); dashboards, alerts, runbooks; DR procedures; on-premise installation packages.

**Gate:** benchmarks vs. capacity model; restore drill executed; upgrade+rollback drill
executed; runbooks tested; human approval: _pending_.

## Phase 10 — Reference deployments & release candidate

**Scope:** SaaS reference deployment; dedicated-tenant deployment; on-premise reference
install; demo institution + seed product catalog; complete API & operator docs; release
checklist; known-limitations register; production-readiness review.

**Gate:** all three reference deployments verified from docs alone; PRD success criteria
(§8) evidenced; human approval: _pending_.

---

## Gate approval log

| Phase | Approved by | Date | Notes |
|---|---|---|---|
| 0 | mohamed@next.mr | 2026-07-18 | Blueprint + ADRs 0001–0008 accepted; Phase 1 authorized |
| 1 | mohamed@next.mr | 2026-07-18 | Engineering foundation accepted (CI run #3 evidence); ADR-0009 (Celery) accepted; Phase 2 authorized |
| 2 | mohamed@next.mr | 2026-11-25 | Tenancy/IAM/audit foundation accepted (CI run #10); compressed MVP track (Phases 3–6) authorized; OD-1 confirmed (MRU/XOF/EUR/USD) |
