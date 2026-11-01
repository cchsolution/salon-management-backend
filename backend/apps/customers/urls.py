from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.customers.views import CustomerViewSet, CustomerActivityViewSet

router = DefaultRouter()
router.register(r'clients', CustomerViewSet, basename='customer')
router.register(r'activities', CustomerActivityViewSet, basename='customer-activity')
router.register(r'', CustomerViewSet, basename='customer-root')

urlpatterns = [
    path('search/', CustomerViewSet.as_view({'get': 'search'}), name='customer-search'),
    path('lookup-or-create/', CustomerViewSet.as_view({'post': 'lookup_or_create'}), name='customer-lookup-create'),
    path('', include(router.urls)),
]
