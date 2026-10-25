from rest_framework import serializers
from apps.core.models import Salon, Branch, User, StaffProfile, AuditLog, UserRole

class SalonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Salon
        fields = [
            'id', 'name', 'slug', 'tagline', 'email', 'phone', 'address',
            'currency', 'timezone', 'tax_rate', 'logo', 'is_active',
            'subscription_plan', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BranchSerializer(serializers.ModelSerializer):
    salon_name = serializers.ReadOnlyField(source='salon.name')

    class Meta:
        model = Branch
        fields = [
            'id', 'salon', 'salon_name', 'name', 'code', 'phone', 'email',
            'address', 'city', 'is_primary', 'is_active',
            'opening_time', 'closing_time', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


ROLE_PERMISSIONS = {
    UserRole.SUPERADMIN: [
        'all', 'superadmin', 'dashboard', 'appointments', 'calendar', 'customers',
        'services', 'staff', 'products', 'inventory', 'pos_orders', 'website_builder',
        'reports', 'analytics', 'marketing', 'salon_settings', 'audit_logs'
    ],
    UserRole.SALON_OWNER: [
        'dashboard', 'appointments', 'calendar', 'customers', 'services', 'staff',
        'products', 'inventory', 'pos_orders', 'website_builder', 'reports',
        'analytics', 'marketing', 'salon_settings', 'audit_logs'
    ],
    UserRole.SALON_MANAGER: [
        'dashboard', 'appointments', 'calendar', 'customers', 'services', 'staff',
        'products', 'inventory', 'pos_orders', 'reports', 'analytics', 'salon_settings'
    ],
    UserRole.RECEPTIONIST: [
        'appointments', 'calendar', 'customers', 'services', 'pos_orders',
        'notifications', 'profile'
    ],
    UserRole.STYLIST: [
        'appointments', 'calendar', 'assigned_customers', 'services',
        'notifications', 'profile'
    ],
    UserRole.CUSTOMER: [
        'appointments', 'profile'
    ],
}


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    salon_name = serializers.ReadOnlyField(source='salon.name')
    branch_name = serializers.ReadOnlyField(source='branch.name')
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'phone', 'role', 'permissions', 'salon', 'salon_name', 'branch', 'branch_name',
            'avatar', 'is_active', 'date_joined'
        ]
        read_only_fields = ['id', 'date_joined', 'permissions']

    def get_permissions(self, obj):
        return ROLE_PERMISSIONS.get(obj.role, [])


class StaffProfileSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    branch_name = serializers.ReadOnlyField(source='branch.name')
    salon_name = serializers.ReadOnlyField(source='salon.name')

    class Meta:
        model = StaffProfile
        fields = [
            'id', 'salon', 'salon_name', 'user', 'user_details', 'branch',
            'branch_name', 'title', 'bio', 'commission_rate', 'is_bookable',
            'color_code', 'employment_start', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.ReadOnlyField(source='user.get_full_name')

    class Meta:
        model = AuditLog
        fields = [
            'id', 'salon', 'user', 'user_name', 'action', 'entity_type',
            'entity_id', 'ip_address', 'details', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=UserRole.choices, default=UserRole.CUSTOMER)
    salon_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    salon_slug = serializers.SlugField(max_length=255, required=False, allow_blank=True)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
