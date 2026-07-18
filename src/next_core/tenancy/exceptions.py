"""Tenancy errors. All are hard failures — there is never a fallback tenant."""


class TenantError(Exception):
    """Base class for tenancy failures."""


class TenantContextMissingError(TenantError):
    """A data-plane operation ran without an established tenant context.

    This is a defect in the calling code, never a condition to recover from by
    guessing a tenant.
    """


class TenantResolutionError(TenantError):
    """The request/job could not be mapped to a valid, active tenant."""
