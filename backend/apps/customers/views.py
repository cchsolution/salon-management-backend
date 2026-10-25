from rest_framework import viewsets, permissions, filters
from apps.customers.models import Customer, CustomerActivity
from apps.customers.serializers import CustomerSerializer, CustomerActivitySerializer
from apps.tenants.permissions import IsSalonStaff, IsTenantMember
from apps.core.models import UserRole

class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['first_name', 'last_name', 'phone', 'email']
    ordering_fields = ['first_name', 'total_spend', 'last_visit', 'visit_count']

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return Customer.objects.none()

        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return Customer.objects.all().prefetch_related('activities')

        if not user.salon:
            return Customer.objects.none()

        # Salon Owner / Manager / Receptionist: all customers of their salon
        if user.role in [UserRole.SALON_OWNER, UserRole.SALON_MANAGER, UserRole.RECEPTIONIST]:
            qs = Customer.objects.filter(salon=user.salon).prefetch_related('activities')
            tag = self.request.query_params.get('tag')
            if tag:
                qs = qs.filter(tags__contains=[tag])
            return qs

        # Hair Stylist: their assigned customers where applicable
        if user.role == UserRole.STYLIST:
            from apps.appointments.models import Appointment
            if hasattr(user, 'staff_profile'):
                assigned_customer_ids = Appointment.objects.filter(
                    salon=user.salon,
                    staff=user.staff_profile
                ).values_list('customer_id', flat=True)
                qs = Customer.objects.filter(salon=user.salon, id__in=assigned_customer_ids).prefetch_related('activities')
            else:
                qs = Customer.objects.none()
            tag = self.request.query_params.get('tag')
            if tag:
                qs = qs.filter(tags__contains=[tag])
            return qs

        # Normal customer only sees own profile record
        if user.role == UserRole.CUSTOMER:
            return Customer.objects.filter(salon=user.salon, user=user).prefetch_related('activities')

        return Customer.objects.none()

    def perform_create(self, serializer):
        serializer.save(salon=self.request.user.salon)


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

