from django.contrib import admin
from apps.loyalty.models import (
    ServicePackage, CustomerPackage, MembershipPlan, CustomerMembership, Coupon
)

@admin.register(ServicePackage)
class ServicePackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'salon', 'price', 'validity_days', 'is_active')


@admin.register(CustomerPackage)
class CustomerPackageAdmin(admin.ModelAdmin):
    list_display = ('customer', 'package', 'remaining_credits', 'expiry_date', 'is_active')


@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'salon', 'tier', 'price', 'billing_cycle', 'discount_percentage', 'is_active')


@admin.register(CustomerMembership)
class CustomerMembershipAdmin(admin.ModelAdmin):
    list_display = ('customer', 'plan', 'start_date', 'end_date', 'is_active')


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'salon', 'discount_type', 'discount_value', 'min_spend', 'valid_to', 'used_count', 'usage_limit', 'is_active')
    search_fields = ('code',)
    list_filter = ('salon', 'discount_type', 'is_active')
