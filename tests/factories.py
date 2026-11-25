"""Deterministic test factories (real PostgreSQL; no mocks of financial logic)."""

import itertools
import uuid
from typing import Any

from next_core.accounts import application as accounts
from next_core.accounts.models import Account
from next_core.parties import application as parties
from next_core.parties.models import Party
from next_core.platform.actor import Actor
from next_core.platform.money import Money
from next_core.products.management.commands.bootstrap_tenant import bootstrap_current_tenant
from next_core.products.models import Product
from next_core.transactions import application as txns

TELLER = Actor("teller-1@alpha", "USER")
_seq = itertools.count(1)


def bootstrap() -> dict[str, uuid.UUID]:
    bootstrap_current_tenant()
    return {p.code: p.id for p in Product.objects.all()}


def party(kyc_level: int = 2) -> Party:
    p = parties.create_party(
        {"type": "INDIVIDUAL", "display_name": f"Customer {next(_seq)}", "given_name": "Test"}, []
    )
    if kyc_level:
        p = parties.record_kyc(p.id, status="VERIFIED", level=kyc_level, reference="kyc-ref")
    return p


def account(
    products: dict[str, uuid.UUID],
    code: str = "CURRENT",
    currency: str = "MRU",
    overrides: dict[str, Any] | None = None,
    owner: Party | None = None,
) -> Account:
    return accounts.open_account(
        party_id=(owner or party()).id,
        product_id=products[code],
        currency=currency,
        parameter_overrides=overrides,
        nickname="",
        actor=TELLER,
    )


def money(raw: str, currency: str = "MRU") -> Money:
    return Money.from_wire(raw, currency)


def deposit(acc: Account, raw: str, channel: str = "BRANCH") -> Any:
    from django.db import transaction

    with transaction.atomic(using=acc._state.db):
        common = txns.CommonFields(channel=channel)
        return txns.deposit(acc.id, money(raw, acc.currency), common, TELLER)
