# Authorization Matrix *(structure live since Phase 2; MVP-track endpoints added 2026-11-25)*

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

## Role bundles (seed — `src/next_core/iam/permissions.py`)

| Role | Permissions |
|---|---|
| `teller` | `parties:read/write`, `products:read`, `accounts:read`, `accounts:open`, `transactions:read`, `transactions:post`, `holds:manage` |
| `supervisor` | teller + `accounts:control`, `transactions:reverse`, `loans:disburse` |
| `loan_officer` | `parties:read`, `products:read`, `accounts:read`, `accounts:open`, `transactions:read`, `loans:disburse` |
| `product_manager` (maker) | `products:read`, `products:write`, `ledger:read` |
| `product_approver` (checker) | `products:read`, `products:approve`, `ledger:read` |
| `operations` | `operations:run`, `ledger:read`, `accounts:read`, `transactions:read`, `products:read` |
| `auditor` | `audit:read`, `parties:read`, `products:read`, `accounts:read`, `transactions:read`, `ledger:read` |
| `api_client` | `parties:read`, `products:read`, `accounts:read`, `transactions:read`, `transactions:post`, `holds:manage` — **not** `loans:disburse`. Residual (security review H2, OD-42): within its tenant an `api_client` can still transfer from any account and capture a hold to any target; channel/account scoping is required before onboarding production channels. |
| `platform_ops` | `audit:read` |

**Object-level condition (all data-plane rows below):** the resource must belong to the
resolved tenant — enforced by tenant-database routing plus a `tenant_id` predicate on every
scoped manager; any other id yields `404 RESOURCE_NOT_FOUND` (existence masked). There is no
finer ownership model (branch/portfolio/customer self-service) in the MVP (OD-36).

## Parties (MVP track)

| Operation | API scope | Permission | Roles (default bundles) | Object-level condition | Maker-checker | Audit evidence |
|---|---|---|---|---|---|---|
| `GET /api/v1/parties`, `GET /parties/{id}` | bearer | `parties:read` | teller, supervisor, loan_officer, auditor, api_client | Tenant scope; 404 masking | none | — (read) |
| `POST /parties`, `PATCH /parties/{id}` | bearer | `parties:write` | teller, supervisor | Tenant scope | none | outbox `party.created` / `party.updated` |
| `POST /parties/{id}/status`, `POST /parties/{id}/kyc` | bearer | `parties:write` | teller, supervisor | Tenant scope; legal status transitions only | none (OD-36 follow-up: KYC maker-checker) | outbox `party.status.changed`, `party.kyc.recorded` |

## Products (MVP track)

| Operation | API scope | Permission | Roles (default bundles) | Object-level condition | Maker-checker | Audit evidence |
|---|---|---|---|---|---|---|
| List/get products & versions, templates, validate, simulate | bearer | `products:read` | all bundles except platform_ops | Tenant scope | none | — |
| Create product, draft version, edit draft, submit | bearer | `products:write` | product_manager | Tenant scope; edit only DRAFT | **maker** | audit `product.version.drafted/edited/submitted` |
| Approve, reject | bearer | `products:approve` | product_approver | Tenant scope; PENDING_APPROVAL only | **required**: approver ≠ submitter and ≠ last editor (app check + DB CHECK `pv_maker_checker`) | audit `product.version.approved/rejected`; outbox `product.version.activated` |
| Retire | bearer | `products:approve` | product_approver | Tenant scope (unknown/foreign product → 404); ACTIVE only | none — **documented exception**: single privileged step (OD-43) | audit `product.retired` |

## Accounts (MVP track)

| Operation | API scope | Permission | Roles (default bundles) | Object-level condition | Maker-checker | Audit evidence |
|---|---|---|---|---|---|---|
| List/get account, balances, statement, limits, history | bearer | `accounts:read` | teller, supervisor, loan_officer, operations, auditor, api_client | Tenant scope; 404 masking | none | — |
| Open account | bearer | `accounts:open` | teller, supervisor, loan_officer | Tenant scope; party ACTIVE + KYC level ≥ product minimum | none | audit `account.opened`; outbox `account.opened` |
| Change status (freeze/unfreeze/dormant/close), set blocks | bearer | `accounts:control` | supervisor | Tenant scope; closure requires zero book figures and no holds | none (follow-up) | audit + outbox `account.status.changed`; append-only status history |

## Transactions, holds, loans (MVP track)

| Operation | API scope | Permission | Roles (default bundles) | Object-level condition | Maker-checker | Audit evidence |
|---|---|---|---|---|---|---|
| Deposit, withdrawal, transfer, loan repayment | bearer + `Idempotency-Key` | `transactions:post` | teller, supervisor, api_client | Tenant scope; account state & product rules | none | transitions history; outbox `transaction.state.changed`, `journal_entry.posted`; idempotency record |
| Loan disbursement — `POST /loans/{id}/disbursements` | bearer + `Idempotency-Key` | `loans:disburse` | supervisor, loan_officer | Tenant scope; product credit limit | none (credit decision kept off channel clients) | transitions history; outbox `transaction.state.changed`, `journal_entry.posted`; idempotency record |
| Place / capture / release hold | bearer + `Idempotency-Key` | `holds:manage` | teller, supervisor, api_client | Tenant scope | none | same |
| Reverse a POSTED transaction | bearer + `Idempotency-Key` | `transactions:reverse` | supervisor | Tenant scope; no closed account | **four-eyes rule**: the original's initiator cannot reverse it (`403 MAKER_CHECKER_VIOLATION`; DB trigger `business_transaction_reversal_four_eyes`). Full request→approve workflow deferred (OD-41) | audit `transaction.reversed`; outbox `journal_entry.reversed` |
| List/get transactions, transitions, holds; simulate | bearer | `transactions:read` | teller, supervisor, loan_officer, operations, auditor, api_client | Tenant scope | none | — |

## Ledger & operations (MVP track)

| Operation | API scope | Permission | Roles (default bundles) | Object-level condition | Maker-checker | Audit evidence |
|---|---|---|---|---|---|---|
| GL accounts, trial balance, journal entry | bearer | `ledger:read` | operations, auditor, product_manager, product_approver | Tenant scope | none | — |
| Integrity run, EoD steps | bearer | `operations:run` | operations | Tenant scope | none | persisted `IntegrityRun`; outbox `integrity.mismatch`; EoD postings via transactions |

No endpoint mutates a ledger balance directly (invariant 8).

Cross-cutting conditions enforced on every authenticated route: resolved tenant context
(hard 400 otherwise) + token issuer bound to the resolved tenant's realm (401 on mismatch) +
registered permission (403 otherwise). A method a view does not implement answers `405
METHOD_NOT_ALLOWED`; a handler without a mapped permission is denied. Registry source of truth:
`src/next_core/iam/permissions.py`.

Each subsequent phase appends its rows in the same change as its endpoints
(ledger/Phase 3, accounts-products/Phase 4, transfers-holds/Phase 5, config workflow/Phase 6,
recon-EoD/Phase 7…). The `security-reviewer` blocks any endpoint missing its row.
