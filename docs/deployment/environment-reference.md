# Environment & Settings Reference

| | |
|---|---|
| **Purpose** | Configuration reference per profile + documented `manage.py check --deploy` results (Phase 1 gate item). |
| **Audience** | Engineering, operators. |
| **Owning phase** | Phase 1 (this version) — extended every time a setting is added (same-change rule). |
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

## Environment variables (Phase 1 set)

| Variable | Required | Default | Notes |
|---|---|---|---|
| `NEXT_CORE_PROFILE` | no | `local` | Profile selection |
| `DJANGO_SECRET_KEY` | **yes** (saas/onprem) | dev value in local/test only | No production default, boot fails without it |
| `DJANGO_ALLOWED_HOSTS` | **yes** (saas/onprem) | `localhost,127.0.0.1` (local) | Comma-separated |
| `DJANGO_DEBUG` | no | `true` local only | Ignored (forced False) in saas/onprem |
| `DATABASE_URL` | **yes** | local dev DSN in local/test | **PostgreSQL only** — any other engine refuses to boot (ADR-0003) |
| `DATABASE_CONN_MAX_AGE` | no | `60` | Seconds |
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
