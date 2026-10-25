from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.appointments.views import (
    AppointmentViewSet, StylistShiftViewSet, StylistLeaveViewSet
)

router = DefaultRouter()
router.register(r'bookings', AppointmentViewSet, basename='appointment')
router.register(r'shifts', StylistShiftViewSet, basename='stylist-shift')
router.register(r'leaves', StylistLeaveViewSet, basename='stylist-leave')

urlpatterns = [
    path('', include(router.urls)),
]
