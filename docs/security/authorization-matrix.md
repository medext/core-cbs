# Authorization Matrix *(skeleton — authored Phase 2, extended every phase)*

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

## Seed content to author in Phase 2

Platform operations (tenant admin, token introspection, audit read), account operations
skeleton. Each subsequent phase appends its rows in the same change as its endpoints
(ledger/Phase 3, accounts-products/Phase 4, transfers-holds/Phase 5, config workflow/Phase 6,
recon-EoD/Phase 7…). The `security-reviewer` blocks any endpoint missing its row.
