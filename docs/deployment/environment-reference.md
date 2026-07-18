# Environment & Settings Reference

| | |
|---|---|
| **Purpose** | Configuration reference per profile + documented `manage.py check --deploy` results (Phase 1 gate item). |
| **Audience** | Engineering, operators. |
| **Owning phase** | Started Phase 1; extended every time a setting is added (same-change rule) — current through Phase 2. |
| **Related** | [Tenancy & deployment](../architecture/tenancy-and-deployment.md) · `.env.example` |

## Profiles

`NEXT_CORE_PROFILE` ∈ `local` | `saas` | `onprem` selects the settings module
(`next_core.settings.<profile>`; tests use `next_core.settings.test`).

| Profile | DEBUG | Default secrets | TLS posture |
|---|---|---|---|
| `local` | env (`DJANGO_DEBUG`, default true) | insecure dev defaults allowed | plain HTTP |
| `saas` | **forced False** | none — missing env fails boot | `SECURE_SSL_REDIRECT=True`, HSTS 1y + preload, proxy header |
| `onprem` | **forced False** | none — missing env fails boot | redirect/HSTS env-tunable (TLS may terminate on customer LB) |
| `test` | False | test-only defaults | n/a |

## Environment variables (current set)

| Variable | Required | Default | Notes |
|---|---|---|---|
| `NEXT_CORE_PROFILE` | no | `local` | Profile selection |
| `DJANGO_SECRET_KEY` | **yes** (saas/onprem) | dev value in local/test only | No production default, boot fails without it |
| `DJANGO_ALLOWED_HOSTS` | **yes** (saas/onprem) | `localhost,127.0.0.1` (local) | Comma-separated |
| `DJANGO_DEBUG` | no | `true` local only | Ignored (forced False) in saas/onprem |
| `DATABASE_URL` | **yes** | local dev DSN in local/test | **PostgreSQL only** — any other engine refuses to boot (ADR-0003) |
| `DATABASE_CONN_MAX_AGE` | no | `60` | Seconds |
| `TEST_DB_PORT` | no | `5433` | test profile & `make test-db-*` only: port of the local test PostgreSQL |
| `NEXT_CORE_TENANT_RESOLVER` | no | `header` (forced `static` in onprem) | `header` = X-Tenant-ID (dev/test/staging behind trusted gateway); `static` = on-prem single tenant |
| `NEXT_CORE_TENANT_DIRECTORY` | no | `control` (forced `static` in onprem) | Tenant lookup source: control-plane registry vs. static config |
| `NEXT_CORE_TENANT_ID` / `NEXT_CORE_TENANT_SLUG` | **yes** (onprem) | none — boot fails | The on-premise tenant identity (UUID + slug) |
| `OIDC_ISSUER_TEMPLATE` | yes for authenticated APIs | empty (auth fails closed) | Per-tenant issuer, e.g. `https://kc/realms/{tenant}` |
| `OIDC_AUDIENCE` | no | `next-core` | Expected token audience |
| `OIDC_JWKS_URL_TEMPLATE` | no | `{issuer}/protocol/openid-connect/certs` | JWKS location (Keycloak-style default) |
| `OIDC_ROLES_CLAIM` | no | `realm_access.roles` | Dotted claim path for role extraction |
| — `OIDC_JWKS_STATIC` (settings-only) | no | unset | Static JWKS document bypassing network fetch. **Test-suite mechanism today**; operator-reachable env wiring for air-gapped installs lands with on-prem packaging (Phase 9) |
| `REDIS_URL` | no | unset → LocMem cache | Cache/rate-limit only, never truth |
| `LOG_LEVEL` | no | `INFO` | Structured JSON logs |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | no | unset → telemetry no-op | Air-gap friendly |
| `OTEL_SERVICE_NAME` | no | `next-core` | |
| `DJANGO_SECURE_SSL_REDIRECT` | no | `true` (onprem) | onprem only |
| `DJANGO_SECURE_HSTS_SECONDS` | no | `31536000` (onprem) | onprem only |

## `manage.py check --deploy` results (2026-07-18, Django 5.2.16)

Executed with production-shaped env (real secret, hosts, PostgreSQL DSN):

| Profile | Result |
|---|---|
| `saas` | **System check identified no issues (0 silenced).** |
| `onprem` | 1 warning: `security.W021` (HSTS preload not forced) — **intentional**: preload list submission is a per-customer domain decision on-premise; enable via `DJANGO_SECURE_HSTS_SECONDS` + institutional policy. No other findings. |

Security-relevant settings in force (base for all profiles): `SECURE_CONTENT_TYPE_NOSNIFF`,
`SECURE_REFERRER_POLICY=same-origin`, `X_FRAME_OPTIONS=DENY` (+ clickjacking middleware),
CSRF middleware, secure session/CSRF cookies (outside local), request-body bound
`DATA_UPLOAD_MAX_MEMORY_SIZE=2.5MiB`, `USE_TZ=True` (UTC), DRF default permission
`IsAdminUser` (deny-by-default; endpoints opt in explicitly).

This check re-runs at every phase gate; regressions are gate-blocking.
