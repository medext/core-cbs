"""Run the implemented end-of-day steps for tenant(s): hold expiry, interest accrual and
capitalization, outbox drain is separate (relay_outbox). Idempotent & resumable: re-running
for the same business date is a no-op for already-processed accounts."""

from argparse import ArgumentParser
from datetime import date
from typing import Any

from django.core.management.base import BaseCommand

from next_core.platform import clock
from next_core.platform.actor import Actor
from next_core.tenancy.context import tenant_context
from next_core.tenancy.directory import get_directory
from next_core.transactions.application import expire_holds, reconcile_holds, run_interest

EOD = Actor("system:eod", "SYSTEM")


class Command(BaseCommand):
    help = "Expire holds and run interest accrual/capitalization for a business date."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--tenant", help="Single tenant slug (default: all active).")
        parser.add_argument("--date", help="Business date YYYY-MM-DD (default: today UTC).")

    def handle(self, *args: Any, **options: Any) -> None:
        on = date.fromisoformat(options["date"]) if options["date"] else clock.business_date()
        directory = get_directory()
        tenants = (
            [directory.lookup(options["tenant"])] if options["tenant"] else directory.all_active()
        )
        for ctx in tenants:
            with tenant_context(ctx):
                expired = expire_holds(EOD)
                summary = run_interest(on, EOD)
                hold_findings = reconcile_holds()
            self.stdout.write(
                f"[{ctx.slug}] {on}: holds expired={expired}; interest accounts="
                f"{summary.accounts_considered} accrued={summary.accrued} "
                f"capitalized={summary.capitalized}; hold findings={len(hold_findings)}"
            )
