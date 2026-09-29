from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone

from accounts.models import User
from schools.models import School
from subscriptions.models import Subscription, SubscriptionPayment


class SuperAdminDashboardService:
    
    def _get_stats(self):

        now = timezone.now()
        last_month_start = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
        this_month_start = now.replace(day=1)

        total_schools = School.objects.filter(status=School.SchoolStatus.ACTIVE).count()
        schools_this_month = School.objects.filter(
            created_at__gte=this_month_start
        ).count()
        schools_last_month = School.objects.filter(
            created_at__gte=last_month_start,
            created_at__lt=this_month_start,
        ).count()

        subscriptions_data = Subscription.objects.aggregate(
            active_subscriptions=Count('id', filter=Q(status__in=["active", "trial"])),
            this_month_subscriptions=Count('id', filter=Q(status__in=["active", "trial"]), created_at__gte=this_month_start),
            last_month_subscriptions=Count('id', filter=Q(status__in=['active', "trial"]), created_at__gte=last_month_start, created_at__lt=this_month_start)
        )

        active_subscriptions = subscriptions_data['active_subscriptions']
        subscriptions_this_month = subscriptions_data['this_month_subscriptions']
        subscriptions_last_month = subscriptions_data['last_month_subscriptions']

        revenue_this_month = SubscriptionPayment.objects.filter(
            created_at__gte=this_month_start,
            status__in=["active", "trial"],
            amount__isnull=False,
        ).aggregate(total=Sum("amount"))["total"] or 0

        revenue_last_month = SubscriptionPayment.objects.filter(
            created_at__gte=last_month_start,
            created_at__lt=this_month_start,
            status__in=["active", "trial"],
            amount__isnull=False,
        ).aggregate(total=Sum("amount"))["total"] or 0

        users_stats = User.objects.aggregate(
            active_users=Count('id', filter=Q(is_active=True, deleted_at__isnull=True)),
            users_this_month=Count('id', filter=Q(created_at__gte=this_month_start, is_active=True, school__isnull=False)),
            users_last_month=Count('id', filter=Q(created_at__gte=last_month_start, created_at__lt=this_month_start, is_active=False, school__isnull=True)),
        )

        active_users = users_stats["active_users"]
        users_this_month = users_stats["users_this_month"]
        users_last_month = users_stats["users_last_month"]

        return {
            "total_schools": {
                "value": total_schools,
                "change": self._percent_change(schools_last_month, schools_this_month),
                "is_positive": schools_this_month >= schools_last_month,
            },
            "active_subscriptions": {
                "value": active_subscriptions,
                "change": self._percent_change(
                    subscriptions_last_month, subscriptions_this_month
                ),
                "is_positive": subscriptions_this_month >= subscriptions_last_month,
            },
            "monthly_revenue": {
                "value": float(revenue_this_month),
                "currency": "GHS",
                "change": self._percent_change(revenue_last_month, revenue_this_month),
                "is_positive": revenue_this_month >= revenue_last_month,
            },
            "active_users": {
                "value": active_users,
                "change": self._percent_change(users_last_month, users_this_month),
                "is_positive": users_this_month >= users_last_month,
            },
        }

    
    
    def _get_recent_onboarding(self):
        """Last 10 schools onboarded with their subscription status."""
        from schools.models import School

        schools = (
            School.objects
            .select_related()
            .prefetch_related("subscriptions__plan")
            .order_by("-created_at")[:10]
        )

        result = []
        for school in schools:
            latest_sub = (
                school.subscriptions
                .order_by("-start_date")
                .first()
            )
            result.append({
                "id": str(school.id),
                "name": school.name,
                "city": school.city,
                "country": school.country,
                "email": school.email,
                "subscription_status": latest_sub.status if latest_sub else "none",
                "registered": school.created_at,
            })

        return result

    def _get_subscription_distribution(self):
        from subscriptions.models import Subscription

        total_active = Subscription.objects.filter(
            status__in=["active", "trial"]
        ).count()

        if total_active == 0:
            return []

        distribution = (
            Subscription.objects
            .filter(status__in=["active", "trial"])
            .values("plan__name", "plan__plan_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        return [
            {
                "plan_name": entry["plan__name"],
                "plan_type": entry["plan__plan_type"],
                "count": entry["count"],
                "percentage": round((entry["count"] / total_active) * 100, 1),
            }
            for entry in distribution
        ]


    def _percent_change(self, previous, current):
            if previous == 0:
                return "+100%" if current > 0 else "0%"
            change = ((current - previous) / previous) * 100
            sign = "+" if change >= 0 else ""
            return f"{sign}{change:.1f}%"