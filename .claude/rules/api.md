# Rules — APIs (`src/next_core/**/api/`, serializers, OpenAPI specs)

Read `docs/api/api-standards.md` first.

## Contract

- All APIs are versioned (`/api/v1/...`). Breaking changes require a new version + deprecation
  policy entry — never break `v1` silently.
- Every endpoint is tenant-aware and permission-scoped (explicit OAuth scopes + object-level
  checks). An endpoint without an authorization test does not merge.
- Financial write endpoints **require** an `Idempotency-Key` header; reject its absence.
  Repeated identical request → original response; same key + different payload → `409` with
  the idempotency-conflict error code.
- OpenAPI 3.1 spec is generated/updated in the same change as the endpoint, with request and
  response examples.

## Errors

- Use the standard problem-details error structure (`docs/api/error-catalog.md`): stable
  machine-readable `code`, human `detail`, `correlation_id`, `retryable` flag, field-level
  validation errors.
- Never invent ad-hoc error shapes or reuse an existing code with a new meaning. New codes are
  added to the catalog in the same change.
- Insufficient funds, account-state violations, limit breaches, and idempotency conflicts each
  have their own stable code — never a generic 400.

## Safety

- Serializers use explicit field allow-lists — no `fields = "__all__"` (mass assignment).
- Pagination on all collection endpoints; bounded page sizes.
- Filtering through an explicit allow-list of filterable fields — never pass client input into
  arbitrary ORM lookups.
- Request-size limits and input validation at the boundary; domain revalidates.
- Responses never leak other tenants' identifiers, internal IDs, stack traces, or secrets.

## Observability

- Every request carries/propagates correlation + trace IDs; financial operations log a
  structured audit-relevant record (see `.claude/rules/security.md` for what must NOT be
  logged).
