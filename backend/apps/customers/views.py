from django.db.models import Q
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.customers.models import Customer, CustomerActivity
from apps.customers.serializers import CustomerSerializer, CustomerActivitySerializer
from apps.tenants.permissions import IsSalonStaff, IsTenantMember
from apps.core.models import Salon, UserRole

def resolve_customer_salon(request):
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


class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['first_name', 'last_name', 'phone', 'email']
    ordering_fields = ['first_name', 'total_spend', 'last_visit', 'visit_count']

    def get_permissions(self):
        if self.action in ['lookup_or_create']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsTenantMember()]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return Customer.objects.none()

        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            qs = Customer.objects.all().select_related('salon', 'user').prefetch_related('activities')
        elif not user.salon:
            return Customer.objects.none()
        elif user.role in [UserRole.SALON_OWNER, UserRole.SALON_MANAGER, UserRole.RECEPTIONIST]:
            # Salon Owner / Manager / Receptionist: all customers of their salon
            qs = Customer.objects.filter(salon=user.salon).select_related('salon', 'user').prefetch_related('activities')
        elif user.role == UserRole.STYLIST:
            # Hair Stylist: their assigned customers where applicable
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
            # Normal customer only sees own profile record
            return Customer.objects.filter(salon=user.salon, user=user).select_related('salon', 'user').prefetch_related('activities')
        else:
            return Customer.objects.none()

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

    def perform_create(self, serializer):
        salon = self.request.user.salon or resolve_customer_salon(self.request)
        serializer.save(salon=salon)

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
                email=email
            )
        elif request.data.get('first_name') and customer.first_name == 'Guest':
            customer.first_name = request.data.get('first_name').strip()
            if request.data.get('last_name'):
                customer.last_name = request.data.get('last_name').strip()
            customer.save(update_fields=['first_name', 'last_name'])

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

