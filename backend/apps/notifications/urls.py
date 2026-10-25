from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.notifications.serializers import InAppNotificationViewSet

router = DefaultRouter()
router.register(r'alerts', InAppNotificationViewSet, basename='in-app-notification')

urlpatterns = [
    path('', include(router.urls)),
]
