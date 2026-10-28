"""Coupon API, policy and subscription integration regression tests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.core.management import call_command
from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from accounts.models import User
from core.models import AuditLog
from schools.models import School
from subscriptions.coupon_serializers import CouponSerializer
from subscriptions.models import (
    Coupon,
    CouponRedemption,
    Package,
    Subscription,
)
from subscriptions.services.coupons import CouponService
from subscriptions.services.payments import PaymentService
from subscriptions.services.subscriptions import SubscriptionService


def fixtures():
    user = User.objects.create_user(email='coupon-admin@example.com', role='superadmin', is_superuser=True)
    school = School.objects.create(name='Coupon School', school_code='COUPON')
    plan = Package.objects.create(name='Pro', code='coupon-pro', price='100.00')
    coupon = Coupon.objects.create(code='WELCOME20', discount_type='percentage', discount_value=20, duration='once', target='all', created_by=user)
    return user, school, plan, coupon


def subscription(school, plan):
    return Subscription.objects.create(
        school=school, plan=plan,
        start_date=timezone.localdate(), end_date=timezone.now() + timedelta(days=30),
    )


class CouponTests(APITestCase):
    def setUp(self):
        self.user, self.school, self.plan, self.coupon = fixtures()
        self.client.force_authenticate(self.user)
        self.url = '/api/v1/coupons/'

    def payload(self, **kwargs):
        return dict(code='new10', discount_type='percentage', discount_value='10.00', duration='once', target='all', **kwargs)

    def test_create_normalizes_and_audits(self):
        response = self.client.post(self.url, self.payload(), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['data']['code'], 'NEW10')
        self.assertTrue(AuditLog.objects.filter(resource='Coupon', action='create').exists())
        response = self.client.post(self.url, self.payload(), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('code', response.data['errors'])

    def test_invalid_inputs(self):
        for changes in [dict(code='bad-code'), dict(discount_value=0), dict(discount_value=101), dict(max_usage=0), dict(max_usage=1.5), dict(target='specific_plan'), dict(expiry_date=str(timezone.localdate())), dict(discount_type='fixed', discount_value=-1)]:
            data = self.payload(); data.update(changes)
            with self.subTest(changes=changes):
                serializer = CouponSerializer(data=data)
                self.assertFalse(serializer.is_valid())

    def test_patch_validates_merged_fields_and_ignores_usage(self):
        url = f'{self.url}{self.coupon.pk}/'
        self.assertEqual(self.client.patch(url, {'discount_value': 101}, format='json').status_code, 400)
        response = self.client.patch(url, {'usage_count': 100, 'status': 'disabled'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.usage_count, 0)
        self.assertFalse(response.data['data']['is_active'])
        self.assertTrue(AuditLog.objects.filter(action='update', resource='Coupon').exists())

    def test_effective_status_search_and_stats(self):
        Coupon.objects.filter(pk=self.coupon.pk).update(expiry_date=timezone.localdate() - timedelta(days=1), status='disabled')
        response = self.client.get(self.url, {'search': 'welcome'})
        self.assertEqual(response.data['data']['count'], 1)
        self.assertEqual(response.data['data']['results'][0]['status'], 'expired')
        self.assertEqual(self.client.get(self.url, {'search': 'nomatch'}).data['data']['count'], 0)
        self.assertEqual(self.client.get(self.url + 'stats/').data['data']['active_codes'], 0)


    def test_only_platform_superadmins_can_modify_coupons(self):
        school_admin = User.objects.create_user(email='coupon-school@example.com', school=self.school, role='admin')
        self.client.force_authenticate(school_admin)
        url = f'{self.url}{self.coupon.pk}/'
        self.assertEqual(self.client.post(self.url, self.payload(), format='json').status_code, 403)
        self.assertEqual(self.client.patch(url, {'status': 'disabled'}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.status, 'active')
        self.client.force_authenticate(None)
        self.assertIn(self.client.post(self.url, self.payload(), format='json').status_code, (401, 403))

    def test_checkout_validation_school_authentication_and_errors(self):
        user = User.objects.create_user(email='coupon-school@example.com', school=self.school, role='admin')
        self.client.force_authenticate(user)
        data = {'code': 'welcome20', 'plan_id': str(self.plan.pk)}
        response = self.client.post(self.url + 'validate/', data, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['data']['discount_value'], '20.00')
        self.coupon.refresh_from_db(); self.assertEqual(self.coupon.usage_count, 0)
        data['code'] = 'missing'
        self.assertEqual(self.client.post(self.url + 'validate/', data, format='json').data['error'], 'Coupon not found.')


    def test_delete_unused_and_expiry_command(self):
        Coupon.objects.filter(pk=self.coupon.pk).update(expiry_date=timezone.localdate() - timedelta(days=1))
        call_command('expire_coupons', verbosity=0)
        self.coupon.refresh_from_db(); self.assertEqual(self.coupon.status, 'expired')
        self.assertEqual(self.client.delete(f'{self.url}{self.coupon.pk}/').status_code, 204)

    def test_payment_discount_completion_and_stale_retry(self):
        _, payment = PaymentService.initiate(self.school, self.user, self.plan, None, coupon_code='welcome20')
        self.assertEqual(payment.amount, Decimal('80.00'))
        self.coupon.refresh_from_db(); self.assertEqual(self.coupon.usage_count, 0)
        first = SubscriptionService.complete_payment(self.school, self.plan, None, payment)
        retry = SubscriptionService.complete_payment(self.school, self.plan, None, payment)
        self.assertEqual(first.subscription.pk, retry.subscription.pk)
        self.assertFalse(retry.created)
        self.assertEqual(CouponRedemption.objects.count(), 1)

    def test_fully_discounted_checkout_skips_gateway(self):
        Coupon.objects.filter(pk=self.coupon.pk).update(discount_value=100)
        with patch('subscriptions.services.payments.get_payment_provider') as gateway:
            result, payment = PaymentService.initiate(self.school, self.user, self.plan, None, provider='paystack', coupon_code='WELCOME20')
            self.assertEqual(payment.amount, 0)
            self.assertEqual(result.payment_url, '')
            activation = SubscriptionService.complete_payment(self.school, self.plan, None, payment)
            gateway.assert_not_called()
        self.assertEqual(activation.subscription.coupon_redemption.discount_applied, Decimal('100.00'))


    def test_full_update_target_detail_and_pagination(self):
        data = self.payload()
        data.update(target='specific_plan', target_plan_id=str(self.plan.pk))
        url = f'{self.url}{self.coupon.pk}/'
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.get(url).data['target_plan']['id'], str(self.plan.pk))
        response = self.client.get(self.url, {'page_size': 1})
        self.assertEqual(len(response.data['data']['results']), 1)
        self.assertEqual(self.client.patch(url, {'target': 'all'}, format='json').data['data']['target_plan_id'], None)


@skipUnlessDBFeature('has_select_for_update')
class CouponConcurrencyTests(TransactionTestCase):
    def test_only_one_redemption_claims_last_use(self):
        user, school, plan, coupon = fixtures()
        coupon.max_usage = 1; coupon.save()
        subs = [subscription(school, plan), subscription(school, plan)]
        barrier = Barrier(2)

        def redeem(sub):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    CouponService.redeem(coupon.pk, sub, Decimal('20'))
                    return 'created'
                except ValidationError:
                    return 'rejected'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(redeem, subs))
        self.assertCountEqual(results, ['created', 'rejected'])
        coupon.refresh_from_db(); self.assertEqual(coupon.usage_count, 1)
        self.assertEqual(CouponRedemption.objects.count(), 1)

    def test_duplicate_apply_is_idempotent_under_concurrency(self):
        user, school, plan, coupon = fixtures()
        sub = subscription(school, plan)
        barrier = Barrier(2)

        def redeem():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return CouponService.redeem(coupon.pk, sub, Decimal('20')).pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(redeem) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(results[0], results[1])
        coupon.refresh_from_db()
        self.assertEqual(coupon.usage_count, 1)
        self.assertEqual(CouponRedemption.objects.count(), 1)
