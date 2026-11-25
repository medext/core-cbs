"""Seed chart of accounts and seed product catalog (demo institution, OD-1: MRU/XOF/EUR/USD).

These are *configuration documents*, exactly what an institution would submit through the
product API — no product behavior is coded anywhere. They double as executable examples
for docs/products/product-engine.md.
"""

from typing import Any

from next_core.ledger.application import GLSeed
from next_core.ledger.domain import GLType

SEED_CURRENCIES = ("MRU", "XOF", "EUR", "USD")

SEED_COA: tuple[GLSeed, ...] = (
    GLSeed("1000", "Assets", GLType.ASSET),
    GLSeed("1010", "Vault cash", GLType.ASSET, "1000"),
    GLSeed("1210", "Settlement account", GLType.ASSET, "1000"),
    GLSeed("1300", "Loans to customers", GLType.ASSET, "1000"),
    GLSeed("1310", "Accrued interest receivable", GLType.ASSET, "1000"),
    GLSeed("2000", "Liabilities", GLType.LIABILITY),
    GLSeed("2110", "Current accounts", GLType.LIABILITY, "2000"),
    GLSeed("2120", "Savings deposits", GLType.LIABILITY, "2000"),
    GLSeed("2130", "Term deposits", GLType.LIABILITY, "2000"),
    GLSeed("2140", "E-money wallets", GLType.LIABILITY, "2000"),
    GLSeed("2150", "Accrued interest payable", GLType.LIABILITY, "2000"),
    GLSeed("2400", "Tax payable", GLType.LIABILITY, "2000"),
    GLSeed("2900", "Suspense", GLType.LIABILITY, "2000"),
    GLSeed("3100", "Share capital", GLType.EQUITY),
    GLSeed("4100", "Fee income", GLType.INCOME),
    GLSeed("4200", "Interest income", GLType.INCOME),
    GLSeed("5100", "Interest expense", GLType.EXPENSE),
)

# Major-unit amounts per currency for a nominal "unit" — keeps seed numbers comparable.
_SCALE = {"MRU": 40, "XOF": 600, "EUR": 1, "USD": 1}


def per_currency(eur_amount: str) -> dict[str, str]:
    """Express an amount given in EUR-equivalent units per seed currency (wire format)."""
    from decimal import Decimal

    base = Decimal(eur_amount)
    out: dict[str, str] = {}
    for cur, factor in _SCALE.items():
        value = base * factor
        out[cur] = f"{value:.0f}" if cur == "XOF" else f"{value:.2f}"
    return out


def _common_gl(principal: str) -> dict[str, str]:
    return {"principal": principal, "cash": "1010", "fee_income": "4100", "tax_payable": "2400"}


CURRENT_ACCOUNT: dict[str, Any] = {
    "schema_version": 1,
    "category": "CURRENT_ACCOUNT",
    "balance_side": "LIABILITY",
    "currencies": list(SEED_CURRENCIES),
    "gl_mapping": _common_gl("2110"),
    "parameters": {
        "overdraft_limit": {
            "type": "money",
            "default": per_currency("0"),
            "min": per_currency("0"),
            "max": per_currency("5000"),
            "overridable": True,
            "description": "Authorized overdraft (negative headroom).",
        }
    },
    "overdraft_parameter": "overdraft_limit",
    "allowed_operations": ["DEPOSIT", "WITHDRAWAL", "TRANSFER_OUT", "TRANSFER_IN", "HOLD"],
    "fees": [
        {
            "code": "WITHDRAWAL_FEE",
            "operations": ["WITHDRAWAL"],
            "calculation": {"type": "FLAT", "amount": per_currency("0.50")},
            "tax_rate": "0.16",
            "description": "Cash withdrawal fee + 16% tax.",
        },
        {
            "code": "TRANSFER_FEE",
            "operations": ["TRANSFER_OUT"],
            "calculation": {
                "type": "PERCENTAGE",
                "rate": "0.005",
                "min": per_currency("0.10"),
                "max": per_currency("10"),
            },
            "condition": "channel != 'BRANCH'",
            "tax_rate": "0.16",
        },
    ],
    "limits": [
        {
            "code": "DAILY_OUT",
            "operations": ["WITHDRAWAL", "TRANSFER_OUT"],
            "window": "DAILY",
            "max_amount": per_currency("10000"),
            "max_count": 50,
        }
    ],
    "lifecycle": {"min_kyc_level": 1, "min_opening_amount": per_currency("0")},
}

