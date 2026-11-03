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
    recent_activities = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            'id', 'salon', 'user', 'first_name', 'last_name', 'full_name',
            'email', 'phone', 'gender', 'birth_date', 'address', 'city',
            'notes', 'preferences', 'tags', 'loyalty_points', 'total_spend',
            'visit_count', 'last_visit', 'is_active', 'recent_activities',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'salon', 'loyalty_points', 'total_spend', 'visit_count', 'last_visit', 'created_at', 'updated_at']

    def get_recent_activities(self, obj):
        if hasattr(obj, '_prefetched_objects_cache') and 'activities' in obj._prefetched_objects_cache:
            return CustomerActivitySerializer(obj.activities.all()[:10], many=True).data
        return []
