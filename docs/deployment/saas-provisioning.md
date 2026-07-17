# SaaS Provisioning Guide *(skeleton — authored Phase 10)*

See [deployment README](README.md) for scope. To author with the reference deployment:

1. Platform prerequisites (K8s, Helm, PostgreSQL fleet, Keycloak, observability stack).
2. Installing/upgrading the platform (Helm values reference, secrets wiring).
3. Tenant provisioning runbook: create tenant DB (bootstrap role) → run migrations → create
   IAM realm → register routing + entitlements → smoke checks → hand-off.
4. Dedicated-SaaS variant (dedicated deployment/DB/keys/namespace).
5. Tenant suspension, decommissioning (with data-export & retention obligations).
6. Capacity management & scaling playbook.
