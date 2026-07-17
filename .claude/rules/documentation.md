# Rules — Documentation (`docs/`)

## Same-change rule

Documentation is part of the product and part of the Definition of Done. Any change that
alters behavior, schema, API, configuration, or operations updates the corresponding docs
**in the same commit/PR** — never "later". Architecture documents that do not match the
implementation are prohibited; when you find drift, fixing the doc is part of the current task.

## Where things go

- `docs/decisions/adr/` — one ADR per significant decision, numbered sequentially
  (`NNNN-slug.md`), using the template in that directory. Use the `/new-adr` command.
  An accepted ADR is immutable; changes of direction are a new ADR that supersedes it.
- `docs/decisions/open-decisions.md` — every assumption you introduce while working must be
  registered here with its label (Confirmed / Recommended / Assumption / Open / Deferred).
- `docs/accounting/` owns ledger semantics; `docs/domain/glossary.md` owns terminology.
- Skeleton docs contain per-section guidance comments — replace guidance with content in the
  owning phase; do not delete the structure.

## Style

- English. Precise banking vocabulary from the glossary — never use bare "balance" without the
  qualified term (book/available/cleared…). If a needed term is missing, add it to the glossary
  in the same change.
- Diagrams as Mermaid in Markdown (C4 style for architecture). Keep diagrams next to the text
  that explains them, and update them with the code.
- State facts that were verified, assumptions as assumptions. No aspirational claims
  ("fully secure", "infinitely scalable") and no compliance claims.
- Each doc starts with: purpose, audience, owning phase, related ADRs.

## Review

Run the `documentation-reviewer` subagent when completing a phase gate or any large feature,
to verify doc/code consistency and the same-change rule.
