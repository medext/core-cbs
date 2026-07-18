"""Fan-out migrations across tenant databases.

Runs ``migrate`` once per tenant database, in deterministic (slug) order, with explicit
per-tenant status output. Django migrations are idempotent, so re-running after a partial
failure resumes safely: already-migrated tenants are no-ops. A failure stops the run
(exit != 0) and names the failed tenant; it never continues silently.
"""

from argparse import ArgumentParser
from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from next_core.tenancy.context import tenant_context
from next_core.tenancy.directory import get_directory


class Command(BaseCommand):
    help = "Apply data-plane migrations to every active tenant database (idempotent)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--tenant",
            help="Migrate a single tenant (slug) instead of all active tenants.",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit non-zero if any tenant database has unapplied migrations.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        directory = get_directory()
        if options["tenant"]:
            tenants = [directory.lookup(options["tenant"])]
        else:
            tenants = directory.all_active()
        if not tenants:
            raise CommandError("No active tenants found; refusing to no-op silently.")

        for ctx in tenants:
            label = f"[{ctx.slug} -> {ctx.db_alias}]"
            self.stdout.write(f"{label} migrating...")
            try:
                with tenant_context(ctx):
                    call_command(
                        "migrate",
                        database=ctx.db_alias,
                        interactive=False,
                        check_unapplied=options["check"],
                        verbosity=1,
                    )
            except SystemExit as exc:  # `migrate --check` signals via SystemExit
                raise CommandError(f"{label} has unapplied migrations.") from exc
            except Exception as exc:
                raise CommandError(
                    f"{label} FAILED: {exc}. Fix the cause and re-run; completed tenants "
                    "are idempotent no-ops."
                ) from exc
            self.stdout.write(self.style.SUCCESS(f"{label} OK"))
