# Deployment Documentation *(skeletons — authored Phases 9–10)*

| | |
|---|---|
| **Purpose** | Deployment guides per profile. Structure fixed now; content lands with the reference deployments. |
| **Owning phase** | Phases 9–10 (same-change rule with `deploy/` artifacts). |
| **Related** | [Tenancy & deployment architecture](../architecture/tenancy-and-deployment.md) · ADR-0005 |

| Document | Content when authored | Phase |
|---|---|---|
| [`saas-provisioning.md`](saas-provisioning.md) | Shared-SaaS install (Helm), tenant provisioning workflow (DB creation, realm, routing registration, entitlements), scaling config, per-tenant observability namespaces, dedicated-SaaS variant | 10 |
| [`onprem-installation.md`](onprem-installation.md) | Offline artifact bundle (images, charts/compose, checksums, SBOM), prerequisites, customer-managed PostgreSQL/secrets/IAM wiring, proxy & air-gapped setup, install health checks, upgrade & rollback procedure, migration verification | 9–10 |
| [`environment-reference.md`](environment-reference.md) | Configuration/env-var reference per profile + `check --deploy` results | **1 (authored)**, extended per phase |
| `upgrade-strategy.md` | N-1 compatibility rules, zero/low-downtime migration playbook, fleet fan-out ordering | 9 (see also [migrations](../migrations/README.md)) |

Until authored, the authoritative deployment positions are in the
[tenancy & deployment architecture](../architecture/tenancy-and-deployment.md).
