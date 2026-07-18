# Project Status — Session Handoff Document

> **This file is the entry point for every new working session.** It always reflects the
> exact current state and the exact next step. It is updated **in the same commit** as any
> work it describes (same-change rule). If you are Claude Code starting a fresh session:
> read this file first, then `CLAUDE.md`, then follow "How to resume" below.

**Last updated:** 2026-07-18 · **Branch:** `claude/core-banking-prd-structure-ty3inr`

## Where the project stands

| Phase | Status |
|---|---|
| 0 — Architecture blueprint | ✅ Approved 2026-07-18 (ADRs 0001–0008 Accepted) |
| **1 — Repository & engineering foundation** | 🔨 **IN PROGRESS** (started 2026-07-18) |
| 2–10 | Not started (see `docs/product/roadmap.md`) |

## Phase 1 slice backlog (execute in order)

| # | Slice | Status |
|---|---|---|
| 1.0 | Record Phase 0 approval (roadmap, ADRs → Accepted) | ✅ done |
| 1.1 | STATUS.md + session-handoff protocol in CLAUDE.md | 🔨 in progress |
| 1.2 | Toolchain: pyproject (uv), Makefile, .pre-commit-config, .gitignore, .env.example | ⬜ next |
| 1.3 | Django skeleton: settings profiles (local/saas/onprem/test), urls/wsgi/asgi, manage.py | ⬜ |
| 1.4 | platform: structlog JSON logging + correlation-ID middleware, OTel bootstrap | ⬜ |
| 1.5 | Health endpoints `/health/live` + `/health/ready` + tests (unit + real-PG integration) | ⬜ |
| 1.6 | deploy/docker/Dockerfile + compose.yaml (postgres 16, redis 7, app; keycloak behind `iam` profile) | ⬜ |
| 1.7 | CI `.github/workflows/ci.yml` (ruff, mypy, pytest+PG service, migration check, mkdocs, bandit, pip-audit, gitleaks, compose smoke) | ⬜ |
| 1.8 | MkDocs site (mkdocs.yml) + `docs/deployment/environment-reference.md` incl. `check --deploy` results | ⬜ |
| 1.9 | ADR-0009 worker framework (OD-5) — Proposed status | ⬜ |
| 1.10 | Finalize CLAUDE.md commands section; run full local verification; gate report | ⬜ |

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

- **Environment quirk:** the remote dev container has uv 0.8.17, local PostgreSQL 16.13 and
  Redis 7 binaries, but **no Docker daemon** — validate `compose.yaml` with
  `docker compose config`; runtime compose proof comes from CI. Local tests run against a
  pg_ctl-managed PostgreSQL instance (see Makefile `test-db-*` targets once slice 1.2 lands).
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
