"""Restricted expression language for product rules (OD-11 → ADR-0010).

Product configurations may carry small expressions — fee conditions, fee formulas,
operation guards — e.g. ``amount >= 100000 and kyc_level < 2`` or ``max(amount * 0.01, 5)``.
This is NOT Python execution. Expressions are parsed with ``ast`` and then interpreted by a
whitelist evaluator:

- allowed: literals (int / decimal / string / bool), declared variable names, arithmetic
  ``+ - * /``, comparisons (incl. chained, ``in``/``not in`` against literal lists),
  ``and``/``or``/``not``, ``x if cond else y``, and the functions ``min``, ``max``, ``abs``;
- refused at compile time: attribute access, subscripts, any other call, lambdas,
  comprehensions, ``**``, bit operations, assignments, f-strings, unknown names;
- numbers are ``Decimal`` from the literal's source text — a float never exists;
- bounded: ≤ 500 characters, ≤ 120 AST nodes; evaluation is pure and deterministic.

Nothing here calls ``eval``/``exec``/``compile`` on user content (security rules).
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, DecimalException, localcontext
from typing import Any, Final

MAX_LENGTH: Final = 500
MAX_NODES: Final = 120

Value = Decimal | str | bool


class ExpressionError(ValueError):
    """Invalid expression (compile time) or invalid evaluation (runtime)."""


_BIN_OPS: Final[dict[type[ast.operator], Callable[[Decimal, Decimal], Decimal]]] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}
_CMP_OPS: Final[dict[type[ast.cmpop], Callable[[Any, Any], bool]]] = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}
_FUNCS: Final = frozenset({"min", "max", "abs"})
_ALLOWED: Final = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.BinOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.IfExp,
    ast.Call,
    ast.List,
    ast.Tuple,
    *_BIN_OPS.keys(),
    *_CMP_OPS.keys(),
)


@dataclass(frozen=True, slots=True)
class Expression:
    source: str
    tree: ast.Expression
    names: frozenset[str]

    def evaluate(self, env: Mapping[str, Value]) -> Value:
        missing = self.names - env.keys()
        if missing:
            raise ExpressionError(f"Unbound variable(s): {', '.join(sorted(missing))}.")
        with localcontext() as ctx:
            ctx.prec = 34
            ctx.Emax, ctx.Emin = 30, -30  # bounded magnitude: overflow is an error, not a hang
            try:
                result: Value = _Evaluator(self.source, env).visit(self.tree.body)
                return result
            except DecimalException as exc:
                raise ExpressionError(f"Arithmetic error in '{self.source}'.") from exc

    def evaluate_bool(self, env: Mapping[str, Value]) -> bool:
        result = self.evaluate(env)
        if not isinstance(result, bool):
            raise ExpressionError(f"Condition '{self.source}' must evaluate to a boolean.")
        return result

    def evaluate_decimal(self, env: Mapping[str, Value]) -> Decimal:
        result = self.evaluate(env)
        if isinstance(result, bool) or not isinstance(result, Decimal):
            raise ExpressionError(f"Formula '{self.source}' must evaluate to a number.")
        return result


def compile_expression(source: str, allowed_names: frozenset[str]) -> Expression:
    if not isinstance(source, str) or not source.strip():
        raise ExpressionError("Expression must be a non-empty string.")
    if len(source) > MAX_LENGTH:
        raise ExpressionError(f"Expression exceeds {MAX_LENGTH} characters.")
    try:
        tree = ast.parse(source.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"Syntax error in expression: {exc.msg}.") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_NODES:
        raise ExpressionError(f"Expression exceeds {MAX_NODES} nodes.")
    names: set[str] = set()
    for node in nodes:
        if not isinstance(node, _ALLOWED):
            raise ExpressionError(f"Construct '{type(node).__name__}' is not allowed.")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
                raise ExpressionError("Only min(), max() and abs() calls are allowed.")
            if node.keywords or not node.args:
                raise ExpressionError("Function calls take positional arguments only.")
        elif isinstance(node, ast.Name) and not _is_call_target(node, nodes):
            if node.id not in allowed_names:
                raise ExpressionError(f"Unknown variable '{node.id}'.")
            names.add(node.id)
        elif isinstance(node, ast.Constant):
            if not isinstance(node.value, int | float | str):
                raise ExpressionError("Only number, string and boolean literals are allowed.")
            if isinstance(node.value, int | float) and not isinstance(node.value, bool):
                _check_literal(ast.get_source_segment(source.strip(), node) or "")
    return Expression(source.strip(), tree, frozenset(names))


MAX_LITERAL_DIGITS: Final = 24
MAX_LITERAL_EXPONENT: Final = 18


def _check_literal(text: str) -> None:
    try:
        value = Decimal(text.replace("_", ""))
    except DecimalException as exc:
        raise ExpressionError(f"Invalid numeric literal '{text[:20]}'.") from exc
    digits = value.as_tuple().digits
    if (
        not value.is_finite()
        or len(digits) > MAX_LITERAL_DIGITS
        or abs(value.adjusted()) > MAX_LITERAL_EXPONENT
    ):
        raise ExpressionError("Numeric literal out of bounds (|exponent| <= 18, <= 24 digits).")


def _is_call_target(name: ast.Name, nodes: list[ast.AST]) -> bool:
    return any(isinstance(n, ast.Call) and n.func is name for n in nodes)


class _Evaluator:
    def __init__(self, source: str, env: Mapping[str, Value]) -> None:
        self.source = source.strip()
        self.env = env

    def visit(self, node: ast.expr) -> Any:
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, bool | str):
                return value
            # Decimal from the literal's *source text*: 0.1 is exactly 0.1, never a float.
            segment = ast.get_source_segment(self.source, node)
            if segment is None:  # pragma: no cover - parser always gives positions
                raise ExpressionError("Cannot resolve literal.")
            return Decimal(segment.replace("_", ""))
        if isinstance(node, ast.Name):
            bound = self.env[node.id]
            return (
                Decimal(bound) if isinstance(bound, int) and not isinstance(bound, bool) else bound
            )
        if isinstance(node, ast.UnaryOp):
            operand = self.visit(node.operand)
            if isinstance(node.op, ast.Not):
                return not self._bool(operand)
            num = self._num(operand)
            return -num if isinstance(node.op, ast.USub) else +num
        if isinstance(node, ast.BinOp):
            return _BIN_OPS[type(node.op)](
                self._num(self.visit(node.left)), self._num(self.visit(node.right))
            )
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(self._bool(self.visit(v)) for v in node.values)
            return any(self._bool(self.visit(v)) for v in node.values)
        if isinstance(node, ast.Compare):
            left = self.visit(node.left)
            for op, comparator in zip(node.ops, node.comparators, strict=True):
                right = self.visit(comparator)
                self._comparable(left, right, op)
                if not _CMP_OPS[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return (
                self.visit(node.body)
                if self._bool(self.visit(node.test))
                else self.visit(node.orelse)
            )
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):  # pragma: no cover - compile-time guard
                raise ExpressionError("Only named function calls are allowed.")
            args = [self._num(self.visit(a)) for a in node.args]
            if node.func.id == "abs":
                if len(args) != 1:
                    raise ExpressionError("abs() takes exactly one argument.")
                return abs(args[0])
            return min(args) if node.func.id == "min" else max(args)
        if isinstance(node, ast.List | ast.Tuple):
            return tuple(self.visit(e) for e in node.elts)
        raise ExpressionError(f"Unsupported construct '{type(node).__name__}'.")  # pragma: no cover

    @staticmethod
    def _num(value: Any) -> Decimal:
        if isinstance(value, bool) or not isinstance(value, Decimal):
            raise ExpressionError("Arithmetic requires numeric operands.")
        return value

    @staticmethod
    def _bool(value: Any) -> bool:
        if not isinstance(value, bool):
            raise ExpressionError("Logical operators require boolean operands.")
        return value

    @staticmethod
    def _comparable(left: Any, right: Any, op: ast.cmpop) -> None:
        if isinstance(op, ast.In | ast.NotIn):
            if not isinstance(right, tuple):
                raise ExpressionError("'in' requires a literal list on the right.")
            return
        numeric = isinstance(left, Decimal) and isinstance(right, Decimal)
        textual = isinstance(left, str) and isinstance(right, str)
        boolean = isinstance(left, bool) and isinstance(right, bool)
        if not (numeric or textual or boolean):
            raise ExpressionError("Comparison operands must have the same type.")
        if (textual or boolean) and not isinstance(op, ast.Eq | ast.NotEq):
            raise ExpressionError("Strings and booleans support only == and !=.")
