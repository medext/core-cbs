"""Money and currency primitives (ADR-0004).

- Storage and domain: integer **minor units** + ISO-4217 code. ``float`` is never accepted.
- Computation boundary: ``decimal.Decimal`` for rates, quantized exactly once to minor units
  with an explicit rounding mode (default round-half-even).
- Wire format: decimal string in major units with at most the currency's exponent digits.

This module is part of the shared kernel: zero business policy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_UP, Decimal, localcontext
from enum import StrEnum
from typing import Final


class CurrencyError(ValueError):
    """Unknown/unsupported currency, or an operation mixing currencies."""


class AmountFormatError(ValueError):
    """A wire amount is malformed or carries more precision than the currency allows."""


@dataclass(frozen=True, slots=True)
class Currency:
    code: str
    exponent: int
    name: str


# Supported currencies (OD-1 confirmed 2026-11-25: MRU, XOF, EUR, USD are the seed set).
# TND (exponent 3) is registered so the 0/2/3-exponent matrix is exercised by tests and
# available to institutions that need it. Exponents per ISO 4217.
CURRENCIES: Final[dict[str, Currency]] = {
    c.code: c
    for c in (
        Currency("MRU", 2, "Mauritanian ouguiya"),
        Currency("XOF", 0, "CFA franc BCEAO"),
        Currency("EUR", 2, "Euro"),
        Currency("USD", 2, "US dollar"),
        Currency("TND", 3, "Tunisian dinar"),
    )
}

# Sanity ceiling (ADR-0004 consequence): no single amount above 10^15 minor units.
MAX_ABS_MINOR: Final[int] = 10**15

_WIRE_RE = re.compile(r"^(-)?(\d{1,16})(?:\.(\d{1,6}))?$")


def get_currency(code: str) -> Currency:
    try:
        return CURRENCIES[code]
    except KeyError as exc:
        raise CurrencyError(f"Unsupported currency '{code}'.") from exc


class Rounding(StrEnum):
    HALF_EVEN = "HALF_EVEN"
    HALF_UP = "HALF_UP"
    UP = "UP"
    DOWN = "DOWN"


_ROUNDING_MODES: Final[dict[Rounding, str]] = {
    Rounding.HALF_EVEN: ROUND_HALF_EVEN,
    Rounding.HALF_UP: ROUND_HALF_UP,
    Rounding.UP: ROUND_UP,
    Rounding.DOWN: ROUND_DOWN,
}


def quantize_minor(value: Decimal, rounding: Rounding = Rounding.HALF_EVEN) -> int:
    """Quantize a Decimal expressed in **minor units** to an integer, exactly once."""
    if not isinstance(value, Decimal):
        raise TypeError("quantize_minor accepts Decimal only (never float).")
    if not value.is_finite():
        raise ValueError("Cannot quantize a non-finite value.")
    with localcontext() as ctx:
        ctx.prec = 50
        return int(value.quantize(Decimal(1), rounding=_ROUNDING_MODES[rounding]))


@dataclass(frozen=True, slots=True, order=False)
class Money:
    """Immutable money value: integer minor units + currency code."""

    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if type(self.amount_minor) is not int:  # rejects bool, float, Decimal
            raise TypeError("Money.amount_minor must be an int (minor units).")
        get_currency(self.currency)
        if abs(self.amount_minor) > MAX_ABS_MINOR:
            raise ValueError("Amount exceeds the configured sanity ceiling.")

    # -- construction ---------------------------------------------------------------------
    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(0, currency)

    @classmethod
    def from_wire(cls, raw: str, currency: str) -> Money:
        """Parse a decimal string in major units; reject excess precision."""
        if not isinstance(raw, str):
            raise AmountFormatError("Amounts must be decimal strings.")
        cur = get_currency(currency)
        match = _WIRE_RE.match(raw.strip())
        if not match:
            raise AmountFormatError(f"'{raw}' is not a valid decimal amount.")
        sign, whole, frac = match.group(1), match.group(2), match.group(3) or ""
        if len(frac) > cur.exponent:
            raise AmountFormatError(
                f"{currency} allows at most {cur.exponent} decimal place(s); got '{raw}'."
            )
        minor = int(whole) * 10**cur.exponent + (int(frac.ljust(cur.exponent, "0")) if frac else 0)
        return cls(-minor if sign else minor, currency)

    @classmethod
    def from_major_decimal(
        cls, value: Decimal, currency: str, rounding: Rounding = Rounding.HALF_EVEN
    ) -> Money:
        cur = get_currency(currency)
        return cls(quantize_minor(value * (Decimal(10) ** cur.exponent), rounding), currency)

    # -- representation -------------------------------------------------------------------
    def to_wire(self) -> str:
        exp = get_currency(self.currency).exponent
        sign = "-" if self.amount_minor < 0 else ""
        digits = abs(self.amount_minor)
        if exp == 0:
            return f"{sign}{digits}"
        whole, frac = divmod(digits, 10**exp)
        return f"{sign}{whole}.{frac:0{exp}d}"

    def to_major_decimal(self) -> Decimal:
        return Decimal(self.amount_minor).scaleb(-get_currency(self.currency).exponent)

    def __str__(self) -> str:
        return f"{self.to_wire()} {self.currency}"

    # -- arithmetic (same currency only) --------------------------------------------------
    def _check(self, other: Money) -> None:
        if not isinstance(other, Money):
            raise TypeError("Money arithmetic requires Money operands.")
        if other.currency != self.currency:
            raise CurrencyError(f"Currency mismatch: {self.currency} vs {other.currency}.")

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount_minor, self.currency)

    def __lt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount_minor < other.amount_minor

    def __le__(self, other: Money) -> bool:
        self._check(other)
        return self.amount_minor <= other.amount_minor

    def __gt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount_minor > other.amount_minor

    def __ge__(self, other: Money) -> bool:
        self._check(other)
        return self.amount_minor >= other.amount_minor

    @property
    def is_zero(self) -> bool:
        return self.amount_minor == 0

    @property
    def is_positive(self) -> bool:
        return self.amount_minor > 0
