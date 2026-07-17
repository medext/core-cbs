# BLNK Concept-Adoption Matrix

| | |
|---|---|
| **Purpose** | Decision matrix over BLNK's ledger concepts: what Next Core adopts, modifies, postpones, or rejects — and the core-banking extensions BLNK does not provide. |
| **Audience** | Architects, reviewers. |
| **Owning phase** | Phase 0. |
| **Related** | [Ledger architecture](../accounting/ledger-architecture.md) · [Roadmap](../product/roadmap.md) |

> **Source caveat (registered as OD-16):** the live BLNK documentation
> (`docs.blnkfinance.com`) was unreachable from this build environment (network policy).
> This matrix is built from project knowledge of BLNK current to January 2026 and must be
> re-validated against the live docs (including `llms.txt`) before the Phase 3 gate. No BLNK
> source code is copied; BLNK is Apache-2.0-licensed Go software studied at concept level
> only — licensing review applies only if implementation details are ever borrowed.

**Verdicts:** ✅ Adopt · 🔧 Modify (adopt with changes) · ⏳ Postpone · ❌ Reject

| BLNK concept | Meaning in BLNK | Verdict | Rationale & Next Core mapping | Required CBS extension | Risks | Proposed implementation |
|---|---|---|---|---|---|---|
| Ledgers | Top-level grouping container for balances | 🔧 | Keep as tenant-scoped container, but bind to a versioned CoA — BLNK ledgers are folder-like; a bank needs accounting structure | CoA + GL typing per ledger | Over-flexible grouping → uncontrolled proliferation; mitigate via config workflow | `Ledger` entity, Phase 3 |
| General Ledger / balance groupings | Aggregated views over balances (e.g., `@` internal balances) | 🔧 | Replace ad-hoc internal balances with a first-class CoA + subledger→GL mapping and control equations | Trial balance, per-type normal sides, period totals | Mapping errors → wrong GL; mitigated by integrity runs | [Accounting model](../accounting/accounting-model.md), Phases 3–7 |
| Balances | Store of value with debit/credit totals + computed balance | ✅ | Direct fit: `LedgerBalance` with `ledger_debit_total`/`ledger_credit_total` and derived figures | Normal-side awareness; available/cleared/pending semantics beyond BLNK's inflight model | — | [Balance semantics](../accounting/balance-semantics.md), Phase 3 |
| Identities | Person/org profiles attachable to balances | 🔧 | Split into a full `parties` context (KYC refs, roles, related parties, beneficial owners) kept **out** of the ledger; balances reference owner IDs only | Party model per §6.3; account (contract) layer between party and balance | Leaking PII into ledger metadata; barred by rules | `parties` context, Phase 4 |
| Transactions | Value movement between two balances (source→destination) | 🔧 | BLNK's 2-party transaction becomes: business transaction (orchestration) + journal entry with **n postings** — true multi-leg double entry (fees, tax, FX legs in one atomic entry) | Posting rules producing multi-leg entries | More complex model; controlled by posting-rule declarativity | `transactions` + `ledger` split, Phases 3/5 |
| Double-entry enforcement | Every transaction debits a source and credits a destination | 🔧 | Strengthen from pairwise to per-currency balanced n-leg entries with DB-level backstop trigger | Balanced-entry constraint; normal-balance semantics | — | Invariants 1–2, Phase 3 |
| Transaction immutability | Recorded transactions are never edited | ✅ | Core principle adopted and hardened: append-only + DB grants revoking UPDATE/DELETE | Grant-level enforcement, tamper-evident snapshots | — | Invariants 5–7, Phase 3 |
| Idempotency | Idempotency keys prevent duplicate application | 🔧 | Adopt, strengthen: scope (tenant, operation, client), request-hash conflict detection, response replay, same-transaction record | 409-on-mismatch contract; retention classes | — | ADR-0006, Phase 3 |
| Queued transactions | Transactions enqueued (Redis/asynq) and applied by workers | 🔧 | Adopt the pattern for bulk/scheduled/throttled paths only; synchronous posting is the default; queue is transport, DB decides (BLNK also ultimately applies via workers — we keep sync-first for funds checks) | Lifecycle `QUEUED` state; partitioning strategy for hot balances (Phase 8+) | Queue lag on payment paths; monitored | Lifecycle spec + workers, Phase 5+ |
| Inflight transactions | Two-phase: hold effect on balance, then commit or void | 🔧 | Becomes first-class **holds** with expiry, partial capture, and available-balance semantics — richer than inflight (which BLNK models as transaction state) | Hold entity, capture/release/expire ops, hold races tested | Hold/capture race bugs; dedicated CT suite | Phase 5 |
| Transaction lifecycle (queued→applied etc.) | Status progression of a transaction | 🔧 | Expanded to the full banking state machine (RECEIVED…REVERSED) with append-only transitions, actor rules, and funds-effect table | Maker-checker `PENDING`, `SETTLED` for external legs | State explosion; controlled by per-operation path declarations | [Lifecycle spec](../domain/transaction-lifecycle.md), Phases 3/5 |
| Parent/child transactions | Linked transaction structures (e.g., splits) | 🔧 | Modeled as business-transaction → journal-entries (1..n) linkage + batch grouping; explicit reversal/refund links | Posting batch; bidirectional reversal links | — | Phase 3/5 |
| Scheduled transactions | Execute at a future time | ⏳ | Real need, but requires business-date/calendar machinery first | Business-day scheduling (not wall clock), cutoffs, holidays | Premature build on server time would be wrong | Phase 8 (design reserved in lifecycle: `QUEUED`) |
| Bulk & split transactions | Multiple movements in one request; proportional splits | ⏳ | Bulk = Phase 5+ (per-item idempotency + batch report); splits = posting-rule multi-leg entries make them mostly unnecessary as a special type | Batch API contract, partial-failure semantics | Partial-failure ambiguity; explicit per-item statuses | Phases 5/8 |
| Refunds & reversals | Built-in reversal creating offsetting transaction | ✅ | Adopted as first-class linked reversal entries; refund = business-level reversal flavor with its own rules/fees | Maker-checker on operator reversals; partial refunds via compensating entries | — | Invariants 7, 19; Phase 3/5 |
| Balance reconstruction | Recompute balance from transaction history | ✅ | Adopted and made a gate requirement + scheduled integrity run with persisted findings | Snapshots with hash chaining for tamper evidence | Cost at scale; snapshots bound it | Phase 3 |
| Reconciliation | Match external records against ledger | 🔧 | Expanded to full recon context: ingestion adapters, tolerance & 1:N/N:1 matching, exceptions, maker-checker adjustments, deterministic re-runs | Suspense-account discipline, evidence records | Rule complexity; deterministic engine + fixtures | Phase 7 |
| Metadata | Free-form key-value on entities | 🔧 | Adopted but constrained: size-bounded JSONB, no PII policy, never load-bearing (no business logic reads metadata) | Classification rules; indexing policy | Metadata becoming shadow schema; review rule | Phase 3 |
| Hot-balance handling | Techniques for high-contention balances | 🔧 | Adopt concern, own solution: deterministic lock ordering + hierarchical sub-balances for institutional accounts; measure before sharding | GL-consistent shard rollups; EoD sweeps | Premature optimization; benchmark-gated | [Concurrency doc](../architecture/idempotency-concurrency.md), Phases 3/9 |
| Locking & concurrency | Balance-level locking around application | 🔧 | PostgreSQL row locks + constraints as authority (BLNK uses its own coordination); Redis never guards correctness | Hostile concurrency test suite as gate | — | ADR-0003/0006, Phase 3 |
| Search | Typesense-backed search over ledger data | ❌ (as core) | A dedicated search engine is not a core dependency for a CBS MVP; PostgreSQL indexes + filtered listing suffice; full-text/analytics later by ADR if justified | Filterable list APIs with allow-lists | Search-engine sync = another consistency surface | Reconsider post-Phase 7 |
| Webhooks | Event notifications to consumers | 🔧 | Adopted with bank-grade hardening: outbox-sourced, signed, per-tenant secrets, retries/DLQ/replay, event versioning, endpoint suspension | AsyncAPI catalog; consumer dedup guidance | — | ADR-0007, Phase 3+ |
| Observability | Metrics/traces/logs for ledger ops | ✅ | Adopted, extended with financial-specific metrics (posting latency, idempotency conflicts, outbox lag, recon exceptions, EoD duration, reconstruction mismatches) | Tenant-level health dimensions | — | Phases 1/9 |
| Backup & recovery | Ledger backup guidance | 🔧 | Per-tenant PostgreSQL backup/PITR + restore verification drills; on-prem local/S3 targets | Restore-drill runbooks; backup encryption | Untested backups; drill required at Phase 9 gate | Phase 9 |
| Migration & backdated transactions | Import history; post with past effective dates | 🔧 | Backdating = value-dated entries into OPEN periods only (never closed-period rewrites); migration = dedicated cutover tooling with balanced control totals | Data-migration strategy doc; migration control accounts | Backdating abused as edit mechanism; period rules + audit | Phases 7/9; accounting-model rules |

## Core-banking extensions BLNK does not provide (Next Core scope)

Banking products & versioning · commercial account layer (lifecycle, blocks, signatories,
account numbers/IBAN) · Chart of Accounts + subledger→GL mapping + trial balance ·
declarative versioned posting rules · fees/pricing plans · limits with atomic consumption ·
interest & accruals · value dates & business dates & accounting periods · end-of-day
processing · statements · maker-checker & config workflow · multi-tenant control plane &
on-premise profile — each mapped to its bounded context and phase in the
[domain model](../domain/domain-model.md) and [roadmap](../product/roadmap.md).
