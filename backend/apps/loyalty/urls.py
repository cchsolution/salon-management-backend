from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.loyalty.views import (
    ServicePackageViewSet, CustomerPackageViewSet,
    MembershipPlanViewSet, CustomerMembershipViewSet, CouponViewSet
)

router = DefaultRouter()
router.register(r'packages', ServicePackageViewSet, basename='service-package')
router.register(r'client-packages', CustomerPackageViewSet, basename='customer-package')
router.register(r'membership-plans', MembershipPlanViewSet, basename='membership-plan')
router.register(r'client-memberships', CustomerMembershipViewSet, basename='customer-membership')
router.register(r'coupons', CouponViewSet, basename='coupon')

urlpatterns = [
    path('', include(router.urls)),
]
