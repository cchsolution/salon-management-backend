from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.appointments.views import (
    AppointmentViewSet, StylistShiftViewSet, StylistLeaveViewSet
)

router = DefaultRouter()
router.register(r'bookings', AppointmentViewSet, basename='appointment')
router.register(r'shifts', StylistShiftViewSet, basename='stylist-shift')
router.register(r'leaves', StylistLeaveViewSet, basename='stylist-leave')
router.register(r'', AppointmentViewSet, basename='appointment-root')

urlpatterns = [
    # Kebab-case aliases for frontend convenience
    path('available-slots/', AppointmentViewSet.as_view({'get': 'available_slots'}), name='appointment-available-slots'),
    path('eligible-stylists/', AppointmentViewSet.as_view({'get': 'eligible_stylists'}), name='appointment-eligible-stylists'),
    path('calendar/', AppointmentViewSet.as_view({'get': 'calendar'}), name='appointment-calendar-view'),
    path('', include(router.urls)),
]
