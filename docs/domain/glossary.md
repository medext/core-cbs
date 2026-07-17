# Domain Glossary

| | |
|---|---|
| **Purpose** | Authoritative vocabulary. Ambiguous use of these terms in code, docs, or APIs is a defect. |
| **Audience** | Everyone. |
| **Owning phase** | Phase 0 (extended in every phase, same-change rule). |
| **Related** | [Balance semantics](../accounting/balance-semantics.md) · [Transaction lifecycle](transaction-lifecycle.md) |

**Rule:** the bare word **"balance"** is banned in code and docs — always use a qualified
term (book balance, available balance…). Likewise "transaction" must be qualified where
ambiguous (business transaction vs. accounting transaction vs. database transaction).

## Accounting & ledger

| Term | Definition |
|---|---|
| **Ledger** | A tenant-scoped, append-only collection of journal entries and postings governed by one chart of accounts. |
| **Chart of Accounts (CoA)** | The versioned catalog of GL accounts, their codes, types (asset/liability/income/expense/equity), and normal balance sides for an institution. |
| **GL account** | A general-ledger account in the CoA; aggregates activity (directly or from subledger mappings). |
| **Customer subledger** | The set of ledger balances belonging to customer accounts, each mapped to a GL account for aggregation. |
| **Journal entry** | The atomic accounting record: a set of ≥2 postings that balances per currency; immutable once posted. |
| **Posting** | One debit or credit of a specific amount and currency against one ledger balance, belonging to exactly one journal entry; immutable. |
| **Accounting transaction** | Synonym for journal entry seen from the posting engine; distinct from *business transaction*. |
| **Business transaction** | A customer/operator-level operation (transfer, deposit, fee…) orchestrated by the Transactions context; references the journal entries it produced. |
| **Posting rule** | Versioned, declarative mapping from a business operation (+product/config) to the postings it must generate (which sides, which accounts, fee/tax legs). |
| **Normal balance (side)** | The side (debit or credit) on which an account's balance conventionally increases (assets/expenses: debit; liabilities/income/equity: credit). |
| **Direction** | DEBIT or CREDIT on a posting. Never encoded as a signed amount. |
| **Reversal** | A new journal entry that exactly offsets a prior entry, linked to it via a mandatory reversal relationship; the original is untouched. |
| **Compensating entry** | A new entry correcting an economic error without being a strict mirror (e.g., partial correction); always linked to its cause. |
| **Posting batch** | A grouped set of journal entries processed together (e.g., EoD fees) with batch-level traceability. |
| **Accounting period** | A bounded interval (e.g., month) that can be open, closing, or closed; postings into closed periods are prohibited (corrections post into the open period with a value date). |
| **Trial balance** | Per-period statement proving total debits = total credits across the CoA, derived from postings. |
| **Balance projection** | A stored, performance-oriented representation of a ledger balance, always reconstructable from postings; never authoritative on its own. |
| **Balance reconstruction** | Recomputing a balance (or all balances) strictly from the posting history and comparing to projections. |
| **Integrity verification record** | Persisted evidence of an integrity check run (scope, result, mismatches). |
| **FX bridge** | The explicitly modeled mechanism (position accounts + rate reference) through which cross-currency operations become per-currency-balanced entries. |

## Money & dates

| Term | Definition |
|---|---|
| **Money** | Value object: integer amount in minor units + ISO-4217 currency code (ADR-0004). |
| **Minor units** | Smallest currency denomination (cents, centimes); exponent per ISO 4217 (with documented overrides table). |
| **Value date** | The date on which funds affect interest/availability economics; may differ from posting date (backdated/forward-dated). |
| **Booking/posting timestamp** | Wall-clock instant the entry was committed to the ledger. |
| **Effective date** | Date a configuration (product version, fee plan, rate) takes effect. |
| **Business date** | The tenant's official banking day, advanced by day open/close — independent of server time. |
| **Settlement date** | Date an obligation with an external party is settled. |

