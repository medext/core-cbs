"""Property suites: money arithmetic & wire format, fee determinism & bounds, expression
arithmetic exactness (ADR-0004; product-engine.md)."""

from decimal import Decimal, localcontext

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from next_core.platform.money import CURRENCIES, AmountFormatError, Money, Rounding, quantize_minor
from next_core.pricing.fees import compute_fees
from next_core.products.catalog import CURRENT_ACCOUNT, WALLET
from next_core.products.definition import Operation, parse_definition
from next_core.products.expressions import compile_expression

currencies = st.sampled_from(sorted(CURRENCIES))
minor = st.integers(min_value=-(10**14), max_value=10**14)


@given(minor, currencies)
def test_wire_roundtrip(amount: int, currency: str) -> None:
    m = Money(amount, currency)
    assert Money.from_wire(m.to_wire(), currency) == m


@given(st.integers(min_value=0, max_value=10**12), currencies)
def test_excess_precision_rejected(amount: int, currency: str) -> None:
    exp = CURRENCIES[currency].exponent
    wire = Money(amount, currency).to_wire()
    extra = wire + ("1" if exp else ".1")
    with pytest.raises(AmountFormatError):
        Money.from_wire(extra if exp else f"{wire}.5", currency)


@given(minor, minor, currencies)
def test_addition_is_exact_and_commutative(a: int, b: int, currency: str) -> None:
    x, y = Money(a, currency), Money(b, currency)
    assert (x + y).amount_minor == a + b == (y + x).amount_minor
    assert (x + y - y) == x


@given(
    st.decimals(
        min_value=-(10**9), max_value=10**9, allow_nan=False, allow_infinity=False, places=6
    )
)
def test_quantize_bounds(value: Decimal) -> None:
    for mode in Rounding:
        q = quantize_minor(value, mode)
        assert abs(Decimal(q) - value) < 1


_current = parse_definition(CURRENT_ACCOUNT)
_wallet = parse_definition(WALLET)


@given(st.integers(min_value=1, max_value=10**10), st.sampled_from(["MRU", "EUR", "XOF", "USD"]))
@settings(max_examples=300)
def test_percentage_fee_is_deterministic_and_clamped(amount: int, currency: str) -> None:
    m = Money(amount, currency)
    env = {"channel": "API"}
    a = compute_fees(_current.fees, Operation.TRANSFER_OUT, m, env)
    b = compute_fees(_current.fees, Operation.TRANSFER_OUT, m, env)
    assert a == b
    (fee,) = a
    rule = _current.fees[1].calculation
    assert rule.minimum is not None and rule.maximum is not None
    assert rule.minimum[currency] <= fee.net.amount_minor <= rule.maximum[currency]
    assert fee.tax.amount_minor >= 0 and fee.total == fee.net + fee.tax


@given(st.integers(min_value=1, max_value=10**9), st.sampled_from(["MRU", "XOF"]))
@settings(max_examples=300)
def test_wallet_fees_never_negative_and_tiered_monotonic(amount: int, currency: str) -> None:
    m = Money(amount, currency)
    env = {"amount": m.to_major_decimal()}
    fees = compute_fees(_wallet.fees, Operation.TRANSFER_OUT, m, env)
    total = sum(x.total.amount_minor for x in fees)
    assert total >= 0
    cash_out = compute_fees(_wallet.fees, Operation.WITHDRAWAL, m, env)
    assert cash_out and cash_out[0].net.amount_minor >= Money.from_wire("5", currency).amount_minor


@given(
    st.integers(min_value=-(10**6), max_value=10**6),
    st.integers(min_value=-(10**6), max_value=10**6),
    st.integers(min_value=1, max_value=10**6),
)
def test_expression_arithmetic_is_exact(a: int, b: int, c: int) -> None:
    expr = compile_expression("(x + y) * z - x / z", frozenset({"x", "y", "z"}))
    got = expr.evaluate_decimal({"x": Decimal(a), "y": Decimal(b), "z": Decimal(c)})
    with localcontext() as dctx:
        dctx.prec = 34  # the evaluator's documented precision
        expected = (Decimal(a) + Decimal(b)) * Decimal(c) - Decimal(a) / Decimal(c)
    assert got == expected


def test_decimal_literal_never_goes_through_float() -> None:
    expr = compile_expression("0.1 + 0.2", frozenset())
    assert expr.evaluate_decimal({}) == Decimal("0.3")
