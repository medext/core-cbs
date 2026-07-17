# Event & Webhook Standards *(skeleton — authored Phase 3)*

| | |
|---|---|
| **Purpose** | Standards for domain events and outgoing webhooks; the event catalog grows with each phase. |
| **Audience** | Engineering, webhook consumers. |
| **Owning phase** | Phase 3 (with the outbox implementation, same-change rule). |
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

## To author in Phase 3 (with implementation)

1. **Envelope schema** — id, type, version, tenant, occurred_at, correlation_id, aggregate
   refs, payload. AsyncAPI document location & CI check.
2. **Event catalog** — table per context: type, trigger, payload schema, example. Seeds:
   `journal_entry.posted`, `journal_entry.reversed`, `transaction.state.changed`,
   `integrity.mismatch`; grows each phase (accounts, products, recon, EoD).
3. **Delivery operations** — retry schedule, backoff, dead-letter states, replay tooling &
   authorization, endpoint suspension thresholds, delivery-log retention.
4. **Consumer guide** — verification code samples, dedup patterns, ordering caveats.
5. **Internal consumption** — inbox pattern usage, exactly-once effect recipes.
