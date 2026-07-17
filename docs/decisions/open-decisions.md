# Open Decisions & Assumptions Register

| | |
|---|---|
| **Purpose** | Every assumption and undecided point, labeled and tracked. Sessions must register new assumptions here (same-change rule). |
| **Audience** | Everyone. |
| **Owning phase** | Living document. |

**Labels:** `Confirmed` (human-approved) · `Recommended` (agent position awaiting approval) ·
`Assumption` (conservative bank-grade default, consequences stated) · `Open` (needs an owner
decision) · `Deferred` (explicitly later, with trigger).

| ID | Topic | Status | Position / consequence | Owner | Due |
|---|---|---|---|---|---|
| OD-1 | Initial target markets & currencies | **Open** | Assumed: WAEMU/North-Africa-style e-money institutions first (user context); seed currencies XOF/MRU/EUR/USD in examples. Drives seed CoA, identifier schemes, statement formats. No architecture impact — extension modules absorb market specifics. | Human | Before Phase 4 |
| OD-2 | Regulatory reporting formats per jurisdiction | **Deferred** | Extract/data surface in core; format packs as `integrations` extensions. Trigger: first committed market. | Human | Market entry |
| OD-3 | Product name / repo naming | **Assumption** | Product "Next Core", repo `medext/core-cbs` — documented in repo-structure deviations. | Human | Anytime |
| OD-4 | FX depth for MVP | **Recommended** | Same-currency operations only through Phase 5; FX bridge modeled (accounts + rate reference) but inactive. Consequence: no cross-currency transfers in MVP. | Human | Phase 5 gate |
| OD-5 | Worker framework (Celery vs. Dramatiq) | **Open** | Decided by ADR in Phase 1 (evaluation criteria: reliability semantics, observability, on-prem simplicity). | Eng | Phase 1 |
| OD-6 | OpenAPI tooling | **Recommended** | drf-spectacular (OpenAPI 3.1) — confirm in Phase 1 with version check. | Eng | Phase 1 |
| OD-7 | Business-date default cutover & calendar seed | **Assumption** | Tenant-configurable calendar; default Mon–Fri + configurable holidays; single business date per tenant (no branch-level dates in MVP). Consequence: branch-level day management deferred. | Human | Phase 7 |
| OD-8 | Idempotency & audit retention horizons | **Assumption** | 10 years for financial records/audit/idempotency (conservative bank-grade default); consequence: storage archival tooling needed by Phase 9. Confirm against target-market law. | Human | Phase 9 |
| OD-9 | RPO/RTO commitments & PostgreSQL HA topology | **Assumption** | Working targets RPO ≤ 5 min, RTO ≤ 4 h; synchronous-replica evaluation in Phase 9. No SLO published before drills. | Human+Eng | Phase 9 |
| OD-10 | Connection pooling (per-tenant pools vs. PgBouncer) | **Deferred** | Decide with real tenant counts/load in Phase 9; Phase 2 ships bounded per-tenant pools. | Eng | Phase 9 |
| OD-11 | Rules-engine formalism for posting rules (Phase 6) | **Open** | Declarative schema (YAML/JSON + restricted expression language, sandboxed & versioned). No arbitrary code — non-negotiable. Formalism ADR due Phase 6. | Eng | Phase 6 |
| OD-12 | Licensing & distribution model | **Open** | README says proprietary pending decision. Affects on-prem artifact distribution. | Human | Before Phase 10 |
| OD-13 | Duplicate of OD-5 — merged. | — | — | — | — |
| OD-14 | DB-role separation for posting path (separate role owning INSERT on postings; app role read-only on them) | **Recommended** | Strongest enforcement of invariants 5/8; small connection-management cost. Decide in Phase 3 design review. | Eng | Phase 3 |
| OD-15 | Balance-snapshot hash-chaining design (tamper evidence) | **Recommended** | EoD snapshots chained by hash; exact scheme (per-balance vs. per-ledger Merkle) decided in Phase 3. | Eng | Phase 3 |
| OD-16 | BLNK matrix re-validation against live docs | **Open** | Build environment could not reach docs.blnkfinance.com; matrix built from Jan-2026 project knowledge. Re-validate (incl. llms.txt) before Phase 3 gate. | Eng | Phase 3 |
| OD-17 | Back-office UI scope (Django admin vs. dedicated ops UI) | **Assumption** | MVP: guarded Django admin + ops APIs; no financial mutations via admin. Dedicated ops UI is post-R2 product work. | Human | Phase 6 |
| OD-18 | Per-tenant Keycloak realm vs. instance in shared SaaS | **Recommended** | Realm-per-tenant initially; dedicated instances for dedicated-SaaS. Validate realm-count operability in Phase 9. | Eng | Phase 9 |

## Resolution protocol

Resolving an entry requires: decision recorded (ADR if architectural), label →
`Confirmed`, link to the ADR/doc, and the change applied under the same-change rule.
Human-owned entries are stop-points (see development workflow §7).
