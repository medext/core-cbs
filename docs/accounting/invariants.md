# Accounting Invariants — Enforcement Matrix

| | |
|---|---|
| **Purpose** | The 25 non-negotiable invariants and, for each, every layer that enforces it. This is the checklist behind `/invariant-check` and the ledger reviewers. |
| **Audience** | Engineering, reviewers, auditors. |
| **Owning phase** | Phase 0 (matrix) → each enforcement lands in its listed phase. |
| **Related** | [Ledger architecture](ledger-architecture.md) · `.claude/rules/ledger.md` · `.claude/commands/invariant-check.md` |

**Legend — enforcement layers:** `DOM` domain validation · `DB` database constraint/grant ·
`UT` unit test · `PT` property-based test · `IT` integration test (real PostgreSQL) ·
`CT` concurrency test · `MON` operational monitoring. Phase = where enforcement is first
implemented. An invariant is "enforced" only when **all** listed layers exist and pass.

| # | Invariant | Enforcement | Phase |
|---|---|---|---|
| 1 | Every posted journal entry is balanced. | DOM entry validation; DB deferred trigger Σdebit=Σcredit per (entry,currency); UT; PT (random entries); IT (trigger fires on bad direct SQL) | 3 |
| 2 | Per currency, debit and credit totals are equal unless an explicitly modeled FX bridge/clearing is used. | DOM per-currency check; FX ops must reference bridge accounts + rate ref; DB trigger is per-currency; PT | 3 |
| 3 | Financial amounts never use binary floating point. | DOM Money type (int minor units, ADR-0004); lint rule banning float/FloatField in financial modules; UT; code review | 3 |
| 4 | Storage representation of money is defined through an ADR. | ADR-0004 accepted before Phase 3 code; schema review against it | 0/3 |
| 5 | Ledger postings are immutable after commit. | DOM no update API; DB: UPDATE/DELETE revoked on posting/entry tables for app role; IT (revocation verified); hook/review ban on raw writes | 3 |
| 6 | Journal entries are never edited to correct an error. | Same as 5 + process rule; audit of any privileged-role DDL/DML (MON) | 3 |
| 7 | Corrections use reversal or compensating entries. | DOM reversal API is the only correction path; UT; PT (reversal restores position) | 3 |
| 8 | Balances cannot be manually overwritten. | DOM: only posting service mutates projections; DB: balance UPDATE limited to posting-path role (OD-14) ; IT; API contract test (no mutation endpoint) | 3 |
| 9 | Authoritative balances can be reconstructed from postings. | Reconstruction command; PT (projection == rebuild); scheduled MON job | 3 |
| 10 | Balance projections must reconcile with posting history. | Integrity runs + findings; MON alert on mismatch; EoD check | 3/7 |
| 11 | A financial request cannot be posted twice because of retries. | DOM idempotency gate in posting transaction; DB UNIQUE (tenant,scope,key); CT (concurrent duplicates); ambiguous-retry CT | 3 |
| 12 | An idempotency key reused with a different payload conflicts. | DOM request-hash compare → 409; UT; contract test | 3 |
| 13 | Transactions either commit completely or not at all. | Single DB transaction for the whole posting write path; IT (fault injection mid-path ⇒ nothing persisted) | 3 |
| 14 | Cross-tenant financial access is impossible. | Tenant routing + scoped managers (DOM); DB-per-tenant physical isolation (ADR-0005); cross-tenant test suite (IT) at every gate; MON isolation checks | 2 |
| 15 | Every financial operation has a traceable business source. | DOM: entry requires source ref; DB NOT NULL + FK; IT | 3 |
| 16 | Every posting includes currency and accounting direction. | DB NOT NULL + CHECK direction; DOM Money carries currency; UT | 3 |
| 17 | Every account has a defined normal balance behavior. | DB NOT NULL normal_side on GL account & ledger balance; DOM typed account types; UT | 3 |
| 18 | Available funds cannot be overspent under concurrency unless an authorized overdraft rule permits it. | DOM funds check under row lock; DB CHECK available floor per overdraft policy (backstop, design in Phase 3); CT double-spend suite | 3/5 |
| 19 | Reversals preserve the complete relationship to the original. | DB FK reversal_of + bidirectional query; DOM; UT; contract test exposes links | 3 |
| 20 | Account closure cannot destroy historical records. | DOM closure state machine (no deletes); DB no-cascade FKs; IT (close then full history retrievable) | 4 |
| 21 | Product configuration changes do not rewrite historical transaction behavior. | Immutable product versions (DOM+DB); transactions FK the version in force; IT | 4/6 |
| 22 | End-of-day jobs are idempotent and resumable. | Step framework with persisted checkpoints (DOM); kill-and-resume IT/CT; MON EoD duration/failures | 7 |
| 23 | Database constraints must support application-level checks. | Design rule: every DOM financial check has a DB backstop where expressible; schema review item in `/invariant-check` | 3+ |
| 24 | Financial integrity must not depend solely on application code. | Same as 23 + grants (5,8) + integrity runs (10) | 3+ |
| 25 | Events are published only after the authoritative database commit succeeds. | Transactional outbox (ADR-0007): event row in same tx, relay post-commit; IT (rollback ⇒ no event; crash between commit and relay ⇒ eventual delivery); MON outbox lag | 3 |

