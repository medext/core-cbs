# Migration Strategy *(skeletons — authored Phases 1 & 9)*

| | |
|---|---|
| **Purpose** | Schema-migration discipline and customer data-migration strategy. |
| **Owning phase** | Phase 1 (schema rules live in `.claude/rules/migrations.md`) · Phase 9 (data migration & upgrade strategy). |
| **Related** | `.claude/rules/migrations.md` · ADR-0005 (fan-out) |

## Fixed positions

- Released migrations are frozen; corrections are new migrations (hook-enforced).
- No migration may lose financial data; destructive DDL on financial tables is a human-
  approval stop-point.
- N-1 compatibility: old app version must run against new schema during rollout.
- Multi-tenant fan-out: per-tenant execution with resumable status ledger.

## To author

| Document | Content | Phase |
|---|---|---|
| `schema-migration-playbook.md` | Expand-and-contract recipes, `CONCURRENTLY` index rules, constraint-addition patterns on hot tables, fleet rollout ordering, verification tooling | 1–3 |
| `data-migration-strategy.md` | Customer onboarding/cutover from legacy CBS: extract→transform→load with balanced control totals, migration control accounts, opening-balance entries (never fabricated history), backdated-item policy, dry-run & reconciliation of migrated positions, rollback/abort criteria | 9 |
| `versioning-upgrade-strategy.md` | Release versioning, upgrade paths & support windows, per-edition upgrade mechanics, rollback strategy | 9 |
