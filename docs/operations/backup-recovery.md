# Backup, Recovery & Disaster Recovery *(skeleton — authored Phase 9)*

| | |
|---|---|
| **Purpose** | Backup/restore design, DR assumptions, and verification procedures. |
| **Owning phase** | Phase 9 — same-change rule with tooling; working assumptions tracked as OD-9. |
| **Related** | ADR-0003/0005 · [Runbooks](../runbooks/README.md) |

## Fixed positions

- Per-tenant PostgreSQL backups (physical + PITR), encrypted; on-premise targets local or
  S3-compatible storage; restore procedures are **drilled**, not assumed — a restore drill is
  a Phase 9 gate item.
- Working targets (unvalidated, OD-9): RPO ≤ 5 min, RTO ≤ 4 h. No published commitment
  before drills.

## To author in Phase 9

1. Backup architecture per profile (schedules, retention, encryption, integrity checks).
2. Restore procedures (single tenant, control plane, full platform) + verification
   (post-restore ledger integrity run + reconstruction + trial balance).
3. DR assumptions & topology (replication mode, failover semantics, split-brain prevention,
   data-loss disclosure rules).
4. Backup verification automation (scheduled test-restores).
5. Outbox/webhook recovery semantics after restore (replay windows, consumer contract).
