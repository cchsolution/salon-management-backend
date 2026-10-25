from rest_framework import permissions
from apps.core.models import UserRole


class IsSuperAdmin(permissions.BasePermission):
    """Platform administrator with global access across all tenants."""
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.role == UserRole.SUPERADMIN or request.user.is_superuser)
        )


class IsSalonOwner(permissions.BasePermission):
    """
    Grants access only to Superadmin, Salon Owner, or Salon Manager.
    Explicitly denies Hair Stylist, Receptionist, and Customers (HTTP 403).
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role == UserRole.SUPERADMIN or request.user.is_superuser:
            return True
        return request.user.role in [UserRole.SALON_OWNER, UserRole.SALON_MANAGER]

    def has_object_permission(self, request, view, obj):
        if request.user.role == UserRole.SUPERADMIN or request.user.is_superuser:
            return True
        obj_salon = getattr(obj, 'salon', obj)
        return bool(request.user.salon and obj_salon == request.user.salon)


class IsOwnerOrReceptionist(permissions.BasePermission):
    """
    Grants access to Superadmin, Salon Owner, Salon Manager, and Receptionist.
    Used for front-desk operations (e.g. POS billing, customer check-in, bookings).
    Hair Stylist and Customer are explicitly denied (HTTP 403).
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role == UserRole.SUPERADMIN or request.user.is_superuser:
            return True
        return request.user.role in [
            UserRole.SALON_OWNER,
            UserRole.SALON_MANAGER,
            UserRole.RECEPTIONIST
        ]

    def has_object_permission(self, request, view, obj):
        if request.user.role == UserRole.SUPERADMIN or request.user.is_superuser:
            return True
        obj_salon = getattr(obj, 'salon', obj)
        return bool(request.user.salon and obj_salon == request.user.salon)


class IsSalonStaff(permissions.BasePermission):
    """
    Grants access to any authenticated salon staff member (Owner, Manager, Receptionist, Stylist).
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_salon_staff)

    def has_object_permission(self, request, view, obj):
        if request.user.role == UserRole.SUPERADMIN or request.user.is_superuser:
            return True
        obj_salon = getattr(obj, 'salon', obj)
        return bool(request.user.salon and obj_salon == request.user.salon)


class IsTenantMember(permissions.BasePermission):
    """
    Ensures request user belongs to the same salon tenant as the target object.
    Blocks cross-salon access even if IDs are guessed or forged.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role == UserRole.SUPERADMIN or request.user.is_superuser:
            return True
        return bool(request.user.salon)

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == UserRole.SUPERADMIN or request.user.is_superuser:
            return True
        obj_salon = getattr(obj, 'salon', None)
        if obj_salon is None and hasattr(obj, 'id') and obj.__class__.__name__ == 'Salon':
            obj_salon = obj
        return bool(request.user.salon and obj_salon == request.user.salon)


class IsOwnerOrReadOnlyForStaff(permissions.BasePermission):
    """
    Safe methods (GET, HEAD, OPTIONS) allowed for all salon staff.
    Write methods (POST, PUT, PATCH, DELETE) strictly restricted to Salon Owner / SuperAdmin.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role in [UserRole.SUPERADMIN, UserRole.SALON_OWNER, UserRole.SALON_MANAGER] or request.user.is_superuser:
            return True
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_salon_staff
        return False

    def has_object_permission(self, request, view, obj):
        if request.user.role == UserRole.SUPERADMIN or request.user.is_superuser:
            return True
        obj_salon = getattr(obj, 'salon', obj)
        if not request.user.salon or obj_salon != request.user.salon:
            return False
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_salon_staff
        return request.user.role in [UserRole.SALON_OWNER, UserRole.SALON_MANAGER]


class IsPublicOrStaffOnly(permissions.BasePermission):
    """Safe read-only methods for public/storefront customers, write methods for salon staff."""
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.is_salon_staff)

