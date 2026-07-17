---
description: Drive one implementation task through the mandatory 19-step vertical-slice working method (master prompt §19).
---

Execute the following working method for the task: $ARGUMENTS

Work through ALL steps in order. Do not skip steps; do not report success without executed,
inspected commands.

1. **Inspect** — Read the current repository state and the documentation relevant to this task
   (`docs/product/roadmap.md` for current phase, the owning context docs, related ADRs).
2. **Restate** — Restate the objective of this slice in one paragraph, tied to the current
   phase objective.
3. **Contexts** — Identify the impacted bounded contexts (see `docs/domain/domain-model.md`)
   and confirm the change respects their ownership rules.
4. **Assumptions** — List assumptions; register new ones in
   `docs/decisions/open-decisions.md` with the correct label.
5. **Slice** — Propose the smallest safe vertical slice that delivers verifiable value.
6. **Risks** — Identify financial and security risks specific to this slice (double-posting,
   race windows, tenant leakage, authz gaps…).
7. **Acceptance** — Define concrete acceptance criteria.
8. **Tests first** — Define the tests (use the `test-engineer` subagent in design mode for
   financially significant slices) before or alongside implementation.
9. **Plan** — Present the file-level implementation plan.
10. **Implement** — In small coherent changes, respecting `.claude/rules/` for each touched
    path.
11. **Targeted tests** — Run targeted tests after each meaningful change; show results.
12. **Quality gate** — Run the complete relevant gate (`make check` or the phase's subset);
    show results.
13. **Migrations review** — If migrations changed: review against `.claude/rules/migrations.md`.
14. **Authz & tenancy review** — Verify authorization and tenant isolation for every new
    access path; run `security-reviewer` if in scope.
15. **Invariants review** — Run `ledger-accounting-reviewer` (and
    `postgres-concurrency-reviewer` for concurrent write paths) if any financial state is
    touched; resolve or escalate all blockers.
16. **Docs** — Update documentation in this same change (same-change rule).
17. **Report** — Produce a concise change report: what changed, evidence of verification,
    doc updates.
18. **Debt** — List remaining risks and technical debt created or discovered.
19. **Gate check** — If this slice completes a phase gate item, update the gate checklist;
    if the gate requires human approval, STOP and request it explicitly.
