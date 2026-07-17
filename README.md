# Next Core — Bank-Grade Lightweight Core Banking System

**Status: Phase 0 — Architecture Blueprint (awaiting human approval before implementation)**

Next Core is a modern, lightweight, bank-grade Core Banking System designed as real financial
infrastructure — not a prototype. It targets regulated banks, electronic money institutions,
fintechs, government institutions, and financial service providers, deployable as multi-tenant
SaaS, dedicated SaaS, or on-premise (including air-gapped) from **one common codebase**.

Correctness, accounting integrity, traceability, tenant isolation, operability, maintainability,
and security take precedence over implementation speed.

## What is in this repository right now

This repository contains the **Phase 0 deliverables only**: the Product Requirements Document,
the complete architecture blueprint, decision records, and the Claude Code project configuration
that governs how the system will be built. **No production code exists yet, by design** — the
project's working method requires explicit human approval of the Phase 0 architecture before
any implementation begins.

## Start here

| If you are… | Read |
|---|---|
| Anyone new to the project | [`docs/executive/architecture-overview.md`](docs/executive/architecture-overview.md) |
| Reviewing / approving Phase 0 | [`docs/executive/phase0-review.md`](docs/executive/phase0-review.md) |
| Looking for the PRD | [`docs/product/prd.md`](docs/product/prd.md) |
| Planning the build | [`docs/product/roadmap.md`](docs/product/roadmap.md) + [`docs/product/development-workflow.md`](docs/product/development-workflow.md) |
| An engineer starting Phase 1+ | [`CLAUDE.md`](CLAUDE.md), then [`docs/architecture/repository-structure.md`](docs/architecture/repository-structure.md) |
| Interested in the ledger design | [`docs/accounting/ledger-architecture.md`](docs/accounting/ledger-architecture.md) |

## Documentation map

```text
docs/
  executive/      Architecture overview, Phase 0 review summary
  product/        PRD, scope, roadmap & acceptance gates, development workflow, capacity model
  architecture/   C4 diagrams, tenancy & deployment, idempotency & concurrency, repo structure
  domain/         Glossary, domain model & bounded contexts, transaction lifecycle
  accounting/     Ledger architecture, accounting model, invariants, balance semantics, CoA
  api/            API standards, error catalog (skeleton — Phase 3+)
  events/         Event & webhook standards (skeleton — Phase 3+)
  security/       Threat model, security architecture, authorization matrix, control readiness
  deployment/     SaaS / dedicated / on-premise / air-gapped guides (skeleton — Phase 9+)
  operations/     Observability & operations (skeleton — Phase 9+)
  runbooks/       Operational runbooks (skeleton — Phase 9+)
  testing/        Test strategy
  migrations/     Data & schema migration strategy (skeleton — Phase 1+)
  decisions/      ADRs, BLNK adoption matrix, open-decisions register
```

Documents marked *(skeleton)* have their structure and per-section guidance in place; content is
authored in the phase that owns them. **Documentation is part of the Definition of Done** and is
updated in the same change as the code it describes.

## Technology position (summary — see ADRs for rationale)

- **Modular monolith first** with strict bounded contexts ([ADR-0001](docs/decisions/adr/0001-modular-monolith.md))
- **Python / Django / Django REST Framework** as the primary framework ([ADR-0002](docs/decisions/adr/0002-django-primary-framework.md))
- **PostgreSQL** as the sole authority for all financial state ([ADR-0003](docs/decisions/adr/0003-postgresql-authority.md))
- **Integer minor units** for money — never floating point ([ADR-0004](docs/decisions/adr/0004-money-representation.md))
- **Database-per-tenant** isolation for regulated financial data ([ADR-0005](docs/decisions/adr/0005-multi-tenancy-model.md))
- External IAM (Keycloak reference implementation), OAuth 2.0 / OIDC ([ADR-0008](docs/decisions/adr/0008-external-iam.md))

## Implementation phases

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Architecture blueprint & PRD | ✅ This repository — **awaiting approval** |
| 1 | Repository & engineering foundation | Blocked on Phase 0 gate |
| 2 | Tenancy, IAM & audit foundation | — |
| 3 | Ledger kernel | — |
| 4 | Parties, products & customer accounts | — |
| 5 | Transfers, holds, fees & limits | — |
| 6 | Posting rules & product configurability | — |
| 7 | Reconciliation & business-day operations | — |
| 8 | Interest & advanced account capabilities | — |
| 9 | Production hardening | — |
| 10 | Reference deployments & release candidate | — |

Each phase ends at an explicit **acceptance gate** requiring human review. See
[`docs/product/roadmap.md`](docs/product/roadmap.md).

## How this project is developed

This project is developed with Claude Code following a strict, gated working method described in
[`docs/product/development-workflow.md`](docs/product/development-workflow.md). Project-wide rules
live in [`CLAUDE.md`](CLAUDE.md); context-specific rules in [`.claude/rules/`](.claude/rules/);
specialized review subagents in [`.claude/agents/`](.claude/agents/); workflow commands in
[`.claude/commands/`](.claude/commands/).

## License

Proprietary — all rights reserved (to be finalized; see open-decisions register).
