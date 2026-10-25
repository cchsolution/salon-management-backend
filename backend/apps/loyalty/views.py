import datetime
from decimal import Decimal
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.loyalty.models import (
    ServicePackage, CustomerPackage, MembershipPlan, CustomerMembership, Coupon
)
from apps.loyalty.serializers import (
    ServicePackageSerializer, CustomerPackageSerializer,
    MembershipPlanSerializer, CustomerMembershipSerializer, CouponSerializer
)
from apps.tenants.permissions import IsSalonOwner, IsOwnerOrReceptionist, IsTenantMember
from apps.core.models import UserRole

class ServicePackageViewSet(viewsets.ModelViewSet):
    serializer_class = ServicePackageSerializer
    permission_classes = [IsTenantMember]

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [IsSalonOwner()]

    def get_queryset(self):
        user = self.request.user
        salon = getattr(self.request, 'salon', None)
        if user.is_authenticated and (user.role == UserRole.SUPERADMIN or user.is_superuser):
            return ServicePackage.objects.all().prefetch_related('included_services')
        if user.is_authenticated and user.salon:
            return ServicePackage.objects.filter(salon=user.salon).prefetch_related('included_services')
        if salon:
            return ServicePackage.objects.filter(salon=salon, is_active=True).prefetch_related('included_services')
        return ServicePackage.objects.none()

    def perform_create(self, serializer):
        serializer.save(salon=self.request.user.salon)


class CustomerPackageViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerPackageSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def get_permissions(self):
        if self.request.user and self.request.user.is_authenticated:
            if self.request.user.role in [UserRole.SUPERADMIN, UserRole.SALON_OWNER, UserRole.SALON_MANAGER, UserRole.RECEPTIONIST] or self.request.user.is_superuser:
                return [permissions.IsAuthenticated(), IsTenantMember()]
            if self.request.user.role == UserRole.CUSTOMER and self.action in ['list', 'retrieve']:
                return [permissions.IsAuthenticated()]
        return [IsOwnerOrReceptionist()]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return CustomerPackage.objects.none()
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return CustomerPackage.objects.all().select_related('customer', 'package')
        if user.role in [UserRole.SALON_OWNER, UserRole.SALON_MANAGER, UserRole.RECEPTIONIST] and user.salon:
            return CustomerPackage.objects.filter(salon=user.salon).select_related('customer', 'package')
        if user.role == UserRole.CUSTOMER:
            return CustomerPackage.objects.filter(customer__user=user).select_related('customer', 'package')
        return CustomerPackage.objects.none()


class MembershipPlanViewSet(viewsets.ModelViewSet):
    serializer_class = MembershipPlanSerializer
    permission_classes = [IsTenantMember]

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [IsSalonOwner()]

    def get_queryset(self):
        user = self.request.user
        salon = getattr(self.request, 'salon', None)
        if user.is_authenticated and (user.role == UserRole.SUPERADMIN or user.is_superuser):
            return MembershipPlan.objects.all()
        if user.is_authenticated and user.salon:
            return MembershipPlan.objects.filter(salon=user.salon)
        if salon:
            return MembershipPlan.objects.filter(salon=salon, is_active=True)
        return MembershipPlan.objects.none()

    def perform_create(self, serializer):
        serializer.save(salon=self.request.user.salon)


class CustomerMembershipViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerMembershipSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def get_permissions(self):
        if self.request.user and self.request.user.is_authenticated:
            if self.request.user.role in [UserRole.SUPERADMIN, UserRole.SALON_OWNER, UserRole.SALON_MANAGER, UserRole.RECEPTIONIST] or self.request.user.is_superuser:
                return [permissions.IsAuthenticated(), IsTenantMember()]
            if self.request.user.role == UserRole.CUSTOMER and self.action in ['list', 'retrieve']:
                return [permissions.IsAuthenticated()]
        return [IsOwnerOrReceptionist()]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return CustomerMembership.objects.none()
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return CustomerMembership.objects.all().select_related('customer', 'plan')
        if user.role in [UserRole.SALON_OWNER, UserRole.SALON_MANAGER, UserRole.RECEPTIONIST] and user.salon:
            return CustomerMembership.objects.filter(salon=user.salon).select_related('customer', 'plan')
        if user.role == UserRole.CUSTOMER:
            return CustomerMembership.objects.filter(customer__user=user).select_related('customer', 'plan')
        return CustomerMembership.objects.none()


class CouponViewSet(viewsets.ModelViewSet):
    serializer_class = CouponSerializer

    def get_permissions(self):
        if self.action == 'validate_coupon':
            return [permissions.AllowAny()]
        return [IsSalonOwner()]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return Coupon.objects.none()
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return Coupon.objects.all()
        if user.salon:
            return Coupon.objects.filter(salon=user.salon)
        return Coupon.objects.none()


    def perform_create(self, serializer):
        serializer.save(salon=self.request.user.salon)

    @action(detail=False, methods=['post'])
    def validate_coupon(self, request):
        code = request.data.get('code', '').strip().upper()
        spend = Decimal(str(request.data.get('subtotal', '0.00')))
        salon_slug = request.headers.get('X-Salon-Slug') or request.data.get('salon_slug')

        user = request.user
        salon = user.salon if (user.is_authenticated and user.salon) else None
        if not salon and salon_slug:
            from apps.core.models import Salon
            salon = Salon.objects.filter(slug=salon_slug).first()

        if not salon:
            return Response({'error': 'Salon tenant not identified.'}, status=status.HTTP_400_BAD_REQUEST)

        today = datetime.date.today()
        coupon = Coupon.objects.filter(
            salon=salon,
            code=code,
            is_active=True,
            valid_from__lte=today,
            valid_to__gte=today
        ).first()

        if not coupon:
            return Response({'error': 'Invalid or expired coupon code.'}, status=status.HTTP_400_BAD_REQUEST)

        if coupon.usage_limit > 0 and coupon.used_count >= coupon.usage_limit:
            return Response({'error': 'Coupon usage limit has been reached.'}, status=status.HTTP_400_BAD_REQUEST)

        if spend < coupon.min_spend:
            return Response({'error': f'Minimum spend of ${coupon.min_spend} is required for this coupon.'}, status=status.HTTP_400_BAD_REQUEST)

        # Calculate discount
        if coupon.discount_type == 'PERCENTAGE':
            discount = spend * (coupon.discount_value / Decimal('100.0'))
        else:
            discount = min(coupon.discount_value, spend)

        return Response({
            'valid': True,
            'code': coupon.code,
            'discount_type': coupon.discount_type,
            'discount_value': coupon.discount_value,
            'calculated_discount': discount
        })