## Working rules

1. **A FAIL on any invariant is a stop-the-line event**: halt the slice, report prominently,
   remediate before anything else. Never downgrade, defer, or merge around it.
2. Any new financial feature must state, in its change report, which invariants it touches
   and point to the evidence per layer (this matrix's row is the contract).
3. Weakening any listed enforcement (dropping a constraint, skipping a CT) requires an ADR
   plus explicit human approval — treat as invariant-affecting.
4. Monitoring hooks (MON column) become alert definitions in Phase 9; until then the
   commands exist and are run at every phase gate.

## Evidence (MVP track, 2026-11-25)

Status per invariant after the compressed Phases 3–6 build. "Enforced" = every listed layer
exists; "Partial" names the missing layer. Test files: `IT-L` =
`tests/integration/test_ledger_kernel.py`, `IT-F` = `tests/integration/test_banking_flows.py`,
`E2E` = `tests/e2e/test_api_flows.py`, `CT` = `tests/concurrency/test_financial_races.py`,
`PT-L` = `tests/property/test_ledger_properties.py`, `PT-M` =
`tests/property/test_money_and_fees.py`, `UT-X` = `tests/unit/test_expressions.py`, `CON` =
`tests/contract/test_contracts.py`. Reviewer verdicts and human gate approval are pending.

| # | Enforcing code | Tests | Status |
|---|---|---|---|
| 1 | `ledger.domain.validate_entry`; deferred triggers `ledger_entry_balanced_*` | IT-L (domain + raw-SQL unbalanced entry), PT-L | Enforced |
| 2 | Per-currency check in domain and trigger; cross-currency refused (`CURRENCY_MISMATCH`) | IT-L, IT-F | Enforced (FX bridge not built — OD-38) |
| 3 | `platform.money.Money` rejects non-int; Decimal-only rates; expressions build Decimals from source text | PT-M, UT-X, CON (no `float(`/`FloatField` in financial modules) | Enforced |
| 4 | ADR-0004; BIGINT minor units everywhere | schema review | Enforced |
| 5 | Model-level append-only guards; triggers `*_append_only`, writer flag | IT-L | Enforced (grant-level revocation OD-14 not done) |
| 6 | Same as 5; corrections only via reversal API | IT-L | Enforced (privileged DML monitoring: Phase 9) |
| 7 | `reversal_specs` mirror entries; `POST /transactions/{id}/reversal` | IT-L, IT-F, E2E, PT-L | Enforced |
| 8 | Writer-flag + `ledger_balance_guard` trigger; no balance-write endpoint | IT-L, E2E, CON | Enforced |
| 9 | `verify_ledger` reconstruction | IT-L, PT-L, E2E | Enforced |
| 10 | `verify_ledger` findings persisted + `integrity.mismatch` event | IT-L | Partial — command/API only; no scheduled monitor/alert (MON, Phase 9) |
| 11 | Idempotency record inserted in the posting transaction (`INSERT … ON CONFLICT`); unique (source, purpose) on entries | E2E, CT | Enforced |
| 12 | Request-hash compare → `409 IDEMPOTENCY_CONFLICT` | E2E, CT | Enforced |
| 13 | One DB transaction per operation; savepoint rollback on rejection | IT-L, IT-F | Enforced (explicit fault-injection test: follow-up) |
| 14 | Tenant routing + scoped managers (Phase 2) on all new models | E2E (cross-tenant), Phase 2 suites | Enforced |
| 15 | `source_type`/`source_id` NOT NULL on entries; every entry from a business transaction | IT-L | Enforced (no FK to the transactions table — cross-context id reference by design) |
| 16 | Posting CHECKs + `ledger_posting_currency` trigger | IT-L | Enforced |
| 17 | `normal_side` NOT NULL + CHECK by GL type; copied to balances | IT-L | Enforced |
| 18 | Funds check under row lock + `ledger_balance_guard` floor | IT-L, IT-F, CT | Enforced |
| 19 | OneToOne `reversal_of` (entry and business transaction); `reversed_by` exposed | IT-L, E2E | Enforced |
| 20 | Closure state machine; `account_guard` trigger (no delete, no reopen); history append-only | IT-F, E2E | Enforced |
| 21 | Accounts pinned to `product_version_id` (immutable by trigger); `product_version_guard` | E2E | Enforced |
| 22 | EoD steps (hold expiry, interest) idempotent via deterministic ids, one transaction per account | IT-F, E2E | **Partial** — no persisted step framework / kill-and-resume test (Phase 7) |
| 23 | Every domain check above has a DB backstop where expressible | review | Enforced for ledger, products, accounts; limits rely on row locks + CHECK ≥ 0 |
| 24 | Triggers + integrity runs | IT-L | Enforced (grant separation OD-14 pending) |
| 25 | `outbox.emit` refuses outside a transaction; rows commit with the state change | IT-L, E2E | Enforced (HTTP delivery deferred — OD-30) |

Period-related enforcement (posting only into OPEN periods, `PERIOD_CLOSED`) is **deferred**
to Phase 7 (OD-29).
