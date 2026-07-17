# Next Core — Product Requirements Document (PRD)

| | |
|---|---|
| **Purpose** | Define what Next Core is, for whom, what it must do, and the constraints under which it is built. |
| **Audience** | Founders, product, engineering, prospective institutional customers, auditors. |
| **Owning phase** | Phase 0 (living document; updated at every phase gate). |
| **Status** | v1.0 — Phase 0 baseline, awaiting approval. |
| **Related** | [Scope](scope.md) · [Roadmap](roadmap.md) · [Architecture overview](../executive/architecture-overview.md) · [ADR index](../decisions/adr/README.md) |

---

## 1. Vision

**Next Core is a modern, lightweight, bank-grade core banking system**: the authoritative
system of record for accounts, balances, and financial transactions of a regulated financial
institution. It provides an immutable double-entry ledger, configurable banking products,
and bank-grade APIs — deployable as multi-tenant SaaS, dedicated SaaS, or fully on-premise
(including air-gapped) **from a single codebase**.

It is comparable in architectural ambition — not initial feature breadth — to Mambu and
Thought Machine, and takes ledger-design inspiration from BLNK
(see [BLNK adoption matrix](../decisions/blnk-adoption-matrix.md)), extended with real
core-banking constructs: products, chart of accounts, posting rules, holds, limits, fees,
value dates, business dates, accounting periods, end-of-day, reconciliation, statements, and
maker-checker controls.

**Design priorities, in order:** correctness → accounting integrity → traceability → tenant
isolation → security → operability → maintainability → feature breadth → speed of delivery.

### What Next Core is NOT

- Not a mobile/web banking front-end (it powers them through APIs).
- Not a payment switch, card processor, or scheme connector (it integrates with them).
- Not a KYC/AML engine (it references external KYC and exposes hooks).
- Not a general accounting/ERP package (its GL serves banking operations).
- Not a prototype: every release must be defensible in front of a bank's auditors.

## 2. Target customers & personas

### Customer segments

| Segment | Deployment | Key needs |
|---|---|---|
| Electronic money institutions & wallet providers | SaaS multi-tenant | Fast onboarding, wallets, fees, limits, APIs |
| Fintechs / neobanks | SaaS multi-tenant or dedicated | Product configurability, developer experience |
| Microfinance & mid-size banks | Dedicated SaaS or on-premise | Regulatory comfort, GL discipline, statements, EoD |
| Government / state institutions | On-premise, possibly air-gapped | Sovereignty, offline install, customer-managed infra |
| Payment/agent networks | SaaS | Settlement, suspense accounts, reconciliation at scale |

### Personas

| Persona | Representative goals |
|---|---|
| **Integration developer** (customer side) | Open accounts, post transfers, receive webhooks — safely, with idempotent retries and clear errors. |
| **Bank operations officer** | Run business day, investigate exceptions, reconcile external reports, generate statements. |
| **Financial controller / accountant** | Trust the trial balance; trace any figure to postings; verify corrections happened via reversals. |
| **Compliance / auditor** | Reconstruct who did what, when, why, with approvals; evidence of maker-checker; immutable history. |
| **Product manager (institution)** | Configure products, fees, limits — with draft/review/approve workflow, no code changes. |
| **Platform operator (vendor SRE)** | Provision tenants, monitor health per tenant, run upgrades, never touch financial data. |
| **On-premise administrator** | Install offline, manage own PostgreSQL/secrets/IAM, back up and restore, upgrade with rollback. |

## 3. Product editions (one codebase)

| Edition | Description | Control plane | Data isolation |
|---|---|---|---|
| **SaaS multi-tenant** | Shared stateless application layer, vendor-operated | Vendor control-plane DB | Database-per-tenant for financial data (ADR-0005) |
| **Dedicated SaaS** | Dedicated app deployment + DB + keys + observability namespace per customer | Vendor control plane | Fully dedicated |
| **On-premise** | Single tenant, customer-operated, no vendor-cloud dependency, offline installable | **Absent at runtime** | Customer-managed DB |

Edition-specific behavior is achieved exclusively through configuration, policies, feature
flags, and extension interfaces — **never source-code forks** (prohibited pattern).

## 4. Functional capabilities

Detailed domain semantics live in [`docs/domain/domain-model.md`](../domain/domain-model.md).
Requirement IDs (`FR-*`) are referenced by the roadmap and test strategy. MoSCoW priority and
owning phase are given per capability.