SAVINGS: dict[str, Any] = {
    "schema_version": 1,
    "category": "SAVINGS",
    "balance_side": "LIABILITY",
    "currencies": list(SEED_CURRENCIES),
    "gl_mapping": {
        **_common_gl("2120"),
        "accrued_interest": "2150",
        "interest_expense": "5100",
    },
    "parameters": {
        "interest_rate": {
            "type": "rate",
            "default": "0.0300",
            "min": "0",
            "max": "0.0800",
            "overridable": True,
            "description": "Nominal annual rate.",
        }
    },
    "allowed_operations": ["DEPOSIT", "WITHDRAWAL", "TRANSFER_OUT", "TRANSFER_IN"],
    "interest": {
        "rate_parameter": "interest_rate",
        "day_count": "ACT_365",
        "capitalization": "MONTHLY",
        "minimum_balance": per_currency("10"),
    },
    "limits": [
        {
            "code": "MONTHLY_WITHDRAWALS",
            "operations": ["WITHDRAWAL", "TRANSFER_OUT"],
            "window": "MONTHLY",
            "max_count": 4,
        }
    ],
    "lifecycle": {"min_kyc_level": 1, "min_opening_amount": per_currency("20")},
}

TERM_DEPOSIT: dict[str, Any] = {
    "schema_version": 1,
    "category": "TERM_DEPOSIT",
    "balance_side": "LIABILITY",
    "currencies": list(SEED_CURRENCIES),
    "gl_mapping": {
        **_common_gl("2130"),
        "accrued_interest": "2150",
        "interest_expense": "5100",
    },
    "parameters": {
        "interest_rate": {"type": "rate", "default": "0.0500", "min": "0", "max": "0.1200"},
        "term_days": {
            "type": "integer",
            "default": 180,
            "min": 30,
            "max": 1825,
            "overridable": True,
        },
    },
    "allowed_operations": ["DEPOSIT", "TRANSFER_IN", "TRANSFER_OUT", "WITHDRAWAL"],
    "operation_rules": [
        {
            "code": "LOCKED_UNTIL_MATURITY",
            "operations": ["WITHDRAWAL", "TRANSFER_OUT"],
            "condition": "days_to_maturity <= 0",
            "message": "Funds are locked until the maturity date.",
        },
        {
            "code": "SINGLE_FUNDING",
            "operations": ["DEPOSIT", "TRANSFER_IN"],
            "condition": "book_balance == 0",
            "message": "A term deposit is funded once, at opening.",
        },
    ],
    "interest": {
        "rate_parameter": "interest_rate",
        "day_count": "ACT_365",
        "capitalization": "AT_MATURITY",
        "minimum_balance": per_currency("0"),
    },
    "lifecycle": {
        "min_kyc_level": 1,
        "min_opening_amount": per_currency("500"),
        "term_parameter": "term_days",
    },
}

