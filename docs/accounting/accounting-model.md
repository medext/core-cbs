# Accounting Model

| | |
|---|---|
| **Purpose** | The institution-level accounting design: chart of accounts, subledger↔GL mapping, posting-rule model, periods, and the account↔ledger-balance mapping. |
| **Audience** | Engineering, financial controllers, auditors. |
| **Owning phase** | Phase 0 (design) → Phases 3–6 (implementation). |
| **Related** | [Ledger architecture](ledger-architecture.md) · [Balance semantics](balance-semantics.md) · [Chart of accounts](chart-of-accounts.md) · [Glossary](../domain/glossary.md) |

## Double-entry foundation

Every economic event is recorded as a journal entry of ≥2 postings that balances per
currency. Direction semantics follow classical rules driven by each account's **normal side**:

| Account type | Normal side | Debit means | Credit means |
|---|---|---|---|
| Asset (cash, nostro, receivables) | Debit | increase | decrease |
| Liability (customer deposits, payables) | Credit | decrease | increase |
| Income (fees, interest income) | Credit | decrease | increase |
| Expense (interest expense, losses) | Debit | increase | decrease |
| Equity | Credit | decrease | increase |

**Customer current/wallet/savings accounts are institution liabilities** — a customer credit
increases the institution's liability to that customer. This orientation is fixed and
non-configurable per account type; products declare their account type, which determines the
normal side.

## Chart of accounts

- Versioned per institution (tenant), hierarchical codes (e.g., `2xxx` liabilities →
  `2100 Customer deposits` → `2110 Wallets`), each GL account typed and sided.
- A **seed CoA** ships as configuration (Phase 10 demo institution); institutions adapt via
  the configuration workflow, never via code.
- Structure spec and seed content: [`chart-of-accounts.md`](chart-of-accounts.md) (skeleton,
  authored Phase 4/6).

## Subledger ↔ GL mapping

Customer-level ledger balances form the **subledger**. Each ledger balance maps to exactly
one GL account (via its product's accounting mapping). GL-level figures are aggregations:

```text
GL 2110 "Wallet deposits" book total = Σ book balances of all wallet LedgerBalances
```

Control equation (checked by integrity runs and trial balance): every GL account's derived
total equals the sum of its subledger balances; total debits = total credits across the CoA.

Internal accounts (vault cash, settlement, suspense, fee income, interest expense…) are
"subledger of one" — a single ledger balance mapped to its GL account.

## Account ↔ ledger-balance mapping

| Commercial concept (accounts context) | Accounting concept (ledger context) |
|---|---|
| Customer account `ACC-123` (contract, product, lifecycle, blocks) | 1..n `LedgerBalance` rows (store of value) |

- MVP: **one ledger balance per account** (single currency, single dimension).
- The model reserves multi-balance dimensions per account (e.g., principal vs. bonus wallet)
  — justified per product via ADR when needed.
- Mapping rows are created at account opening (with the opening journal entry if an initial
  funding exists) and are immutable once active; closure freezes but never deletes them.
- Account **status** (frozen, blocked…) lives in the accounts context and is enforced at
  posting time through the posting service's validation contract; it is not an accounting
  attribute.

## Posting rules

A **posting rule** declaratively maps (operation type, product version, parameters) → entry
spec(s):

```yaml
# Illustrative shape (final schema in Phase 6; executed subset from Phase 3)
rule: internal_transfer.v1
applies_to: operation=INTERNAL_TRANSFER
entries:
  - description: principal movement
    postings:
      - side: DEBIT,  balance: source.account_balance,   amount: $amount
      - side: CREDIT, balance: target.account_balance,   amount: $amount
  - description: sender fee (if fee_plan yields > 0)
    condition: $fee.total > 0
    postings:
      - side: DEBIT,  balance: source.account_balance,   amount: $fee.total
      - side: CREDIT, balance: gl:4100_fee_income,       amount: $fee.net
      - side: CREDIT, balance: gl:2400_tax_payable,      amount: $fee.tax
```

Properties: **declarative** (no arbitrary code — master prompt §13), versioned,
effective-dated, simulatable, deterministic (same inputs ⇒ same entries), reviewed via
maker-checker (Phase 6). Phase 3 implements the *execution* of a hardcoded-in-configuration
rule set; Phase 6 adds authoring/versioning workflow.

## Accounting periods & dates

- Periods (monthly default) per tenant: OPEN → CLOSING → CLOSED. Entries post only into OPEN
  periods; period close runs in EoD orchestration with trial-balance validation.
- **Backdated business events** (late-arriving external items): posted into the current OPEN
  period with `value_date` in the past — never into a CLOSED period. Interest/eligibility
  computations use value dates; period totals use posting period. This is the standard
  correction-friendly compromise; documented consequence: period totals reflect posting date,
  value-dated reports reflect economics.
- Date fields recap (full semantics in [balance-semantics](balance-semantics.md)):
  `business_date` (tenant day), `value_date` (economic effect), `posted_at` (commit instant),
  `created_at` (record creation).

## Standard flows (MVP examples, same-currency)

**Cash deposit at branch/agent** (customer funds wallet):
```text
DEBIT  1010 Vault cash (asset ↑)               100.00
CREDIT 2110 Customer wallet liability (↑)      100.00
```

**Internal transfer A→B with sender fee 1.00 (tax 0.10):**
```text
Entry 1: DEBIT  2110 Wallet A   100.00 | CREDIT 2110 Wallet B  100.00
Entry 2: DEBIT  2110 Wallet A     1.00 | CREDIT 4100 Fee income  0.90
                                        | CREDIT 2400 Tax payable 0.10
```

**Hold capture (merchant payment 50.00):** hold is not an entry; capture posts:
```text
DEBIT 2110 Customer wallet  50.00 | CREDIT 2120 Merchant wallet 50.00
```

**Reversal of Entry X:** mirror entry with directions flipped, `reversal_of = X`.

**Suspense usage (unmatched inbound settlement):**
```text
On receipt: DEBIT 1210 Settlement account | CREDIT 2900 Suspense
On match:   DEBIT 2900 Suspense           | CREDIT 2110 Customer wallet
```
Suspense balances trend to zero; aged items are reconciliation exceptions.

## Interest & accrual accounting (architecture reserved, Phase 8)

Daily accrual: `DEBIT 5100 Interest expense / CREDIT 2130 Accrued interest payable`;
capitalization: `DEBIT 2130 / CREDIT 2110 customer balance`; withholding at capitalization:
`CREDIT 2410 WHT payable`. Retroactive rate corrections: compensating entries only
(invariant 7). Day-count, rounding, and tiering plans per product version.

## Trial balance & reporting

Trial balance derives strictly from postings per period: per GL account (debit total, credit
total, net per normal side); asserts global balance and subledger↔GL control equations.
Operational reports read projections but reconcile against postings (integrity runs).
