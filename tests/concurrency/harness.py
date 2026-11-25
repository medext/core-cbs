"""Concurrency harness: real parallel PostgreSQL transactions, synchronized by a barrier
(never sleeps). Each worker establishes the tenant context and closes its own connections."""

import threading
from collections.abc import Callable, Sequence
from typing import Any

from django.db import connections

from next_core.tenancy.context import TenantContext, tenant_context


def run_parallel(
    ctx: TenantContext, fns: Sequence[Callable[[], Any]], timeout: float = 60
) -> list[Any]:
    """Run every fn concurrently; return its result or the exception it raised (ordered)."""
    barrier = threading.Barrier(len(fns))
    results: list[Any] = [None] * len(fns)

    def worker(i: int, fn: Callable[[], Any]) -> None:
        try:
            with tenant_context(ctx):
                barrier.wait(timeout=timeout)
                results[i] = fn()
        except Exception as exc:  # collected and asserted by the test, never swallowed
            results[i] = exc
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i, fn)) for i, fn in enumerate(fns)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)
    assert not any(t.is_alive() for t in threads), "worker did not finish (possible deadlock)"
    return results
