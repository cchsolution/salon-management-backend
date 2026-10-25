from rest_framework import serializers
from apps.catalog.models import ServiceCategory, Service, Resource
from apps.core.serializers import StaffProfileSerializer

class ServiceCategorySerializer(serializers.ModelSerializer):
    services_count = serializers.IntegerField(source='services.count', read_only=True)

    class Meta:
        model = ServiceCategory
        fields = [
            'id', 'salon', 'name', 'slug', 'description', 'image',
            'sort_order', 'is_active', 'services_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ServiceSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')
    effective_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    qualified_staff_details = StaffProfileSerializer(source='qualified_staff', many=True, read_only=True)

    class Meta:
        model = Service
        fields = [
            'id', 'salon', 'category', 'category_name', 'name', 'slug',
            'description', 'price', 'discount_price', 'effective_price',
            'duration_minutes', 'buffer_time_minutes', 'image', 'is_active',
            'is_featured', 'tax_exempt', 'branches', 'qualified_staff',
            'qualified_staff_details', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ResourceSerializer(serializers.ModelSerializer):
    branch_name = serializers.ReadOnlyField(source='branch.name')

    class Meta:
        model = Resource
        fields = [
            'id', 'salon', 'branch', 'branch_name', 'name', 'resource_type',
            'capacity', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
