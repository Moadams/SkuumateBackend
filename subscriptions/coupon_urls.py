from rest_framework.routers import SimpleRouter
from subscriptions.views.coupons import CouponViewSet

router = SimpleRouter()
router.register('coupons', CouponViewSet, basename='coupon')
urlpatterns = router.urls
