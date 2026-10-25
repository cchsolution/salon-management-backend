from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.core.views import (
    register_view, login_view, me_view, logout_view, refresh_token_view,
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
    path('auth/refresh/', refresh_token_view, name='auth-refresh'),
    path('auth/token/refresh/', refresh_token_view, name='auth-token-refresh'),
    path('auth/logout/', logout_view, name='auth-logout'),
    path('me/', me_view, name='me'),
    path('refresh/', refresh_token_view, name='refresh'),
    path('token/refresh/', refresh_token_view, name='token-refresh'),
    path('', include(router.urls)),
]
