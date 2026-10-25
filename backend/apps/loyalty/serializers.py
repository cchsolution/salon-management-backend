from rest_framework import serializers
from apps.loyalty.models import (
    ServicePackage, CustomerPackage, MembershipPlan, CustomerMembership, Coupon
)
from apps.catalog.serializers import ServiceSerializer

class ServicePackageSerializer(serializers.ModelSerializer):
    included_services_details = ServiceSerializer(source='included_services', many=True, read_only=True)

    class Meta:
        model = ServicePackage
        fields = [
            'id', 'salon', 'name', 'description', 'price', 'original_value',
            'validity_days', 'included_services', 'included_services_details',
            'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class CustomerPackageSerializer(serializers.ModelSerializer):
    package_name = serializers.ReadOnlyField(source='package.name')
    customer_name = serializers.ReadOnlyField(source='customer.full_name')

    class Meta:
        model = CustomerPackage
        fields = [
            'id', 'salon', 'customer', 'customer_name', 'package', 'package_name',
            'purchase_date', 'expiry_date', 'total_credits', 'remaining_credits',
            'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class MembershipPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = MembershipPlan
        fields = [
            'id', 'salon', 'name', 'tier', 'description', 'price',
            'billing_cycle', 'discount_percentage', 'free_services_count',
            'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class CustomerMembershipSerializer(serializers.ModelSerializer):
    plan_name = serializers.ReadOnlyField(source='plan.name')
    plan_tier = serializers.ReadOnlyField(source='plan.tier')
    customer_name = serializers.ReadOnlyField(source='customer.full_name')

    class Meta:
        model = CustomerMembership
        fields = [
            'id', 'salon', 'customer', 'customer_name', 'plan', 'plan_name',
            'plan_tier', 'start_date', 'end_date', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = [
            'id', 'salon', 'code', 'description', 'discount_type',
            'discount_value', 'min_spend', 'valid_from', 'valid_to',
            'usage_limit', 'used_count', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'used_count', 'created_at']
