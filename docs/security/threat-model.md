# Initial Threat Model

| | |
|---|---|
| **Purpose** | STRIDE-style analysis per trust boundary, driving the security architecture and review priorities. |
| **Audience** | Engineering, security reviewers. |
| **Owning phase** | Phase 0 (initial) → revisited at Phases 2, 5, 9 gates. |
| **Related** | [Security architecture](security-architecture.md) · [Tenancy](../architecture/tenancy-and-deployment.md) · `.claude/rules/security.md` |

## Assets (what attackers want)

A1 Ledger integrity (ability to create/alter value) · A2 Customer funds (unauthorized
movement) · A3 Customer PII/KYC references · A4 Credentials & tokens · A5 Tenant isolation ·
A6 Audit-trail integrity · A7 Configuration integrity (products/fees/limits) · A8 Service
availability.

## Actors

External attacker · malicious/compromised API client of a tenant · malicious tenant (against
other tenants) · malicious insider (institution staff) · malicious/compromised vendor
operator · compromised dependency (supply chain).

## Trust boundaries & top threats

### TB1 — Internet → API layer
| STRIDE | Threat | Mitigations (phase) |
|---|---|---|
| S | Token theft/forgery, replayed requests | OIDC validation (iss/aud/exp/JWKS), short-lived tokens (2); idempotency keys make replays harmless (3) |
| T | Parameter tampering, mass assignment | Allow-list serializers, strict validation, request-size limits (1–3) |
| R | Client disputes an operation | Idempotency records + audit evidence + correlation IDs (2–3) |
| I | BOLA — reading others' accounts/transactions | Object-level authz on every resource; tenant scoping; opaque IDs (2+) |
| D | Volumetric abuse, expensive queries | Rate limiting (Redis), pagination, bounded filters (1–5) |
| E | BFLA — client reaching operator functions | Function-level permission checks; scope model; route segregation (2) |

### TB2 — App layer → tenant databases
Threats: SQL injection; unscoped queries (cross-tenant, **top risk A5**); connection/pool
cross-contamination; direct DML bypassing posting service. Mitigations: ORM
parameterization + raw-SQL review rule; tenant-scoped managers + routing tests; per-tenant
pools; DB grants revoking UPDATE/DELETE on append-only tables; posting-path role separation
(OD-14); constraint backstops (invariants 23–24).

### TB3 — Control plane ↔ data plane
Threats: compromised control plane manipulating financial data (**A1/A5**); routing-map
poisoning sending tenant A traffic to tenant B DB; rogue provisioning. Mitigations: control
plane holds **no tenant-DB credentials** (physical separation, ADR-0005); signed TTL-bound
routing entries validated against tenant registry; provisioning via separate audited
bootstrap role; all control-plane privileged ops audited + alerting; maker-checker on tenant
lifecycle operations.

### TB4 — App ↔ external IAM
Threats: weak token validation, confused-deputy via mis-scoped audiences, IAM compromise.
Mitigations: strict OIDC validation per tenant realm; audience binding per API; authorization
decided inside Next Core (ADR-0008) limiting blast radius of role-claim inflation;
contract tests on the boundary; break-glass procedures documented (runbooks, Phase 9).

### TB5 — Webhooks & integrations (both directions)
Threats: webhook forgery inbound; SSRF via tenant-configured endpoint URLs; secret leakage;
statement-file poisoning (recon ingestion). Mitigations: HMAC signing + timestamp/replay
window verification both directions; outbound URL policy (deny link-local/metadata/private
ranges, scheme allow-list); per-tenant secrets, rotation; ingestion parsing hardened
(size/type limits, no archive-bomb expansion), recon adjustments always maker-checker.

### TB6 — Async workers & queues
Threats: forged/duplicate queue messages; poison messages stalling EoD; Redis compromise.
Mitigations: queue as transport only — workers re-validate against DB (ADR-0003/0007); inbox
dedup; DLQ + alerting; Redis holds no secrets/financial truth; network-isolated Redis.

### TB7 — Operations & supply chain
Threats: malicious dependency/image (A1–A8); CI compromise; secret leakage in
logs/repo/backups; insider with DB access editing history. Mitigations: pinned/scanned
dependencies (pip-audit/Bandit/Semgrep), image scanning, SBOM, signing if available (9);
secret-scan hooks + CI; structured logs with redaction rules; append-only grants +
tamper-evident snapshot chaining (OD-15) + integrity runs detecting history edits;
backup encryption + restore-drill verification (9).

### TB8 — Back office (institution staff)
Threats: insider fraud (self-approval, config manipulation → A2/A7), audit evasion.
Mitigations: maker-checker with maker≠checker enforced server-side; privileged-op audit with
before/after state; no financial mutations via Django admin; ABAC branch restrictions where
configured; alerting on privileged patterns (9).

## Cross-cutting decisions already made

Immutable ledger + reversals only (A1) · DB-per-tenant (A5) · outbox-only events (A6
consistency) · no default tenant · no arbitrary tenant code · encryption in transit
everywhere / at rest for tenant DBs and backups (details in security architecture, Phase 2/9).

## Residual risks (tracked)

| Risk | Status |
|---|---|
| Vendor operator with infra-level DB access (SaaS) | Reduced by role separation + audit + tamper evidence; PAM integration in control-readiness mapping; cannot be eliminated technically — disclosed honestly |
| Compromised customer IAM issuing valid tokens | Bounded by Next Core-side authorization + limits + maker-checker; anomaly alerting Phase 9 |
| Air-gapped installs missing security updates | Offline update bundles + documented cadence; customer responsibility stated in on-prem guide |

## Review cadence

Threat model re-reviewed at Phases 2, 5, 9 gates and whenever a new trust boundary appears
(`security-reviewer` prompts for it). Findings feed the control-readiness mapping — never
certification claims.
