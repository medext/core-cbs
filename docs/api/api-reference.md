# API Reference — v1

| | |
|---|---|
| **Purpose** | The complete list of Next Core v1 endpoints with permissions, idempotency, inputs, outputs and main error codes, plus a quickstart walkthrough. |
| **Audience** | API integrators, engineering, QA, reviewers. |
| **Owning phase** | MVP track (Phases 3–6 compressed, 2026-11-25). Must match `src/next_core/**/api.py` and `urls.py` (same-change rule). |
| **Related** | [API standards](api-standards.md) · [Error catalog](error-catalog.md) · [Authorization matrix](../security/authorization-matrix.md) · [Product engine](../products/product-engine.md) · [Balance semantics](../accounting/balance-semantics.md) · [Transaction lifecycle](../domain/transaction-lifecycle.md) |

## Machine-readable contract

- **OpenAPI 3.1** generated from the code (drf-spectacular): `GET /api/schema/openapi.json`
  (public, no tenant, no token). A committed copy lives at `docs/api/openapi.json` and is
  contract-tested against the generated schema.
- **Redoc** rendering: `GET /api/schema/docs`.

## Common headers

| Header | Direction | Meaning |
|---|---|---|
| `X-Tenant-ID` | request | Tenant slug (header resolver: local/dev/staging behind a trusted gateway). Missing/invalid/unknown → `400 TENANT_RESOLUTION_FAILED`. Ignored on-premise (static tenant). |
| `Authorization: Bearer <JWT>` | request | Access token from the tenant's OIDC realm; issuer must match the resolved tenant, else `401 AUTHENTICATION_REQUIRED`. Roles come from `realm_access.roles`. |
| `Idempotency-Key` | request | **Required on every financial write** (marked "Idem" below); 1–128 printable chars. Missing → `400 IDEMPOTENCY_KEY_REQUIRED`. Scope: (tenant, operation, principal, key). |
| `Idempotent-Replayed` | response | `true` when the response is the stored original (same key + same payload); `false` on first execution. |
| `X-Request-ID` | both | Correlation id, accepted or generated, echoed and present in problem bodies as `correlation_id`. |

Conventions: amounts are **decimal strings in major units** with at most the currency exponent
(`"100.00"` MRU/EUR/USD, `"750"` XOF) plus a `currency` field; excess precision is rejected.
IDs are UUIDs. Write bodies reject unknown fields (`400 VALIDATION_ERROR`). Errors are RFC 9457
problem details (`application/problem+json`). Out-of-tenant or unknown resources → `404
RESOURCE_NOT_FOUND`.

## Parties

| Method & path | Permission | Idem | Request | Response | Main errors |
|---|---|---|---|---|---|
| `GET /api/v1/parties` | `parties:read` | — | filters `status`, `kyc_status`, `external_ref`, `type`; cursor `cursor`, `limit` ≤ 200 | page of parties | — |
| `POST /api/v1/parties` | `parties:write` | — | `type` (INDIVIDUAL/ORGANIZATION), `display_name`, `given_name`, `family_name`, `legal_name`, `registration_number`, `birth_date`, `nationality`, `residence_country`, `email`, `phone`, `risk_rating`, `external_ref`, `identifiers[] {scheme, value, issuing_country}` | 201 party | `VALIDATION_ERROR`, `DUPLICATE_RESOURCE` |
| `GET /api/v1/parties/{id}` | `parties:read` | — | — | party | `RESOURCE_NOT_FOUND` |
| `PATCH /api/v1/parties/{id}` | `parties:write` | — | any updatable attribute above (not `type`) | party | `DUPLICATE_RESOURCE` |
| `POST /api/v1/parties/{id}/status` | `parties:write` | — | `status` (ACTIVE/BLOCKED/DECEASED/CLOSED), `reason` | party | `CONFLICT_STATE` |
| `POST /api/v1/parties/{id}/kyc` | `parties:write` | — | `status` (NOT_STARTED/PENDING/VERIFIED/REJECTED), `level` 0–3, `reference` | party | `VALIDATION_ERROR` (VERIFIED needs level ≥ 1; other statuses level 0) |

Individuals require `given_name` or `family_name`; organizations require `legal_name`.

## Products (product engine)

