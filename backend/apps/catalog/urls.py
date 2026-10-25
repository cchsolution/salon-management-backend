from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.catalog.views import ServiceCategoryViewSet, ServiceViewSet, ResourceViewSet
from apps.core.views import StaffProfileViewSet

router = DefaultRouter()
router.register(r'categories', ServiceCategoryViewSet, basename='service-category')
router.register(r'services', ServiceViewSet, basename='service')
router.register(r'resources', ResourceViewSet, basename='resource')
router.register(r'staff', StaffProfileViewSet, basename='catalog-staff')

urlpatterns = [
    path('', include(router.urls)),
]
