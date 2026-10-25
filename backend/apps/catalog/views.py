from rest_framework import viewsets, permissions
from apps.catalog.models import ServiceCategory, Service, Resource
from apps.catalog.serializers import ServiceCategorySerializer, ServiceSerializer, ResourceSerializer
from apps.tenants.permissions import IsSalonOwner, IsSalonStaff, IsSuperAdmin, IsTenantMember
from apps.core.models import UserRole

class ServiceCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceCategorySerializer
    permission_classes = [IsTenantMember]

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [IsSalonOwner()]

    def get_queryset(self):
        user = self.request.user
        salon = getattr(self.request, 'salon', None)
        if user.is_authenticated and (user.role == UserRole.SUPERADMIN or user.is_superuser):
            return ServiceCategory.objects.all()
        if user.is_authenticated and user.salon:
            return ServiceCategory.objects.filter(salon=user.salon)
        if salon:
            return ServiceCategory.objects.filter(salon=salon, is_active=True)
        return ServiceCategory.objects.none()

    def perform_create(self, serializer):
        serializer.save(salon=self.request.user.salon)


class ServiceViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceSerializer
    permission_classes = [IsTenantMember]

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [IsSalonOwner()]

    def get_queryset(self):
        user = self.request.user
        salon = getattr(self.request, 'salon', None)
        qs = Service.objects.select_related('category', 'salon').prefetch_related('qualified_staff__user')

        if user.is_authenticated and (user.role == UserRole.SUPERADMIN or user.is_superuser):
            pass
        elif user.is_authenticated and user.salon:
            qs = qs.filter(salon=user.salon)
        elif salon:
            qs = qs.filter(salon=salon, is_active=True)
        else:
            return Service.objects.none()

        # Query param filters
        category_id = self.request.query_params.get('category')
        if category_id:
            qs = qs.filter(category_id=category_id)
            
        featured = self.request.query_params.get('featured')
        if featured in ['true', '1']:
            qs = qs.filter(is_featured=True)

        return qs

    def perform_create(self, serializer):
        serializer.save(salon=self.request.user.salon)


class ResourceViewSet(viewsets.ModelViewSet):
    serializer_class = ResourceSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsSalonStaff()]
        return [IsSalonOwner()]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return Resource.objects.none()
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return Resource.objects.all()
        if user.salon:
            return Resource.objects.filter(salon=user.salon).select_related('branch')
        return Resource.objects.none()


    def perform_create(self, serializer):
        serializer.save(salon=self.request.user.salon)
