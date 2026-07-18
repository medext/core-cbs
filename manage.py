#!/usr/bin/env python
"""Django management entry point. Settings module follows NEXT_CORE_PROFILE (local|saas|onprem)."""

import os
import sys


def main() -> None:
    profile = os.environ.get("NEXT_CORE_PROFILE", "local")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"next_core.settings.{profile}")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
