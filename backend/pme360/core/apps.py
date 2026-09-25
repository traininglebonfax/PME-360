from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "pme360.core"
    label = "core"
    verbose_name = "Socle"

    def ready(self) -> None:
        from . import schema  # noqa: F401  (enregistre l'extension OpenAPI)
        from .logging import configure_logging

        configure_logging()
