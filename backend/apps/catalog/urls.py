from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.catalog.views import (
    ServiceCategoryViewSet, ServiceViewSet, ServiceStyleViewSet, ResourceViewSet
)
from apps.core.views import StaffProfileViewSet

router = DefaultRouter()
router.register(r'categories', ServiceCategoryViewSet, basename='service-category')
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'styles', ServiceStyleViewSet, basename='service-style')
router.register(r'resources', ResourceViewSet, basename='resource')
router.register(r'staff', StaffProfileViewSet, basename='catalog-staff')

urlpatterns = [
    # Explicit style endpoints for both slash and non-slash compatibility
    path('styles/', ServiceStyleViewSet.as_view({'get': 'list', 'post': 'create'}), name='catalog-styles-explicit'),
    path('styles/<uuid:pk>/', ServiceStyleViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='catalog-styles-detail-explicit'),
    path('', include(router.urls)),
]
