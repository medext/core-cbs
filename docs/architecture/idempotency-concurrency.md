# Idempotency & Concurrency Strategy

| | |
|---|---|
| **Purpose** | The bank-grade design for at-most-once financial writes and safety under hostile concurrency. |
| **Audience** | Engineering, reviewers (`postgres-concurrency-reviewer` authority doc). |
| **Owning phase** | Phase 0 (design) → Phase 3 (implementation). |
| **Related** | ADR-0003, ADR-0006 · [Ledger architecture](../accounting/ledger-architecture.md) · [Transaction lifecycle](../domain/transaction-lifecycle.md) |

## Idempotency (ADR-0006 summary + operational detail)

### Model

```text
IdempotencyRecord(
  tenant_id, operation, client_id, key,          -- UNIQUE together (scope)
  request_hash,                                   -- canonicalized payload SHA-256
  status: PROCESSING | COMPLETED | FAILED_FINAL,
  response_snapshot, journal_entry_ref,
  created_at, completed_at, retention_class
)
```

- **Scope**: (tenant, API operation, API client, key). The same key on a different operation
  or client is a different request — prevents cross-endpoint collisions and cross-client
  interference.
- **Canonicalization**: JSON payload normalized (sorted keys, no insignificant whitespace,
  amounts in canonical form) before hashing, so semantically identical retries match.

### Protocol (inside the posting DB transaction)

1. `INSERT ... ON CONFLICT (scope) DO NOTHING RETURNING *`.
2. Row inserted → proceed; we own the request.
3. Conflict → load existing row:
   - `request_hash` differs → **409 `IDEMPOTENCY_CONFLICT`** (invariant 12).
   - `COMPLETED` → return stored response (invariant 11).
   - `PROCESSING` → another in-flight execution owns it → **retryable 409/`RETRY_LATER`**
     (client backs off; we never run two executions).
   - `FAILED_FINAL` → return stored final failure (deterministic replay of terminal errors).
4. On success: store response snapshot + entry ref, mark COMPLETED — same transaction as the
   postings, so record and postings commit or vanish **together** (this closes the classic
   crash-window: no state where postings exist without their idempotency record).

### Ambiguous outcomes (client timeout after our commit)

The client retries with the same key → conflict path returns the stored response. This is the
**only** safe client behavior and is documented in the API standards ("always retry with the
same key; never generate a new key for a retry").

### Retention

- Financial write records: retained ≥ dispute/audit horizon (default 10 years — OD-8; never
  hard-deleted within legal horizon; archived per data-retention policy).
- Non-financial idempotent operations: 30 days (config default).
- Expiry never enables replay of a still-retriable window: keys expire only after terminal
  status + retention class horizon.

## Concurrency control

### Decision framework (evaluated options)

| Mechanism | Verdict | Rationale |
|---|---|---|
| PostgreSQL row locks (`SELECT … FOR UPDATE`) | **Primary** | Deterministic, local, proven; fits short posting transactions |
| Deterministic lock ordering | **Mandatory companion** | Global order = balance UUID ascending; eliminates AB/BA deadlocks across all entry shapes |
| Optimistic versioning on projections | **Adopted** (belt) | `version` column detects any illegal out-of-band write |
| READ COMMITTED + explicit locks | **Default isolation** | With explicit locking, avoids mass serialization aborts |
| SERIALIZABLE | Rejected as default | Retry-storm risk on hot rows; may be selectively adopted later via ADR |
| Advisory locks | Auxiliary only | Allowed for coarse coordination (e.g., EoD singleton), never for balance correctness |
| Redis locks | **Prohibited for correctness** | Master prompt §4.3; may only reduce load, never guard invariants |
| Queue partitioning / per-balance sequencing | Phase 8+ option | For extreme hot spots, partition async execution by balance; DB checks remain final |
| Hot-account sharding (hierarchical sub-balances) | Designed mitigation | See below |

### The posting transaction (canonical interleaving-safe script)

```text
BEGIN;                                             -- READ COMMITTED
  idempotency gate (INSERT ... ON CONFLICT)         -- unique constraint arbitrates racers
  SELECT ... FOR UPDATE ORDER BY balance_id         -- ALL touched balances, sorted
  validate funds/limits/blocks ON LOCKED ROWS       -- no stale reads possible
  INSERT journal_entry, postings                    -- append-only
  UPDATE ledger_balance projections (version += 1)
  UPDATE/INSERT limit counters (same lock ordering discipline, limits context)
  INSERT outbox events
COMMIT;                                            -- deferred balanced-entry trigger fires
```

Rules:
- **Everything or nothing in one transaction** (invariant 13). No network calls, queue
  publishes, or cache writes inside it (outbox pattern instead).
- Lock **all** balances the entry touches, sorted by UUID, before reading the values used in
  decisions. Reading before locking is the classic double-spend window — reviewer blocks it.
- Transactions stay short: no user-facing awaits, no external I/O while holding locks.
- Limit counters use the same discipline: counters are rows, locked in the same global
  ordering domain (UUID-sorted across balance+counter IDs), consumed in-transaction —
  making funds check + limit consumption + posting one atomic decision.

### Deadlocks

Deterministic ordering removes lock-order deadlocks by construction. Residual deadlocks
(e.g., DDL, unexpected paths) are handled by: PostgreSQL detection → error class mapped to a
retryable failure → bounded jittered retry (new transaction, fresh idempotency-gate pass —
safe by design). Deadlock rate is a monitored metric with alert.

### Hot balances

1. First line: short transactions + ordering (measure before optimizing).
2. Institutional hot accounts (fee income, settlement, suspense): **hierarchical
   sub-balances** — N shard balances under one GL account; posting rule picks a shard
   (hash/rotation); reporting sums shards; optional EoD internal sweep to the master. Sharding
   never applies to customer available-funds checks.
3. Extreme cases (Phase 8+): per-balance async sequencing via partitioned queues — with the
   DB transaction still the final authority.

### Concurrency test suite (gate-blocking from Phase 3)

Mandatory adversarial tests on real PostgreSQL, parallel transactions with barriers:

| Test | Asserts |
|---|---|
| Double spend: N concurrent transfers draining one account | Σ successful ≤ available; no negative available (no overdraft) |
| Duplicate idempotent requests (same key, concurrent) | Exactly one posting; both callers get identical response |
| Same key, different payload, concurrent | One executes; other gets `IDEMPOTENCY_CONFLICT`; exactly one entry |
| Simultaneous holds exceeding available | Total held ≤ available |
| Capture vs. release race on one hold | Exactly one wins; funds conserved |
| Concurrent reversal of same entry | Single reversal entry; second attempt idempotent/conflict |
| Concurrent closure vs. incoming posting | Either posting completes then closure, or closure blocks posting — never orphan postings on closed account |
| Limit overconsumption: N concurrent ops at limit boundary | Σ consumed ≤ limit |
| A→B vs B→A transfer storm | No deadlock (ordering proof) or bounded retries; conservation holds |
| Kill worker mid-transaction | Nothing partial persisted; retry converges to one posting |
| Ambiguous network outcome (drop response post-commit) | Retry returns original result; one posting |

Money-conservation postcondition on every test: Σ all balances unchanged except by intended
entries; reconstruction matches projections.
