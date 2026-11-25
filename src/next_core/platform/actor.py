"""Who performs an operation — carried explicitly from the boundary into services."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Actor:
    id: str  # opaque principal identity, e.g. "user-1@alpha"
    type: str = "USER"  # USER | SERVICE | SYSTEM


SYSTEM = Actor("system", "SYSTEM")
