from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from apps.core.models import Salon, Branch, User, StaffProfile, AuditLog

@admin.register(Salon)
class SalonAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'email', 'phone', 'is_active', 'subscription_plan', 'created_at')
    search_fields = ('name', 'slug', 'email', 'phone')
    list_filter = ('is_active', 'subscription_plan')


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'salon', 'city', 'is_primary', 'is_active', 'phone')
    search_fields = ('name', 'salon__name', 'city')
    list_filter = ('is_primary', 'is_active')


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'role', 'salon', 'is_active', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name', 'username')
    list_filter = ('role', 'is_active', 'is_staff', 'salon')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email', 'phone', 'avatar')}),
        ('Salon Multi-Tenancy', {'fields': ('role', 'salon', 'branch')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'salon', 'branch', 'title', 'commission_rate', 'is_bookable')
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'title')
    list_filter = ('salon', 'is_bookable', 'branch')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'entity_type', 'entity_id', 'salon', 'user', 'created_at')
    search_fields = ('action', 'entity_type', 'entity_id', 'user__email')
    list_filter = ('action', 'entity_type', 'salon')
    readonly_fields = ('salon', 'user', 'action', 'entity_type', 'entity_id', 'ip_address', 'details', 'created_at')
