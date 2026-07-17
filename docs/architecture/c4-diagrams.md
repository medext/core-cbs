# C4 Architecture Diagrams

| | |
|---|---|
| **Purpose** | System context, container, and component views (C4). Context & container authored now; component diagrams land with their phases. |
| **Audience** | Everyone technical. |
| **Owning phase** | Phase 0 (context, container) → Phases 3+ (components) → Phase 9 (deployment). |
| **Related** | [Domain model](../domain/domain-model.md) · [Tenancy & deployment](tenancy-and-deployment.md) |

## Level 1 — System context

```mermaid
flowchart TB
    DEV[Integration developer<br/>institution's systems & channels]
    OPS[Bank operations & back office]
    PMGR[Institution product manager]
    VOPS[Vendor platform operator<br/>SaaS only]

    NC["**Next Core**<br/>Core Banking System<br/>accounts, ledger, transactions,<br/>products, reconciliation, EoD"]

    IAM[External IAM<br/>Keycloak / OIDC provider]
    KYC[KYC / AML systems]
    PAY[Payment processors,<br/>switches, schemes]
    OBS[Observability stack<br/>Prometheus / OTLP]
    NOTIF[Institution webhook<br/>consumers]

    DEV -- REST APIs (OAuth2, idempotent) --> NC
    OPS -- Back-office APIs/UI --> NC
    PMGR -- Configuration workflow --> NC
    VOPS -- Control-plane APIs --> NC
    NC -- token validation / OIDC --> IAM
    KYC -- references & status --> NC
    PAY -- settlement reports & statements --> NC
    NC -- signed webhooks --> NOTIF
    NC -- metrics / traces / logs --> OBS
```

## Level 2 — Containers (shared SaaS profile)

```mermaid
flowchart TB
    subgraph K8s["Kubernetes (vendor)"]
        subgraph AppLayer["Stateless app layer"]
            API[Django/DRF API<br/>data-plane, versioned APIs]
            BO[Back-office app<br/>Django admin + ops APIs]
            WK[Async workers<br/>outbox relay, webhooks,<br/>EoD steps, queued txns]
        end
        CPA[Control-plane service<br/>Django — registry, routing,<br/>entitlements, provisioning]
    end

    CPDB[(Control-plane<br/>PostgreSQL)]
    TDB1[(Tenant DB 1<br/>PostgreSQL — ledger,<br/>accounts, txns, audit)]
    TDBn[(Tenant DB n)]
    RED[(Redis<br/>cache, rate limits,<br/>queues — never truth)]
    KC[Keycloak<br/>per-tenant realms]

    API --> TDB1 & TDBn
    BO --> TDB1
    WK --> TDB1 & TDBn
    API & BO & WK -- routing (signed cache) --> CPA
    CPA --> CPDB
    API & WK --> RED
    API & BO -- OIDC --> KC
    WK -- signed webhooks --> EXT[Institution endpoints]
```

On-premise profile: same API/BO/WK containers; control-plane service absent (static tenant
config); customer PostgreSQL/Redis/IAM. See [tenancy & deployment](tenancy-and-deployment.md).

## Level 3 — Components

Authored per phase, one section per context, matching the implementation (same-change rule):

- **Ledger & posting engine** — *Phase 3.* Posting service, idempotency gate, balance
  projector, outbox writer, integrity runner, reconstruction command.
- **Transaction orchestration** — *Phase 5.* Intake, lifecycle engine, hold manager,
  rule executor binding, simulation.
- **Tenancy & control plane** — *Phase 2.* Resolver, router, pool manager, fan-out migrator.
- **Configuration workflow** — *Phase 6.* Draft/review/approve engine, activation scheduler.
- **Business day & reconciliation** — *Phase 7.* EoD step framework, matching engine.

## Level 4 — Deployment diagrams

*Phase 9.* Reference topologies (shared SaaS, dedicated, on-premise, air-gapped) with network
zones, trust boundaries, and backup flows.

## Data-flow diagrams

*Phase 3+ per flow.* Transfer, hold capture, webhook delivery, EoD, reconciliation — each as a
sequence diagram in the owning context's component section, cross-referenced from the threat
model's trust-boundary analysis.
