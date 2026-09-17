from django.core.management.base import BaseCommand
from django.utils import timezone
from subscriptions.models import Coupon


class Command(BaseCommand):
    help = 'Mark active coupons with past expiry dates as expired. Run daily.'

    def handle(self, *args, **options):
        count = Coupon.objects.filter(status='active', expiry_date__lt=timezone.localdate()).update(status='expired', updated_at=timezone.now())
        self.stdout.write(self.style.SUCCESS(f'Expired {count} coupons.'))
