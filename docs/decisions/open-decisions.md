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
| OD-5 | Worker framework (Celery vs. Dramatiq) | **Confirmed** (2026-07-18) | ADR-0009 Accepted: Celery with mandatory reliability profile (acks_late, reject-on-worker-lost, explicit queues). Wired in Phase 3. | — | Done |
| OD-6 | OpenAPI tooling & first spec | **Recommended** | drf-spectacular (OpenAPI 3.1). Not shipped in Phases 1–2; the Phase 2 audit endpoint's spec is explicitly deferred with it. Due with the first financial APIs. | Eng | Phase 3 |
| OD-7 | Business-date default cutover & calendar seed | **Assumption** | Tenant-configurable calendar; default Mon–Fri + configurable holidays; single business date per tenant (no branch-level dates in MVP). Consequence: branch-level day management deferred. | Human | Phase 7 |
| OD-8 | Idempotency & audit retention horizons | **Assumption** | 10 years for financial records/audit/idempotency (conservative bank-grade default); consequence: storage archival tooling needed by Phase 9. Confirm against target-market law. | Human | Phase 9 |
| OD-9 | RPO/RTO commitments & PostgreSQL HA topology | **Assumption** | Working targets RPO ≤ 5 min, RTO ≤ 4 h; synchronous-replica evaluation in Phase 9. No SLO published before drills. | Human+Eng | Phase 9 |
| OD-10 | Connection pooling (per-tenant pools vs. PgBouncer) | **Deferred** | Decide with real tenant counts/load in Phase 9. Phase 2 reality: one Django connection per alias per worker, bounded by `CONN_MAX_AGE=60` — no dedicated pooling yet. | Eng | Phase 9 |
| OD-11 | Rules-engine formalism for posting rules (Phase 6) | **Open** | Declarative schema (YAML/JSON + restricted expression language, sandboxed & versioned). No arbitrary code — non-negotiable. Formalism ADR due Phase 6. | Eng | Phase 6 |
| OD-12 | Licensing & distribution model | **Open** | README says proprietary pending decision. Affects on-prem artifact distribution. | Human | Before Phase 10 |
| OD-13 | Duplicate of OD-5 — merged. | — | — | — | — |
| OD-14 | DB-role separation for posting path (separate role owning INSERT on postings; app role read-only on them) | **Recommended** | Strongest enforcement of invariants 5/8; small connection-management cost. Decide in Phase 3 design review. | Eng | Phase 3 |
| OD-15 | Balance-snapshot hash-chaining design (tamper evidence) | **Recommended** | EoD snapshots chained by hash; exact scheme (per-balance vs. per-ledger Merkle) decided in Phase 3. | Eng | Phase 3 |
| OD-16 | BLNK matrix re-validation against live docs | **Open** | Build environment could not reach docs.blnkfinance.com; matrix built from Jan-2026 project knowledge. Re-validate (incl. llms.txt) before Phase 3 gate. | Eng | Phase 3 |
| OD-17 | Back-office UI scope (Django admin vs. dedicated ops UI) | **Assumption** | MVP: guarded Django admin + ops APIs; no financial mutations via admin. Dedicated ops UI is post-R2 product work. | Human | Phase 6 |
| OD-18 | Per-tenant Keycloak realm vs. instance in shared SaaS | **Recommended** | Realm-per-tenant initially; dedicated instances for dedicated-SaaS. Validate realm-count operability in Phase 9. | Eng | Phase 9 |
| OD-19 | Tenant routing integrity (DSN storage + unsigned routing entries) | **Assumption — accepted residual risk** | Phase 2 stores plain DSNs in the control DB and routing entries are unsigned: a compromised control DB could repoint routing for newly-started processes (threat model TB3, documented there with compensating controls). Secret-manager refs + signed/validated routing entries land with provisioning automation. `db_alias` values are never reused across tenant lifecycles. Hard deadline: before any SaaS production tenant. | Eng+Human | Phase 9 / SaaS go-live |
| OD-20 | DB-grant hardening for append-only audit table | **Recommended** | Revoke UPDATE/DELETE from app role on `audit_event` via provisioning tooling (same pattern as Phase 3 ledger grants); app-level guards exist now. | Eng | Phase 3 |
| OD-21 | Production SaaS tenant resolution (host- or token-claim-based) | **Open** | `header` resolver is dev/staging-grade behind a trusted gateway; public SaaS routing needs host/claim resolution + gateway design. Startup check next_core.E001 already blocks shared-issuer misconfiguration. | Eng | Before SaaS go-live (Phase 9/10) |
| OD-22 | Token tenant-claim cross-check (second factor beyond issuer binding) | **Recommended** | Add validation of an explicit tenant claim against the resolved tenant, as defense in depth on top of realm-per-tenant issuer binding. | Eng | Phase 3 |
| OD-23 | TLS enforcement on tenant-DB DSNs (`sslmode=require`) in SaaS profile | **Recommended** | register_tenant_alias currently trusts the DSN author for transport security; enforce/validate sslmode for SaaS-profile registrations. | Eng | Phase 9 |
| OD-24 | Ingress overwrite of client-supplied X-Request-ID in production | **Recommended** | Correlation IDs are sanitized but attacker-choosable; production ingress should overwrite/namespace them so audit correlation evidence is server-controlled. | Eng | Phase 9 |
| OD-25 | Import-linter boundary contracts (golden dependency rules in CI) | **Deferred** | Planned for Phase 2, not shipped; due with the ledger kernel where cross-context import rules become financially load-bearing. | Eng | Phase 3 |
| OD-26 | Pagination style: bounded page-number (shipped) vs. cursor (API standard) | **Assumption** | Phase 2's audit listing ships bounded PageNumber pagination; the cursor-pagination standard applies from the first financial collections (Phase 3+), and the audit endpoint migrates then. Documented in api-standards. | Eng | Phase 3 |
| OD-27 | RFC 9457 exception handler for DRF 401/403 responses | **Deferred** | Phase 2's 401/403 use DRF's default `{"detail": …}` shape (no `code`/`correlation_id`); the problem-details handler lands with the error-catalog build-out. | Eng | Phase 3 |

## Resolution protocol

Resolving an entry requires: decision recorded (ADR if architectural), label →
`Confirmed`, link to the ADR/doc, and the change applied under the same-change rule.
Human-owned entries are stop-points (see development workflow §7).
