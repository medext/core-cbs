# Security Architecture *(sections 1–2 authored Phase 2; remainder skeleton, hardened Phase 9)*

| | |
|---|---|
| **Purpose** | The implemented security design: authn/authz, encryption, secrets, logging redaction, hardening. |
| **Audience** | Engineering, security reviewers, customer security teams. |
| **Owning phase** | Phase 2 (foundations) / Phase 9 (hardening) — same-change rule. |
| **Related** | [Threat model](threat-model.md) · ADR-0008 · `.claude/rules/security.md` · [Authorization matrix](authorization-matrix.md) · [Control readiness](control-readiness.md) |

## Positions fixed in Phase 0 (binding)

Secure-by-default; external OIDC only (ADR-0008); authorization inside Next Core
(tenant-scoped RBAC + object-level + maker-checker); DB-per-tenant isolation (ADR-0005);
append-only financial tables with revoked UPDATE/DELETE; signed webhooks both directions;
no secrets/PII in logs; no tenant-supplied code; encryption in transit everywhere and at rest
for tenant data; Django `check --deploy` clean as a permanent gate item.

## 1. Authentication flows *(implemented Phase 2 — `src/next_core/iam/authentication.py`)*

Bearer tokens only; validation pipeline per request: tenant context is resolved first
(middleware), then the token is validated against **that tenant's** expected issuer —
`OIDC_ISSUER_TEMPLATE.format(tenant=slug)` (realm-per-tenant, ADR-0008). Enforced:
RS256 only (algorithm-confusion blocked), signature via issuer JWKS, `iss`, `aud`
(`OIDC_AUDIENCE`), `exp`/required claims (`exp, iss, sub, aud`), 30 s leeway. Every token
defect — malformed token included — yields 401, never 500; rejection logs carry only the
exception class, never token material or claims.

- **Tenant/token binding** is structural: a valid token from tenant A's realm presented
  against tenant B fails issuer validation (proven by contract tests). Startup check
  `next_core.E001` refuses multi-tenant deployments whose issuer template lacks
  `{tenant}` (shared-issuer misconfiguration). Defense-in-depth tenant-claim cross-check:
  OD-22.
- **JWKS**: fetched from `{issuer}/protocol/openid-connect/certs` (template-configurable),
  cached per process (5 min lifespan → rotation pickup ≤5 min; emergency rotation =
  process restart). `OIDC_JWKS_STATIC` (a pinned JWKS in settings, no network) is the
  mechanism the test suite uses and the intended air-gap path — operator-reachable wiring
  for on-premise installs ships with on-prem packaging (Phase 9).
- **Service accounts**: client-credentials tokens validate identically; the principal is
  flagged service-typed and audit evidence records it. Token lifetimes are IAM policy
  (short-lived per rules); Next Core never issues or stores credentials.

## 2. Authorization engine *(implemented Phase 2 — `src/next_core/iam/permissions.py`)*

Authorization is decided **inside Next Core**; the IAM asserts identity + coarse roles only.
- **Permission registry**: append-only string codes (`audit:read`, …) — the source of truth
  behind the [authorization matrix](authorization-matrix.md); `require_permission(code)`
  refuses unregistered codes at import time.
- **Roles → permissions**: static seed bundles in Phase 2 (`auditor`, `platform_ops`);
  institution-configurable recomposition and ABAC attributes (branch/org-unit) arrive with
  the configuration workflow; maker-checker engine lands in Phase 6.
- **Deny by default**: DRF default permission is unsatisfiable by API principals
  (`is_staff=False`), so an endpoint without an explicit permission class is unreachable;
  every endpoint also sits behind tenant resolution (hard 400) and issuer-bound
  authentication (401). Roles never map to Django admin access.
- **Object-level checks**: Phase 2's only data-plane resource (audit events) is
  tenant-global; object-ownership helpers land with customer-owned resources (Phase 4) and
  are mandatory per `.claude/rules/api.md`.

## To author with implementation
3. **Encryption & key management** *(Phases 2/9)* — TLS posture, at-rest strategy per
   profile (vendor KMS / customer-managed), per-tenant key model, backup encryption,
   rotation procedures.
4. **PII classification & data separation** *(Phase 4)* — field inventory, classes, storage
   separation (parties vs. ledger), masking/redaction rules, retention.
5. **Secret management** *(Phases 1/9)* — providers per profile, rotation, `*.example`
   discipline, CI scanning.
6. **Platform hardening** *(Phase 9)* — rate-limit architecture, request-size limits,
   container hardening, image signing, SBOM, dependency policy, mTLS evaluation,
   settings inventory from `check --deploy`.
7. **Security logging & monitoring** *(Phase 9)* — auth failures, privileged ops, isolation
   alerts, incident classification hooks (runbooks).
