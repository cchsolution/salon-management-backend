from decimal import Decimal
from rest_framework import serializers
from apps.core.models import Salon, Branch, User, StaffProfile, AuditLog, UserRole

SUPPORTED_GST_RATES = [Decimal('0.00'), Decimal('5.00'), Decimal('18.00'), Decimal('40.00')]

class SalonSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Salon
        fields = [
            'id', 'name', 'slug', 'tagline', 'email', 'phone', 'address',
            'currency', 'timezone', 'tax_rate', 'logo', 'is_active',
            'subscription_plan', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'salon', 'user', 'created_at', 'updated_at']

    def validate_tax_rate(self, value):
        if value is None:
            return Decimal('18.00')
        val_dec = Decimal(str(value))
        if val_dec not in [
            Decimal('0'), Decimal('0.00'),
            Decimal('5'), Decimal('5.00'),
            Decimal('18'), Decimal('18.00'),
            Decimal('40'), Decimal('40.00')
        ]:
            raise serializers.ValidationError("Supported GST rates are 0%, 5%, 18%, and 40%.")
        return val_dec


class BranchSerializer(serializers.ModelSerializer):
    salon_name = serializers.SerializerMethodField()

    class Meta:
        model = Branch
        fields = [
            'id', 'salon', 'salon_name', 'name', 'code', 'phone', 'email',
            'address', 'city', 'is_primary', 'is_active',
            'opening_time', 'closing_time', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'salon', 'created_at', 'updated_at']

    def get_salon_name(self, obj):
        if 'salon' in getattr(obj._state, 'fields_cache', {}):
            return obj.salon.name if obj.salon else None
        return getattr(obj, '_salon_name', None)


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
    salon_name = serializers.SerializerMethodField()
    branch_name = serializers.SerializerMethodField()
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

    def get_salon_name(self, obj):
        if 'salon' in getattr(obj._state, 'fields_cache', {}):
            return obj.salon.name if obj.salon else None
        return getattr(obj, '_salon_name', None)

    def get_branch_name(self, obj):
        if 'branch' in getattr(obj._state, 'fields_cache', {}):
            return obj.branch.name if obj.branch else None
        return getattr(obj, '_branch_name', None)


class StaffProfileSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    name = serializers.CharField(source='user.get_full_name', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    phone = serializers.CharField(source='user.phone', read_only=True)
    is_active = serializers.BooleanField(source='user.is_active', read_only=True)
    branch_name = serializers.SerializerMethodField()
    salon_name = serializers.SerializerMethodField()
    assigned_categories = serializers.SerializerMethodField()
    assigned_services = serializers.SerializerMethodField()
    assigned_styles = serializers.SerializerMethodField()

    class Meta:
        model = StaffProfile
        fields = [
            'id', 'salon', 'salon_name', 'user', 'user_details', 'name', 'email', 'phone', 'is_active',
            'branch', 'branch_name', 'title', 'bio', 'commission_rate', 'is_bookable',
            'color_code', 'employment_start', 'assigned_categories', 'assigned_services',
            'assigned_styles', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'salon', 'user', 'created_at', 'updated_at']

    def get_salon_name(self, obj):
        if 'salon' in getattr(obj._state, 'fields_cache', {}):
            return obj.salon.name if obj.salon else None
        return getattr(obj, '_salon_name', None)

    def get_branch_name(self, obj):
        if 'branch' in getattr(obj._state, 'fields_cache', {}):
            return obj.branch.name if obj.branch else None
        return getattr(obj, '_branch_name', None)

    def get_assigned_categories(self, obj):
        if hasattr(obj, '_prefetched_objects_cache') and 'qualified_categories' in obj._prefetched_objects_cache:
            return [cat.id for cat in obj.qualified_categories.all()]
        return []

    def get_assigned_services(self, obj):
        if hasattr(obj, '_prefetched_objects_cache') and 'qualified_services' in obj._prefetched_objects_cache:
            return [srv.id for srv in obj.qualified_services.all()]
        return []

    def get_assigned_styles(self, obj):
        if hasattr(obj, '_prefetched_objects_cache') and 'qualified_styles' in obj._prefetched_objects_cache:
            return [st.id for st in obj.qualified_styles.all()]
        return []


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
