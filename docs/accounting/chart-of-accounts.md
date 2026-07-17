# Chart of Accounts Model & Seed *(skeleton — authored Phases 4–6)*

| | |
|---|---|
| **Purpose** | CoA structure specification and the seed chart shipped with the demo institution. |
| **Owning phase** | Phase 4 (structure with products) · Phase 6/10 (seed + configuration workflow). |
| **Related** | [Accounting model](accounting-model.md) · [Ledger architecture](ledger-architecture.md) |

## Fixed positions (from the accounting model)

Versioned per tenant; hierarchical codes; every GL account typed
(ASSET/LIABILITY/INCOME/EXPENSE/EQUITY) with fixed normal side; customer products map
subledger balances to GL accounts; institutions adapt via configuration workflow
(maker-checker), never code.

## To author

1. **Structure spec** *(Phase 4)* — code scheme & depth, account classes, mapping rules
   (product → GL accounts per role: principal/fee/tax/interest/suspense), lifecycle of GL
   accounts (add/retire, never delete with history), CoA versioning & effective dating.
2. **Seed CoA** *(Phase 6/10)* — the demo institution chart: 1xxx assets (vault, settlement,
   nostro), 2xxx liabilities (customer products, suspense, accrued interest, tax payable),
   4xxx income (fees, interest income), 5xxx expenses (interest expense, losses) — with the
   product-mapping table used by the seed catalog.
3. **Control equations** *(Phase 7)* — subledger↔GL checks and trial-balance derivation as
   implemented.
