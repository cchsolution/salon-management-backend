import logging
from django.db.models import Q
from django.core.cache import cache
from django.core import signing
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.customers.models import Customer, CustomerActivity
from apps.customers.serializers import CustomerSerializer, CustomerActivitySerializer
from apps.tenants.permissions import IsSalonStaff, IsSalonOwner, IsTenantMember
from apps.tenants.utils import get_authenticated_salon
from apps.core.models import Salon, UserRole, AuditLog

logger = logging.getLogger(__name__)

DELETION_TOKEN_SALT = 'crm-customer-deletion-salt'
DELETION_TOKEN_MAX_AGE = 600  # 10 minutes


def get_crm_version(salon_id):
    return cache.get(f"crm_ver_{salon_id}", 1)


def invalidate_crm_cache(salon_id):
    try:
        ver = cache.get(f"crm_ver_{salon_id}", 1)
        cache.set(f"crm_ver_{salon_id}", ver + 1, timeout=86400)
    except Exception:
        pass


def resolve_customer_salon(request):
    return get_authenticated_salon(request, allow_public=True)


class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['first_name', 'last_name', 'phone', 'email']
    ordering_fields = ['first_name', 'total_spend', 'last_visit', 'visit_count']

    def get_permissions(self):
        if self.action in ['lookup_or_create']:
            return [permissions.AllowAny()]
        if self.action in ['update', 'partial_update', 'destroy', 'request_deletion_token', 'request_delete_token']:
            return [permissions.IsAuthenticated(), IsSalonOwner()]
        return [permissions.IsAuthenticated(), IsTenantMember()]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return Customer.objects.none()

        include_inactive = self.request.query_params.get('include_inactive', '').lower() in ['true', '1']

        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            qs = Customer.objects.all().select_related('salon', 'user').prefetch_related('activities')
        elif not user.salon:
            return Customer.objects.none()
        elif user.role in [UserRole.SALON_OWNER, UserRole.SALON_MANAGER, UserRole.RECEPTIONIST]:
            qs = Customer.objects.filter(salon=user.salon).select_related('salon', 'user').prefetch_related('activities')
        elif user.role == UserRole.STYLIST:
            from apps.appointments.models import Appointment
            if hasattr(user, 'staff_profile'):
                assigned_customer_ids = Appointment.objects.filter(
                    salon=user.salon,
                    staff=user.staff_profile
                ).values_list('customer_id', flat=True)
                qs = Customer.objects.filter(salon=user.salon, id__in=assigned_customer_ids).select_related('salon', 'user').prefetch_related('activities')
            else:
                qs = Customer.objects.none()
        elif user.role == UserRole.CUSTOMER:
            return Customer.objects.filter(salon=user.salon, user=user).select_related('salon', 'user').prefetch_related('activities')
        else:
            return Customer.objects.none()

        if not include_inactive and self.action not in ['retrieve', 'update', 'partial_update', 'destroy']:
            qs = qs.filter(is_active=True)

        # Custom search filters
        phone_param = self.request.query_params.get('phone')
        if phone_param:
            qs = qs.filter(phone__icontains=phone_param.strip())

        name_param = self.request.query_params.get('name')
        if name_param:
            parts = name_param.strip().split()
            if len(parts) > 1:
                qs = qs.filter(first_name__icontains=parts[0], last_name__icontains=parts[-1])
            else:
                qs = qs.filter(Q(first_name__icontains=name_param) | Q(last_name__icontains=name_param))

        q_param = self.request.query_params.get('q') or self.request.query_params.get('query')
        if q_param:
            qs = qs.filter(
                Q(first_name__icontains=q_param) |
                Q(last_name__icontains=q_param) |
                Q(phone__icontains=q_param) |
                Q(email__icontains=q_param)
            )

        tag = self.request.query_params.get('tag')
        if tag:
            qs = qs.filter(tags__contains=[tag])

        return qs

    def list(self, request, *args, **kwargs):
        salon_id = getattr(request.user, 'salon_id', None) or 'public'
        ver = get_crm_version(salon_id)
        qstr = request.META.get('QUERY_STRING', '')
        ckey = f"crm_clients_{salon_id}_{request.user.id}_v{ver}_{qstr}"
        cached = cache.get(ckey)
        if cached is not None:
            return Response(cached)
        res = super().list(request, *args, **kwargs)
        cache.set(ckey, res.data, timeout=60)
        return res

    def perform_create(self, serializer):
        salon = resolve_customer_salon(self.request)
        serializer.save(salon=salon)
        if salon:
            invalidate_crm_cache(salon.id)

    def perform_update(self, serializer):
        customer = serializer.save()
        if customer and customer.salon:
            invalidate_crm_cache(customer.salon.id)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsSalonOwner])
    def request_deletion_token(self, request, pk=None):
        """
        Generates a secure, time-limited (10 min), single-use cryptographic confirmation token
        bound strictly to the target customer and the authenticated user.
        """
        customer = self.get_object()
        signer = signing.TimestampSigner(salt=DELETION_TOKEN_SALT)
        token_payload = {
            'customer_id': str(customer.id),
            'user_id': str(request.user.id),
            'action': 'DELETE_CUSTOMER'
        }
        token = signer.sign_object(token_payload)

        # Store in cache to enforce single-use
        cache_key = f"crm_del_token_{token}"
        cache.set(cache_key, str(customer.id), timeout=DELETION_TOKEN_MAX_AGE)

        return Response({
            'confirmation_token': token,
            'customer_id': str(customer.id),
            'customer_name': customer.full_name,
            'expires_in_seconds': DELETION_TOKEN_MAX_AGE,
            'message': 'Confirmation token generated. Submit this token via confirmation_token to authorize deletion.'
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsSalonOwner])
    def request_delete_token(self, request, pk=None):
        """Convenience alias for request_deletion_token."""
        return self.request_deletion_token(request, pk=pk)

    def destroy(self, request, *args, **kwargs):
        """
        Safely archives / soft-deletes a customer after verifying the cryptographic confirmation token.
        Preserves all related invoices, payments, and historical appointments intact.
        """
        customer = self.get_object()

        # Extract confirmation token from headers, query params, or body
        token = (
            request.headers.get('X-Delete-Token') or
            request.headers.get('X-Confirmation-Token') or
            request.query_params.get('confirmation_token') or
            request.query_params.get('token') or
            (request.data.get('confirmation_token') if isinstance(request.data, dict) else None) or
            (request.data.get('token') if isinstance(request.data, dict) else None) or
            (request.data.get('confirm_token') if isinstance(request.data, dict) else None)
        )

        if not token:
            return Response({
                'error': 'A server-issued deletion confirmation token is required to delete a customer. Call request_deletion_token first to generate a token.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Verify cryptographic token signature and age
        signer = signing.TimestampSigner(salt=DELETION_TOKEN_SALT)
        try:
            payload = signer.unsign_object(token, max_age=DELETION_TOKEN_MAX_AGE)
        except signing.SignatureExpired:
            return Response({'error': 'The deletion confirmation token has expired. Please request a new token.'}, status=status.HTTP_400_BAD_REQUEST)
        except (signing.BadSignature, Exception):
            return Response({'error': 'Invalid deletion confirmation token.'}, status=status.HTTP_400_BAD_REQUEST)

        # Verify token is bound to this specific customer and user
        if payload.get('customer_id') != str(customer.id):
            return Response({'error': 'The deletion token was not issued for this customer.'}, status=status.HTTP_403_FORBIDDEN)
        if payload.get('user_id') != str(request.user.id):
            return Response({'error': 'The deletion token was issued for a different authorized user.'}, status=status.HTTP_403_FORBIDDEN)

        # Enforce single-use
        cache_key = f"crm_del_token_{token}"
        if not cache.get(cache_key):
            return Response({'error': 'This deletion confirmation token has already been used or expired.'}, status=status.HTTP_400_BAD_REQUEST)
        cache.delete(cache_key)

        # Perform safe soft-deletion / archival to preserve financial history and appointments
        customer.is_active = False
        customer.save(update_fields=['is_active'])

        # Audit log and activity record
        CustomerActivity.objects.create(
            salon=customer.salon,
            customer=customer,
            activity_type='NOTE',
            title='Customer Profile Archived',
            description=f'Customer profile was safely archived by {request.user.get_full_name() or request.user.email}.',
            metadata={'archived_by': str(request.user.id)}
        )

        AuditLog.objects.create(
            salon=customer.salon,
            user=request.user,
            action='ARCHIVE_CUSTOMER',
            entity_type='Customer',
            entity_id=str(customer.id),
            details={'customer_name': customer.full_name, 'phone': customer.phone}
        )

        if customer.salon_id:
            invalidate_crm_cache(customer.salon_id)

        return Response({
            'message': f'Customer "{customer.full_name}" has been safely archived.',
            'id': str(customer.id),
            'is_active': False
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def search(self, request):
        """
        Dedicated search endpoint for name and phone, strictly salon-scoped.
        Query params: phone, name, query, search
        """
        qs = self.get_queryset()
        return Response(CustomerSerializer(qs[:50], many=True).data)

    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def lookup_or_create(self, request):
        """
        Public/Booking wizard helper: finds an existing customer by phone within
        the salon or creates a new one. Never exposes customers across salons.
        """
        salon = resolve_customer_salon(request)
        if not salon:
            return Response({'error': 'Salon tenant could not be identified.'}, status=status.HTTP_400_BAD_REQUEST)

        phone = (request.data.get('phone') or '').strip()
        if not phone:
            return Response({'error': 'phone is required.'}, status=status.HTTP_400_BAD_REQUEST)

        customer = Customer.objects.filter(salon=salon, phone=phone).first()
        if not customer:
            first_name = (request.data.get('first_name') or request.data.get('name') or 'Guest').strip()
            last_name = (request.data.get('last_name') or '').strip()
            email = (request.data.get('email') or '').strip()

            customer = Customer.objects.create(
                salon=salon,
                phone=phone,
                first_name=first_name,
                last_name=last_name,
                email=email,
                is_active=True
            )
            invalidate_crm_cache(salon.id)
        else:
            # Reactivate if previously archived
            updated_fields = []
            if not customer.is_active:
                customer.is_active = True
                updated_fields.append('is_active')
            if request.data.get('first_name') and customer.first_name == 'Guest':
                customer.first_name = request.data.get('first_name').strip()
                updated_fields.append('first_name')
                if request.data.get('last_name'):
                    customer.last_name = request.data.get('last_name').strip()
                    updated_fields.append('last_name')
            if updated_fields:
                customer.save(update_fields=updated_fields)
                invalidate_crm_cache(salon.id)

        return Response(CustomerSerializer(customer).data)


class CustomerActivityViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerActivitySerializer
    permission_classes = [IsSalonStaff, IsTenantMember]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return CustomerActivity.objects.none()
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return CustomerActivity.objects.all()
        if user.salon:
            return CustomerActivity.objects.filter(salon=user.salon)
        return CustomerActivity.objects.none()

    def perform_create(self, serializer):
        serializer.save(salon=self.request.user.salon)
