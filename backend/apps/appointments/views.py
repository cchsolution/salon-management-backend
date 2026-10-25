import datetime
from django.db import transaction
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.appointments.models import (
    Appointment, AppointmentItem, StylistShift, StylistLeave,
    AppointmentStatus, BookingSource
)
from apps.appointments.serializers import (
    AppointmentSerializer, StylistShiftSerializer, StylistLeaveSerializer
)
from apps.appointments.services import check_appointment_conflict, get_available_slots
from apps.core.models import Salon, Branch, StaffProfile, UserRole, AuditLog
from apps.customers.models import Customer, CustomerActivity
from apps.catalog.models import Service
from apps.tenants.permissions import IsSalonStaff, IsSalonOwner, IsTenantMember

class AppointmentViewSet(viewsets.ModelViewSet):
    serializer_class = AppointmentSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['date', 'start_time', 'created_at']

    def get_permissions(self):
        if self.action in ['create', 'available_slots']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsTenantMember()]

    def get_queryset(self):
        user = self.request.user
        qs = Appointment.objects.select_related(
            'salon', 'branch', 'customer', 'staff__user'
        ).prefetch_related('items__service')

        if not (user and user.is_authenticated):
            return Appointment.objects.none()

        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            pass
        elif user.is_salon_staff and user.salon:
            qs = qs.filter(salon=user.salon)
            # Stylist only sees their own appointments if not owner/manager
            if user.role == UserRole.STYLIST:
                if hasattr(user, 'staff_profile'):
                    qs = qs.filter(staff=user.staff_profile)
                else:
                    return Appointment.objects.none()
        else:
            # Customer role
            qs = qs.filter(customer__user=user)


        # Query Filters
        date = self.request.query_params.get('date')
        if date:
            qs = qs.filter(date=date)

        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            qs = qs.filter(date__range=[start_date, end_date])

        branch_id = self.request.query_params.get('branch')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        staff_id = self.request.query_params.get('staff')
        if staff_id:
            qs = qs.filter(staff_id=staff_id)

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        return qs

    def create(self, request, *args, **kwargs):
        data = request.data
        user = request.user if request.user.is_authenticated else None

        # 1. Determine Salon & Branch
        salon = None
        if user and user.salon:
            salon = user.salon
        elif data.get('salon_id'):
            salon = Salon.objects.filter(id=data['salon_id']).first()
        elif request.headers.get('X-Salon-Slug'):
            salon = Salon.objects.filter(slug=request.headers.get('X-Salon-Slug')).first()

        if not salon:
            return Response({'error': 'Salon tenant could not be identified.'}, status=status.HTTP_400_BAD_REQUEST)

        branch_id = data.get('branch') or data.get('branch_id')
        branch = Branch.objects.filter(salon=salon, id=branch_id).first()
        if not branch:
            branch = Branch.objects.filter(salon=salon, is_primary=True).first()
            if not branch:
                return Response({'error': 'A valid branch is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Identify or Create Customer
        customer = None
        if user and not user.is_salon_staff:
            customer = Customer.objects.filter(salon=salon, user=user).first()

        if not customer:
            customer_id = data.get('customer') or data.get('customer_id')
            if customer_id:
                customer = Customer.objects.filter(salon=salon, id=customer_id).first()

        if not customer:
            # Guest or Walk-in customer creation
            first_name = data.get('customer_first_name') or data.get('first_name', 'Walk-in')
            last_name = data.get('customer_last_name') or data.get('last_name', 'Customer')
            phone = data.get('customer_phone') or data.get('phone', '0000000000')
            email = data.get('customer_email') or data.get('email', '')

            customer, _ = Customer.objects.get_or_create(
                salon=salon,
                phone=phone,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': email,
                    'user': user if (user and not user.is_salon_staff) else None
                }
            )

        # 3. Stylist
        staff_id = data.get('staff') or data.get('staff_id')
        staff = StaffProfile.objects.filter(salon=salon, id=staff_id).first()
        if not staff:
            # Pick any available bookable staff
            staff = StaffProfile.objects.filter(salon=salon, is_bookable=True).first()
            if not staff:
                return Response({'error': 'No bookable stylist found for this salon.'}, status=status.HTTP_400_BAD_REQUEST)

        # 4. Services & Calculation
        service_ids = data.get('service_ids', [])
        if not service_ids and data.get('service_id'):
            service_ids = [data.get('service_id')]

        services = Service.objects.filter(salon=salon, id__in=service_ids, is_active=True)
        if not services.exists():
            return Response({'error': 'At least one valid service must be selected.'}, status=status.HTTP_400_BAD_REQUEST)

        total_duration = sum(s.duration_minutes for s in services)
        total_price = sum(s.effective_price for s in services)

        # 5. Timing & Conflict Validation (Transaction Safe)
        date_str = data.get('date')
        start_time_str = data.get('start_time')
        try:
            target_date = datetime.date.fromisoformat(date_str)
            if len(start_time_str.split(':')) == 2:
                start_time_str += ':00'
            start_time = datetime.time.fromisoformat(start_time_str)
        except Exception:
            return Response({'error': 'Invalid date or start_time format.'}, status=status.HTTP_400_BAD_REQUEST)

        start_dt = datetime.datetime.combine(target_date, start_time)
        end_dt = start_dt + datetime.timedelta(minutes=total_duration)
        end_time = end_dt.time()

        booking_source = data.get('booking_source')
        if not booking_source:
            booking_source = BookingSource.WALK_IN if (user and user.is_salon_staff) else BookingSource.ONLINE

        with transaction.atomic():
            # Concurrency check
            if check_appointment_conflict(staff, target_date, start_time, end_time):
                return Response(
                    {'error': f'Stylist {staff.user.get_full_name()} is no longer available between {start_time.strftime("%H:%M")} and {end_time.strftime("%H:%M")}. Please pick another time slot.'},
                    status=status.HTTP_409_CONFLICT
                )

            appointment = Appointment.objects.create(
                salon=salon,
                branch=branch,
                customer=customer,
                staff=staff,
                date=target_date,
                start_time=start_time,
                end_time=end_time,
                status=AppointmentStatus.CONFIRMED,
                booking_source=booking_source,
                total_amount=total_price,
                total_duration_minutes=total_duration,
                notes=data.get('notes', ''),
            )

            for s in services:
                AppointmentItem.objects.create(
                    salon=salon,
                    appointment=appointment,
                    service=s,
                    price=s.effective_price,
                    duration_minutes=s.duration_minutes
                )

            # Customer timeline entry
            CustomerActivity.objects.create(
                salon=salon,
                customer=customer,
                activity_type='BOOKING',
                title=f"Booked {', '.join([s.name for s in services])}",
                description=f"Appointment on {appointment.date} at {appointment.start_time.strftime('%H:%M')} with {staff.user.get_full_name()}.",
                metadata={'appointment_id': str(appointment.id)}
            )

            # Audit Log
            AuditLog.objects.create(
                salon=salon,
                user=user,
                action='CREATE_APPOINTMENT',
                entity_type='Appointment',
                entity_id=str(appointment.id),
                details={'total_amount': str(total_price), 'customer': customer.full_name}
            )

        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsSalonStaff])
    def update_status(self, request, pk=None):
        appointment = self.get_object()
        new_status = request.data.get('status')
        if new_status not in AppointmentStatus.values:
            return Response({'error': f'Invalid status. Choices are: {AppointmentStatus.values}'}, status=status.HTTP_400_BAD_REQUEST)

        old_status = appointment.status
        appointment.status = new_status
        if new_status == AppointmentStatus.CANCELLED:
            appointment.cancellation_reason = request.data.get('reason', '')
        appointment.save()

        # Update customer metrics if completed
        if new_status == AppointmentStatus.COMPLETED and old_status != AppointmentStatus.COMPLETED:
            customer = appointment.customer
            customer.visit_count += 1
            customer.last_visit = datetime.datetime.combine(appointment.date, appointment.start_time)
            customer.save(update_fields=['visit_count', 'last_visit'])

            CustomerActivity.objects.create(
                salon=appointment.salon,
                customer=customer,
                activity_type='COMPLETED',
                title='Appointment Completed',
                description=f"Appointment on {appointment.date} was marked completed.",
                metadata={'appointment_id': str(appointment.id)}
            )

        return Response(AppointmentSerializer(appointment).data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def available_slots(self, request):
        """
        Public endpoint: computes available booking slots.
        Query params: date (YYYY-MM-DD), staff_id, branch_id, duration (minutes)
        """
        date_str = request.query_params.get('date')
        staff_id = request.query_params.get('staff_id')
        branch_id = request.query_params.get('branch_id')
        duration = int(request.query_params.get('duration', 60))

        if not date_str:
            return Response({'error': 'date parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            return Response({'error': 'Invalid date format (use YYYY-MM-DD).'}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve salon
        salon = getattr(request, 'salon', None)
        if not salon and request.user.is_authenticated and request.user.salon:
            salon = request.user.salon
        elif not salon and request.query_params.get('salon_slug'):
            salon = Salon.objects.filter(slug=request.query_params.get('salon_slug')).first()

        if not salon and staff_id:
            staff = StaffProfile.objects.filter(id=staff_id).first()
            if staff:
                salon = staff.salon

        if not salon:
            return Response({'error': 'Salon tenant could not be identified.'}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve staff & branch
        staff = None
        if staff_id:
            staff = StaffProfile.objects.filter(salon=salon, id=staff_id, is_bookable=True).first()
        if not staff:
            staff = StaffProfile.objects.filter(salon=salon, is_bookable=True).first()

        if not staff:
            return Response({'slots': [], 'message': 'No bookable stylist found.'})

        branch = None
        if branch_id:
            branch = Branch.objects.filter(salon=salon, id=branch_id).first()
        if not branch and staff.branch:
            branch = staff.branch
        if not branch:
            branch = Branch.objects.filter(salon=salon, is_primary=True).first()

        slots = get_available_slots(salon, branch, staff, target_date, duration)
        return Response({
            'date': date_str,
            'staff': {'id': str(staff.id), 'name': staff.user.get_full_name(), 'title': staff.title},
            'branch': {'id': str(branch.id), 'name': branch.name} if branch else None,
            'duration_minutes': duration,
            'slots': slots
        })


class StylistShiftViewSet(viewsets.ModelViewSet):
    serializer_class = StylistShiftSerializer
    permission_classes = [IsTenantMember]

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsSalonStaff(), IsTenantMember()]
        return [IsSalonOwner()]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return StylistShift.objects.none()
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return StylistShift.objects.all()
        if user.role == UserRole.STYLIST:
            if hasattr(user, 'staff_profile'):
                return StylistShift.objects.filter(salon=user.salon, staff=user.staff_profile).select_related('staff__user', 'branch')
            return StylistShift.objects.none()
        if user.salon:
            return StylistShift.objects.filter(salon=user.salon).select_related('staff__user', 'branch')
        return StylistShift.objects.none()

    def perform_create(self, serializer):
        serializer.save(salon=self.request.user.salon)


class StylistLeaveViewSet(viewsets.ModelViewSet):
    serializer_class = StylistLeaveSerializer
    permission_classes = [IsTenantMember]

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'create']:
            return [IsSalonStaff(), IsTenantMember()]
        return [IsSalonOwner()]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return StylistLeave.objects.none()
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return StylistLeave.objects.all()
        if user.role == UserRole.STYLIST:
            if hasattr(user, 'staff_profile'):
                return StylistLeave.objects.filter(salon=user.salon, staff=user.staff_profile).select_related('staff__user')
            return StylistLeave.objects.none()
        if user.salon:
            return StylistLeave.objects.filter(salon=user.salon).select_related('staff__user')
        return StylistLeave.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        staff = getattr(user, 'staff_profile', None) if user.role == UserRole.STYLIST else serializer.validated_data.get('staff')
        serializer.save(salon=user.salon, staff=staff or serializer.validated_data.get('staff'))

