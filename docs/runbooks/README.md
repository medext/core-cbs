# Operational Runbooks *(skeletons — authored Phases 7–9)*

| | |
|---|---|
| **Purpose** | Step-by-step procedures for defined operational scenarios. Each runbook is written with (and tested against) the feature it operates. |
| **Owning phase** | Phases 7–9 (same-change rule). |
| **Related** | [Observability](../operations/observability.md) · [Backup & recovery](../operations/backup-recovery.md) |

## Runbook standard (binding)

Every runbook: trigger/symptoms → severity & escalation → preconditions/access → numbered
steps with exact commands → verification → rollback/abort path → evidence to record.
Runbooks never include destructive commands without an explicit approval checkpoint.

## Planned runbooks

| Runbook | Phase |
|---|---|
| EoD failure: diagnose, resume, verify | 7 |
| Reconciliation exception surge / suspense aging | 7 |
| Balance reconstruction mismatch (integrity alert) — **SEV-1 path** | 3 (command) / 9 (full) |
| Outbox lag / webhook delivery failure / endpoint suspension & replay | 3/9 |
| Idempotency `PROCESSING` backlog sweep | 3/9 |
| Hot-account contention response | 9 |
| Tenant provisioning failure rollback | 2/9 |
| Suspected cross-tenant anomaly — **SEV-1 path** | 9 |
| Backup restore drill (scheduled) | 9 |
| Database failover | 9 |
| Upgrade & rollback (fleet fan-out) | 9 |
| Break-glass IAM outage access | 9 |
| Incident communication & post-incident review template | 9 |
