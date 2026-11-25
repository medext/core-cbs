"""Relay pending outbox events for every active tenant (or one), until drained."""

from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand

from next_core.platform.outbox.service import relay_batch
from next_core.tenancy.context import tenant_context
from next_core.tenancy.directory import get_directory


class Command(BaseCommand):
    help = "Deliver pending outbox events (at-least-once) per tenant."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--tenant", help="Single tenant slug.")
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args: Any, **options: Any) -> None:
        directory = get_directory()
        tenants = (
            [directory.lookup(options["tenant"])] if options["tenant"] else directory.all_active()
        )
        for ctx in tenants:
            total = 0
            with tenant_context(ctx):
                while True:
                    n = relay_batch(batch_size=options["batch_size"])
                    total += n
                    if n == 0:
                        break
            self.stdout.write(f"[{ctx.slug}] delivered {total} event(s)")
