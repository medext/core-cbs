import os

from django.core.asgi import get_asgi_application

from next_core.platform.telemetry import setup_telemetry

profile = os.environ.get("NEXT_CORE_PROFILE", "local")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"next_core.settings.{profile}")

setup_telemetry()
application = get_asgi_application()
