# API Error Catalog

| | |
|---|---|
| **Purpose** | The registry of stable machine-readable error codes. Codes are append-only; meanings never change. |
| **Audience** | Engineering, API consumers. |
| **Owning phase** | Phase 0 (structure + seed codes) → extended with each endpoint (same-change rule). |
| **Related** | [API standards](api-standards.md) |

## Error shape (RFC 9457 profile)

```json
{
  "type": "https://docs.nextcore.example/errors/INSUFFICIENT_FUNDS",
  "title": "Insufficient funds",
  "status": 422,
  "code": "INSUFFICIENT_FUNDS",
  "detail": "Available balance 20.00 XOF is less than requested 25.00 XOF.",
  "retryable": false,
  "correlation_id": "req_01H…",
  "errors": [ {"field": "amount", "code": "…", "message": "…"} ]
}
```

`errors[]` present only for validation failures. `detail` is human-oriented and may change;
`code` never does. Amounts in `detail` respect log-safety rules (no PII).

## Seed codes (Phase 3/5 implementation binds status + exact semantics)

| Code | Category | Retryable | Notes |
|---|---|---|---|
| `VALIDATION_ERROR` | 400 | No | With `errors[]` field details |
| `AUTHENTICATION_REQUIRED` / `TOKEN_EXPIRED` | 401 | After refresh | |
| `PERMISSION_DENIED` | 403 | No | Function-level |
| `RESOURCE_NOT_FOUND` | 404 | No | Also masks cross-tenant existence |
| `IDEMPOTENCY_CONFLICT` | 409 | No | Key reused with different payload |
| `REQUEST_IN_PROGRESS` | 409 | **Yes** (backoff) | Same key currently executing |
| `CONFLICT_STATE` | 409 | No | Illegal lifecycle transition |
| `INSUFFICIENT_FUNDS` | 422 | No | Available-balance check failed |
| `ACCOUNT_STATE_INVALID` | 422 | No | Blocked/frozen/closed/dormant target |
| `LIMIT_EXCEEDED` | 422 | No | With limit descriptor (which limit, window) |
| `CURRENCY_MISMATCH` | 422 | No | |
| `PERIOD_CLOSED` | 422 | No | Posting into non-OPEN period |
| `APPROVAL_REQUIRED` | 202/422 | No | Maker-checker pending path |
| `RATE_LIMITED` | 429 | Yes | With `Retry-After` |
| `INTERNAL_ERROR` | 500 | Yes | Never leaks internals |
| `DEPENDENCY_UNAVAILABLE` | 503 | Yes | IAM/queue/db-pool exhaustion |

## Registry rules

- New codes are added here **in the same change** as the code that raises them, with:
  category, HTTP status, retryability, trigger conditions, and an example payload.
- A code's meaning is frozen once released; semantic drift requires a new code.
- Contract tests verify every raised code exists in this catalog and matches its documented
  status/retryability.
