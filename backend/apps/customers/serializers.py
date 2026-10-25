from rest_framework import serializers
from apps.customers.models import Customer, CustomerActivity

class CustomerActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerActivity
        fields = [
            'id', 'salon', 'customer', 'activity_type', 'title',
            'description', 'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class CustomerSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    recent_activities = CustomerActivitySerializer(source='activities', many=True, read_only=True)

    class Meta:
        model = Customer
        fields = [
            'id', 'salon', 'user', 'first_name', 'last_name', 'full_name',
            'email', 'phone', 'gender', 'birth_date', 'address', 'city',
            'notes', 'preferences', 'tags', 'loyalty_points', 'total_spend',
            'visit_count', 'last_visit', 'is_active', 'recent_activities',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'loyalty_points', 'total_spend', 'visit_count', 'last_visit', 'created_at', 'updated_at']
