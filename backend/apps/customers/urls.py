from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.customers.views import CustomerViewSet, CustomerActivityViewSet

router = DefaultRouter()
router.register(r'clients', CustomerViewSet, basename='customer')
router.register(r'activities', CustomerActivityViewSet, basename='customer-activity')

urlpatterns = [
    path('', include(router.urls)),
]
