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
