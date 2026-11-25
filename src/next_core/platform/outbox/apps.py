from django.apps import AppConfig


class OutboxConfig(AppConfig):
    name = "next_core.platform.outbox"
    label = "outbox"
    default_auto_field = "django.db.models.BigAutoField"
