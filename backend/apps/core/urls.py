from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.core.views import (
    register_view, login_view, me_view, logout_view,
    SalonViewSet, BranchViewSet, StaffProfileViewSet, AuditLogViewSet
)

router = DefaultRouter()
router.register(r'salons', SalonViewSet, basename='salon')
router.register(r'branches', BranchViewSet, basename='branch')
router.register(r'staff', StaffProfileViewSet, basename='staff')
router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')

urlpatterns = [
    path('auth/register/', register_view, name='auth-register'),
    path('auth/login/', login_view, name='auth-login'),
    path('auth/me/', me_view, name='auth-me'),
    path('auth/logout/', logout_view, name='auth-logout'),
    path('', include(router.urls)),
]
