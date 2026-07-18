# Next Core — Project Rules

Bank-grade lightweight Core Banking System. Modular monolith. Django + DRF + PostgreSQL.
Correctness, accounting integrity, tenant isolation, and security take precedence over speed.

## Session start & handoff protocol (mandatory)

**Every new session starts by reading `STATUS.md`** — it holds the current phase, the slice
backlog with the exact next step, and environment quirks. Every session that does any work
**updates `STATUS.md` in the same commit** (backlog status, date, handoff notes) so the next
session can resume from the repo alone, without prior conversation context. Work state lives
in the repository, never only in a conversation.

## Project status

**Phase 1 (repository & engineering foundation) — in progress.** Phase 0 approved 2026-07-18;
ADRs 0001–0008 Accepted. Check `docs/product/roadmap.md` for the current phase and its
acceptance gate before starting any work. Never skip a phase gate.

## Commands

Canonical commands — do not invent alternatives:

- Install: `uv sync`
- Lint: `make lint` (Ruff) · Types: `make typecheck` (mypy strict) · Format: `make format`
- Tests: `make test` · Targeted: `uv run pytest <path> -x` (**real PostgreSQL** — start it
  with `make test-db-start` when Docker is unavailable; compose service otherwise)
- Full gate: `make check` (lint + types + tests + docs build)
- Docs: `make docs` (MkDocs, strict) · Run app: `make run` · Stack: `docker compose up`

## Architecture boundaries

- Modular monolith under `src/next_core/`, one package per bounded context
  (see `docs/architecture/repository-structure.md`). No cross-context model imports —
  contexts communicate through application services and domain events only.
- Domain logic lives in domain/application layers — **never** in Django views, serializers,
  or model methods beyond trivial invariant guards.
- PostgreSQL is the sole authority for financial state. Redis is never a source of truth.
- Events are published through the transactional outbox, only after DB commit.
- No new infrastructure dependency, framework, or service split without an ADR in
  `docs/decisions/adr/`.

## Financial invariants (non-negotiable)

The full 25-invariant enforcement matrix is `docs/accounting/invariants.md`. Highlights:

1. Every posted journal entry balances (per currency) — enforced in code AND by DB constraints.
2. Money is integer minor units + ISO-4217 currency. **Floating point for money is forbidden.**
3. Postings and journal entries are immutable after commit. Corrections = reversal/compensating
   entries. Never edit or delete posted rows.
4. Balances are projections reconstructable from postings; direct balance mutation is forbidden.
5. All financial writes are idempotent (tenant + operation + client scoped keys); key reuse with
   a different payload must 409.
6. Concurrency safety comes from the database (row locks, constraints, deterministic lock
   ordering) — never from Redis locks alone.

**A change that violates or weakens an invariant must be stopped and escalated — never merged.**

## Tenancy & security rules

- Every data-plane query is tenant-scoped. No unscoped ORM queries. **No default tenant
  fallback** — tenant-resolution failure is a hard error.
- Authorization enforced on every endpoint (object- and function-level). Maker-checker for
  privileged/config changes.
- Never log or commit secrets, tokens, card data, or unnecessary PII.
- External IAM (OAuth2/OIDC); do not build password auth.

## Migration rules

- Never modify a migration after it has been released. Never write a migration that loses
  financial data. Destructive DDL requires explicit human approval.
- See `.claude/rules/migrations.md`.

## Prohibited patterns

Full list: master prompt §20, mirrored in `.claude/rules/`. Never: float money, direct balance
updates, editing posted entries, Redis-only correctness, tenant-specific code forks, generic
CRUD for posting logic, SQLite as concurrency evidence, mock-only "tests", broad
`except Exception` without re-raise/classification, arbitrary tenant-supplied code execution,
claiming compliance certifications.

## Documentation & Definition of Done

- Documentation is updated **in the same change** as the code it describes.
- A feature is done only when: domain behavior + authz + tenant isolation + DB constraints +
  unit/property/integration/concurrency tests + API contract + audit evidence + observability +
  docs are all in place. Full checklist: master prompt §22 / `docs/product/development-workflow.md`.
- Never report success without having actually run the commands and inspected results. Never
  hide failing tests, type errors, or migration risks.

## Working method

Follow the 19-step vertical-slice loop in `docs/product/development-workflow.md` for every
implementation task (`/vertical-slice` command). Use the review subagents in `.claude/agents/`
before completing ledger, concurrency, security, or migration work. Detailed per-path rules
live in `.claude/rules/` — read the relevant one before touching that area.
