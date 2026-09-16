from django.apps import AppConfig


class PlatformRbacConfig(AppConfig):
    name = "platform_rbac"
    verbose_name = "Platform Admin (Users, Roles & Permissions)"

    def ready(self):
        from . import signals  # noqa: F401  (wire cache invalidation signals)
        from .sync import seed_on_migrate

        from django.db.models.signals import post_migrate

        post_migrate.connect(seed_on_migrate, sender=self)