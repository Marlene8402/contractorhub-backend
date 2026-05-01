from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        # Import side-effect: registers @receiver(post_save, ...) handlers
        # for Subcontract and Project so they auto-push to QB on save.
        # See api/qb_signals.py.
        from . import qb_signals  # noqa: F401
