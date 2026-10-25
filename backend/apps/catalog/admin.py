from django.contrib import admin
from apps.catalog.models import ServiceCategory, Service, Resource

@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'salon', 'slug', 'sort_order', 'is_active')
    search_fields = ('name', 'slug', 'salon__name')
    list_filter = ('salon', 'is_active')


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'salon', 'category', 'price', 'discount_price', 'duration_minutes', 'is_active', 'is_featured')
    search_fields = ('name', 'slug', 'salon__name')
    list_filter = ('salon', 'category', 'is_active', 'is_featured')


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'salon', 'branch', 'resource_type', 'capacity', 'is_active')
    search_fields = ('name', 'salon__name')
    list_filter = ('salon', 'branch', 'resource_type')
