"""Deterministic interest accrual (pure).

Daily accrual = balance * annual_rate / days_in_year(day_count), quantized once per day
with the product's rounding. Accrual applies when the accruing figure is ≥ the product's
minimum balance and > 0. (Higher-precision accrual carry-forward is registered as OD-31.)
"""

import calendar
from datetime import date
from decimal import Decimal, localcontext

from next_core.platform.money import Rounding, quantize_minor
from next_core.products.definition import DayCount


def days_in_year(day_count: DayCount, on: date) -> int:
    if day_count == DayCount.ACT_360:
        return 360
    if day_count == DayCount.ACT_ACT:
        return 366 if calendar.isleap(on.year) else 365
    return 365


def daily_accrual(
    balance_minor: int,
    annual_rate: Decimal,
    day_count: DayCount,
    on: date,
    rounding: Rounding,
    minimum_balance_minor: int = 0,
) -> int:
    if balance_minor <= 0 or balance_minor < minimum_balance_minor or annual_rate <= 0:
        return 0
    with localcontext() as ctx:
        ctx.prec = 50  # exact quotient before the single quantization
        return quantize_minor(
            Decimal(balance_minor) * annual_rate / Decimal(days_in_year(day_count, on)), rounding
        )
