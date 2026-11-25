# Project Status — Session Handoff Document

> **This file is the entry point for every new working session.** It always reflects the
> exact current state and the exact next step. It is updated **in the same commit** as any
> work it describes (same-change rule). If you are Claude Code starting a fresh session:
> read this file first, then `CLAUDE.md`, then follow "How to resume" below.

**Last updated:** 2026-11-25 (MVP track delivered) · **Branch:** `claude/core-banking-system-mvp-1ryv2t`

## Where the project stands

| Phase | Status |
|---|---|
| 0 — Architecture blueprint | ✅ Approved 2026-07-18 (ADRs 0001–0008 Accepted) |
| 1 — Repository & engineering foundation | ✅ Approved 2026-07-18 (ADR-0009 Celery Accepted) |
| 2 — Tenancy, IAM & audit foundation | ✅ Approved 2026-11-25 by mohamed@next.mr (with authorization of the compressed MVP track) |
| **3–6 — MVP track (compressed: ledger, parties/products/accounts, transfers/holds/fees/limits, product configurability)** | 🟡 **Built & reviewed — awaiting human gate approval** (OD-37) |
| 7–10 | Not started (pre-built pieces: interest accrual/capitalization, hold expiry, EoD steps — see roadmap) |

## MVP track backlog (compressed Phases 3–6, authorized 2026-11-25)

| # | Slice | Status |
|---|---|---|
| M.0 | Record Phase 2 approval + MVP-track authorization; OD-1 confirmed (MRU/XOF/EUR/USD) | ✅ done |
| M.1 | `platform`: Money/Currency (ADR-0004), RFC 9457 error taxonomy + DRF handler (OD-27), clock, tenant-scoped/append-only persistence, transactional outbox app + relay (ADR-0007) | ✅ done |
| M.2 | `ledger` kernel: CoA, balances, entries, postings, posting service, reversals, holds projection, integrity/reconstruction, trial balance, statement; DB triggers (balanced, append-only, writer session, funds floor, born-empty, txid guard) | ✅ done |
| M.3 | `parties`, `products` (declarative engine, restricted expressions, versioning, maker-checker, simulation, seed catalog), `accounts` (lifecycle, blocks, closure, mod-97 numbers) | ✅ done |
| M.4 | `transactions` (idempotent orchestration, state machine, deposits/withdrawals/transfers/holds/loans/reversals, interest), `pricing`, `limits` | ✅ done |
| M.5 | API v1 (43 routes) + OpenAPI 3.1 committed (`make openapi`, drift contract test) | ✅ done |
| M.6 | Test suites: unit, property (Hypothesis), integration, concurrency (13 hostile races), contract (catalog, OpenAPI, golden dependency rules), e2e (incl. all-routes cross-tenant walk) — **198 passed, coverage 93%, `make check` ALL GATES PASSED** | ✅ done |
| M.7 | Reviews: ledger (BLOCK → lifted), concurrency, security — all **APPROVE-WITH-CONDITIONS after re-verification**; documentation review — see roadmap | ✅ done (conditions → OD-40, 42, 46–49) |
| M.8 | **Human gate decision on the combined Phase 3–6 gate** (`docs/product/roadmap.md` → MVP track) + ADR-0010 acceptance | ⬜ **NEXT — stop-point** |
| M.9 | Close gate conditions: DB-role separation & table-truncation protection (OD-14/OD-40), `api_client` scoping (OD-42), kill-worker & ambiguous-response tests (OD-46), ledger Hypothesis suites for fees/holds (OD-47), route-walk depth (OD-48) | ⬜ after M.8 |

**Next step for a fresh session:** do not start Phase 7. Present the combined gate
(roadmap → "MVP track") to the human; on approval, work M.9 items in the order listed.
CI evidence for the MVP track: **all 6 jobs green** — run
<https://github.com/medext/core-cbs/actions/runs/45695450049> (commit `ad048e2`). Earlier runs
on this branch caught three real defects: Bandit (control-flow asserts), the on-prem
single-database migration defect, and pip-audit advisories on pinned dependencies.

## Phase 2 slice backlog (execute in order)

