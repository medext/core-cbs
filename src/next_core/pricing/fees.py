"""Deterministic fee calculation (pure functions over product fee rules).

Semantics (docs/products/product-engine.md#fees):
- the computed figure is the **net fee** (fee income); tax = net * tax_rate is charged on
  top; the customer pays ``net + tax``;
- PERCENTAGE: net = amount * rate, quantized once with the rule's rounding, then clamped
  to [min, max];
- TIERED: volume tiers — the tier whose ``up_to`` first covers the amount applies to the
  whole amount (flat amount or rate);
- EXPRESSION: restricted formula in major units, quantized with the rule's rounding;
- fees whose condition is false, or that compute to zero, are omitted.
Same inputs ⇒ same outputs (property-tested).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext

import structlog

from next_core.platform.errors import ProductRuleViolationError
from next_core.platform.money import Money, Rounding, quantize_minor
from next_core.products.definition import FeeCalculation, FeeRule, Operation
from next_core.products.expressions import ExpressionError, Value

log = structlog.get_logger("next_core")


@dataclass(frozen=True, slots=True)
class FeeCharge:
    code: str
    net: Money
    tax: Money

    @property
    def total(self) -> Money:
        return self.net + self.tax


def _net(calc: FeeCalculation, amount: Money, env: Mapping[str, Value], rounding: Rounding) -> int:
    with localcontext() as ctx:
        ctx.prec = 50  # exact products before the single quantization (no double rounding)
        return _net_exact(calc, amount, env, rounding)


def _net_exact(
    calc: FeeCalculation, amount: Money, env: Mapping[str, Value], rounding: Rounding
) -> int:
    cur = amount.currency
    if calc.type == "FLAT":
        if calc.amount is None:
            raise ProductRuleViolationError(
                "Invalid fee configuration."
            )  # unreachable after parsing
        return calc.amount[cur]
    if calc.type == "PERCENTAGE":
        if calc.rate is None:
            raise ProductRuleViolationError(
                "Invalid fee configuration."
            )  # unreachable after parsing
        net = quantize_minor(Decimal(amount.amount_minor) * calc.rate, rounding)
        if calc.minimum is not None:
            net = max(net, calc.minimum[cur])
        if calc.maximum is not None:
            net = min(net, calc.maximum[cur])
        return net
    if calc.type == "TIERED":
        for tier in calc.tiers:
            if tier.up_to is None or amount.amount_minor <= tier.up_to[cur]:
                if tier.flat is not None:
                    return tier.flat[cur]
                if tier.rate is None:
                    raise ProductRuleViolationError(
                        "Invalid fee configuration."
                    )  # unreachable after parsing
                return quantize_minor(Decimal(amount.amount_minor) * tier.rate, rounding)
        raise ProductRuleViolationError("No fee tier covers the amount.")  # pragma: no cover
    if calc.formula is None:
        raise ProductRuleViolationError("Invalid fee configuration.")  # unreachable after parsing
    try:
        major = calc.formula.evaluate_decimal(env)
        return Money.from_major_decimal(major, cur, rounding).amount_minor
    except (ExpressionError, ArithmeticError, ValueError) as exc:
        # Source/text stays server-side (L1): clients only learn which rule failed.
        log.warning("pricing.fee_formula_failed", error=type(exc).__name__)
        raise ProductRuleViolationError("A fee formula could not be evaluated.") from exc


def compute_fees(
    rules: Sequence[FeeRule], operation: Operation, amount: Money, env: Mapping[str, Value]
) -> list[FeeCharge]:
    charges: list[FeeCharge] = []
    for rule in rules:
        if operation not in rule.operations:
            continue
        try:
            if rule.condition is not None and not rule.condition.evaluate_bool(env):
                continue
        except ExpressionError as exc:
            log.warning("pricing.fee_condition_failed", fee=rule.code, error=str(exc))
            raise ProductRuleViolationError(
                f"Fee '{rule.code}' condition could not be evaluated."
            ) from exc
        net = _net(rule.calculation, amount, env, rule.rounding)
        if net < 0:
            raise ProductRuleViolationError(f"Fee '{rule.code}' computed a negative amount.")
        if net == 0:
            continue
        with localcontext() as ctx:
            ctx.prec = 50
            tax = quantize_minor(Decimal(net) * rule.tax_rate, rule.rounding)
        charges.append(
            FeeCharge(rule.code, Money(net, amount.currency), Money(tax, amount.currency))
        )
    return charges
