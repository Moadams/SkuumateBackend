from django.apps import AppConfig
from django.db.models.signals import post_migrate


class SubscriptionsConfig(AppConfig):
    name = 'subscriptions'

    def ready(self):
        import subscriptions.signals
        from subscriptions.sync import sync_features_on_migrate
        post_migrate.connect(sync_features_on_migrate, sender=self)