WALLET: dict[str, Any] = {
    "schema_version": 1,
    "category": "WALLET",
    "balance_side": "LIABILITY",
    "currencies": ["MRU", "XOF"],
    "gl_mapping": _common_gl("2140"),
    "parameters": {
        "tier0_max_balance": {
            "type": "money",
            "default": {"MRU": "8000.00", "XOF": "120000"},
            "description": "Max book balance for unverified (KYC 0) wallets.",
        }
    },
    "allowed_operations": ["DEPOSIT", "WITHDRAWAL", "TRANSFER_OUT", "TRANSFER_IN", "HOLD"],
    "operation_rules": [
        {
            "code": "KYC0_BALANCE_CAP",
            "operations": ["DEPOSIT", "TRANSFER_IN"],
            "condition": "kyc_level >= 1 or book_balance + amount <= param_tier0_max_balance",
            "message": "Unverified wallets cannot exceed the tier-0 balance cap.",
        }
    ],
    "fees": [
        {
            "code": "P2P_FEE",
            "operations": ["TRANSFER_OUT"],
            "calculation": {
                "type": "TIERED",
                "tiers": [
                    {
                        "up_to": {"MRU": "200.00", "XOF": "3000"},
                        "flat": {"MRU": "0.00", "XOF": "0"},
                    },
                    {"up_to": {"MRU": "4000.00", "XOF": "60000"}, "rate": "0.01"},
                    {"up_to": None, "flat": {"MRU": "50.00", "XOF": "750"}},
                ],
            },
            "rounding": "UP",
        },
        {
            "code": "CASH_OUT_FEE",
            "operations": ["WITHDRAWAL"],
            "calculation": {"type": "EXPRESSION", "formula": "max(amount * 0.015, 5)"},
        },
    ],
    "limits": [
        {
            "code": "SINGLE_TXN_MAX",
            "operations": ["WITHDRAWAL", "TRANSFER_OUT"],
            "window": "TRANSACTION",
            "max_amount": {"MRU": "20000.00", "XOF": "300000"},
        },
        {
            "code": "DAILY_OUT",
            "operations": ["WITHDRAWAL", "TRANSFER_OUT"],
            "window": "DAILY",
            "max_amount": {"MRU": "40000.00", "XOF": "600000"},
            "max_count": 20,
        },
    ],
    "lifecycle": {"min_kyc_level": 0},
}

LOAN: dict[str, Any] = {
    "schema_version": 1,
    "category": "LOAN",
    "balance_side": "ASSET",
    "currencies": list(SEED_CURRENCIES),
    "gl_mapping": {
        **_common_gl("1300"),
        "accrued_interest": "1310",
        "interest_income": "4200",
    },
    "parameters": {
        "credit_limit": {
            "type": "money",
            "default": per_currency("1000"),
            "min": per_currency("50"),
            "max": per_currency("50000"),
            "overridable": True,
        },
        "interest_rate": {
            "type": "rate",
            "default": "0.1200",
            "min": "0",
            "max": "0.3000",
            "overridable": True,
        },
    },
    "credit_limit_parameter": "credit_limit",
    "allowed_operations": ["DISBURSEMENT", "REPAYMENT"],
    "fees": [
        {
            "code": "ORIGINATION_FEE",
            "operations": ["DISBURSEMENT"],
            "calculation": {"type": "PERCENTAGE", "rate": "0.01", "min": per_currency("1")},
        }
    ],
    "interest": {
        "rate_parameter": "interest_rate",
        "day_count": "ACT_360",
        "capitalization": "MONTHLY",
        "minimum_balance": per_currency("0"),
    },
    "lifecycle": {"min_kyc_level": 2},
}

SEED_PRODUCTS: tuple[tuple[str, str, str, dict[str, Any]], ...] = (
    ("CURRENT", "Current account", "Everyday account with optional overdraft.", CURRENT_ACCOUNT),
    ("SAVINGS", "Savings account", "Interest-bearing, monthly capitalization.", SAVINGS),
    ("TERM_DEPOSIT", "Term deposit", "Locked until maturity; interest at maturity.", TERM_DEPOSIT),
    ("WALLET", "Mobile wallet", "E-money wallet with KYC-tiered caps.", WALLET),
    ("PERSONAL_LOAN", "Personal loan", "Credit line with monthly interest.", LOAN),
)
