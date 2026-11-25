"""Reconstruct balances from postings and verify integrity for every (or one) tenant.

Exit code is non-zero when any tenant has findings — usable as a scheduled monitor."""

from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from next_core.ledger.integrity import verify_ledger
from next_core.tenancy.context import tenant_context
from next_core.tenancy.directory import get_directory


class Command(BaseCommand):
    help = "Verify ledger integrity (projection == reconstruction, balanced entries)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--tenant", help="Single tenant slug.")

    def handle(self, *args: Any, **options: Any) -> None:
        directory = get_directory()
        tenants = (
            [directory.lookup(options["tenant"])] if options["tenant"] else directory.all_active()
        )
        failed = []
        for ctx in tenants:
            with tenant_context(ctx):
                run = verify_ledger()
            status = "OK" if run.ok else f"{len(run.findings)} FINDING(S)"
            self.stdout.write(
                f"[{ctx.slug}] balances={run.balances_checked} entries={run.entries_checked} "
                f"-> {status} (run {run.id})"
            )
            if not run.ok:
                failed.append(ctx.slug)
        if failed:
            raise CommandError(f"Integrity findings in: {', '.join(failed)}")
