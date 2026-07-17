# Rules — Database Migrations (`src/next_core/**/migrations/`)

## Immutability of released migrations

- A migration that has been merged to the default branch (or shipped in any release) is
  **frozen**. Never edit, reorder, squash, or delete it. Corrections are new migrations.
- Auto-generated migrations must be reviewed line by line before commit — never trust
  `makemigrations` output blindly.

## Financial data safety

- No migration may silently lose or rewrite financial data. Dropping/altering columns on
  ledger, posting, journal-entry, idempotency, audit, or outbox tables requires: an explicit
  written justification, a data-preservation plan, and human approval — treat as a stop-point.
- Renames are expand-and-contract: add new, backfill, dual-write if needed, switch reads,
  remove old in a later release. Never in-place destructive renames on financial tables.
- Default values on large tables: use database defaults / backfill in batches; avoid
  full-table rewrites that lock production tables.

## Constraints

- Constraints that enforce accounting invariants (balance checks, uniqueness of idempotency
  keys, FK chains) may be added but never removed or weakened without an ADR and explicit
  human approval.
- New financial tables must ship with their constraints in the same migration as the table —
  not "added later".

## Zero/low-downtime discipline (Phase 9 formalizes; apply from Phase 1)

- Migrations must be backward-compatible with the previous application version (N-1 rule):
  the old code must run against the new schema during rollout.
- Long-running DDL (index builds) uses `CONCURRENTLY` where applicable and lives in separate,
  non-atomic migrations.

## Process

- Every migration PR includes: forward migration, documented rollback strategy (or explicit
  "irreversible + why"), and a test run against a real PostgreSQL with representative data.
- Multi-tenant reality: a migration runs once per tenant database. It must be idempotent-safe
  under re-run after partial failure across the tenant fleet.
- Never run destructive commands (`migrate --fake`, `reset_db`, manual `DROP`) against any
  shared or production-like database without explicit human approval in the session.