| # | Slice | Status |
|---|---|---|
| 2.0 | Record Phase 1 approval; ADR-0009 → Accepted; OD-5 confirmed | ✅ done |
| 2.1 | `tenancy` context: explicit `TenantContext` (contextvar), DB router raising on missing context (no default tenant), resolver strategies (header=dev, static=onprem) + middleware | ✅ done |
| 2.2 | `control_plane` context: Tenant registry model (separate control DB), runtime tenant-DB alias registration | ✅ done |
| 2.3 | Migration fan-out: `migrate_tenants` management command (per-tenant, idempotent, resumable) | ✅ done |
| 2.4 | `audit` context: append-only AuditEvent (tenant DB), record service w/ correlation IDs, `/api/v1/audit/events` read endpoint (first data-plane route) | ✅ done |
| 2.5 | `iam` context: OIDC token validation boundary (JWKS, per-tenant issuer/audience), permission registry + DRF permission classes, tenant↔token binding via issuer | ✅ done |
| 2.6 | Profile wiring: saas/onprem DATABASES & INSTALLED_APPS (control plane absent on-prem), compose keycloak (`iam` profile), CI `onprem-boot` job | ✅ done |
| 2.7 | Gate test suites: cross-tenant fail-safe, no-implicit-tenant hard errors, concurrent mixed-tenant routing determinism, audit emission, OIDC contract tests — **71 tests green, coverage 96%** | ✅ done |
| 2.8 | Security review (3 HIGH + 3 MEDIUM fixed w/ regression tests), documentation review (1 BLOCKER + 8 CONCERNs fixed), CI 6 jobs green ([run #10](https://github.com/medext/core-cbs/actions/runs/29661840687)), gate report delivered | ✅ done — **awaiting human approval** |

## Phase 1 slice backlog (✅ complete, gate approved 2026-07-18)

| # | Slice | Status |
|---|---|---|
| 1.0 | Record Phase 0 approval (roadmap, ADRs → Accepted) | ✅ done |
| 1.1 | STATUS.md + session-handoff protocol in CLAUDE.md | ✅ done |
| 1.2 | Toolchain: pyproject (uv), Makefile, .pre-commit-config, .gitignore, .env.example | ✅ done |
| 1.3 | Django skeleton: settings profiles (local/saas/onprem/test), urls/wsgi/asgi, manage.py | ✅ done |
| 1.4 | platform: structlog JSON logging + correlation-ID middleware, OTel bootstrap | ✅ done |
| 1.5 | Health endpoints `/health/live` + `/health/ready` + tests (17 passing, 100% coverage) | ✅ done |
| 1.6 | deploy/docker/Dockerfile + compose.yaml (postgres 16, redis 7, app; keycloak behind `iam` profile) | ✅ done (`config` validated; runtime proof = CI compose-smoke) |
| 1.7 | CI `.github/workflows/ci.yml` (quality, tests+PG, docs, security, compose-smoke) | ✅ done — green in CI run #3 (evidence below) |
| 1.8 | MkDocs site + `docs/deployment/environment-reference.md` incl. `check --deploy` results | ✅ done (strict build green; saas: 0 issues, onprem: W021 intentional) |
| 1.9 | ADR-0009 worker framework (Celery reliability profile) — Proposed | ✅ done — needs human decision at gate |
| 1.10 | Finalize CLAUDE.md commands; full `make check`; gate report → human approval | ✅ done — **gate report delivered, awaiting human approval** |

**Phase 2 CI evidence:** run #10 all 6 jobs green (quality, tests+PG+Redis+tenant DBs, docs,
security, onprem-boot, compose smoke) —
<https://github.com/medext/core-cbs/actions/runs/29661840687> (commit `4d9b962`). Runs #8–#9
caught two real defects (missing state migration for the append-only managers; unformatted
generated migration). Phase 1 evidence: run #3 (5 jobs) — runs #1–#2 caught the Dockerfile
README copy and the RedisCache backend defects.

**Definition of the Phase 1 gate** (all must have executed evidence):
`docs/product/roadmap.md` → Phase 1 Gate. Then **STOP — human approval required** before Phase 2.

## How to resume in a fresh session

1. Read this file, then `CLAUDE.md`.
2. Read `docs/product/roadmap.md` (current phase + gate) and
   `docs/product/development-workflow.md` (working method — the 19-step loop is mandatory).
3. Check `docs/decisions/open-decisions.md` for blockers relevant to your slice.
4. Pick the first ⬜ slice in the backlog above; run it via the `/vertical-slice` command.
5. Before ending the session: update this file (backlog statuses, "Last updated", notes
   below), update the roadmap gate checklist if evidence landed, commit **everything in the
   same change**, and push to the branch above.

## Session notes / handoff context

- **Quick demo:** `make test-db-start`; `uv sync`; local profile: `migrate`, register a
  tenant in the control plane, `migrate_tenants`, `bootstrap_tenant --tenant <slug>`,
  `runserver` — verified in-session (schema 200, data plane 401 without token, 400 without
  tenant). The README quickstart curl walkthrough has **not** been executed end-to-end.
- **Test isolation quirk:** concurrent pytest runs (e.g. reviewer subagents) share the
  `test_next_core_*` databases and break each other — run one suite at a time.
- **Hook quirk:** `.claude/hooks/guard-destructive.sh` blocks any Bash command containing the
  SQL truncation keyword followed by a space, even inside doc text — write such edits via files.

- **Environment quirk:** the remote dev container has uv 0.8.17, local PostgreSQL 16.13 and
  Redis 7 binaries, but **no Docker daemon** — validate `compose.yaml` with
  `docker compose config`; runtime compose proof comes from CI. Local tests run against a
  pg_ctl-managed PostgreSQL instance (see Makefile `test-db-*` targets).
- **BLNK docs unreachable** from the dev container (proxy 403) — OD-16 re-validation of the
  BLNK matrix is due before the Phase 3 gate, from an environment with access.
- No PR exists yet; work is pushed directly to the branch. PR creation only on explicit
  request.
- Open decisions needing the human soon: OD-1 (target markets/currencies — shapes Phase 4
  seeds), OD-12 (licensing — before Phase 10).

## Key documents map

Architecture: `docs/executive/architecture-overview.md` · Ledger: `docs/accounting/` ·
Invariants: `docs/accounting/invariants.md` · Tenancy: `docs/architecture/tenancy-and-deployment.md` ·
Concurrency: `docs/architecture/idempotency-concurrency.md` · ADRs: `docs/decisions/adr/` ·
Gate history: `docs/product/roadmap.md` (approval log at bottom).