### FR-1 Control plane & tenancy (Phase 2)

- FR-1.1 (Must) Tenant lifecycle: create, configure, activate, suspend, decommission.
- FR-1.2 (Must) Deployment profile per tenant (shared / dedicated / on-premise descriptor).
- FR-1.3 (Must) Deterministic tenant→database routing; connection-pool isolation.
- FR-1.4 (Must) Feature entitlements & release-compatibility metadata per tenant.
- FR-1.5 (Must) The control plane has **no read/write path to tenant financial data**.
- FR-1.6 (Should) Data-residency metadata; maintenance state; provisioning automation.

### FR-2 Identity, access & authorization (Phase 2)

- FR-2.1 (Must) OAuth 2.0 / OIDC against external IAM (Keycloak reference; ADR-0008).
- FR-2.2 (Must) Service accounts & API clients with scoped credentials.
- FR-2.3 (Must) Tenant-scoped RBAC; permission model per operation; object-level authorization.
- FR-2.4 (Must) Maker-checker approval for privileged and configuration operations.
- FR-2.5 (Should) ABAC (branch/org-unit restrictions); session/token auditability.
- FR-2.6 (Won't-build) Password authentication stack (delegated to IAM).

### FR-3 Parties & customers (Phase 4)

- FR-3.1 (Must) Party types: individual, organization, financial institution, merchant, agent,
  government entity, internal entity.
- FR-3.2 (Must) Contact/address data; external KYC references; status & risk metadata.
- FR-3.3 (Should) Related parties & beneficial owners.
- FR-3.4 (Must) KYC orchestration stays **outside** the ledger; references are reliable.

### FR-4 Product catalog (Phases 4, 6)

- FR-4.1 (Must) Versioned product definitions: wallet, current account, savings account,
  internal, settlement, suspense, fee, interest accounts. (Term deposits, loans: later phases.)
- FR-4.2 (Must) Product configuration: currency, account type, normal balance side, overdraft
  policy, balance constraints, fee plan, limit plan, posting rules, allowed operations,
  opening/closure rules, dormancy, statement rules, effective dates.
- FR-4.3 (Must) Version activation/retirement; **historical behavior never rewritten** —
  transactions stay linked to the product version in force at execution.
- FR-4.4 (Must) Draft → review → approve → scheduled activation workflow with audit trail
  (Phase 6). Simulation & impact analysis (Should).

### FR-5 Accounts (Phase 4)

- FR-5.1 (Must) Commercial account (contract & lifecycle) separated from ledger balances
  (stores of value); documented mapping.
- FR-5.2 (Must) Identifiers: internal ID + human-readable account number; IBAN/local schemes
  via extension modules (Should).
- FR-5.3 (Must) Lifecycle: pending, active, frozen, debit-blocked, credit-blocked, fully
  blocked, dormant, closed — with atomic enforcement of block rules.
- FR-5.4 (Must) Balance dimensions: book, available, pending debits/credits, holds; overdraft/
  credit limit ([balance semantics](../accounting/balance-semantics.md)).
- FR-5.5 (Must) Closure preserves complete history; ownership & signatories; branch attribute.

### FR-6 Ledger & posting engine (Phase 3 — the kernel)

- FR-6.1 (Must) Immutable double-entry ledger: journal entries with ≥2 postings, balanced per
  currency; append-only.
- FR-6.2 (Must) Chart of accounts; GL accounts; customer subledger→GL mapping.
- FR-6.3 (Must) Balances as reconcilable projections; reconstruction command; integrity
  verification records.
- FR-6.4 (Must) Reversals as first-class linked entries; posting batches; accounting periods.
- FR-6.5 (Must) All 25 invariants in [`invariants.md`](../accounting/invariants.md) enforced at
  domain + database + test layers.
- FR-6.6 (Must) Transactional outbox for event publication after commit.

### FR-7 Transaction orchestration (Phases 3, 5)

- FR-7.1 (Must) Business operations modeled separately from postings, referencing the journal
  entries they produce: internal transfer, deposit, withdrawal, account funding, fee
  collection, refund, reversal, adjustment, hold place/capture/release.
- FR-7.2 (Must) Explicit lifecycle state machine ([spec](../domain/transaction-lifecycle.md))
  with append-only state-transition records.
- FR-7.3 (Must) Bank-grade idempotency on every financial write (ADR-0006).
- FR-7.4 (Should) Scheduled transfers, standing orders, bulk payments (Phase 8); transaction
  simulation (Phase 5).

### FR-8 Pricing & fees (Phase 5)

- FR-8.1 (Must) Fixed, percentage, min/max-bounded, and tiered fees; tax components.
- FR-8.2 (Must) Bearer models: sender / receiver / institution / shared; configurable fee
  accounts.
- FR-8.3 (Must) Effective-dated fee plans; deterministic calculation; pre-execution simulation.

### FR-9 Limits (Phase 5)

- FR-9.1 (Must) Amount & count limits per operation, daily/weekly/monthly/rolling windows.
- FR-9.2 (Must) Scopes: customer, account, product, channel, institution.
- FR-9.3 (Must) **Atomic** limit consumption safe under concurrency; override workflows (Should).

### FR-10 Interest & accruals (Phase 8 — architecture anticipated from Phase 3)

- FR-10.1 (Should) Simple/compound, positive/negative interest; tiered rates; effective-dated
  rate tables; day-count conventions; documented rounding.
- FR-10.2 (Should) Daily accrual, accrual posting, capitalization, withholding tax.
- FR-10.3 (Must, when built) Retroactive corrections only via compensating entries.

### FR-11 Reconciliation (Phase 7)

- FR-11.1 (Must) Ingestion of external statements / processor & switch reports.
- FR-11.2 (Must) Matching: exact & tolerance; 1:1, 1:N, N:1; batch + near-real-time.
- FR-11.3 (Must) Exceptions queue, manual investigation, maker-checker adjustments,
  reconciliation evidence, deterministic re-runs.

### FR-12 Business date & end-of-day (Phase 7)

- FR-12.1 (Must) Per-tenant business date independent of server time; open/close day;
  accounting-period controls; cutoffs.
- FR-12.2 (Must) EoD pipeline: scheduled transactions, fees, accruals, statements,
  reconciliation jobs, trial balance, exception checks — **idempotent and resumable**.

### FR-13 Audit & compliance evidence (Phase 2, enriched every phase)

- FR-13.1 (Must) Every operation records: actor, tenant, role, source app, channel, request/
  correlation/trace IDs, IP/user-agent where applicable, timestamp, business date, operation,
  before/after state for config, reason, approval, related transaction, auth context.
- FR-13.2 (Must) Financial postings and audit evidence are never silently deleted;
  tamper-evident audit records.

### FR-14 Notifications & webhooks (Phase 3+)

- FR-14.1 (Must) Signed webhooks (tenant-specific secrets), retries with exponential backoff,
  dead-letter, delivery logs, replay, endpoint suspension.
- FR-14.2 (Must) At-least-once delivery; event versioning; consumer deduplication guidance.

### FR-15 Statements & reporting (Phases 5, 7)

- FR-15.1 (Must) Account statements per statement rules; trial balance; operational reports.

## 5. API requirements

Per [`docs/api/api-standards.md`](../api/api-standards.md): versioned (`/api/v1`),
tenant-aware, idempotent financial writes (`Idempotency-Key` mandatory), OpenAPI 3.1
documented with examples, explicit scopes, correlation IDs, pagination, allow-list filtering,
RFC 9457 problem-details errors with stable machine-readable codes (insufficient-funds,
account-state, limit, idempotency-conflict…), documented backward-compatibility & deprecation
policy, Postman/Bruno collections, Python SDK examples, webhook event catalog.

## 6. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 **Correctness** | The 25 accounting invariants hold at all times; enforced in domain code, DB constraints, and 6 test layers. An invariant violation is a release-blocking incident. |
| NFR-2 **Auditability** | Any balance reconstructable from postings; any figure traceable to business source; full audit evidence per FR-13. |
| NFR-3 **Isolation** | Cross-tenant financial access impossible; proven by mandatory failing-safely tests at every phase gate. |
| NFR-4 **Security** | Secure-by-default per [threat model](../security/threat-model.md); OWASP API Top-10 addressed; control-readiness mapping maintained — **no certification claims**. |
| NFR-5 **Availability** | Target 99.9% for SaaS API (initial; refined by capacity model). Graceful degradation: reads survive worker outage; financial writes fail closed. |
| NFR-6 **Performance** | Initial working targets (to be validated by Phase 9 benchmarks, see [capacity model](capacity-model.md)): p99 posting commit < 250 ms at 100 TPS sustained per tenant DB; EoD for 1M-account tenant < 4 h. These are hypotheses, not SLOs, until benchmarked. |
| NFR-7 **Operability** | Runbooks, dashboards, alerts, ledger-integrity verification commands; operable by a medium-sized engineering organization. |
| NFR-8 **Recoverability** | Documented backup/restore with verification; EoD resumable; RPO ≤ 5 min / RTO ≤ 4 h initial assumptions (open decision OD-9). |
| NFR-9 **Portability** | Same artifacts run SaaS (K8s/Helm) and on-premise (standard containers, offline install, proxy/restricted networks). |
| NFR-10 **Observability** | OpenTelemetry traces, Prometheus metrics, structured JSON logs with correlation IDs, no sensitive data in logs; metric list in master prompt §15. |
| NFR-11 **Maintainability** | Modular monolith with enforced boundaries; mypy strict; docs updated with code; no premature microservices. |

## 7. Scope by release

**MVP (end of Phase 5):** tenancy + IAM + audit foundation; ledger kernel; parties, products
(v1), accounts; internal transfers, deposits/withdrawals via internal accounts, holds, fees,
limits, reversals, statements (basic); APIs + webhooks for all of the above.

**R1 (end of Phase 7):** + product configurability workflow, posting-rule versioning,
reconciliation, business date & EoD, trial balance.

**R2 (end of Phase 10):** + interest/accruals, scheduled/standing orders, dormancy, production
hardening, reference deployments (SaaS, dedicated, on-premise), release candidate.

**Out of scope (this product cycle):** lending/loan servicing (future bounded context), cards
issuing/processing, payment-scheme connectivity (ISO 8583/20022 adapters — integration points
only), FX trading, AML transaction monitoring (events exposed for external tools), general ERP
accounting, customer-facing channels.

Full scope statement: [`scope.md`](scope.md).

## 8. Success criteria

1. **Ledger trustworthiness**: 100% of phase-gate invariant checks pass; balance
   reconstruction matches projections on every gate run; zero known paths to mutate posted
   entries.
2. **Concurrency proof**: the hostile-concurrency suite (double spend, duplicate requests,
   hold races, limit overconsumption, deadlocks, ambiguous retries) passes on real PostgreSQL
   at every gate from Phase 3 on.
3. **Isolation proof**: cross-tenant test suite passes at every gate from Phase 2 on; on-prem
   profile boots and serves with control plane absent.
4. **Configurability**: a demo institution with 3+ products, fee plans, and limit plans is
   configured **without code changes** (Phase 10 seed catalog).
5. **Operability**: an operator can install on-premise from offline artifacts, run a business
   day, take/verify a backup, and upgrade+rollback using only the documentation.
6. **Developer experience**: integration developer can go from credentials to a successful
   idempotent transfer using only public docs + OpenAPI + collections.

## 9. Key risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | Ledger correctness defect discovered late | Ledger built first (Phase 3) behind hostile test suite; invariants in DB constraints, not only code; integrity verification & reconstruction commands from day one. |
| R2 | Hot-account contention limits throughput | Explicit strategy in [idempotency & concurrency](../architecture/idempotency-concurrency.md); benchmark before SLOs; hierarchical settlement accounts as designed mitigation. |
| R3 | Multi-tenant data leak | DB-per-tenant isolation, no-default-tenant rule, mandatory cross-tenant tests, tenant-isolation monitoring. |
| R4 | Scope creep toward full CBS breadth | Phased roadmap with hard gates; MoSCoW discipline; out-of-scope register. |
| R5 | On-premise divergence from SaaS | Single artifact set; on-prem profile tested in CI from Phase 2; no vendor-cloud runtime dependency. |
| R6 | Configuration engine becomes arbitrary code execution | Declarative, versioned, sandboxed rules only (master prompt §13); prohibited-patterns enforcement. |
| R7 | Team/agent development discipline erodes | CLAUDE.md + path rules + review subagents + phase gates with human approval; Definition of Done enforced. |
| R8 | Regulatory expectations vary per market | Control-readiness mapping instead of claims; extension modules for local identifiers/statements; open-decisions register per market entry. |

## 10. Assumptions & open decisions

All assumptions are labeled and tracked in
[`docs/decisions/open-decisions.md`](../decisions/open-decisions.md). Highlights: initial
target markets and currencies (OD-1), regulatory reporting formats (OD-2), FX support depth
(OD-4), RPO/RTO commitments (OD-9), licensing model (OD-12).
