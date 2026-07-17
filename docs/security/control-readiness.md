# Control-Readiness Mapping *(skeleton — authored Phase 9)*

| | |
|---|---|
| **Purpose** | Honest mapping of implemented technical controls vs. organizational controls vs. items requiring independent assessment. **Never a certification claim.** |
| **Audience** | Customers' risk teams, vendor management, auditors. |
| **Owning phase** | Phase 9 (with hardening evidence); structure fixed now. |
| **Related** | [Security architecture](security-architecture.md) · [Threat model](threat-model.md) |

## Binding rule

Next Core documentation never claims ISO 27001, PCI DSS, SOC 2, or any certification.
This document states, per control family: what the product implements (with evidence links),
what remains the operating organization's responsibility, and what only an independent
assessment can attest.

## Structure to fill (Phase 9)

Per framework family (ISO 27001 Annex A themes, SOC 2 TSC, PCI-DSS-relevant subset if card
data ever transits — currently out of scope):

| Control | Product-implemented (evidence) | Organizational (SaaS vendor / on-prem customer) | Requires independent assessment |
|---|---|---|---|

Seed families: access control · cryptography · logging & monitoring · change management
(maker-checker, ADRs, frozen migrations) · backup/recovery · secure development (CI scans,
SBOM, reviews) · supplier management · incident response · business continuity.

On-premise deployments shift many organizational rows to the customer — the matrix carries a
per-profile responsibility column when authored.
