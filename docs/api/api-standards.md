# API Standards

| | |
|---|---|
| **Purpose** | Binding standards for all Next Core APIs. Core rules fixed now; sections marked *[authored Phase 3]* are completed with the first public endpoints. |
| **Audience** | Engineering, API consumers. |
| **Owning phase** | Phase 0 (rules) → Phase 3+ (completion, same-change rule). |
| **Related** | `.claude/rules/api.md` · [Error catalog](error-catalog.md) · ADR-0006 · [Balance semantics](../accounting/balance-semantics.md) |

## Fixed rules (binding from Phase 3)

- **Versioning:** URI-based `/api/v1/…`; breaking change ⇒ new version; deprecation policy
  below.
- **Tenancy:** every request runs in an explicit tenant context (resolution per deployment
  config); URLs never contain guessable cross-tenant IDs (opaque UUIDs).
- **Idempotency:** `Idempotency-Key` header **required** on all financial writes; semantics
  per ADR-0006 (replay original / 409 on payload mismatch / retryable conflict in-flight).
  Client guidance: *always retry with the same key*.
- **Errors:** RFC 9457 problem details + stable machine-readable `code` from the
  [error catalog](error-catalog.md); `retryable` boolean; `correlation_id` echoed.
- **Money on the wire:** decimal strings + `currency` per ADR-0004; excess precision rejected.
- **Collections:** cursor pagination (`limit` ≤ bounded max); filtering via documented
  allow-lists only; stable sort keys.
- **Correlation:** `X-Request-ID` accepted/generated, propagated to traces, logs, audit.
- **Auth:** OAuth2 bearer; scope + permission documented per endpoint; 401 vs 403 semantics
  fixed (403 never confirms resource existence cross-tenant — 404).
- **Safety:** no unbounded request bodies; strict content types; write endpoints reject
  unknown fields (`400 VALIDATION_ERROR`).

## Backward-compatibility policy

Non-breaking (allowed in-version): new optional fields, new endpoints, new enum values
**only where catalog marks the enum open**, new error codes. Breaking (new version): removing/
renaming fields, changing types/semantics, tightening validation on existing inputs, closing
an enum. Deprecation: announced in docs + `Deprecation` header ≥ 6 months before removal;
policy details finalized Phase 5. Contract tests enforce this against the last released
schema.

## Sections completed with implementation *[authored Phase 3+]*

Each lands in the same change as the code it describes:

1. **Resource model & naming conventions** — nouns, nesting depth, sub-resources
   (Phase 3: ledger/transaction resources; Phase 4: parties/accounts/products; Phase 5:
   transfers/holds).
2. **Standard endpoint shapes** — create/get/list/action patterns, async-operation pattern
   (202 + status resource) for queued work.
3. **OpenAPI 3.1 generation & publication** — tooling (OD-6), CI schema check, example
   coverage requirement (every endpoint ships request+response examples).
4. **Collections** — Postman/Bruno collections generated per release.
5. **SDK examples** — Python quickstarts per flow (fund→transfer→reverse).
6. **Webhook consumer guide** — see [event standards](../events/event-standards.md).
7. **Rate limiting** — headers, tiers, retry guidance (Phase 5).
