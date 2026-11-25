"""Provision a tenant's seed chart of accounts and seed product catalog (idempotent).

Products are created through the same services as the API, activated through the
maker-checker path with two distinct system principals; every step is audited."""

from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand

from next_core.ledger.application import ensure_gl_accounts
from next_core.platform.actor import Actor
from next_core.products.application import bootstrap_activate, create_product
from next_core.products.catalog import SEED_COA, SEED_PRODUCTS
from next_core.products.models import Product
from next_core.tenancy.context import tenant_context
from next_core.tenancy.directory import get_directory

MAKER = Actor("system:bootstrap-maker", "SYSTEM")
CHECKER = Actor("system:bootstrap-checker", "SYSTEM")


def bootstrap_current_tenant(with_products: bool = True) -> tuple[int, list[str]]:
    created_gl = ensure_gl_accounts(SEED_COA)
    created_products: list[str] = []
    if with_products:
        for code, name, description, definition in SEED_PRODUCTS:
            if Product.objects.filter(code=code).exists():
                continue
            version = create_product(
                code=code, name=name, description=description, definition=definition, actor=MAKER
            )
            bootstrap_activate(version, MAKER, CHECKER)
            created_products.append(code)
    return created_gl, created_products


class Command(BaseCommand):
    help = "Seed the chart of accounts and the demo product catalog for tenant(s)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--tenant", help="Single tenant slug (default: all active).")
        parser.add_argument("--coa-only", action="store_true", help="Skip the product catalog.")

    def handle(self, *args: Any, **options: Any) -> None:
        directory = get_directory()
        tenants = (
            [directory.lookup(options["tenant"])] if options["tenant"] else directory.all_active()
        )
        for ctx in tenants:
            with tenant_context(ctx):
                gl, products = bootstrap_current_tenant(not options["coa_only"])
            self.stdout.write(
                f"[{ctx.slug}] GL accounts created: {gl}; products activated: "
                f"{', '.join(products) or 'none (already present)'}"
            )
