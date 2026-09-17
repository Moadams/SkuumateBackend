from django.apps import AppConfig


class AcademicsConfig(AppConfig):
    name = 'academics'
    verbose_name = 'Academics'

    def ready(self):
        from . import signals  # noqa: F401