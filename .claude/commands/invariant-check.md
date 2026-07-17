---
description: Review the current diff (or a given path) against the 25 accounting invariants and report an enforcement-evidence table.
---

Perform an accounting-invariant review of: $ARGUMENTS (if empty, use the current uncommitted
diff plus any commits on this branch not yet reviewed).

Procedure:

1. Read `docs/accounting/invariants.md` — the authoritative list of 25 invariants and their
   required enforcement layers (domain validation, DB constraint, unit test, property test,
   integration test, concurrency test, monitoring).
2. Identify which invariants are in scope for this change (any change touching money, postings,
   balances, transaction state, idempotency, tenancy of financial data, or events is in scope
   for several).
3. For each in-scope invariant, verify EVERY required enforcement layer and cite evidence
   (file:line for code/constraints, test path + executed result for tests). Run targeted tests
   where cheap; otherwise mark the layer NOT-VERIFIED.
4. Delegate deep review to `ledger-accounting-reviewer` and, if concurrent write paths are
   involved, `postgres-concurrency-reviewer`; reconcile their findings into one table.
5. Output the **Invariant Report**:
   | # | Invariant | In scope? | Domain | DB constraint | Tests | Monitoring | Status |
   with status PASS / FAIL / PARTIAL / NOT-VERIFIED per row, followed by findings ordered by
   severity.
6. If ANY invariant is FAIL: stop the current work, do not merge, do not proceed to other
   tasks — report the failure prominently and propose the remediation plan. An invariant
   failure is never downgraded, deferred, or worked around.
