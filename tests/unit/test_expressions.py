"""The restricted expression language is a sandbox: everything not whitelisted is refused at
compile time; evaluation is pure Decimal arithmetic (security rules: no eval/exec)."""

from decimal import Decimal

import pytest

from next_core.products.expressions import ExpressionError, compile_expression

NAMES = frozenset({"amount", "currency", "kyc_level", "param_cap"})


@pytest.mark.parametrize(
    "source",
    [
        "__import__('os').system('id')",
        "amount.__class__",
        "open('/etc/passwd')",
        "[x for x in (1, 2)]",
        "lambda: 1",
        "amount ** 1000",
        "amount << 2",
        "amount[0]",
        "f'{amount}'",
        "unknown_name > 1",
        "max(amount, key=1)",
        "None",
        "(amount := 1)",
        "1j",
        "x" * 600,
        " + ".join(["1"] * 80),
    ],
)
def test_refused_constructs(source: str) -> None:
    with pytest.raises(ExpressionError):
        compile_expression(source, NAMES)


def test_evaluation_semantics() -> None:
    env: dict[str, Decimal | str | bool] = {
        "amount": Decimal("150.50"),
        "currency": "MRU",
        "kyc_level": Decimal(1),
        "param_cap": Decimal(100),
    }
    assert compile_expression("amount > param_cap and currency == 'MRU'", NAMES).evaluate_bool(env)
    assert compile_expression("currency in ('MRU', 'XOF')", NAMES).evaluate_bool(env)
    assert compile_expression("0 < kyc_level <= 2", NAMES).evaluate_bool(env)
    assert compile_expression("max(amount * 0.01, 5)", NAMES).evaluate_decimal(env) == Decimal("5")
    assert compile_expression("10 if kyc_level < 2 else 0", NAMES).evaluate_decimal(env) == 10
    assert compile_expression("abs(-amount)", NAMES).evaluate_decimal(env) == Decimal("150.50")
    assert compile_expression("not (amount < 1)", NAMES).evaluate_bool(env)


@pytest.mark.parametrize(
    ("source", "env"),
    [
        ("amount / 0", {"amount": Decimal(1)}),
        ("amount + currency", {"amount": Decimal(1), "currency": "MRU"}),
        ("currency > 'A'", {"currency": "MRU"}),
        ("amount and True", {"amount": Decimal(1)}),
        ("amount", {}),
        ("abs(amount, amount)", {"amount": Decimal(1)}),
    ],
)
def test_runtime_errors_are_typed(source: str, env: dict[str, Decimal | str]) -> None:
    with pytest.raises(ExpressionError):
        compile_expression(source, NAMES).evaluate(env)


def test_type_of_result_is_checked() -> None:
    with pytest.raises(ExpressionError):
        compile_expression("amount", NAMES).evaluate_bool({"amount": Decimal(1)})
    with pytest.raises(ExpressionError):
        compile_expression("amount > 1", NAMES).evaluate_decimal({"amount": Decimal(2)})
