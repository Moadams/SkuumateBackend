"""Platform coupon management and authenticated checkout validation."""
from django.db import transaction
from django.db.models import Q
from django_filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsSuperAdminOrReadOnly
from subscriptions.coupon_serializers import (
    CouponSerializer,
    CouponValidationSerializer,
)
from subscriptions.models import Coupon
from subscriptions.services.coupons import CouponService


class CouponPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({'success': True, 'data': {'count': self.page.paginator.count, 'results': data}})


class CouponViewSet(viewsets.ModelViewSet):
    serializer_class = CouponSerializer
    pagination_class = CouponPagination
    filter_backends = (DjangoFilterBackend, SearchFilter)
    search_fields = ('code', 'description')
    permission_classes = (IsSuperAdminOrReadOnly,)

    def get_queryset(self):
        queryset = Coupon.objects.select_related('target_plan')
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        CouponService.save(serializer, request)
        return Response({'success': True, 'data': serializer.data}, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        instance = Coupon.objects.select_for_update().get(pk=instance.pk)
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.pop('partial', False))
        serializer.is_valid(raise_exception=True)
        CouponService.save(serializer, request)
        return Response({'success': True, 'data': serializer.data})

    def destroy(self, request, *args, **kwargs):
        CouponService.delete(self.get_object(), request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        return Response({'success': True, 'data': CouponService.stats()})

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated], url_path='validate')
    def validate_coupon(self, request):
        serializer = CouponValidationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.school_id:
            return Response({'success': False, 'error': 'A school account is required.'}, status=403)
        try:
            coupon = CouponService.checkout_coupon(request.user.school, serializer.validated_data['plan_id'], serializer.validated_data['code'])
        except ValidationError as exc:
            return Response({'success': False, 'error': str(exc.detail[0])}, status=400)
        value = format(coupon.discount_value.normalize(), 'f')
        discount = f'{value}%' if coupon.discount_type == 'percentage' else f'GH₵{value}'
        timing = 'your first payment' if coupon.duration == 'once' else 'each eligible subscription payment'
        return Response({'success': True, 'data': {
            'code': coupon.code, 'discount_type': coupon.discount_type,
            'discount_value': str(coupon.discount_value), 'duration': coupon.duration,
            'message': f'{discount} discount applied to {timing}.',
        }})
