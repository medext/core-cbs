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

## Phase 1 — Repository & engineering foundation — **CURRENT**

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
- [ ] Human approval: _pending_ (see also ADR-0009 worker-framework decision).

## Phase 2 — Tenancy, IAM & audit foundation

**Objective:** Tenant-safe skeleton: no financial code yet, but isolation proven.

**Scope:** control-plane tenant registry (separate DB); `TenantContext` + middleware; tenant→
database routing (ADR-0005) incl. migration fan-out tooling; on-premise single-tenant profile
(control plane absent); OIDC integration boundary (Keycloak dev realm); permission framework +
scope model; audit event foundation; correlation IDs end-to-end; cross-tenant test harness.

**Gate:**
- [ ] Cross-tenant access tests fail safely (404/403, no leak) for every data-plane route.
- [ ] No request path can run with an implicit/default tenant (tests prove hard failure).
- [ ] Routing deterministic under concurrent mixed-tenant load (test evidence).
- [ ] Audit events emitted for auth'd operations with correlation IDs.
- [ ] On-prem profile boots & serves with control-plane runtime absent (CI job).
- [ ] Human approval: _pending_.

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

**Scope:** business date; accounting periods; EoD workflow (resumable, idempotent); external
record ingestion; matching rules & engine; exceptions & investigation; maker-checker
adjustments; trial balance; operational reports.

**Gate:**
- [ ] EoD idempotent & resumable (kill-and-resume tests).
- [ ] Reconciliation re-runs deterministic; adjustments require approval.
- [ ] Trial balance validates against ledger.
- [ ] Human approval: _pending_.

## Phase 8 — Interest & advanced capabilities

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
