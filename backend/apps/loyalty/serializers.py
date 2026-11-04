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
        read_only_fields = ['id', 'salon', 'created_at']


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
        read_only_fields = ['id', 'salon', 'created_at']


class MembershipPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = MembershipPlan
        fields = [
            'id', 'salon', 'name', 'tier', 'description', 'price',
            'billing_cycle', 'discount_percentage', 'free_services_count',
            'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'salon', 'created_at']


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
        read_only_fields = ['id', 'salon', 'created_at']


class CouponSerializer(serializers.ModelSerializer):
    customer_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        write_only=True
    )
    applicable_customer_names = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Coupon
        fields = [
            'id', 'salon', 'code', 'description', 'discount_type',
            'discount_value', 'min_spend', 'valid_from', 'valid_to',
            'usage_limit', 'used_count', 'audience', 'applicable_customers',
            'customer_ids', 'applicable_customer_names',
            'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'salon', 'used_count', 'applicable_customers', 'created_at']

    def get_applicable_customer_names(self, obj):
        if obj.audience == 'SPECIFIC':
            return [{'id': str(c.id), 'name': c.full_name, 'phone': c.phone} for c in obj.applicable_customers.all()]
        return []

    def validate(self, attrs):
        request = self.context.get('request')
        salon = getattr(getattr(request, 'user', None), 'salon', None)
        if not salon and self.instance:
            salon = self.instance.salon

        code = attrs.get('code')
        if code:
            code = code.strip().upper()
            attrs['code'] = code
            if salon:
                qs = Coupon.objects.filter(salon=salon, code=code)
                if self.instance:
                    qs = qs.exclude(pk=self.instance.pk)
                if qs.exists():
                    raise serializers.ValidationError({'code': ['A coupon with this code already exists for this salon.']})

        valid_from = attrs.get('valid_from', self.instance.valid_from if self.instance else None)
        valid_to = attrs.get('valid_to', self.instance.valid_to if self.instance else None)
        if valid_from and valid_to and valid_from > valid_to:
            raise serializers.ValidationError({'valid_to': ['Valid to date cannot be before valid from date.']})

        discount_type = attrs.get('discount_type', self.instance.discount_type if self.instance else 'PERCENTAGE')
        discount_value = attrs.get('discount_value', self.instance.discount_value if self.instance else None)
        if discount_value is not None:
            if discount_value < 0:
                raise serializers.ValidationError({'discount_value': ['Discount value cannot be negative.']})
            if discount_type == 'PERCENTAGE' and discount_value > 100:
                raise serializers.ValidationError({'discount_value': ['Percentage discount cannot exceed 100%.']})

        audience = attrs.get('audience', self.instance.audience if self.instance else 'ALL')
        customer_ids = attrs.get('customer_ids')
        if audience == 'SPECIFIC':
            if customer_ids is not None and len(customer_ids) == 0 and not (self.instance and self.instance.applicable_customers.exists()):
                raise serializers.ValidationError({'customer_ids': ['Please select at least one client for targeted coupon.']})
            if customer_ids and salon:
                from apps.customers.models import Customer
                invalid_count = Customer.objects.filter(id__in=customer_ids).exclude(salon=salon).count()
                if invalid_count > 0:
                    raise serializers.ValidationError({'customer_ids': ['One or more selected clients do not belong to this salon.']})

        return attrs

    def create(self, validated_data):
        customer_ids = validated_data.pop('customer_ids', None)
        coupon = super().create(validated_data)
        if coupon.audience == 'SPECIFIC' and customer_ids:
            coupon.applicable_customers.set(customer_ids)
        return coupon

    def update(self, instance, validated_data):
        customer_ids = validated_data.pop('customer_ids', None)
        coupon = super().update(instance, validated_data)
        if customer_ids is not None:
            if coupon.audience == 'SPECIFIC':
                coupon.applicable_customers.set(customer_ids)
            else:
                coupon.applicable_customers.clear()
        return coupon
