---
description: Scaffold a new Architecture Decision Record with the correct number, template, and register updates.
---

Create a new ADR for the decision: $ARGUMENTS

Procedure:

1. List `docs/decisions/adr/` and determine the next sequential number `NNNN`.
2. Derive a short kebab-case slug from the decision topic.
3. Create `docs/decisions/adr/NNNN-slug.md` from the template
   (`docs/decisions/adr/0000-template.md`) with ALL sections filled:
   - **Status**: start as `Proposed` (only a human review moves it to `Accepted`).
   - **Context**: the problem, forces, and constraints — including the banking/regulatory
     angle where relevant.
   - **Decision**: the choice, stated actively and precisely.
   - **Alternatives considered**: each with why it was rejected (real reasons, not straw men).
   - **Consequences**: positive, negative, and neutral — including operational and on-premise
     impact, and what becomes harder.
   - **Compliance/security impact** and **Reversibility** (what a future reversal would cost).
4. If this ADR supersedes an earlier one: set `Supersedes: ADR-XXXX` here, and add
   `Superseded-by: ADR-NNNN` to the old ADR's status line — do not otherwise edit the old ADR.
5. Update the ADR index table in `docs/decisions/adr/README.md`.
6. If the decision resolves an entry in `docs/decisions/open-decisions.md`, update that entry's
   label and link it to the new ADR.
7. Present the ADR for review. Remind: it stays `Proposed` until a human accepts it, and once
   `Accepted` it becomes immutable.
