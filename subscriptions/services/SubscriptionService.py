from datetime import timedelta, timezone

from subscriptions.models import Subscription


class SubscriptionService:

    @staticmethod
    def free_trial_subscription(school, user):
        if school.subscriptions.filter(status=Subscription.Status.TRIAL).exists():
            return None  # School already has a free trial subscription

        start_date = timezone.now()
        end_date = start_date + timedelta(days=Subscription.TRIAL_DAYS)

        return Subscription.objects.create(
            school=school,
            status=Subscription.Status.TRIAL,
            start_date=start_date,
            end_date=end_date,
            activated_by=user,
            is_current=True,
        )