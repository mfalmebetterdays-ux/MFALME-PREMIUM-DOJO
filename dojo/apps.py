from django.apps import AppConfig


class DojoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dojo"
    verbose_name = "TimesTable Dojo"

    def ready(self):
        import dojo.signals  # noqa: F401 — registers signal handlers
