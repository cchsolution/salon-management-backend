from django.contrib import admin
from apps.customers.models import Customer, CustomerActivity

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'salon', 'phone', 'email', 'total_spend', 'visit_count', 'loyalty_points', 'is_active')
    search_fields = ('first_name', 'last_name', 'phone', 'email')
    list_filter = ('salon', 'is_active')


@admin.register(CustomerActivity)
class CustomerActivityAdmin(admin.ModelAdmin):
    list_display = ('customer', 'activity_type', 'title', 'created_at')
    search_fields = ('customer__first_name', 'customer__last_name', 'title')
    list_filter = ('activity_type', 'salon')
