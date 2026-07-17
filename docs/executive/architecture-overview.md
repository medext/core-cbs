# Executive Architecture Overview

| | |
|---|---|
| **Purpose** | The 10-minute read: what Next Core is, how it is built, and why. |
| **Audience** | Executives, new team members, prospective customers' architects. |
| **Owning phase** | Phase 0 (kept current at every gate). |
| **Related** | [PRD](../product/prd.md) · [Phase 0 review](phase0-review.md) · [C4 diagrams](../architecture/c4-diagrams.md) |

## What it is

Next Core is a bank-grade core banking system: the system of record for customer accounts,
balances, and financial transactions of regulated institutions. One codebase ships three
editions — shared SaaS, dedicated SaaS, and on-premise (air-gap capable). Institutions
configure products, fees, limits, and posting rules; they never fork the code.

## The five load-bearing decisions

1. **Modular monolith, not microservices** *(ADR-0001)* — financial invariants (balanced
   entries, atomic funds checks) live inside single PostgreSQL transactions. Strict bounded
   contexts with enforced import rules keep future extraction possible without betting the
   ledger on distributed consistency.

2. **PostgreSQL is the only financial authority** *(ADR-0003)* — journal entries, postings,
   balances, transaction state, idempotency, audit, and outbox all commit atomically in one
   store, protected by constraints and grants, not just application code. Redis only ever
   accelerates; it never decides.

3. **An immutable double-entry ledger at the kernel** — append-only journal entries and
   postings (UPDATE/DELETE revoked at the database level); balances are projections that are
   continuously reconciled against, and reconstructable from, the posting history.
   Corrections are linked reversals — history is never edited. 25 explicit invariants each
   map to domain checks, database constraints, dedicated test suites, and monitoring
   ([enforcement matrix](../accounting/invariants.md)).

4. **Database-per-tenant isolation** *(ADR-0005)* — each institution's financial data lives
   in its own database with its own keys, backups, and residency options. The vendor control
   plane manages tenants but holds no path to financial data. On-premise is simply the
   single-tenant special case with the control plane absent — not a fork.

5. **Bank-grade write semantics** *(ADR-0006/0007)* — every financial API write is
   idempotent (database-arbitrated keys, payload-hash conflict detection, response replay);
   concurrency safety comes from deterministic row locking inside the posting transaction,
   proven by a hostile concurrency test suite (double spends, races, ambiguous retries) that
   gates every ledger release. Events publish only after commit, via transactional outbox.

## What sits around the kernel

Business transactions (transfers, deposits, holds, fees, reversals) are orchestrated
separately from accounting and traced to the journal entries they produce, through
declarative, versioned **posting rules**. Products, fee plans, and limit plans are versioned
configuration with draft→review→approve→activate workflow and maker-checker controls.
Operations get first-class treatment: per-tenant business dates, idempotent resumable
end-of-day, reconciliation with deterministic re-runs, trial balance, statements, signed
webhooks, and full audit evidence. Identity is delegated to external OIDC providers
(Keycloak reference); authorization — tenant-scoped RBAC, object-level checks,
maker-checker — lives in the product *(ADR-0008)*.

## How it is being built

Ten phases with hard acceptance gates ([roadmap](../product/roadmap.md)): foundation →
tenancy & audit → **ledger kernel** → accounts & products → transfers/holds/fees/limits
(MVP) → configurability → reconciliation & EoD → interest → hardening → reference
deployments. Development runs through Claude Code under a strict operating system of rules,
specialized reviewers, and guard hooks ([development workflow](../product/development-workflow.md));
every phase gate requires executed evidence and explicit human approval. Documentation is
part of the Definition of Done — these documents are contractually kept in sync with the
implementation.

## Where we are

Phase 0 is complete: this blueprint, the PRD, eight foundational ADRs, the BLNK-inspired
ledger design, the threat model, and the full development operating system are in the
repository, awaiting human approval ([Phase 0 review](phase0-review.md)). No production code
exists yet — by design.