| Method & path | Permission | Idem | Request | Response | Main errors |
|---|---|---|---|---|---|
| `GET /api/v1/products` | `products:read` | — | filter `category`; `page`, `page_size` | page of products (with `active_version`, `versions[]`) | — |
| `POST /api/v1/products` | `products:write` | — | `code`, `name`, `description`, `definition` | 201 version 1 (DRAFT) | `VALIDATION_ERROR` (field paths), `DUPLICATE_RESOURCE` |
| `GET /api/v1/products/templates` | `products:read` | — | — | seed definitions | — |
| `POST /api/v1/products/validate` | `products:read` | — | `definition` | summary (`valid`, fees, limits, rules) | `VALIDATION_ERROR` |
| `GET /api/v1/products/{id}` | `products:read` | — | — | product | `RESOURCE_NOT_FOUND` |
| `POST /api/v1/products/{id}/retire` | `products:approve` | — | — | retired version | `CONFLICT_STATE` |
| `POST /api/v1/products/{id}/simulate` | `products:read` | — | `operation`, `amount`, `currency`, `channel`, `kyc_level`, `book_balance`, `account_age_days`, `days_to_maturity`, `parameter_overrides`, optional `version` | `allowed`, `rules[]`, `fees[]`, `limits[]` | `PRODUCT_NOT_ACTIVE`, `VALIDATION_ERROR` |
| `GET /api/v1/products/{id}/versions` | `products:read` | — | — | versions | — |
| `POST /api/v1/products/{id}/versions` | `products:write` | — | `definition` | 201 new DRAFT | `CONFLICT_STATE` (open draft exists), `VALIDATION_ERROR` |
| `GET /api/v1/products/{id}/versions/{n}` | `products:read` | — | — | version | `RESOURCE_NOT_FOUND` |
| `PUT /api/v1/products/{id}/versions/{n}` | `products:write` | — | `definition` | version | `CONFLICT_STATE` (not DRAFT) |
| `POST /api/v1/products/{id}/versions/{n}/submit` | `products:write` | — | `reason` (optional) | PENDING_APPROVAL | `CONFLICT_STATE` |
| `POST /api/v1/products/{id}/versions/{n}/approve` | `products:approve` | — | `reason` (optional) | ACTIVE (previous ACTIVE → SUPERSEDED) | `MAKER_CHECKER_VIOLATION`, `CONFLICT_STATE`, `VALIDATION_ERROR` (GL mapping) |
| `POST /api/v1/products/{id}/versions/{n}/reject` | `products:approve` | — | `reason` (required) | REJECTED | `MAKER_CHECKER_VIOLATION` |

## Accounts

| Method & path | Permission | Idem | Request | Response | Main errors |
|---|---|---|---|---|---|
| `GET /api/v1/accounts` | `accounts:read` | — | filters `party_id`, `status`, `product_code`, `currency`, `number`; cursor | page of accounts | `VALIDATION_ERROR` |
| `POST /api/v1/accounts` | `accounts:open` | — | `party_id`, `product_id`, `currency`, `parameter_overrides`, `nickname` | 201 account with `balances[]` | `PARTY_STATE_INVALID`, `KYC_LEVEL_INSUFFICIENT`, `PRODUCT_NOT_ACTIVE`, `VALIDATION_ERROR` |
| `GET /api/v1/accounts/{id}` | `accounts:read` | — | — | account + qualified balances | `RESOURCE_NOT_FOUND` |
| `GET /api/v1/accounts/{id}/balances` | `accounts:read` | — | — | per ledger balance: `book_balance`, `available_balance`, `cleared_balance`, `held_amount`, `pending_debit`, `pending_credit`, `overdraft_limit`, `as_of` | — |
| `GET /api/v1/accounts/{id}/statement` | `accounts:read` | — | `purpose` (PRINCIPAL / ACCRUED_INTEREST), `after` (posting id), `limit` ≤ 200 | `lines[]` with `running_book_balance`, `next_after` | `VALIDATION_ERROR` |
| `GET /api/v1/accounts/{id}/limits` | `accounts:read` | — | — | windowed limit usage | — |
| `GET /api/v1/accounts/{id}/history` | `accounts:read` | — | — | status & block history | — |
| `POST /api/v1/accounts/{id}/status` | `accounts:control` | — | `status` (ACTIVE/FROZEN/DORMANT/CLOSED), `reason` | account | `CONFLICT_STATE`, `ACCOUNT_STATE_INVALID` (closure with value/holds) |
| `POST /api/v1/accounts/{id}/blocks` | `accounts:control` | — | `debit_blocked`, `credit_blocked`, `reason` | account | `CONFLICT_STATE` (closed) |

Account numbers are 12 digits: a 10-digit per-tenant sequence + 2 ISO 7064 mod-97 check digits
(`int(number) % 97 == 1`).

