# ADR-0004 — Money as integer minor units + ISO-4217 currency

- **Status:** Accepted
- **Date:** 2026-07-17
- **Deciders:** mohamed@next.mr — approved 2026-07-18 (Phase 0 gate)

## Context

Invariants 3–4: no binary floating point for money; the storage representation must be fixed
by ADR. Requirements: exactness, safe arithmetic, multi-currency (different exponents, e.g.
XOF 0, USD 2, TND 3), deterministic rounding for fees/interest, DB constraint compatibility,
unambiguous API wire format.

## Decision

- **Storage:** `BIGINT` amount in **minor units** + `CHAR(3)` ISO-4217 code on every money
  column (postings, projections, limits, fees). Currency exponent comes from a versioned
  currency table seeded from ISO 4217 (overridable per deployment for special cases,
  config-controlled).
- **Domain:** immutable `Money` value object (`amount_minor: int`, `currency: Currency`);
  arithmetic only between same-currency values (mismatch raises); no implicit conversion.
- **Computation boundary:** rates/percentages (fees, interest, FX) computed with
  `decimal.Decimal` at documented precision, then **quantized once** to minor units per the
  rounding policy: **round-half-even** by default; per-plan override (e.g. round-up on tax)
  must be explicit in the plan configuration and recorded with the computed result.
- **API wire format:** amounts as **decimal strings** in major units with exactly the
  currency's exponent (`"100.00"` USD, `"100" `XOF) + explicit `currency` field; parsing
  rejects excess precision. Integers-in-minor-units accepted nowhere externally (ambiguity),
  used everywhere internally.
- **Prohibitions:** `float`/`FloatField`/SQL `double precision` anywhere near money —
  lint-enforced; `NUMERIC` storage rejected for postings (see below).

## Alternatives considered

- **`NUMERIC(p,s)` storage** — rejected for ledger tables: pushes exponent knowledge into
  every schema definition, slower aggregation, invites fractional-minor-unit rows; kept
  admissible for *rate* storage (rates aren't money).
- **Decimal-string storage** — rejected: no arithmetic/constraint support.
- **Minor-units-on-the-wire API** — rejected: integer-cents APIs are chronically misread
  (×100 bugs on the customer side); decimal strings + strict validation are safer.
- **Float anywhere** — prohibited by invariant 3.

## Consequences

- **Positive:** exact arithmetic; `SUM()` in SQL is exact; CHECK constraints trivial;
  cross-currency mixing structurally impossible in domain code.
- **Negative / accepted costs:** every human-facing surface must format via the currency
  exponent (helper in `platform`); BIGINT ceiling ≈ 9.2×10¹⁸ minor units — fine for realistic
  balances, monitored by a sanity constraint on absurd amounts (config).
- **Neutral:** FX rate precision & policy detailed with the FX bridge design (OD-4).

## Compliance & security impact

Deterministic, reproducible computations are audit-defensible; rounding decisions are
configuration, versioned and traceable.

## Reversibility

Low: the `Money` object isolates representation; a storage change would be a migration
program but domain code would not change semantics.
