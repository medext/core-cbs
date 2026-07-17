# Scope and Non-Scope

| | |
|---|---|
| **Purpose** | Authoritative statement of what Next Core does and does not include, to defend against scope creep and ambiguity. |
| **Audience** | Product, engineering, customers, auditors. |
| **Owning phase** | Phase 0 (updated at phase gates). |
| **Related** | [PRD](prd.md) · [Roadmap](roadmap.md) |

## In scope

### Financial core
- Immutable double-entry ledger, chart of accounts, GL accounts, customer subledger with GL
  mapping, posting rules, accounting periods, posting batches, balance projections with
  reconstruction, integrity verification.
- Transactional accounts: wallets, current accounts, savings accounts, internal, settlement,
  suspense, fee, and interest accounts. (Term deposits: Phase 8+; loan products: future
  bounded context, architecture reserved.)
- Business operations: internal transfer, cash deposit/withdrawal (via branch/agent internal
  accounts), account funding, merchant payment, fee collection, interest payment (Phase 8),
  settlement, refund, reversal, adjustment, holds (place/capture/release/expire), scheduled
  transfer, bulk payment, standing order (Phase 8).
- Pricing/fees, limits, interest & accruals (Phase 8), statements, trial balance.
- Reconciliation of external reports; business date & end-of-day processing.

### Platform
- Multi-tenant control plane (SaaS), dedicated SaaS profile, single-tenant on-premise profile
  (air-gap capable) — one codebase, one artifact set.
- External IAM integration (OAuth2/OIDC), RBAC(+ABAC), maker-checker.
- Audit evidence, signed webhooks, transactional outbox events.
- Versioned product/fee/limit/posting-rule/calendar configuration with
  draft→review→approve→activate workflow.
- Bank-grade versioned APIs (OpenAPI 3.1), Python SDK examples, API collections.
- Observability (OTel, Prometheus, structured logs), runbooks, backup/restore, upgrade/rollback.

## Out of scope (this product cycle)

| Area | Position |
|---|---|
| Lending (origination, servicing, schedules, provisioning) | Future bounded context; ledger/product architecture must not preclude it. |
| Card issuing/processing, PIN/HSM | Integration points only (holds + settlement + reconciliation). |
| Payment scheme connectivity (ISO 8583, ISO 20022, SWIFT, instant-payment rails) | Adapter/integration surface only; no in-core scheme stacks. |
| KYC/AML engines, sanctions screening, transaction monitoring | External systems; Next Core stores references and emits events. |
| FX trading/treasury | Only the FX bridge needed for multi-currency postings (depth: OD-4). |
| General ERP/corporate accounting | GL serves banking operations; not a general accounting package. |
| Customer-facing channels (mobile/web/USSD/agents apps) | API consumers, not part of core. |
| Regulatory report generation per jurisdiction | Data/extract surface provided; format packs are extensions (OD-2). |
| Built-in password authentication | Delegated to external IAM (ADR-0008). |

## Non-goals (permanent)

- Customer-specific source-code forks (prohibited; configurability instead).
- Microservices-first architecture (ADR-0001).
- Arbitrary tenant-supplied executable code.
- Compliance-certification claims without independent assessment.

## Change control

Moving an item across these lists requires: PRD update + open-decisions entry + human approval
at a phase gate (or an explicit interim decision), in the same change.
