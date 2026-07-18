# Authorization Matrix *(structure live since Phase 2; extended every phase)*

| | |
|---|---|
| **Purpose** | The authoritative operation × role/scope × conditions matrix. Every endpoint/command must appear here before release. |
| **Audience** | Engineering, reviewers, institution admins, auditors. |
| **Owning phase** | Phase 2 structure; every phase appends its operations (same-change rule). |
| **Related** | [Security architecture](security-architecture.md) · ADR-0008 |

## Structure (binding)

One table per context. Columns:

| Operation | API scope | Permission | Roles (default bundles) | Object-level condition | Maker-checker | Audit evidence |
|---|---|---|---|---|---|---|

Rules:
- Every mutating operation names its permission; "authenticated" is never sufficient.
- Object-level condition column is mandatory (ownership/branch/tenant conditions spelled out).
- Maker-checker column: none / required / threshold-based (with the threshold source).
- Default role bundles (teller, supervisor, ops, product-admin, auditor-readonly,
  api-client…) are *seeds*; institutions recompose them via configuration.

## Audit context (Phase 2)

| Operation | API scope | Permission | Roles (default bundles) | Object-level condition | Maker-checker | Audit evidence |
|---|---|---|---|---|---|---|
| List audit events — `GET /api/v1/audit/events` | bearer token (per-tenant realm) | `audit:read` | `auditor`, `platform_ops` | Tenant scope only (events are tenant-global; routed to tenant DB + `tenant_id` predicate) | none (read) | `audit.trail.viewed` event recorded per access |

Cross-cutting conditions enforced on every authenticated route: resolved tenant context
(hard 400 otherwise) + token issuer bound to the resolved tenant's realm (401 on mismatch) +
registered permission (403 otherwise). Registry source of truth:
`src/next_core/iam/permissions.py`.

Each subsequent phase appends its rows in the same change as its endpoints
(ledger/Phase 3, accounts-products/Phase 4, transfers-holds/Phase 5, config workflow/Phase 6,
recon-EoD/Phase 7…). The `security-reviewer` blocks any endpoint missing its row.