## Balances (full semantics: [balance-semantics](../accounting/balance-semantics.md))

| Term | Definition |
|---|---|
| **Book balance** | Sum of all posted entries on a ledger balance (per its normal side). |
| **Available balance** | Funds usable now: book − holds − pending debits + authorized overdraft headroom (exact formula in spec). |
| **Cleared balance** | Book balance restricted to entries whose value date ≤ business date. |
| **Pending debit / pending credit** | Amounts from business transactions authorized but not yet posted. |
| **Held amount** | Sum of active holds (reservations) against an account. |
| **Hold** | A named, expiring reservation of available funds tied to a business transaction; not a posting. Captured (becomes postings), released, or expired. |
| **Overdraft limit** | Authorized negative headroom on the available-balance check for eligible products. |

## Accounts & parties

| Term | Definition |
|---|---|
| **Party** | A legal or natural person (or internal entity) that can own accounts or act: individual, organization, financial institution, merchant, agent, government entity, internal entity. |
| **Customer account** | The commercial contract (product, ownership, lifecycle, identifiers); distinct from its ledger balance(s). |
| **Internal account** | Institution-owned account (cash/vault, settlement, suspense, fee income, interest expense…), also mapped to ledger balances. |
| **Settlement account** | Internal account tracking positions with an external network/counterparty. |
| **Suspense account** | Internal account temporarily holding unmatched/in-transit value; must trend to zero; reconciled. |
| **Account number** | Human-readable identifier generated per configurable scheme; distinct from immutable internal ID. |
| **Signatory** | Party authorized to act on an account per mandate rules. |
| **Dormancy** | Product-policy-driven inactive state restricting operations until reactivation. |
| **Blocks** | Debit block, credit block, full block, freeze — enforced atomically at posting time. |

## Products & configuration

| Term | Definition |
|---|---|
| **Product** | Versioned definition of a banking offering (wallet, current account…) bundling currency, accounting mapping, policies, plans, and allowed operations. |
| **Product version** | Immutable snapshot of a product configuration with an effective range; active accounts/transactions reference the version in force. |
| **Fee plan / Limit plan / Interest (rate) plan** | Versioned, effective-dated configuration bundles referenced by product versions. |
| **Maker-checker** | Control requiring a change (maker) to be approved by a distinct authorized user (checker) before activation. |
| **Effective dating** | Configurations carry activation dates; behavior is selected by date, never by mutating history. |

## Platform & tenancy

| Term | Definition |
|---|---|
| **Tenant** | One institution's isolated data plane + configuration within Next Core. |
| **Control plane** | Vendor-side components managing tenant lifecycle/routing/entitlements; barred from financial data. |
| **Data plane** | Tenant-scoped application + database serving banking operations. |
| **Tenant context** | Explicit, validated per-request/job carrier of tenant identity used for routing and scoping. |
| **Deployment profile** | shared-saas / dedicated-saas / on-premise runtime configuration of the same artifacts. |
| **Idempotency key** | Client-supplied unique key scoping one logical financial request per (tenant, operation, client); guarantees at-most-once posting. |
| **Transactional outbox** | Pattern: events written in the same DB transaction as state, relayed after commit (at-least-once). |
| **Inbox / deduplication** | Consumer-side pattern discarding already-processed event deliveries. |
| **Correlation ID** | Identifier propagated across a request/job/event chain for tracing and audit. |

## Operations

| Term | Definition |
|---|---|
| **End of Day (EoD)** | The resumable, idempotent job pipeline run at business-day close (cutoffs, fees, accruals, statements, reconciliation, trial balance, checks). |
| **Reconciliation** | Matching internal records against external reports; producing matches, exceptions, and evidence; deterministic on re-run. |
| **Exception (recon)** | An unmatched or mismatched item requiring investigation/adjustment. |
| **Statement** | Periodic, product-rule-driven account activity document. |
| **Runbook** | Step-by-step operational procedure for a defined scenario. |
