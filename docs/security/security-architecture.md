# Security Architecture *(skeleton — authored Phase 2, hardened Phase 9)*

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

## To author with implementation

1. **Authentication flows** *(Phase 2)* — token validation pipeline, per-tenant issuer/
   audience config, service-account patterns, token lifetimes, key rotation (JWKS refresh).
2. **Authorization engine** *(Phase 2)* — permission registry, role definitions, scope→
   permission mapping, object-level check helpers, maker-checker engine states & storage,
   ABAC attributes (branch/org-unit).
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
