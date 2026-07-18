# ADR-0008 — External IAM via OAuth 2.0 / OIDC (Keycloak reference); no homegrown authentication

- **Status:** Accepted
- **Date:** 2026-07-17
- **Deciders:** mohamed@next.mr — approved 2026-07-18 (Phase 0 gate)

## Context

Master prompt §6.2/§11: OAuth2/OIDC, service accounts, RBAC/ABAC, maker-checker, token
auditability — and "do not build password authentication from scratch." On-premise customers
often mandate their own IAM (AD FS, corporate Keycloak, other OIDC providers).

## Decision

- **Authentication is fully delegated to an external OIDC provider.** Next Core validates
  OIDC tokens (JWKS, issuer/audience per tenant), never stores passwords, never renders
  login UI.
- **Keycloak is the reference implementation** (dev realm in compose from Phase 2; per-tenant
  realm in SaaS profiles), but the integration boundary is **standard OIDC**, so on-premise
  customers may bring any compliant provider (configuration, not code).
- **Authorization lives in Next Core**, not the IAM: the IAM asserts identity + coarse roles/
  groups; Next Core maps them to its tenant-scoped permission model (RBAC now, ABAC
  branch/org-unit restrictions where justified), object-level checks, and the maker-checker
  engine. Fine-grained banking permissions in IAM tokens are rejected (token bloat, sync
  drift, per-tenant configurability).
- **Service accounts / API clients:** OAuth2 client-credentials; short-lived access tokens;
  rotatable secrets; scopes name coarse API areas, Next Core permissions decide operations.
- Session/token events (issuance context, auth strength) captured into audit evidence via
  token claims + gateway logs.

## Alternatives considered

- **Build authentication in Django** — rejected: explicitly barred; credential storage, MFA,
  federation, lockout policies are undifferentiated heavy liability.
- **Authorization in the IAM (Keycloak authz services)** — rejected: banking permissions are
  product/tenant configuration (maker-checker, limits overrides) that must version and audit
  with the rest of the config plane; coupling it to a specific IAM breaks the bring-your-own-
  IAM requirement.
- **SaaS-only hosted identity (Auth0 etc.)** — rejected as the *reference*: violates
  on-premise/air-gap independence; remains usable by SaaS customers since the boundary is
  plain OIDC.

## Consequences

- **Positive:** no credential liability; per-tenant identity realms; on-prem freedom;
  authorization versioned/audited inside the product.
- **Negative / accepted costs:** Keycloak is an operational component in SaaS (HA, upgrades);
  claim-mapping contract per tenant must be validated at provisioning; contract tests for
  the IAM boundary are mandatory (test strategy).
- **Neutral:** mTLS for service-to-service evaluated in Phase 9 hardening.

## Compliance & security impact

Cleanly maps to access-control expectations in control-readiness mapping (least privilege,
short-lived tokens, PAM integration point). Threat model gains an explicit IAM trust
boundary: token validation code is security-review-mandatory.

## Reversibility

Provider-level: trivial (any OIDC). Model-level (moving authz out): costly and not desired.
