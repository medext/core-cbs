# Chart of Accounts Model & Seed

| | |
|---|---|
| **Purpose** | CoA structure specification and the seed chart shipped with the demo institution. |
| **Owning phase** | Phase 4 (structure with products) · Phase 6/10 (seed + configuration workflow). Structure and seed authored in the MVP track 2026-11-25. |
| **Related** | [Accounting model](accounting-model.md) · [Ledger architecture](ledger-architecture.md) |

## Fixed positions (from the accounting model)

Versioned per tenant; hierarchical codes; every GL account typed
(ASSET/LIABILITY/INCOME/EXPENSE/EQUITY) with fixed normal side; customer products map
subledger balances to GL accounts; institutions adapt via configuration workflow
(maker-checker), never code.

## Structure (as built)

- Table `ledger_gl_account` per tenant database: `code` (≤ 20 chars, unique per tenant),
  `name`, `type` (ASSET/LIABILITY/EQUITY/INCOME/EXPENSE), `normal_side` (CHECK-bound to the
  type), `parent_code` (hierarchy for roll-ups), `is_active`.
- Code scheme of the seed: 4 digits; first digit = class (1 assets, 2 liabilities, 3 equity,
  4 income, 5 expenses); `x000` codes are class headers.
- GL accounts are created idempotently (`ensure_gl_accounts`), never deleted once referenced
  (ledger balances reference them with `PROTECT`); retirement = `is_active = false`.
- **Product mapping**: each product version's `gl_mapping` names GL codes per role —
  `principal`, `cash`, `fee_income`, `tax_payable`, and optionally `accrued_interest`,
  `interest_expense`, `interest_income` ([product engine](../products/product-engine.md)).
  At approval every mapped code must exist and be active; `principal` must be a LIABILITY
  account for deposit products and an ASSET account for lending products.
- Customer accounts form the subledger (one ledger balance per account, purpose and currency);
  internal accounts are one balance per (GL, currency).
- CoA versioning/effective dating and a maker-checker workflow for GL changes are **not built**
  (GL accounts are seeded by `bootstrap_tenant`).

## Seed chart (`products/catalog.py` → `SEED_COA`, installed by `bootstrap_tenant`)

| Code | Name | Type | Parent | Used by seed products as |
|---|---|---|---|---|
| 1000 | Assets | ASSET | — | header |
| 1010 | Vault cash | ASSET | 1000 | `cash` (all) |
| 1210 | Settlement account | ASSET | 1000 | — (reserved) |
| 1300 | Loans to customers | ASSET | 1000 | PERSONAL_LOAN `principal` |
| 1310 | Accrued interest receivable | ASSET | 1000 | PERSONAL_LOAN `accrued_interest` |
| 2000 | Liabilities | LIABILITY | — | header |
| 2110 | Current accounts | LIABILITY | 2000 | CURRENT `principal` |
| 2120 | Savings deposits | LIABILITY | 2000 | SAVINGS `principal` |
| 2130 | Term deposits | LIABILITY | 2000 | TERM_DEPOSIT `principal` |
| 2140 | E-money wallets | LIABILITY | 2000 | WALLET `principal` |
| 2150 | Accrued interest payable | LIABILITY | 2000 | SAVINGS, TERM_DEPOSIT `accrued_interest` |
| 2400 | Tax payable | LIABILITY | 2000 | `tax_payable` (all) |
| 2900 | Suspense | LIABILITY | 2000 | — (reserved, reconciliation) |
| 3100 | Share capital | EQUITY | — | — |
| 4100 | Fee income | INCOME | — | `fee_income` (all) |
| 4200 | Interest income | INCOME | — | PERSONAL_LOAN `interest_income` |
| 5100 | Interest expense | EXPENSE | — | SAVINGS, TERM_DEPOSIT `interest_expense` |

## Control equations

Implemented as checks in `verify_ledger` (projection = reconstruction; per-currency global
debit = credit) and the trial balance endpoint. Formal period-based trial balance and
subledger↔GL control reports: Phase 7.

## Still to author

CoA versioning & effective dating, GL change maker-checker workflow (Phase 6 follow-up),
period-based control equations (Phase 7).
