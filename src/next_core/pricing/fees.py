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
from decimal import Decimal

from next_core.platform.errors import ProductRuleViolationError
from next_core.platform.money import Money, Rounding, quantize_minor
from next_core.products.definition import FeeCalculation, FeeRule, Operation
from next_core.products.expressions import ExpressionError, Value


@dataclass(frozen=True, slots=True)
class FeeCharge:
    code: str
    net: Money
    tax: Money

    @property
    def total(self) -> Money:
        return self.net + self.tax


def _net(calc: FeeCalculation, amount: Money, env: Mapping[str, Value], rounding: Rounding) -> int:
    cur = amount.currency
    if calc.type == "FLAT":
        assert calc.amount is not None
        return calc.amount[cur]
    if calc.type == "PERCENTAGE":
        assert calc.rate is not None
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
                assert tier.rate is not None
                return quantize_minor(Decimal(amount.amount_minor) * tier.rate, rounding)
        raise ProductRuleViolationError("No fee tier covers the amount.")  # pragma: no cover
    assert calc.formula is not None
    try:
        major = calc.formula.evaluate_decimal(env)
    except ExpressionError as exc:
        raise ProductRuleViolationError(f"Fee formula failed: {exc}") from exc
    return Money.from_major_decimal(major, cur, rounding).amount_minor


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
            raise ProductRuleViolationError(f"Fee '{rule.code}' condition failed: {exc}") from exc
        net = _net(rule.calculation, amount, env, rule.rounding)
        if net < 0:
            raise ProductRuleViolationError(f"Fee '{rule.code}' computed a negative amount.")
        if net == 0:
            continue
        tax = quantize_minor(Decimal(net) * rule.tax_rate, rule.rounding)
        charges.append(
            FeeCharge(rule.code, Money(net, amount.currency), Money(tax, amount.currency))
        )
    return charges
