# On-Premise Installation Guide *(skeleton — authored Phases 9–10)*

See [deployment README](README.md) for scope. To author with the on-prem package:

1. Editions & prerequisites (containers, customer PostgreSQL versions, OIDC provider,
   storage, no vendor-cloud dependency statement).
2. Offline bundle contents & integrity verification (checksums, SBOM, image signatures if
   available).
3. Installation (compose and K8s variants), static single-tenant configuration, secrets
   (customer-managed), proxy/restricted-network & air-gapped notes.
4. Post-install health checks & validation checklist.
5. Backup configuration (local/S3-compatible), restore drill.
6. Upgrade procedure (N-1 rule, migration verification, rollback), offline update cadence.
7. Local observability integration (Prometheus scrape/OTLP export).
8. Support & diagnostics bundle (log collection with redaction).

## Database layout and install sequence (as built, MVP track)

On-premise runs **one physical PostgreSQL database** behind both Django aliases: `default`
(Django internals) and `tenant_main` (data plane). Because both aliases share one
`django_migrations` table, the on-prem profile sets `NEXT_CORE_SINGLE_DATABASE = True`, which
makes the database router allow every app's tables on whichever alias migrates first.
Without it, `migrate` recorded the data-plane migrations as applied without creating their
tables, and `migrate_tenants` then skipped them — a latent Phase 2 defect caught by the CI
`onprem-boot` job once the bootstrap step was added (regression test:
`tests/integration/test_onprem_profile.py::test_onprem_migrates_bootstraps_and_verifies_on_real_postgres`).

Verified install sequence (CI `onprem-boot` job and the regression test):

```bash
python manage.py migrate --noinput     # creates all tables (single database)
python manage.py migrate_tenants       # no-op on-prem; kept for a uniform runbook
python manage.py bootstrap_tenant      # seed chart of accounts + product catalog (idempotent)
python manage.py verify_ledger         # integrity check; non-zero exit on findings
```
