---
description: Run the acceptance-gate checklist for the current (or given) implementation phase and produce a gate report for human approval.
---

Run the phase acceptance gate. Phase: $ARGUMENTS (if empty, determine the current phase from
`docs/product/roadmap.md`).

Procedure:

1. Open `docs/product/roadmap.md` and extract the acceptance-gate checklist for the phase.
2. For every gate item, gather **executed evidence** — run the actual commands (tests, lint,
   type checks, docs build, targeted verification scripts) and capture results. An item
   without executed evidence is NOT-VERIFIED, never assumed.
3. Run the relevant review subagents for the phase and include their verdicts:
   - Ledger-touching phases (3, 5, 6, 7, 8): `ledger-accounting-reviewer` +
     `postgres-concurrency-reviewer`.
   - Tenancy/IAM phases (2+): `security-reviewer`.
   - Every gate: `documentation-reviewer` (same-change rule + drift check).
4. Check cross-cutting gate conditions that apply to every phase:
   - No failing tests, type errors, or lint errors anywhere in the repo.
   - No secrets in the repository.
   - `docs/decisions/open-decisions.md` is current (no unregistered assumptions).
   - All ADRs affected by the phase are Accepted and consistent with the implementation.
5. Produce the **Gate Report**:
   - Phase and objective.
   - Checklist table: item / status (PASS, FAIL, NOT-VERIFIED) / evidence (command + result).
   - Subagent verdicts with unresolved findings.
   - Known risks and technical debt carried forward.
   - Explicit recommendation: READY FOR APPROVAL or NOT READY (with the blocking list).
6. **STOP.** Present the report and request explicit human approval. Do not begin the next
   phase, and do not mark the gate passed, without that approval. Record the approval
   (date + approver) in `docs/product/roadmap.md` when granted.