## Transactions

All writes return the business transaction (201) or a problem body; a business rejection is
recorded as a `REJECTED` transaction (its id in `transaction_id`) and replayed identically for
the same key (OD-35).

| Method & path | Permission | Idem | Request | Main errors |
|---|---|---|---|---|
| `POST /api/v1/transactions/deposits` | `transactions:post` | **yes** | `account_id`, `amount`, `currency`, `reference`, `narrative`, `channel` | `ACCOUNT_STATE_INVALID`, `OPERATION_NOT_ALLOWED`, `PRODUCT_RULE_VIOLATION`, `LIMIT_EXCEEDED`, `CURRENCY_MISMATCH` |
| `POST /api/v1/transactions/withdrawals` | `transactions:post` | **yes** | same | + `INSUFFICIENT_FUNDS` |
| `POST /api/v1/transactions/transfers` | `transactions:post` | **yes** | `source_account_id`, `target_account_id`, amount… | + `INSUFFICIENT_FUNDS`, `CURRENCY_MISMATCH` (cross-currency) |
| `POST /api/v1/transactions/simulate` | `transactions:read` | — | `type` (DEPOSIT/WITHDRAWAL/TRANSFER/DISBURSEMENT/REPAYMENT/HOLD) + the fields of that operation | returns `outcome` (`WOULD_POST`, `WOULD_BE_HELD`, `WOULD_BE_REJECTED`), predicted `transaction`, `balances_after`, or `error`; always rolled back |
| `GET /api/v1/transactions` | `transactions:read` | — | filters `account_id`, `type`, `state`; cursor | — |
| `GET /api/v1/transactions/{id}` | `transactions:read` | — | — | `RESOURCE_NOT_FOUND` |
| `GET /api/v1/transactions/{id}/transitions` | `transactions:read` | — | — | — |
| `POST /api/v1/transactions/{id}/reversal` | `transactions:reverse` | **yes** | `reason` | `CONFLICT_STATE` (not POSTED / not reversible), `ACCOUNT_STATE_INVALID` (closed account) |

Transaction body: `id`, `type`, `state`, `is_terminal`, `funds_reserved`, `amount`,
`currency`, `debit_account_id`, `credit_account_id`, `fees[] {code, account_id, amount, tax,
total, currency}`, `total_fees`, `reference`, `narrative`, `channel`, `business_date`,
`value_date`, `journal_entry_ids`, `product_versions`, `reversal_of`, `reversed_by`,
`rejection {code, detail}`, `hold`, `created_at`.

## Holds

| Method & path | Permission | Idem | Request | Main errors |
|---|---|---|---|---|
| `POST /api/v1/holds` | `holds:manage` | **yes** | `account_id`, `amount`, `currency`, `expires_in_seconds` (60–2 592 000, default 7 days), `reference`, `narrative`, `channel` | `INSUFFICIENT_FUNDS`, `LIMIT_EXCEEDED`, `ACCOUNT_STATE_INVALID` |
| `GET /api/v1/holds/{id}` | `transactions:read` | — | — | `RESOURCE_NOT_FOUND` |
| `POST /api/v1/holds/{id}/capture` | `holds:manage` | **yes** | `target_account_id`, optional `amount` + `currency` (partial; remainder released) | `CONFLICT_STATE` (not ACTIVE / expired), `VALIDATION_ERROR` |
| `POST /api/v1/holds/{id}/release` | `holds:manage` | **yes** | — | `CONFLICT_STATE` |

Expired ACTIVE holds are voided by the EoD step (`EXPIRED`).

## Loans

| Method & path | Permission | Idem | Request | Main errors |
|---|---|---|---|---|
| `POST /api/v1/loans/{loan_account_id}/disbursements` | `transactions:post` | **yes** | `target_account_id`, `amount`, `currency`, … | `CREDIT_LIMIT_EXCEEDED`, `OPERATION_NOT_ALLOWED` |
| `POST /api/v1/loans/{loan_account_id}/repayments` | `transactions:post` | **yes** | `source_account_id`, `amount`, `currency`, … | `AMOUNT_EXCEEDS_OUTSTANDING`, `INSUFFICIENT_FUNDS` |

## Ledger (read-only) and operations

There is **no endpoint that writes a ledger balance**; value changes only through business
transactions.

