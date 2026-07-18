from django.apps import AppConfig


class IamConfig(AppConfig):
    name = "next_core.iam"
    label = "iam"

    def ready(self) -> None:
        from next_core.iam import checks  # noqa: F401 — registers system checks
