"""Product definition schema v1 — the declarative contract of the product engine.

A product version carries one JSON document validated here into immutable typed objects.
Everything a financial product does is *configuration*: accounting side & GL mapping,
typed parameters (with account-level overrides inside bounds), allowed operations,
operation guards, fees, limits, interest, credit line, lifecycle. Money values are
per-currency maps in wire format (ADR-0004), e.g. ``{"MRU": "50.00", "XOF": "750"}``,
and must cover every currency the product supports.

Full reference with examples: docs/products/product-engine.md.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Final

from next_core.platform.errors import FieldError, ValidationFailedError
from next_core.platform.money import AmountFormatError, CurrencyError, Money, Rounding
from next_core.products.expressions import Expression, ExpressionError, compile_expression

SCHEMA_VERSION: Final = 1


class Category(StrEnum):
    CURRENT_ACCOUNT = "CURRENT_ACCOUNT"
    SAVINGS = "SAVINGS"
    TERM_DEPOSIT = "TERM_DEPOSIT"
    WALLET = "WALLET"
    LOAN = "LOAN"
    INTERNAL = "INTERNAL"


class BalanceSide(StrEnum):
    LIABILITY = "LIABILITY"  # deposits: the institution owes the customer (credit-normal)
    ASSET = "ASSET"  # lending: the customer owes the institution (debit-normal)


class Operation(StrEnum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRANSFER_OUT = "TRANSFER_OUT"
    TRANSFER_IN = "TRANSFER_IN"
    HOLD = "HOLD"
    DISBURSEMENT = "DISBURSEMENT"
    REPAYMENT = "REPAYMENT"


class LimitWindow(StrEnum):
    TRANSACTION = "TRANSACTION"
    DAILY = "DAILY"
    MONTHLY = "MONTHLY"


class DayCount(StrEnum):
    ACT_365 = "ACT_365"
    ACT_360 = "ACT_360"
    ACT_ACT = "ACT_ACT"


class Capitalization(StrEnum):
    NONE = "NONE"
    MONTHLY = "MONTHLY"
    AT_MATURITY = "AT_MATURITY"


class ParamType(StrEnum):
    MONEY = "money"
    RATE = "rate"
    INTEGER = "integer"
    BOOLEAN = "boolean"


# Variables every expression may use (plus ``param_<name>`` for declared parameters).
BASE_VARIABLES: Final = frozenset(
    {
        "amount",
        "currency",
        "operation",
        "channel",
        "kyc_level",
        "account_age_days",
        "days_to_maturity",
        "book_balance",
        "available_balance",
    }
)

GL_ROLES_REQUIRED: Final = ("principal", "cash", "fee_income", "tax_payable")
GL_ROLES_OPTIONAL: Final = ("accrued_interest", "interest_expense", "interest_income")

MoneyMap = Mapping[str, int]  # currency -> minor units


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    type: ParamType
    default: Any
    minimum: Any = None
    maximum: Any = None
    overridable: bool = False
    description: str = ""


@dataclass(frozen=True, slots=True)
class FeeTier:
    up_to: MoneyMap | None  # None = open-ended last tier
    flat: MoneyMap | None = None
    rate: Decimal | None = None


@dataclass(frozen=True, slots=True)
class FeeCalculation:
    type: str  # FLAT | PERCENTAGE | TIERED | EXPRESSION
    amount: MoneyMap | None = None
    rate: Decimal | None = None
    minimum: MoneyMap | None = None
    maximum: MoneyMap | None = None
    tiers: tuple[FeeTier, ...] = ()
    formula: Expression | None = None


@dataclass(frozen=True, slots=True)
class FeeRule:
    code: str
    operations: frozenset[Operation]
    calculation: FeeCalculation
    condition: Expression | None = None
    tax_rate: Decimal = Decimal(0)
    rounding: Rounding = Rounding.HALF_EVEN
    description: str = ""


@dataclass(frozen=True, slots=True)
class LimitRule:
    code: str
    operations: frozenset[Operation]
    window: LimitWindow
    max_amount: MoneyMap | None = None
    max_count: int | None = None


@dataclass(frozen=True, slots=True)
class OperationRule:
    code: str
    operations: frozenset[Operation]
    condition: Expression  # must evaluate True for the operation to be allowed
    message: str


@dataclass(frozen=True, slots=True)
class InterestConfig:
    rate_parameter: str
    day_count: DayCount
    capitalization: Capitalization
    minimum_balance: MoneyMap
    rounding: Rounding = Rounding.HALF_EVEN


@dataclass(frozen=True, slots=True)
class Lifecycle:
    min_kyc_level: int = 1
    min_opening_amount: MoneyMap = field(default_factory=dict)
    allow_close_with_balance: bool = False
    term_parameter: str | None = None  # integer parameter: term in days → maturity date
    dormancy_days: int | None = None


@dataclass(frozen=True, slots=True)
class ProductDefinition:
    category: Category
    balance_side: BalanceSide
    currencies: tuple[str, ...]
    gl_mapping: Mapping[str, str]
    parameters: Mapping[str, Parameter]
    allowed_operations: frozenset[Operation]
    operation_rules: tuple[OperationRule, ...]
    fees: tuple[FeeRule, ...]
    limits: tuple[LimitRule, ...]
    interest: InterestConfig | None
    overdraft_parameter: str | None
    credit_limit_parameter: str | None
    lifecycle: Lifecycle

    def money_param(self, name: str, currency: str, overrides: Mapping[str, Any]) -> int:
        param = self.parameters[name]
        if param.type != ParamType.MONEY:
            raise ValidationFailedError(f"Parameter '{name}' is not a money parameter.")
        value = overrides.get(name, param.default)
        return int(value[currency])

    def param_value(self, name: str, overrides: Mapping[str, Any]) -> Any:
        return overrides.get(name, self.parameters[name].default)

    def expression_env_params(
        self, currency: str, overrides: Mapping[str, Any]
    ) -> dict[str, Decimal | str | bool]:
        env: dict[str, Decimal | str | bool] = {}
        for name, p in self.parameters.items():
            value = overrides.get(name, p.default)
            if p.type == ParamType.MONEY:
                env[f"param_{name}"] = Money(int(value[currency]), currency).to_major_decimal()
            elif p.type == ParamType.RATE:
                env[f"param_{name}"] = Decimal(value)
            elif p.type == ParamType.INTEGER:
                env[f"param_{name}"] = Decimal(int(value))
            else:
                env[f"param_{name}"] = bool(value)
        return env


# ------------------------------------------------------------------------------ parsing


class _Parser:
    def __init__(self) -> None:
        self.errors: list[FieldError] = []
        self.currencies: tuple[str, ...] = ()
        self.variables: frozenset[str] = BASE_VARIABLES

    def err(self, path: str, message: str, code: str = "invalid") -> None:
        self.errors.append(FieldError(path, code, message))

    def obj(self, raw: Any, path: str) -> dict[str, Any]:
        if not isinstance(raw, dict):
            self.err(path, "Expected an object.")
            return {}
        return raw

    def enum(self, enum_cls: type[StrEnum], raw: Any, path: str) -> Any:
        try:
            return enum_cls(raw)
        except ValueError:
            allowed = ", ".join(e.value for e in enum_cls)
            self.err(path, f"Must be one of: {allowed}.")
            return None

    def ops(self, raw: Any, path: str) -> frozenset[Operation]:
        if not isinstance(raw, list) or not raw:
            self.err(path, "Expected a non-empty list of operations.")
            return frozenset()
        return frozenset(
            op for i, r in enumerate(raw) if (op := self.enum(Operation, r, f"{path}[{i}]"))
        )

    def rate(self, raw: Any, path: str, lo: str = "0", hi: str = "1") -> Decimal | None:
        if not isinstance(raw, str):
            self.err(path, 'Rates are decimal strings (e.g. "0.0125").')
            return None
        try:
            value = Decimal(raw)
        except InvalidOperation:
            self.err(path, "Not a decimal number.")
            return None
        if not value.is_finite() or value < Decimal(lo) or value > Decimal(hi):
            self.err(path, f"Must be between {lo} and {hi}.")
            return None
        return value

    def money_map(self, raw: Any, path: str, *, allow_negative: bool = False) -> dict[str, int]:
        if not isinstance(raw, dict):
            self.err(path, 'Expected a per-currency map, e.g. {"MRU": "10.00"}.')
            return {}
        out: dict[str, int] = {}
        for cur in self.currencies:
            if cur not in raw:
                self.err(f"{path}.{cur}", "Missing amount for a supported currency.")
        for cur, value in raw.items():
            if cur not in self.currencies:
                self.err(f"{path}.{cur}", "Currency is not supported by this product.")
                continue
            try:
                minor = Money.from_wire(value, cur).amount_minor
            except (AmountFormatError, CurrencyError, ValueError, TypeError) as exc:
                self.err(f"{path}.{cur}", str(exc))
                continue
            if minor < 0 and not allow_negative:
                self.err(f"{path}.{cur}", "Must not be negative.")
                continue
            out[cur] = minor
        return out

    def expr(self, raw: Any, path: str) -> Expression | None:
        try:
            return compile_expression(raw, self.variables)
        except ExpressionError as exc:
            self.err(path, str(exc), "invalid_expression")
            return None

    def code(self, raw: Any, path: str) -> str:
        if (
            not isinstance(raw, str)
            or not raw
            or len(raw) > 40
            or not raw.replace("_", "").isalnum()
        ):
            self.err(path, "Codes are 1-40 chars of letters, digits and underscores.")
            return ""
        return raw.upper()

    # -- sections -------------------------------------------------------------------------
    def parameter(self, name: str, raw: Any, path: str) -> Parameter | None:
        spec = self.obj(raw, path)
        ptype = self.enum(ParamType, spec.get("type"), f"{path}.type")
        if ptype is None:
            return None
        overridable = bool(spec.get("overridable", False))
        description = str(spec.get("description", ""))[:200]

        def conv(value: Any, sub: str) -> Any:
            if value is None:
                return None
            if ptype == ParamType.MONEY:
                return self.money_map(value, f"{path}.{sub}")
            if ptype == ParamType.RATE:
                return self.rate(value, f"{path}.{sub}", "-1", "10")
            if ptype == ParamType.INTEGER:
                if not isinstance(value, int) or isinstance(value, bool):
                    self.err(f"{path}.{sub}", "Expected an integer.")
                    return None
                return value
            if not isinstance(value, bool):
                self.err(f"{path}.{sub}", "Expected a boolean.")
                return None
            return value

        default = conv(spec.get("default"), "default")
        if default is None:
            self.err(f"{path}.default", "A default value is required.")
            return None
        param = Parameter(
            name=name,
            type=ptype,
            default=default,
            minimum=conv(spec.get("min"), "min"),
            maximum=conv(spec.get("max"), "max"),
            overridable=overridable,
            description=description,
        )
        for problem in check_bounds(param, default):
            self.err(f"{path}.default", problem)
        return param

    def fee(self, raw: Any, path: str) -> FeeRule | None:
        spec = self.obj(raw, path)
        code = self.code(spec.get("code"), f"{path}.code")
        operations = self.ops(spec.get("operations"), f"{path}.operations")
        calc_raw = self.obj(spec.get("calculation"), f"{path}.calculation")
        ctype = calc_raw.get("type")
        cpath = f"{path}.calculation"
        calc: FeeCalculation | None = None
        if ctype == "FLAT":
            calc = FeeCalculation(
                "FLAT", amount=self.money_map(calc_raw.get("amount"), f"{cpath}.amount")
            )
        elif ctype == "PERCENTAGE":
            calc = FeeCalculation(
                "PERCENTAGE",
                rate=self.rate(calc_raw.get("rate"), f"{cpath}.rate"),
                minimum=self.money_map(calc_raw["min"], f"{cpath}.min")
                if "min" in calc_raw
                else None,
                maximum=self.money_map(calc_raw["max"], f"{cpath}.max")
                if "max" in calc_raw
                else None,
            )
        elif ctype == "TIERED":
            tiers_raw = calc_raw.get("tiers")
            tiers: list[FeeTier] = []
            if not isinstance(tiers_raw, list) or not tiers_raw:
                self.err(f"{cpath}.tiers", "Expected a non-empty list of tiers.")
            else:
                for i, t in enumerate(tiers_raw):
                    tp = f"{cpath}.tiers[{i}]"
                    tspec = self.obj(t, tp)
                    up_to = (
                        None
                        if tspec.get("up_to") is None
                        else self.money_map(tspec["up_to"], f"{tp}.up_to")
                    )
                    if up_to is None and i != len(tiers_raw) - 1:
                        self.err(f"{tp}.up_to", "Only the last tier may be open-ended.")
                    flat = self.money_map(tspec["flat"], f"{tp}.flat") if "flat" in tspec else None
                    rate = self.rate(tspec["rate"], f"{tp}.rate") if "rate" in tspec else None
                    if (flat is None) == (rate is None):
                        self.err(tp, "A tier sets exactly one of 'flat' or 'rate'.")
                    tiers.append(FeeTier(up_to, flat, rate))
                if tiers and tiers[-1].up_to is not None:
                    self.err(f"{cpath}.tiers", "The last tier must be open-ended (up_to: null).")
                for cur in self.currencies:
                    bounds = [t.up_to[cur] for t in tiers if t.up_to and cur in t.up_to]
                    if bounds != sorted(bounds) or len(set(bounds)) != len(bounds):
                        self.err(f"{cpath}.tiers", f"Tier bounds must strictly increase ({cur}).")
            calc = FeeCalculation("TIERED", tiers=tuple(tiers))
        elif ctype == "EXPRESSION":
            calc = FeeCalculation(
                "EXPRESSION", formula=self.expr(calc_raw.get("formula"), f"{cpath}.formula")
            )
        else:
            self.err(f"{cpath}.type", "Must be one of: FLAT, PERCENTAGE, TIERED, EXPRESSION.")
        condition = (
            self.expr(spec["condition"], f"{path}.condition") if spec.get("condition") else None
        )
        tax_rate = self.rate(spec.get("tax_rate", "0"), f"{path}.tax_rate") or Decimal(0)
        rounding = self.enum(Rounding, spec.get("rounding", "HALF_EVEN"), f"{path}.rounding")
        if calc is None or rounding is None:
            return None
        return FeeRule(
            code,
            operations,
            calc,
            condition,
            tax_rate,
            rounding,
            str(spec.get("description", ""))[:200],
        )

    def limit(self, raw: Any, path: str) -> LimitRule | None:
        spec = self.obj(raw, path)
        window = self.enum(LimitWindow, spec.get("window"), f"{path}.window")
        max_amount = (
            self.money_map(spec["max_amount"], f"{path}.max_amount")
            if "max_amount" in spec
            else None
        )
        max_count = spec.get("max_count")
        if max_count is not None and (
            not isinstance(max_count, int) or isinstance(max_count, bool) or max_count < 1
        ):
            self.err(f"{path}.max_count", "Expected a positive integer.")
            max_count = None
        if max_amount is None and max_count is None:
            self.err(path, "A limit sets max_amount and/or max_count.")
        if window == LimitWindow.TRANSACTION and max_count is not None:
            self.err(f"{path}.max_count", "Per-transaction limits cannot have max_count.")
        if window is None:
            return None
        return LimitRule(
            self.code(spec.get("code"), f"{path}.code"),
            self.ops(spec.get("operations"), f"{path}.operations"),
            window,
            max_amount,
            max_count,
        )


def check_bounds(param: Parameter, value: Any) -> list[str]:
    """Bound checks shared by definition validation and account-level overrides."""
    problems: list[str] = []
    if param.type == ParamType.MONEY:
        for cur, minor in value.items():
            if param.minimum and minor < param.minimum.get(cur, minor):
                problems.append(f"{cur} value below minimum.")
            if param.maximum and minor > param.maximum.get(cur, minor):
                problems.append(f"{cur} value above maximum.")
    elif param.type in (ParamType.RATE, ParamType.INTEGER):
        if param.minimum is not None and value < param.minimum:
            problems.append("Value below minimum.")
        if param.maximum is not None and value > param.maximum:
            problems.append("Value above maximum.")
    return problems


MAX_DEFINITION_BYTES: Final = 65_536
MAX_SECTION_ITEMS: Final = 50
MAX_TIERS: Final = 20
MAX_DEPTH: Final = 8


def _depth(node: Any, level: int = 0) -> int:
    if level > MAX_DEPTH:
        return level
    if isinstance(node, dict):
        return max((_depth(v, level + 1) for v in node.values()), default=level)
    if isinstance(node, list):
        return max((_depth(v, level + 1) for v in node), default=level)
    return level


def _check_size(raw: Any) -> None:
    """Resource bounds (security review M2): size, nesting, items per section."""
    try:
        size = len(json.dumps(raw, separators=(",", ":")))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValidationFailedError("The product definition is not valid JSON.") from exc
    if size > MAX_DEFINITION_BYTES:
        raise ValidationFailedError(f"The product definition exceeds {MAX_DEFINITION_BYTES} bytes.")
    if _depth(raw) > MAX_DEPTH:
        raise ValidationFailedError(f"The product definition nests deeper than {MAX_DEPTH} levels.")
    if isinstance(raw, dict):
        for section in ("fees", "limits", "operation_rules"):
            items = raw.get(section)
            if isinstance(items, list) and len(items) > MAX_SECTION_ITEMS:
                raise ValidationFailedError(
                    f"'{section}' allows at most {MAX_SECTION_ITEMS} items."
                )
        for fee in raw.get("fees") or []:
            tiers = fee.get("calculation", {}).get("tiers") if isinstance(fee, dict) else None
            if isinstance(tiers, list) and len(tiers) > MAX_TIERS:
                raise ValidationFailedError(f"A tiered fee allows at most {MAX_TIERS} tiers.")
        params = raw.get("parameters")
        if isinstance(params, dict) and len(params) > MAX_SECTION_ITEMS:
            raise ValidationFailedError(f"At most {MAX_SECTION_ITEMS} parameters are allowed.")


def parse_definition(raw: Any) -> ProductDefinition:
    """Validate a raw definition document; raise ValidationFailedError with all field errors."""
    _check_size(raw)
    p = _Parser()
    doc = p.obj(raw, "definition")
    if doc.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
        p.err("schema_version", f"Only schema_version {SCHEMA_VERSION} is supported.")
    category = p.enum(Category, doc.get("category"), "category")
    side = p.enum(BalanceSide, doc.get("balance_side"), "balance_side")

    currencies_raw = doc.get("currencies")
    if not isinstance(currencies_raw, list) or not currencies_raw:
        p.err("currencies", "Expected a non-empty list of ISO-4217 codes.")
        currencies_raw = []
    currencies: list[str] = []
    for i, cur in enumerate(currencies_raw):
        try:
            Money.zero(cur)
            currencies.append(cur)
        except (CurrencyError, TypeError):
            p.err(f"currencies[{i}]", "Unsupported currency.")
    if len(set(currencies)) != len(currencies):
        p.err("currencies", "Duplicate currency.")
    p.currencies = tuple(currencies)

    gl_raw = p.obj(doc.get("gl_mapping"), "gl_mapping")
    gl: dict[str, str] = {}
    for role, code in gl_raw.items():
        if role not in GL_ROLES_REQUIRED + GL_ROLES_OPTIONAL:
            p.err(f"gl_mapping.{role}", "Unknown GL role.")
        elif not isinstance(code, str) or not code.isalnum():
            p.err(f"gl_mapping.{role}", "Expected a GL account code.")
        else:
            gl[role] = code
    for role in GL_ROLES_REQUIRED:
        if role not in gl:
            p.err(f"gl_mapping.{role}", "Required GL role is missing.")

    params: dict[str, Parameter] = {}
    for name, spec in p.obj(doc.get("parameters", {}), "parameters").items():
        if not name.isidentifier() or len(name) > 40:
            p.err(f"parameters.{name}", "Parameter names are identifiers (≤ 40 chars).")
            continue
        param = p.parameter(name, spec, f"parameters.{name}")
        if param:
            params[name] = param
    p.variables = BASE_VARIABLES | {f"param_{n}" for n in params}

    def need_param(name: Any, path: str, ptype: ParamType) -> str | None:
        if name is None:
            return None
        if name not in params or params[name].type != ptype:
            p.err(path, f"Must name a declared '{ptype.value}' parameter.")
            return None
        return str(name)

    allowed_ops = p.ops(doc.get("allowed_operations"), "allowed_operations")
    rules = tuple(
        OperationRule(
            p.code(r.get("code"), f"operation_rules[{i}].code"),
            p.ops(r.get("operations"), f"operation_rules[{i}].operations"),
            cond,
            str(r.get("message", "Operation refused by product rule."))[:200],
        )
        for i, r in enumerate(doc.get("operation_rules", []) or [])
        if isinstance(r, dict)
        and (cond := p.expr(r.get("condition"), f"operation_rules[{i}].condition"))
    )
    fees = tuple(
        f
        for i, raw_fee in enumerate(doc.get("fees", []) or [])
        if (f := p.fee(raw_fee, f"fees[{i}]"))
    )
    limits = tuple(
        lim
        for i, raw_lim in enumerate(doc.get("limits", []) or [])
        if (lim := p.limit(raw_lim, f"limits[{i}]"))
    )
    for kind, items in (("fees", fees), ("limits", limits), ("operation_rules", rules)):
        codes = [x.code for x in items]
        if len(codes) != len(set(codes)):
            p.err(kind, "Codes must be unique.")

    interest: InterestConfig | None = None
    if doc.get("interest"):
        ispec = p.obj(doc["interest"], "interest")
        rate_param = need_param(
            ispec.get("rate_parameter"), "interest.rate_parameter", ParamType.RATE
        )
        day_count = p.enum(DayCount, ispec.get("day_count", "ACT_365"), "interest.day_count")
        cap = p.enum(
            Capitalization, ispec.get("capitalization", "MONTHLY"), "interest.capitalization"
        )
        rounding = p.enum(Rounding, ispec.get("rounding", "HALF_EVEN"), "interest.rounding")
        min_bal = p.money_map(
            ispec.get("minimum_balance", dict.fromkeys(currencies, "0")), "interest.minimum_balance"
        )
        for role in (
            "accrued_interest",
            "interest_expense" if side == BalanceSide.LIABILITY else "interest_income",
        ):
            if role not in gl:
                p.err(f"gl_mapping.{role}", "Required when interest is configured.")
        if rate_param and day_count and cap and rounding:
            interest = InterestConfig(rate_param, day_count, cap, min_bal, rounding)

    overdraft = need_param(doc.get("overdraft_parameter"), "overdraft_parameter", ParamType.MONEY)
    credit = need_param(
        doc.get("credit_limit_parameter"), "credit_limit_parameter", ParamType.MONEY
    )
    if overdraft and side != BalanceSide.LIABILITY:
        p.err("overdraft_parameter", "Overdrafts apply to LIABILITY (deposit) products only.")
    if side == BalanceSide.ASSET and not credit:
        p.err(
            "credit_limit_parameter", "ASSET (lending) products require a credit limit parameter."
        )
    if side == BalanceSide.LIABILITY and credit:
        p.err("credit_limit_parameter", "Credit limits apply to ASSET (lending) products only.")
    lending_ops = {Operation.DISBURSEMENT, Operation.REPAYMENT}
    if side == BalanceSide.LIABILITY and allowed_ops & lending_ops:
        p.err("allowed_operations", "DISBURSEMENT/REPAYMENT are lending operations (ASSET side).")
    if side == BalanceSide.ASSET and allowed_ops - lending_ops:
        p.err("allowed_operations", "Lending products allow only DISBURSEMENT and REPAYMENT.")

    lspec = p.obj(doc.get("lifecycle", {}), "lifecycle")
    min_kyc = lspec.get("min_kyc_level", 1)
    if not isinstance(min_kyc, int) or isinstance(min_kyc, bool) or not 0 <= min_kyc <= 3:
        p.err("lifecycle.min_kyc_level", "Expected an integer between 0 and 3.")
        min_kyc = 1
    dormancy = lspec.get("dormancy_days")
    if dormancy is not None and (not isinstance(dormancy, int) or dormancy < 1):
        p.err("lifecycle.dormancy_days", "Expected a positive integer.")
    lifecycle = Lifecycle(
        min_kyc_level=min_kyc,
        min_opening_amount=(
            p.money_map(lspec["min_opening_amount"], "lifecycle.min_opening_amount")
            if "min_opening_amount" in lspec
            else dict.fromkeys(currencies, 0)
        ),
        allow_close_with_balance=bool(lspec.get("allow_close_with_balance", False)),
        term_parameter=need_param(
            lspec.get("term_parameter"), "lifecycle.term_parameter", ParamType.INTEGER
        ),
        dormancy_days=dormancy if isinstance(dormancy, int) else None,
    )

    if p.errors or category is None or side is None:
        raise ValidationFailedError("The product definition is invalid.", errors=p.errors)
    return ProductDefinition(
        category=category,
        balance_side=side,
        currencies=p.currencies,
        gl_mapping=gl,
        parameters=params,
        allowed_operations=allowed_ops,
        operation_rules=rules,
        fees=fees,
        limits=limits,
        interest=interest,
        overdraft_parameter=overdraft,
        credit_limit_parameter=credit,
        lifecycle=lifecycle,
    )


def validate_overrides(definition: ProductDefinition, raw: Any, currency: str) -> dict[str, Any]:
    """Account-level parameter overrides: only declared + overridable + within bounds."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValidationFailedError("parameter_overrides must be an object.")
    errors: list[FieldError] = []
    out: dict[str, Any] = {}
    for name, value in raw.items():
        path = f"parameter_overrides.{name}"
        param = definition.parameters.get(name)
        if param is None or not param.overridable:
            errors.append(
                FieldError(path, "not_overridable", "Unknown or non-overridable parameter.")
            )
            continue
        try:
            if param.type == ParamType.MONEY:
                minor = Money.from_wire(value, currency).amount_minor
                converted: Any = {**param.default, currency: minor}
            elif param.type == ParamType.RATE:
                converted = Decimal(str(value)) if isinstance(value, str) else None
                if converted is None:
                    raise ValueError("Rates are decimal strings.")
            elif param.type == ParamType.INTEGER:
                if not isinstance(value, int) or isinstance(value, bool):
                    raise ValueError("Expected an integer.")
                converted = value
            else:
                if not isinstance(value, bool):
                    raise ValueError("Expected a boolean.")
                converted = value
        except (AmountFormatError, ValueError, InvalidOperation) as exc:
            errors.append(FieldError(path, "invalid", str(exc)))
            continue
        for problem in check_bounds(
            param, {currency: converted[currency]} if param.type == ParamType.MONEY else converted
        ):
            errors.append(FieldError(path, "out_of_bounds", problem))
        out[name] = converted
    if errors:
        raise ValidationFailedError("Invalid parameter overrides.", errors=errors)
    return out


def overrides_to_json(
    definition: ProductDefinition, overrides: Mapping[str, Any]
) -> dict[str, Any]:
    """Serialize validated overrides (Decimal → str) for JSON storage."""
    out: dict[str, Any] = {}
    for name, value in overrides.items():
        out[name] = str(value) if definition.parameters[name].type == ParamType.RATE else value
    return out


def overrides_from_json(definition: ProductDefinition, stored: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, value in stored.items():
        param = definition.parameters.get(name)
        if param is None:  # pragma: no cover - versions are immutable; defensive
            continue
        if param.type == ParamType.RATE:
            out[name] = Decimal(value)
        elif param.type == ParamType.MONEY:
            out[name] = {k: int(v) for k, v in value.items()}
        else:
            out[name] = value
    return out
