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
    name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    recent_activities = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            'id', 'salon', 'user', 'name', 'first_name', 'last_name', 'full_name',
            'email', 'phone', 'gender', 'birth_date', 'address', 'city',
            'notes', 'preferences', 'tags', 'loyalty_points', 'total_spend',
            'visit_count', 'last_visit', 'is_active', 'recent_activities',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'salon', 'loyalty_points', 'total_spend', 'visit_count', 'last_visit', 'created_at', 'updated_at']

    def validate(self, attrs):
        name = attrs.pop('name', None)
        if name:
            parts = str(name).strip().split(maxsplit=1)
            attrs['first_name'] = parts[0]
            if len(parts) > 1:
                attrs['last_name'] = parts[1]
            elif 'last_name' not in attrs and not self.instance:
                attrs['last_name'] = ''

        request = self.context.get('request')
        salon = getattr(getattr(request, 'user', None), 'salon', None) if request else None
        if self.instance and hasattr(self.instance, 'salon'):
            salon = self.instance.salon

        phone = attrs.get('phone')
        if phone and salon:
            qs = Customer.objects.filter(salon=salon, phone=phone.strip())
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError({'phone': 'A client with this phone number already exists in this salon.'})

        return attrs

    def get_recent_activities(self, obj):
        if hasattr(obj, '_prefetched_objects_cache') and 'activities' in obj._prefetched_objects_cache:
            return CustomerActivitySerializer(obj.activities.all()[:10], many=True).data
        return []
