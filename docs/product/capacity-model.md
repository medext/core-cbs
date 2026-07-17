# Capacity Model *(skeleton — hypotheses now, validated Phase 9)*

| | |
|---|---|
| **Purpose** | Working load hypotheses, benchmark profiles, and (eventually) validated capacity figures behind any SLO. |
| **Owning phase** | Phase 0 (hypotheses) → Phase 9 (benchmarks & validation). **No SLO is published before Phase 9 evidence.** |
| **Related** | [PRD NFR-6](prd.md) · [Concurrency strategy](../architecture/idempotency-concurrency.md) |

## Working hypotheses (unvalidated — inputs to design, not commitments)

| Dimension | Hypothesis |
|---|---|
| Tenant sizes | S: ≤50k accounts · M: ≤500k · L: ≤1M (shared SaaS ceiling; above → dedicated) |
| Posting throughput | Sustained 100 TPS/tenant, burst 300 TPS (payroll/settlement windows) |
| Latency targets | p99 posting commit < 250 ms; p99 read API < 100 ms |
| EoD window | < 4 h for 1M-account tenant (accruals+statements+recon+trial balance) |
| Hot accounts | Fee/settlement accounts may see >50% of postings → shard strategy sized for 10× skew |
| Storage growth | ~1.5 KB/posting incl. indexes; 100 TPS ≈ ~4 TB/year/tenant order of magnitude — drives archival design |
| Webhook fan-out | ≤5 endpoints/tenant, p95 delivery < 30 s |

## Benchmark profiles to build (Phase 9, before SLOs)

1. **Steady transfer mix** — 80% transfers / 15% holds+captures / 5% reversals, uniform
   accounts.
2. **Hot-account skew** — same mix with Zipf-distributed targets + institutional fee account
   on every operation.
3. **Payroll burst** — bulk credit batch against S/M/L tenants during online traffic.
4. **EoD under load** — EoD pipeline concurrent with 30% online traffic.
5. **Failure injection** — worker/app kill mid-load; DB failover; Redis loss (must degrade,
   not corrupt).
6. **Migration under load** — expand-and-contract migration during profile 1.

Each profile reports: throughput, latency percentiles, lock waits, deadlocks, outbox/queue
lag, integrity-run results post-test (money conservation is a pass/fail criterion).

## To produce in Phase 9

Validated figures per profile → SLO proposal → alert thresholds → scaling playbook inputs →
published limits per edition.
