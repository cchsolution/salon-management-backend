from django.db.models import Prefetch, Count
from django.core.cache import cache
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.catalog.models import ServiceCategory, Service, ServiceStyle, Resource
from apps.catalog.serializers import (
    ServiceCategorySerializer, ServiceSerializer, ServiceStyleSerializer, ResourceSerializer
)
from apps.tenants.permissions import IsSalonOwner, IsSalonStaff, IsSuperAdmin, IsTenantMember
from apps.core.models import Salon, UserRole, StaffProfile

def get_catalog_cache_key(prefix, request, salon):
    salon_id = salon.id if salon else 'public'
    query_str = request.META.get('QUERY_STRING', '')
    return f"cat_{prefix}_{salon_id}_{query_str}"

def invalidate_catalog_cache():
    cache.clear()

def get_optimized_staff_prefetch():
    return StaffProfile.objects.select_related('user', 'branch', 'salon')

def get_optimized_styles_prefetch():
    return ServiceStyle.objects.select_related(
        'service', 'salon'
    ).prefetch_related(
        Prefetch('qualified_staff', queryset=get_optimized_staff_prefetch())
    )

def resolve_catalog_salon(request):
    salon = getattr(request, 'salon', None)
    if salon:
        return salon
    if request.user.is_authenticated and request.user.salon:
        return request.user.salon
    salon_slug = request.query_params.get('salon_slug') or request.headers.get('X-Salon-Slug')
    if salon_slug:
        return Salon.objects.filter(slug=salon_slug, is_active=True).first()
    salon_id = request.query_params.get('salon_id') or request.headers.get('X-Salon-Id')
    if salon_id:
        return Salon.objects.filter(id=salon_id, is_active=True).first()
    return None


class ServiceCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceCategorySerializer
    permission_classes = [IsTenantMember]

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'services']:
            return [permissions.AllowAny()]
        return [IsSalonOwner()]

    def get_queryset(self):
        user = self.request.user
        salon = resolve_catalog_salon(self.request)

        staff_prefetch = Prefetch('qualified_staff', queryset=get_optimized_staff_prefetch())

        qs = ServiceCategory.objects.select_related('salon').annotate(
            services_count_annotated=Count('services', distinct=True)
        ).prefetch_related(staff_prefetch).order_by('sort_order', 'name')

        if user.is_authenticated and (user.role == UserRole.SUPERADMIN or user.is_superuser):
            return qs
        if user.is_authenticated and user.salon:
            qs = qs.filter(salon=user.salon)
            is_active_param = self.request.query_params.get('is_active')
            if is_active_param is not None:
                qs = qs.filter(is_active=is_active_param.lower() in ('true', '1'))
            return qs
        if salon:
            return qs.filter(salon=salon, is_active=True)
        if self.action in ['retrieve', 'services']:
            return qs.filter(is_active=True)
        return ServiceCategory.objects.none()

    def list(self, request, *args, **kwargs):
        salon = resolve_catalog_salon(request)
        ckey = get_catalog_cache_key('cats', request, salon)
        cached = cache.get(ckey)
        if cached is not None:
            return Response(cached)
        res = super().list(request, *args, **kwargs)
        cache.set(ckey, res.data, timeout=120)
        return res

    def perform_create(self, serializer):
        salon = self.request.user.salon or resolve_catalog_salon(self.request)
        serializer.save(salon=salon)
        invalidate_catalog_cache()

    def perform_update(self, serializer):
        serializer.save()
        invalidate_catalog_cache()

    def perform_destroy(self, instance):
        instance.delete()
        invalidate_catalog_cache()

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny])
    def services(self, request, pk=None):
        category = self.get_object()
        services = Service.objects.filter(category=category, is_active=True).select_related(
            'category', 'salon'
        ).prefetch_related(
            'branches',
            Prefetch('qualified_staff', queryset=get_optimized_staff_prefetch()),
            Prefetch('styles', queryset=get_optimized_styles_prefetch())
        )
        return Response(ServiceSerializer(services, many=True).data)


class ServiceViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceSerializer
    permission_classes = [IsTenantMember]

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'styles']:
            return [permissions.AllowAny()]
        return [IsSalonOwner()]

    def get_queryset(self):
        user = self.request.user
        salon = resolve_catalog_salon(self.request)

        qs = Service.objects.select_related('category', 'salon').prefetch_related(
            'branches',
            Prefetch('qualified_staff', queryset=get_optimized_staff_prefetch()),
            Prefetch('styles', queryset=get_optimized_styles_prefetch())
        ).order_by('name')

        if user.is_authenticated and (user.role == UserRole.SUPERADMIN or user.is_superuser):
            pass
        elif user.is_authenticated and user.salon:
            qs = qs.filter(salon=user.salon)
            is_active_param = self.request.query_params.get('is_active')
            if is_active_param is not None:
                qs = qs.filter(is_active=is_active_param.lower() in ('true', '1'))
        elif salon:
            qs = qs.filter(salon=salon, is_active=True)
        elif self.action in ['retrieve', 'styles']:
            qs = qs.filter(is_active=True)
        else:
            return Service.objects.none()

        # Query param filters
        category_id = self.request.query_params.get('category') or self.request.query_params.get('category_id')
        if category_id:
            qs = qs.filter(category_id=category_id)

        featured = self.request.query_params.get('featured')
        if featured in ['true', '1']:
            qs = qs.filter(is_featured=True)

        branch_id = self.request.query_params.get('branch') or self.request.query_params.get('branch_id')
        if branch_id:
            qs = qs.filter(branches__id=branch_id)

        search = self.request.query_params.get('search') or self.request.query_params.get('q')
        if search:
            qs = qs.filter(name__icontains=search)

        return qs

    def list(self, request, *args, **kwargs):
        salon = resolve_catalog_salon(request)
        ckey = get_catalog_cache_key('srvs', request, salon)
        cached = cache.get(ckey)
        if cached is not None:
            return Response(cached)
        res = super().list(request, *args, **kwargs)
        cache.set(ckey, res.data, timeout=120)
        return res

    def perform_create(self, serializer):
        salon = self.request.user.salon or resolve_catalog_salon(self.request)
        serializer.save(salon=salon)
        invalidate_catalog_cache()

    def perform_update(self, serializer):
        serializer.save()
        invalidate_catalog_cache()

    def perform_destroy(self, instance):
        instance.delete()
        invalidate_catalog_cache()

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny])
    def styles(self, request, pk=None):
        service = self.get_object()
        styles = ServiceStyle.objects.filter(service=service, is_active=True).select_related(
            'service', 'salon'
        ).prefetch_related(
            Prefetch('qualified_staff', queryset=get_optimized_staff_prefetch())
        )
        return Response(ServiceStyleSerializer(styles, many=True).data)


class ServiceStyleViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceStyleSerializer
    permission_classes = [IsTenantMember]

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [IsSalonOwner()]

    def get_queryset(self):
        user = self.request.user
        salon = resolve_catalog_salon(self.request)
        qs = ServiceStyle.objects.select_related('service', 'salon').prefetch_related(
            Prefetch('qualified_staff', queryset=get_optimized_staff_prefetch())
        ).order_by('sort_order', 'name')

        if user.is_authenticated and (user.role == UserRole.SUPERADMIN or user.is_superuser):
            pass
        elif user.is_authenticated and user.salon:
            qs = qs.filter(salon=user.salon)
            is_active_param = self.request.query_params.get('is_active')
            if is_active_param is not None:
                qs = qs.filter(is_active=is_active_param.lower() in ('true', '1'))
        elif salon:
            qs = qs.filter(salon=salon, is_active=True)
        else:
            return ServiceStyle.objects.none()

        service_id = self.request.query_params.get('service') or self.request.query_params.get('service_id')
        if service_id:
            qs = qs.filter(service_id=service_id)

        return qs

    def list(self, request, *args, **kwargs):
        salon = resolve_catalog_salon(request)
        ckey = get_catalog_cache_key('styls', request, salon)
        cached = cache.get(ckey)
        if cached is not None:
            return Response(cached)
        res = super().list(request, *args, **kwargs)
        cache.set(ckey, res.data, timeout=120)
        return res

    def perform_create(self, serializer):
        salon = self.request.user.salon or resolve_catalog_salon(self.request)
        service = serializer.validated_data.get('service')
        if service and not salon:
            salon = service.salon
        serializer.save(salon=salon)
        invalidate_catalog_cache()

    def perform_update(self, serializer):
        serializer.save()
        invalidate_catalog_cache()

    def perform_destroy(self, instance):
        instance.delete()
        invalidate_catalog_cache()


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
