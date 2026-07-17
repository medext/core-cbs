# Rules — Security (all code)

Read `docs/security/threat-model.md` and `docs/security/security-architecture.md` first.

## Secrets & sensitive data

- Never commit secrets, keys, tokens, or credentials — not in code, config, fixtures, tests,
  docs, or commit history. Local secrets come from env/secret manager; the repo carries only
  `*.example` templates.
- Never log: passwords, tokens, private keys, full identity documents, full card data (PAN),
  or unnecessary PII. Logs carry correlation IDs and opaque resource IDs instead.
- PII fields are classified (`docs/security/` data classification) and separated from
  accounting data where appropriate; encryption at rest for sensitive stores.

## AuthN / AuthZ

- Authentication is delegated to external IAM (OAuth2/OIDC — ADR-0008). Never implement
  password storage, login forms, or session invention.
- Every endpoint and every command handler enforces: tenant scope + function-level permission +
  object-level ownership (BOLA/BFLA are the top API risks). "Authenticated" is never
  sufficient.
- Privileged and configuration-changing operations require maker-checker: the maker cannot
  approve their own change; enforcement is server-side, tested.
- Short-lived tokens; service-to-service auth via client credentials; webhook receivers verify
  signatures (never trust unverified webhooks).

## Code-level rules

- Parameterized queries only — raw SQL requires review and never interpolates input.
- Validate and bound all input (size, type, range) at the boundary; protect against mass
  assignment (explicit serializer fields).
- No SSRF: outbound URLs (webhooks, statement sources) are validated against allow-list
  policies; no fetching arbitrary user-supplied URLs from the server.
- Broad `except Exception` without re-raise, classification, or a justified recovery strategy
  is prohibited.
- No `eval`/`exec`/dynamic import of tenant-supplied content. A future rules engine must be
  sandboxed, deterministic, versioned, resource-limited (see master prompt §13) — do not
  improvise one.

## Supply chain & platform

- New dependencies require justification; they are scanned (pip-audit/Bandit/Semgrep, image
  scanning) and pinned. SBOM is generated for production artifacts (Phase 9).
- Django deployment checks (`manage.py check --deploy`) must pass; security-relevant settings
  are documented.
- Never claim ISO 27001 / PCI DSS / SOC 2 compliance — maintain the control-readiness mapping
  instead (`docs/security/control-readiness.md`).

## Review

Run the `security-reviewer` subagent on changes touching: auth, tenancy, serializers exposing
new fields, webhook verification, crypto, file/URL handling, or logging.
