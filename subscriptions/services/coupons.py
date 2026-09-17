"""Coupon policy, atomic redemption and audited administration."""
from decimal import Decimal, ROUND_HALF_UP
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from core.utils import log_action
from subscriptions.models import Coupon, CouponRedemption, Subscription


class CouponConflict(APIException):
    status_code = 409
    default_detail = 'Redeemed coupons cannot be deleted.'


class CouponService:
    @staticmethod
    def expired_query():
        return Q(expiry_date__lt=timezone.localdate()) | Q(max_usage__isnull=False, usage_count__gte=F('max_usage'))

    @staticmethod
    def with_status(queryset, status):
        expired = CouponService.expired_query()
        if status == 'expired':
            return queryset.filter(expired | Q(status='expired'))
        return queryset.exclude(expired).filter(status=status)

    @staticmethod
    def validate(coupon, plan):
        if coupon is None:
            raise ValidationError('Coupon not found.')
        if coupon.max_usage is not None and coupon.usage_count >= coupon.max_usage:
            raise ValidationError('This coupon has reached its usage limit.')
        if coupon.effective_status == 'expired':
            raise ValidationError('This coupon has expired.')
        if coupon.status == 'disabled':
            raise ValidationError('This coupon is disabled.')
        if coupon.target_plan_id and coupon.target_plan_id != plan.pk:
            raise ValidationError('This coupon is not valid for the selected plan.')
        if plan.currency != 'GHS':
            raise ValidationError('Coupons are only supported for GHS plans.')
        return coupon

    @staticmethod
    def lookup(code, plan):
        return CouponService.validate(Coupon.objects.filter(code__iexact=code.strip()).first(), plan)

    @staticmethod
    def checkout_coupon(school, plan, code=None):
        """Carry an ongoing promotion forward from the current subscription.

        Recurring and forever both have no cycle limit because the contract
        supplies no recurring-cycle count. Every renewal is revalidated.
        """
        if code:
            coupon = CouponService.lookup(code, plan)
        else:
            previous = CouponRedemption.objects.filter(
                school=school, subscription__is_current=True,
                coupon__duration__in=['recurring', 'forever'],
            ).select_related('coupon').order_by('-redeemed_at').first()
            if previous is None:
                return None
            coupon = CouponService.validate(previous.coupon, plan)
        if coupon.duration == 'once' and coupon.redemptions.filter(school=school).exists():
            raise ValidationError('This coupon has already been used by this school.')
        return coupon

    @staticmethod
    def discount(coupon, amount):
        value = amount * coupon.discount_value / Decimal('100') if coupon.discount_type == 'percentage' else coupon.discount_value
        return min(amount, value).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

    @staticmethod
    @transaction.atomic
    def redeem(coupon_id, subscription, discount_applied):
        # Consistent subscription -> coupon lock order; database constraints backstop retries.
        subscription = Subscription.objects.select_for_update().get(pk=subscription.pk)
        existing = CouponRedemption.objects.filter(subscription=subscription).first()
        if existing:
            if existing.coupon_id != coupon_id:
                raise ValidationError('A coupon has already been applied to this subscription.')
            return existing
        coupon = Coupon.objects.select_for_update().get(pk=coupon_id)
        CouponService.validate(coupon, subscription.plan)
        if coupon.duration == 'once' and coupon.redemptions.filter(school=subscription.school).exists():
            raise ValidationError('This coupon has already been used by this school.')
        updated = Coupon.objects.filter(pk=coupon.pk, status='active').exclude(CouponService.expired_query()).update(usage_count=F('usage_count') + 1, updated_at=timezone.now())
        if not updated:
            raise ValidationError('This coupon is no longer available.')
        Coupon.objects.filter(pk=coupon.pk, max_usage__isnull=False, usage_count__gte=F('max_usage')).update(status='expired')
        return CouponRedemption.objects.create(coupon=coupon, school=subscription.school, subscription=subscription, discount_applied=discount_applied)

    @staticmethod
    @transaction.atomic
    def save(serializer, request):
        creating = serializer.instance is None
        try:
            with transaction.atomic():
                coupon = serializer.save(**({'created_by': request.user} if creating else {}))
        except IntegrityError:
            raise ValidationError({'code': 'A coupon with this code already exists or the coupon violates a data constraint.'})
        log_action(action='create' if creating else 'update', resource='Coupon', resource_id=coupon.pk, description=f'Coupon {coupon.code}: {coupon.status}', request=request)
        return coupon

    @staticmethod
    @transaction.atomic
    def delete(coupon, request):
        coupon = Coupon.objects.select_for_update().get(pk=coupon.pk)
        if coupon.usage_count or coupon.redemptions.exists() or coupon.payment_intents.exists():
            raise CouponConflict('Redeemed coupons or coupons attached to payment intents cannot be deleted.')
        log_action(action='delete', resource='Coupon', resource_id=coupon.pk, description=f'Deleted coupon {coupon.code}', request=request)
        coupon.delete()

    @staticmethod
    def stats():
        return {
            'active_codes': CouponService.with_status(Coupon.objects.all(), 'active').count(),
            'total_claims': Coupon.objects.aggregate(total=Sum('usage_count'))['total'] or 0,
            'revenue_impact': -(CouponRedemption.objects.aggregate(total=Sum('discount_applied'))['total'] or Decimal('0.00')),
            'conversion_lift_percent': None,  # No conversion analytics are collected yet.
        }
