# Event & Webhook Standards

| | |
|---|---|
| **Purpose** | Standards for domain events and outgoing webhooks; the event catalog grows with each phase. |
| **Audience** | Engineering, webhook consumers. |
| **Owning phase** | Phase 3 (outbox implementation, built in the MVP track 2026-11-25; same-change rule). Webhook delivery: OD-30. |
| **Related** | ADR-0007 · [Threat model TB5](../security/threat-model.md) |

## Fixed rules (from ADR-0007, binding)

- Events publish via transactional outbox only, after commit (invariant 25).
- Delivery: at-least-once, ordered per aggregate; consumers must deduplicate (event `id`).
- Webhooks: HMAC-SHA256 signature over timestamp+payload with per-tenant secret; consumers
  must verify signature and reject stale timestamps (replay window).
- Payloads carry IDs and business facts — minimal PII, no secrets, amounts per ADR-0004 wire
  format.
- Event types are versioned (`transaction.state.changed.v1`); schema evolution follows the
  API compatibility policy (additive in-version; breaking ⇒ new version, parallel emission
  during deprecation window).

## As built (MVP track, 2026-11-25)

### Outbox table and write rule

`outbox_event` lives in each tenant database (`src/next_core/platform/outbox/`). Every domain
event is written by `emit(...)` **inside the business DB transaction** — `emit` refuses to run
outside an atomic block. A rolled-back business transaction therefore leaves no event
(invariant 25). Columns: `seq` (bigserial, delivery order), `event_id` (UUID, unique),
`event_type`, `event_version`, `aggregate_type`, `aggregate_id`, `payload`, `correlation_id`,
`status` (PENDING/DISPATCHED/DEAD), `attempts`, `dispatched_at`, `last_error`.

### Envelope

```json
{
  "id": "5d0b…-uuid",
  "type": "journal_entry.posted.v1",
  "tenant": "alpha",
  "occurred_at": "2026-11-25T10:15:02.123456+00:00",
  "correlation_id": "req_…",
  "aggregate": {"type": "journal_entry", "id": "…"},
  "data": { "…": "event-specific payload" }
}
```

### Event catalog (v1)

| Type | Emitted by | Trigger | Payload (data) |
|---|---|---|---|
| `journal_entry.posted` | ledger | Each committed journal entry | `entry_id`, `seq`, `purpose`, `source {type, id}`, `business_date`, `reversal_of` (null), `postings[] {balance_id, direction, amount, currency}` |
| `journal_entry.reversed` | ledger | Each committed reversal entry | same shape, `reversal_of` set |
| `integrity.mismatch` | ledger | Integrity run with findings | `run_id`, `finding_count` |
| `transaction.state.changed` | transactions | Every lifecycle transition after intake | `transaction_id`, `type`, `from`, `to` |
| `account.opened` | accounts | Account opening | `account_id`, `number`, `party_id`, `product_code`, `product_version`, `currency` |
| `account.status.changed` | accounts | Status or block change | `account_id`, `from`, `to`, `debit_blocked`, `credit_blocked` |
| `party.created` | parties | Party creation | `party_id`, `type` (no PII) |
| `party.updated` | parties | Attribute update | `party_id`, `fields` (names only, no values) |
| `party.status.changed` | parties | Status change | `party_id`, `from`, `to`, `reason` |
| `party.kyc.recorded` | parties | KYC outcome recorded | `party_id`, `kyc_status`, `kyc_level` |
| `product.version.activated` | products | Version approved | `product_id`, `version` |

Amounts follow the ADR-0004 wire format. Payloads carry ids and business facts only.

### Relay and delivery semantics

- `manage.py relay_outbox [--tenant slug] [--batch-size N]` drains pending events per tenant.
  **One relay per tenant database at a time**: each batch transaction first takes
  `pg_try_advisory_xact_lock(hashtext('next_core.outbox_relay'))`; a concurrent relay that
  cannot get it returns immediately (the advisory lock coordinates only — it guards no
  financial state). The batch is `SELECT … FOR UPDATE ORDER BY seq`, delivered to a sink and
  marked `DISPATCHED`.
- **At-least-once, ordered per aggregate.** Events are delivered in `seq` order; when an
  event fails, every later event of the **same aggregate** in that batch is held back (stays
  `PENDING`) so it can never overtake it. Events of other aggregates continue. Consumers must
  deduplicate on `id`.
- Transport failures (`OSError`, `ValueError`, `RuntimeError` from the sink) increment
  `attempts`, record the error class; after 10 attempts the event becomes `DEAD` (later
  events of that aggregate are then released on the next batch — the dead event needs
  operator replay).
- The sink is called inside the batch transaction (row locks held during delivery); with
  the log sink this is negligible — an HTTP sink must move delivery outside the lock (OD-30).
- **Current sink: structured log only.** HTTP webhook delivery (HMAC signing, per-tenant
  secrets, retry schedule, endpoint suspension, replay tooling, delivery logs) and the Celery
  relay worker (ADR-0009) are **not built yet** — OD-30.

## Still to author (with OD-30)

1. AsyncAPI document and CI check.
2. Webhook delivery operations — retry schedule, backoff, dead-letter handling, replay
   authorization, endpoint suspension thresholds, delivery-log retention.
3. Consumer guide — signature verification samples, dedup patterns, ordering caveats.
4. Internal consumption — inbox pattern (ADR-0007) when the first internal consumer lands.