| Method & path | Permission | Idem | Response |
|---|---|---|---|
| `GET /api/v1/ledger/gl-accounts` | `ledger:read` | — | chart of accounts |
| `GET /api/v1/ledger/trial-balance` | `ledger:read` | — | per GL × currency debit/credit totals and net; per-currency `balanced` flag |
| `GET /api/v1/ledger/entries/{id}` | `ledger:read` | — | journal entry with postings, `reversal_of`, `reversed_by` |
| `POST /api/v1/operations/integrity-runs` | `operations:run` | — | 201 integrity run: reconstruct projections from postings, check balanced entries |
| `POST /api/v1/operations/eod` | `operations:run` | — (idempotent by design: deterministic ids) | `business_date` (optional) → holds expired, interest accrued/capitalized counts |

## Audit

| Method & path | Permission | Response |
|---|---|---|
| `GET /api/v1/audit/events` | `audit:read` | page of audit events (filters `operation`, `resource_type`); access itself is audited |

## Health & schema (no tenant, no token)

`GET /health/live`, `GET /health/ready`, `GET /api/schema/openapi.json`, `GET /api/schema/docs`.

## Quickstart walkthrough (local)

```bash
make test-db-start && uv sync
export NEXT_CORE_PROFILE=local DJANGO_SETTINGS_MODULE=next_core.settings.local
uv run python manage.py migrate && uv run python manage.py migrate_tenants
uv run python manage.py bootstrap_tenant --tenant alpha   # seed CoA + 5 products
uv run python manage.py runserver 0.0.0.0:8000
```

Tokens come from the tenant's OIDC realm (Keycloak in the compose `iam` profile). Below,
`$T` is a token with roles `teller supervisor operations`; `H` sets the common headers.

```bash
H=(-H "X-Tenant-ID: alpha" -H "Authorization: Bearer $T" -H "Content-Type: application/json")
API=http://localhost:8000/api/v1

# 1. Party + KYC outcome
P=$(curl -s "${H[@]}" $API/parties -d '{"type":"INDIVIDUAL","display_name":"Aminata","given_name":"Aminata"}' | jq -r .id)
curl -s "${H[@]}" $API/parties/$P/kyc -d '{"status":"VERIFIED","level":2,"reference":"kyc-123"}'

# 2. Accounts on the CURRENT product
PROD=$(curl -s "${H[@]}" $API/products | jq -r '.results[]|select(.code=="CURRENT").id')
A=$(curl -s "${H[@]}" $API/accounts -d "{\"party_id\":\"$P\",\"product_id\":\"$PROD\",\"currency\":\"MRU\"}" | jq -r .id)
B=$(curl -s "${H[@]}" $API/accounts -d "{\"party_id\":\"$P\",\"product_id\":\"$PROD\",\"currency\":\"MRU\"}" | jq -r .id)

# 3. Deposit (retry with the SAME key is safe)
curl -s "${H[@]}" -H "Idempotency-Key: dep-001" $API/transactions/deposits \
  -d "{\"account_id\":\"$A\",\"amount\":\"5000.00\",\"currency\":\"MRU\",\"channel\":\"BRANCH\"}"

# 4. Transfer (product fee applied to the sender)
TX=$(curl -s "${H[@]}" -H "Idempotency-Key: trf-001" $API/transactions/transfers \
  -d "{\"source_account_id\":\"$A\",\"target_account_id\":\"$B\",\"amount\":\"1000.00\",\"currency\":\"MRU\"}" | jq -r .id)

# 5. Hold then partial capture
HOLD=$(curl -s "${H[@]}" -H "Idempotency-Key: hold-001" $API/holds \
  -d "{\"account_id\":\"$A\",\"amount\":\"300.00\",\"currency\":\"MRU\",\"expires_in_seconds\":3600}" | jq -r .hold.id)
curl -s "${H[@]}" -H "Idempotency-Key: cap-001" $API/holds/$HOLD/capture \
  -d "{\"target_account_id\":\"$B\",\"amount\":\"250.00\",\"currency\":\"MRU\"}"

# 6. Reverse the transfer (needs transactions:reverse)
curl -s "${H[@]}" -H "Idempotency-Key: rev-001" $API/transactions/$TX/reversal -d '{"reason":"dispute"}'

# 7. Statement and qualified balances
curl -s "${H[@]}" "$API/accounts/$A/statement?limit=50"
curl -s "${H[@]}" $API/accounts/$A/balances

# 8. End of day: hold expiry + interest, then integrity verification
curl -s "${H[@]}" $API/operations/eod -d '{}'
curl -s "${H[@]}" -X POST $API/operations/integrity-runs
```

The same flow is executed automatically by `tests/e2e/test_api_flows.py`.
