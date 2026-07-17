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
