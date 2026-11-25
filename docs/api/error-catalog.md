# API Error Catalog

| | |
|---|---|
| **Purpose** | The registry of stable machine-readable error codes. Codes are append-only; meanings never change. |
| **Audience** | Engineering, API consumers. |
| **Owning phase** | Phase 0 (structure + seed codes) → MVP track 2026-11-25 (all codes bound) → extended with each endpoint (same-change rule). |
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

## Codes (implemented — source of truth in code: `ERROR_CATALOG` in `platform/errors.py`)

All codes below are emitted by the RFC 9457 exception handler (`type`, `title`, `status`,
`code`, `detail`, `retryable`, `correlation_id`, optional `errors[]`). Since the MVP track,
401/403 responses use this shape too (OD-27 resolved). Business rejections of financial
writes are stored on the idempotency record as `FAILED_FINAL` and **replayed identically**
for the same `Idempotency-Key` (body includes `transaction_id` of the REJECTED transaction);
retry after fixing the cause with a **new** key (OD-35).

| Code | HTTP | Retryable | Trigger |
|---|---|---|---|
| `VALIDATION_ERROR` | 400 | No | Malformed/unknown fields, bad amounts (excess precision, ≤ 0), invalid product definition (all field errors in `errors[]`), invalid overrides, illegal argument combinations |
| `IDEMPOTENCY_KEY_REQUIRED` | 400 | No | Financial write without an `Idempotency-Key` header |
| `TENANT_RESOLUTION_FAILED` | 400 | No | Missing/invalid/unknown/inactive tenant; identical `detail` for every cause (anti-enumeration). Example: `{"code": "TENANT_RESOLUTION_FAILED", "title": "Tenant resolution failed", "detail": "The request could not be attributed to a valid tenant.", "correlation_id": "req_…", "retryable": false}` |
| `AUTHENTICATION_REQUIRED` | 401 | No | Missing, malformed, expired or wrongly-issued token (issuer bound to the resolved tenant); response carries `WWW-Authenticate: Bearer`. Clients refresh the token, then retry |
| `PERMISSION_DENIED` | 403 | No | The principal's roles lack the endpoint's registered permission |
| `MAKER_CHECKER_VIOLATION` | 403 | No | The maker (submitter or last editor) of a product version tries to approve or reject it |
| `RESOURCE_NOT_FOUND` | 404 | No | Unknown id, or a resource of another tenant (existence is masked) |
| `METHOD_NOT_ALLOWED` | 405 | No | HTTP method not supported by the route |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | No | Body content type other than JSON |
| `IDEMPOTENCY_CONFLICT` | 409 | No | Same key, same operation and principal, different payload |
| `REQUEST_IN_PROGRESS` | 409 | Yes | Same key currently executing (reserved for async paths; synchronous writes serialize on the unique index instead) |
| `CONFLICT_STATE` | 409 | No | Illegal lifecycle transition (transaction, hold, account, party, product version), already-reversed entry/transaction, open draft already exists |
| `DUPLICATE_RESOURCE` | 409 | No | Product code, party external reference or party identifier already used |
| `INSUFFICIENT_FUNDS` | 422 | No | Available balance check failed under row lock (`balance_id` in body) |
| `ACCOUNT_STATE_INVALID` | 422 | No | Account not ACTIVE, debit/credit blocked, closure with non-zero book figure or holds, reversal touching a closed account |
| `LIMIT_EXCEEDED` | 422 | No | Product limit breached; body has `limit: {code, window}` |
| `CREDIT_LIMIT_EXCEEDED` | 422 | No | Loan disbursement would exceed the credit limit |
| `AMOUNT_EXCEEDS_OUTSTANDING` | 422 | No | Loan repayment larger than outstanding principal |
| `CURRENCY_MISMATCH` | 422 | No | Operation currency ≠ account currency; cross-currency transfer (OD-38) |
| `OPERATION_NOT_ALLOWED` | 422 | No | Operation not in the product's `allowed_operations` |
| `PRODUCT_RULE_VIOLATION` | 422 | No | Product operation rule false (body has `rule`), first deposit below minimum opening amount, fee formula/condition failure |
| `KYC_LEVEL_INSUFFICIENT` | 422 | No | Party KYC level below the product's `min_kyc_level` at opening |
| `PARTY_STATE_INVALID` | 422 | No | Account opening for a non-ACTIVE party |
| `PRODUCT_NOT_ACTIVE` | 422 | No | Opening or simulating on a product without an ACTIVE version |
| `UNBALANCED_ENTRY` | 422 | No | Internal: a journal entry spec does not balance per currency (domain check before the DB trigger) |
| `RATE_LIMITED` | 429 | Yes | Reserved (no rate limiting yet); with `Retry-After` |
| `INTERNAL_ERROR` | 500 | Yes | Unclassified exception; generic detail, type logged without payload |
| `DEPENDENCY_UNAVAILABLE` | 503 | Yes | Reserved (IAM/queue/db-pool exhaustion) |

Not yet emitted (registered meaning reserved): `TOKEN_EXPIRED` (expired tokens currently map to
`AUTHENTICATION_REQUIRED`), `PERIOD_CLOSED` (no accounting periods yet — OD-29),
`APPROVAL_REQUIRED` (no pending-approval transaction path yet).

## Registry rules

- New codes are added here **in the same change** as the code that raises them, with:
  category, HTTP status, retryability, trigger conditions, and an example payload.
- A code's meaning is frozen once released; semantic drift requires a new code.
- Contract tests verify every raised code exists in this catalog and matches its documented
  status/retryability.
