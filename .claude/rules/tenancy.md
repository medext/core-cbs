# Rules — Tenancy & Control Plane (`src/next_core/tenancy/`, `src/next_core/control_plane/`, all data-plane modules)

Read `docs/architecture/tenancy-and-deployment.md` and ADR-0005 first.

## Tenant context

- Every data-plane operation requires an explicit, validated `TenantContext`. It is established
  once at the request/job boundary and passed explicitly — never inferred from global state
  inside domain logic.
- **No default tenant. Ever.** If tenant resolution fails, the request/job fails with an
  explicit error. A fallback tenant is a critical security defect.
- Background jobs, management commands, and event consumers must declare their tenant scope
  explicitly; a job that iterates tenants must re-establish context per tenant and must not
  leak state between iterations.

## Database routing

- Financial data lives in tenant-specific databases (ADR-0005). Routing is deterministic from
  the tenant context; connection pools are isolated per tenant database.
- No unscoped ORM queries in the data plane. Any queryset must be constructed through the
  tenant-scoped manager/repository. Adding a model without a tenant-scoped access path is a
  defect.
- Cross-tenant queries do not exist in the data plane. Aggregation across tenants happens only
  in the control plane over non-financial metadata, or through per-tenant exports.

## Control plane boundaries

- The control plane manages tenant lifecycle, entitlements, routing, and provisioning. It must
  have **no code path that reads or mutates tenant financial balances or postings**. If a
  feature seems to need this, stop and escalate.
- The on-premise profile must run with the control-plane runtime absent — guard any
  control-plane dependency behind the deployment profile and test the single-tenant profile
  without it.

## Testing requirements (blocking)

- Cross-tenant access tests: authenticated as tenant A, every data-plane endpoint must return
  404/403 (never 200, never a leak in error bodies) for tenant B resources.
- Tenant-resolution-failure tests: missing/invalid tenant → hard error, no fallback.
- Routing determinism tests: same tenant → same database, concurrent mixed-tenant requests do
  not cross-contaminate connections.

Run the `security-reviewer` subagent on any change touching tenant resolution, routing, or
middleware ordering.
