"""Product definition validation (pure): seed catalog validity and typed error reporting."""

import copy
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from next_core.platform.errors import ValidationFailedError
from next_core.platform.money import Money, Rounding
from next_core.pricing.interest import daily_accrual, days_in_year
from next_core.products.catalog import CURRENT_ACCOUNT, LOAN, SAVINGS, SEED_PRODUCTS
from next_core.products.definition import (
    BalanceSide,
    DayCount,
    parse_definition,
    validate_overrides,
)


@pytest.mark.parametrize("seed", SEED_PRODUCTS, ids=[s[0] for s in SEED_PRODUCTS])
def test_seed_catalog_is_valid(seed: tuple[str, str, str, dict[str, Any]]) -> None:
    parse_definition(seed[3])


def _errors(defn: dict[str, Any]) -> set[str]:
    with pytest.raises(ValidationFailedError) as info:
        parse_definition(defn)
    return {e.field for e in info.value.errors}


def test_missing_currency_amount_is_reported() -> None:
    bad = copy.deepcopy(CURRENT_ACCOUNT)
    del bad["fees"][0]["calculation"]["amount"]["XOF"]
    assert "fees[0].calculation.amount.XOF" in _errors(bad)


def test_excess_precision_in_config_rejected() -> None:
    bad = copy.deepcopy(CURRENT_ACCOUNT)
    bad["fees"][0]["calculation"]["amount"]["XOF"] = "1.5"
    assert "fees[0].calculation.amount.XOF" in _errors(bad)


def test_float_rates_are_rejected() -> None:
    bad = copy.deepcopy(SAVINGS)
    bad["parameters"]["interest_rate"]["default"] = 0.03
    assert "parameters.interest_rate.default" in _errors(bad)


def test_structural_rules() -> None:
    bad = copy.deepcopy(LOAN)
    bad["allowed_operations"] = ["DEPOSIT"]
    del bad["credit_limit_parameter"]
    errs = _errors(bad)
    assert {"allowed_operations", "credit_limit_parameter"} <= errs
    bad = copy.deepcopy(SAVINGS)
    del bad["gl_mapping"]["interest_expense"]
    assert "gl_mapping.interest_expense" in _errors(bad)
    bad = copy.deepcopy(CURRENT_ACCOUNT)
    bad["parameters"]["overdraft_limit"]["default"]["MRU"] = "999999.00"
    assert "parameters.overdraft_limit.default" in _errors(bad)


def test_overrides_respect_bounds_and_overridability() -> None:
    defn = parse_definition(CURRENT_ACCOUNT)
    ok = validate_overrides(defn, {"overdraft_limit": "100.00"}, "MRU")
    assert ok["overdraft_limit"]["MRU"] == 10_000
    for raw in ({"overdraft_limit": "999999.00"}, {"overdraft_limit": "1.001"}, {"nope": 1}):
        with pytest.raises(ValidationFailedError):
            validate_overrides(defn, raw, "MRU")
    savings = parse_definition(SAVINGS)
    assert validate_overrides(savings, {"interest_rate": "0.05"}, "EUR")[
        "interest_rate"
    ] == Decimal("0.05")
    with pytest.raises(ValidationFailedError):
        validate_overrides(savings, {"interest_rate": 0.05}, "EUR")
    assert parse_definition(LOAN).balance_side == BalanceSide.ASSET


def test_interest_day_counts() -> None:
    assert days_in_year(DayCount.ACT_ACT, date(2028, 1, 1)) == 366
    assert days_in_year(DayCount.ACT_360, date(2027, 1, 1)) == 360
    on = date(2026, 11, 25)
    assert (
        daily_accrual(3_650_000, Decimal("0.05"), DayCount.ACT_365, on, Rounding.HALF_EVEN) == 500
    )
    assert daily_accrual(-100, Decimal("0.05"), DayCount.ACT_365, on, Rounding.HALF_EVEN) == 0
    assert daily_accrual(500, Decimal("0.05"), DayCount.ACT_365, on, Rounding.HALF_EVEN, 1000) == 0


def test_money_basics() -> None:
    assert Money.from_wire("100", "XOF").to_wire() == "100"
    assert Money.from_wire("1.5", "TND").to_wire() == "1.500"
    with pytest.raises(TypeError):
        Money(1.5, "EUR")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Money(True, "EUR")
