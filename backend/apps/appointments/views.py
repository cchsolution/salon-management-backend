import datetime
import logging
import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response

logger = logging.getLogger(__name__)

from apps.appointments.models import (
    Appointment, AppointmentItem, StylistShift, StylistLeave,
    AppointmentStatus, BookingSource
)
from apps.appointments.serializers import (
    AppointmentSerializer, StylistShiftSerializer, StylistLeaveSerializer
)
from apps.appointments.services import (
    get_salon_timezone, get_current_salon_datetime, get_eligible_stylists,
    check_appointment_conflict, get_available_slots, validate_appointment_booking
)
from apps.notifications.services import create_appointment_notification
from apps.core.models import Salon, Branch, StaffProfile, UserRole, AuditLog
from apps.core.serializers import StaffProfileSerializer
from apps.customers.models import Customer, CustomerActivity
from apps.catalog.models import Service, ServiceCategory, ServiceStyle
from apps.tenants.permissions import IsSalonStaff, IsSalonOwner, IsTenantMember
from apps.tenants.utils import get_authenticated_salon, get_authenticated_branch

def safe_uuid(val):
    if not val:
        return None
    try:
        return uuid.UUID(str(val).strip())
    except (ValueError, AttributeError, TypeError):
        return None

def resolve_appointment_salon(request, data=None):
    return get_authenticated_salon(request, data=data, allow_public=True)


class AppointmentViewSet(viewsets.ModelViewSet):
    serializer_class = AppointmentSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['date', 'start_time', 'created_at']

    def get_permissions(self):
        if self.action in ['create', 'available_slots', 'eligible_stylists', 'cancel_public']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsTenantMember()]

    def get_queryset(self):
        user = self.request.user
        qs = Appointment.objects.select_related(
            'salon',
            'branch',
            'customer__user',
            'staff__user',
            'staff__branch',
        ).prefetch_related(
            'items__service',
            'items__style',
        )

        if not (user and user.is_authenticated):
            return Appointment.objects.none()

        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            pass
        elif user.is_salon_staff and user.salon:
            qs = qs.filter(salon=user.salon)
            # Stylist only sees their own appointments if not owner/manager/receptionist
            if user.role == UserRole.STYLIST:
                if hasattr(user, 'staff_profile'):
                    qs = qs.filter(staff=user.staff_profile)
                else:
                    return Appointment.objects.none()
        else:
            # Customer role
            qs = qs.filter(customer__user=user)

        # Filters
        date = self.request.query_params.get('date')
        if date:
            qs = qs.filter(date=date)

        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            qs = qs.filter(date__range=[start_date, end_date])

        branch_id = self.request.query_params.get('branch') or self.request.query_params.get('branch_id')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        staff_id = self.request.query_params.get('staff') or self.request.query_params.get('staff_id')
        if staff_id:
            qs = qs.filter(staff_id=staff_id)

        customer_id = self.request.query_params.get('customer') or self.request.query_params.get('customer_id')
        if customer_id:
            qs = qs.filter(customer_id=customer_id)

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        booking_source = self.request.query_params.get('booking_source')
        if booking_source:
            qs = qs.filter(booking_source=booking_source)

        return qs

    def list(self, request, *args, **kwargs):
        salon_id = getattr(request.user, 'salon_id', None) or 'public'
        qstr = request.META.get('QUERY_STRING', '')
        ckey = f"appt_list_{salon_id}_{request.user.id}_{qstr}"
        cached = cache.get(ckey)
        if cached is not None:
            return Response(cached)
        res = super().list(request, *args, **kwargs)
        cache.set(ckey, res.data, timeout=30)
        return res

    def create(self, request, *args, **kwargs):
        try:
            return self._create_appointment(request, *args, **kwargs)
        except Exception as e:
            logger.error("Error creating appointment: %s", str(e), exc_info=True)
            return Response(
                {'error': 'An unexpected server error occurred while confirming the appointment. Please check the details and try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _create_appointment(self, request, *args, **kwargs):
        data = kwargs.get('data') if kwargs.get('data') is not None else request.data
        user = request.user if request.user.is_authenticated else None

        # 1. Determine Salon
        salon = resolve_appointment_salon(request, data)
        if not salon:
            return Response({'error': 'Salon tenant could not be identified.'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Branch Resolution
        branch = get_authenticated_branch(request, salon, data.get('branch') or data.get('branch_id'))
        if not branch:
            return Response({'error': 'A valid salon branch is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Identify or Create Customer
        customer = None
        if user and not user.is_salon_staff:
            customer = Customer.objects.filter(salon=salon, user=user).first()

        if not customer:
            customer_id = safe_uuid(data.get('customer') or data.get('customer_id'))
            if customer_id:
                customer = Customer.objects.filter(salon=salon, id=customer_id).first()

        if not customer:
            first_name = str(data.get('customer_first_name') or data.get('first_name') or 'Guest').strip()
            last_name = str(data.get('customer_last_name') or data.get('last_name') or '').strip()
            phone = str(data.get('customer_phone') or data.get('phone') or '0000000000').strip()
            email = str(data.get('customer_email') or data.get('email') or '').strip()

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
            # Update customer name if provided
            if first_name != 'Guest' and customer.first_name == 'Guest':
                customer.first_name = first_name
                customer.last_name = last_name
                customer.save(update_fields=['first_name', 'last_name'])

        # 4. Resolve Services & Styles
        raw_service_ids = data.get('service_ids', [])
        if not raw_service_ids and data.get('service_id'):
            raw_service_ids = [data.get('service_id')]
        if not raw_service_ids and data.get('service'):
            raw_service_ids = [data.get('service')]
        if isinstance(raw_service_ids, str):
            raw_service_ids = [raw_service_ids]

        valid_service_uuids = []
        for sid in raw_service_ids:
            u = safe_uuid(sid)
            if u:
                valid_service_uuids.append(u)

        style_id = safe_uuid(data.get('style_id') or data.get('style'))
        selected_style = None
        if style_id:
            selected_style = ServiceStyle.objects.filter(salon=salon, id=style_id, is_active=True).first()
            if selected_style and not valid_service_uuids:
                valid_service_uuids = [selected_style.service_id]

        services = list(Service.objects.filter(salon=salon, id__in=valid_service_uuids, is_active=True))
        if not services:
            return Response({'error': 'At least one valid active service must be selected.'}, status=status.HTTP_400_BAD_REQUEST)

        # 5. Stylist Resolution & Eligibility
        staff_id = safe_uuid(data.get('staff') or data.get('staff_id') or data.get('stylist') or data.get('stylist_id'))
        staff = None
        if staff_id:
            staff = StaffProfile.objects.filter(salon=salon, id=staff_id, is_bookable=True, user__is_active=True).first()
            if not staff:
                return Response({'error': 'The selected stylist is not available or does not belong to this salon.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Pick first eligible bookable staff member
            eligible_qs = get_eligible_stylists(salon, branch=branch, service_id=services[0].id, style_id=selected_style.id if selected_style else None)
            staff = eligible_qs.first()
            if not staff:
                staff = StaffProfile.objects.filter(salon=salon, is_bookable=True, user__is_active=True).first()
            if not staff:
                return Response({'error': 'No eligible bookable stylist available for this service.'}, status=status.HTTP_400_BAD_REQUEST)

        # 6. Timing & Duration Calculation
        date_str = data.get('date')
        start_time_str = data.get('start_time')
        if not date_str or not start_time_str:
            return Response({'error': 'Both date and start_time are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_date = datetime.date.fromisoformat(date_str)
            if len(start_time_str.split(':')) == 2:
                start_time_str += ':00'
            start_time = datetime.time.fromisoformat(start_time_str)
        except Exception:
            return Response({'error': 'Invalid date (YYYY-MM-DD) or start_time (HH:MM) format.'}, status=status.HTTP_400_BAD_REQUEST)

        # Duration & price calculation
        total_duration = 0
        subtotal = Decimal('0.00')
        line_items = []

        for s in services:
            item_style = selected_style if (selected_style and selected_style.service_id == s.id) else None
            price = Decimal(str(item_style.effective_price if item_style else s.effective_price))
            dur = item_style.effective_duration if item_style else s.duration_minutes
            subtotal += price
            total_duration += dur
            line_items.append({
                'service': s,
                'style': item_style,
                'price': price,
                'duration': dur
            })

        # 7. Discount Calculation (Safe Decimal Math, guaranteed NOT NULL)
        raw_discount_type = data.get('discount_type')
        discount_type = 'NONE'
        if isinstance(raw_discount_type, str):
            discount_type = raw_discount_type.strip().upper()
        if discount_type not in ['PERCENTAGE', 'FIXED', 'NONE']:
            discount_type = 'NONE'

        raw_discount_val = (
            data.get('discount_value')
            if data.get('discount_value') is not None
            else data.get('discount_amount')
        )
        if raw_discount_val is None or raw_discount_val == '':
            raw_discount_val = data.get('discount')
        if raw_discount_val is None or raw_discount_val == '':
            raw_discount_val = '0.00'

        try:
            discount_val = Decimal(str(raw_discount_val).strip())
        except Exception:
            discount_val = Decimal('0.00')

        discount_percentage = Decimal('0.00')
        discount_amount = Decimal('0.00')

        if discount_type == 'PERCENTAGE':
            if discount_val < Decimal('0.00') or discount_val > Decimal('100.00'):
                return Response({'error': 'Percentage discount must be between 0 and 100.'}, status=status.HTTP_400_BAD_REQUEST)
            discount_percentage = discount_val
            discount_amount = (subtotal * discount_percentage / Decimal('100.0')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        elif discount_type == 'FIXED':
            if discount_val < Decimal('0.00'):
                return Response({'error': 'Discount amount cannot be negative.'}, status=status.HTTP_400_BAD_REQUEST)
            discount_amount = min(discount_val, subtotal).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            if discount_val > Decimal('0.00'):
                discount_type = 'FIXED'
                discount_amount = min(discount_val, subtotal).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                discount_amount = Decimal('0.00')
                discount_percentage = Decimal('0.00')

        if discount_amount is None:
            discount_amount = Decimal('0.00')
        if discount_percentage is None:
            discount_percentage = Decimal('0.00')
        if subtotal is None:
            subtotal = Decimal('0.00')

        total_amount = max(subtotal - discount_amount, Decimal('0.00'))

        # Check for duplicate submission within last 30 seconds
        recent_duplicate = Appointment.objects.filter(
            salon=salon,
            customer=customer,
            staff=staff,
            date=target_date,
            start_time=start_time,
            created_at__gte=timezone.now() - datetime.timedelta(seconds=30)
        ).first()
        if recent_duplicate:
            return Response(AppointmentSerializer(recent_duplicate).data, status=status.HTTP_200_OK)

        # 8. Backend Authoritative Validation (Timezone, Operating Hours, Leaves, Conflict Overlap)
        is_valid, err_msg, calculated_end_time = validate_appointment_booking(
            salon=salon,
            branch=branch,
            staff=staff,
            target_date=target_date,
            start_time=start_time,
            duration_minutes=total_duration,
            service_ids=[s.id for s in services],
            style_id=selected_style.id if selected_style else None
        )
        if not is_valid:
            status_code = status.HTTP_409_CONFLICT if "already booked" in err_msg else status.HTTP_400_BAD_REQUEST
            return Response({'error': err_msg}, status=status_code)

        # 9. Concurrency Protection & Duplicate Submission Guard
        booking_source = data.get('booking_source')
        if not booking_source:
            booking_source = BookingSource.WALK_IN if (user and user.is_salon_staff) else BookingSource.ONLINE

        with transaction.atomic():
            # Re-check concurrency inside atomic lock
            if check_appointment_conflict(staff, target_date, start_time, calculated_end_time, select_for_update=True):
                return Response(
                    {'error': f'Stylist {staff.user.get_full_name()} is no longer available between {start_time.strftime("%H:%M")} and {calculated_end_time.strftime("%H:%M")}. Please choose another time slot.'},
                    status=status.HTTP_409_CONFLICT
                )

            appointment = Appointment.objects.create(
                salon=salon,
                branch=branch,
                customer=customer,
                staff=staff,
                date=target_date,
                start_time=start_time,
                end_time=calculated_end_time,
                status=AppointmentStatus.CONFIRMED,
                booking_source=booking_source,
                subtotal=subtotal if subtotal is not None else Decimal('0.00'),
                discount_type=discount_type or 'NONE',
                discount_percentage=discount_percentage if discount_percentage is not None else Decimal('0.00'),
                discount_amount=discount_amount if discount_amount is not None else Decimal('0.00'),
                total_amount=total_amount if total_amount is not None else Decimal('0.00'),
                total_duration_minutes=total_duration,
                notes=data.get('notes', '') or '',
            )

            for it in line_items:
                AppointmentItem.objects.create(
                    salon=salon,
                    appointment=appointment,
                    service=it['service'],
                    style=it['style'],
                    price=it['price'] if it.get('price') is not None else Decimal('0.00'),
                    duration_minutes=it['duration'] if it.get('duration') is not None else 30,
                    discount_amount=Decimal('0.00'),
                )

            # Customer timeline entry
            service_names = ', '.join([it['service'].name + (f" ({it['style'].name})" if it['style'] else "") for it in line_items])
            CustomerActivity.objects.create(
                salon=salon,
                customer=customer,
                activity_type='BOOKING',
                title=f"Booked {service_names}",
                description=f"Appointment on {appointment.date} at {appointment.start_time.strftime('%I:%M %p')} with {staff.user.get_full_name()} ({booking_source}).",
                metadata={'appointment_id': str(appointment.id)}
            )

            # Audit Log
            AuditLog.objects.create(
                salon=salon,
                user=user,
                action='CREATE_APPOINTMENT',
                entity_type='Appointment',
                entity_id=str(appointment.id),
                details={
                    'total_amount': str(total_amount),
                    'customer': customer.full_name,
                    'booking_source': booking_source
                }
            )

            # Trigger Salon Owner Notification safely
            try:
                create_appointment_notification(appointment, event_type='CREATED')
            except Exception as notif_err:
                logger.warning("Notification dispatch failed for appointment %s: %s", appointment.id, notif_err)

        # Immediately return the fresh committed record
        fresh_appointment = Appointment.objects.select_related(
            'salon', 'branch', 'customer', 'staff__user'
        ).prefetch_related('items__service', 'items__style').get(id=appointment.id)

        cache.clear()
        return Response(AppointmentSerializer(fresh_appointment).data, status=status.HTTP_201_CREATED)

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

        if new_status == AppointmentStatus.CANCELLED:
            try:
                create_appointment_notification(appointment, event_type='CANCELLED')
            except Exception as notif_err:
                logger.warning("Notification dispatch failed for appointment cancellation %s: %s", appointment.id, notif_err)

        cache.clear()
        return Response(AppointmentSerializer(appointment).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.AllowAny])
    def cancel(self, request, pk=None):
        """Cancels an appointment with an optional reason."""
        try:
            appointment = Appointment.objects.select_related('salon', 'customer', 'staff__user').get(pk=pk)
        except Appointment.DoesNotExist:
            return Response({'error': 'Appointment not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Permission check: staff member, or appointment's customer
        user = request.user if request.user.is_authenticated else None
        if user and not user.is_salon_staff and appointment.customer.user != user:
            return Response({'error': 'You do not have permission to cancel this appointment.'}, status=status.HTTP_403_FORBIDDEN)

        reason = request.data.get('reason', 'Customer requested cancellation')
        appointment.status = AppointmentStatus.CANCELLED
        appointment.cancellation_reason = reason
        appointment.save(update_fields=['status', 'cancellation_reason'])

        CustomerActivity.objects.create(
            salon=appointment.salon,
            customer=appointment.customer,
            activity_type='CANCELLED',
            title='Appointment Cancelled',
            description=f"Appointment on {appointment.date} was cancelled. Reason: {reason}",
            metadata={'appointment_id': str(appointment.id)}
        )

        create_appointment_notification(appointment, event_type='CANCELLED')
        cache.clear()
        return Response(AppointmentSerializer(appointment).data)

    @action(detail=True, methods=['post'], permission_classes=[IsSalonStaff])
    def reschedule(self, request, pk=None):
        """Reschedules an appointment to a new date and time after authoritative validation."""
        appointment = self.get_object()
        new_date_str = request.data.get('date')
        new_start_time_str = request.data.get('start_time')
        new_staff_id = request.data.get('staff_id') or request.data.get('staff')

        if not new_date_str or not new_start_time_str:
            return Response({'error': 'Both date and start_time are required to reschedule.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_date = datetime.date.fromisoformat(new_date_str)
            if len(new_start_time_str.split(':')) == 2:
                new_start_time_str += ':00'
            start_time = datetime.time.fromisoformat(new_start_time_str)
        except Exception:
            return Response({'error': 'Invalid date (YYYY-MM-DD) or start_time (HH:MM) format.'}, status=status.HTTP_400_BAD_REQUEST)

        staff = appointment.staff
        if new_staff_id:
            found_staff = StaffProfile.objects.filter(salon=appointment.salon, id=new_staff_id, is_bookable=True).first()
            if not found_staff:
                return Response({'error': 'Selected stylist is invalid or not bookable.'}, status=status.HTTP_400_BAD_REQUEST)
            staff = found_staff

        duration = appointment.total_duration_minutes
        is_valid, err_msg, end_time = validate_appointment_booking(
            salon=appointment.salon,
            branch=appointment.branch,
            staff=staff,
            target_date=target_date,
            start_time=start_time,
            duration_minutes=duration,
            exclude_appointment_id=appointment.id
        )
        if not is_valid:
            status_code = status.HTTP_409_CONFLICT if "already booked" in err_msg else status.HTTP_400_BAD_REQUEST
            return Response({'error': err_msg}, status=status_code)

        with transaction.atomic():
            old_date = appointment.date
            old_time = appointment.start_time

            appointment.date = target_date
            appointment.start_time = start_time
            appointment.end_time = end_time
            appointment.staff = staff
            if appointment.status == AppointmentStatus.CANCELLED:
                appointment.status = AppointmentStatus.CONFIRMED
            appointment.save()

            CustomerActivity.objects.create(
                salon=appointment.salon,
                customer=appointment.customer,
                activity_type='BOOKING',
                title='Appointment Rescheduled',
                description=f"Rescheduled from {old_date} {old_time.strftime('%H:%M')} to {target_date} {start_time.strftime('%H:%M')}.",
                metadata={'appointment_id': str(appointment.id)}
            )

            create_appointment_notification(appointment, event_type='RESCHEDULED')

        cache.clear()
        return Response(AppointmentSerializer(appointment).data)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        cache.clear()

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        cache.clear()

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def available_slots(self, request):
        """
        Public endpoint: computes available booking slots using salon timezone,
        excluding past dates and past times today.
        Query params: date (YYYY-MM-DD), staff_id, branch_id, duration, service_id, style_id, salon_slug
        """
        date_str = request.query_params.get('date')
        staff_id = request.query_params.get('staff_id') or request.query_params.get('staff')
        branch_id = request.query_params.get('branch_id') or request.query_params.get('branch')
        service_id = request.query_params.get('service_id') or request.query_params.get('service')
        style_id = request.query_params.get('style_id') or request.query_params.get('style')
        duration = int(request.query_params.get('duration', 60))

        if not date_str:
            return Response({'error': 'date parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            return Response({'error': 'Invalid date format (use YYYY-MM-DD).'}, status=status.HTTP_400_BAD_REQUEST)

        salon = resolve_appointment_salon(request)
        if not salon and staff_id:
            st = StaffProfile.objects.filter(id=staff_id).first()
            if st:
                salon = st.salon

        if not salon:
            return Response({'error': 'Salon tenant could not be identified.'}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve staff & branch
        staff = None
        if staff_id:
            staff = StaffProfile.objects.filter(salon=salon, id=staff_id, is_bookable=True, user__is_active=True).first()
        if not staff:
            # Pick first eligible stylist
            eligible_qs = get_eligible_stylists(salon, branch=None, service_id=service_id, style_id=style_id)
            staff = eligible_qs.first()
        if not staff:
            staff = StaffProfile.objects.filter(salon=salon, is_bookable=True, user__is_active=True).first()

        if not staff:
            return Response({'slots': [], 'message': 'No bookable stylist found for this salon/service.'})

        branch = None
        if branch_id:
            branch = Branch.objects.filter(salon=salon, id=branch_id).first()
        if not branch and staff.branch:
            branch = staff.branch
        if not branch:
            branch = Branch.objects.filter(salon=salon, is_primary=True).first() or Branch.objects.filter(salon=salon).first()

        slots = get_available_slots(salon, branch, staff, target_date, duration)
        return Response({
            'date': date_str,
            'salon': {'id': str(salon.id), 'name': salon.name, 'timezone': salon.timezone},
            'staff': {'id': str(staff.id), 'name': staff.user.get_full_name(), 'title': staff.title},
            'branch': {'id': str(branch.id), 'name': branch.name} if branch else None,
            'duration_minutes': duration,
            'slots': slots
        })

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def eligible_stylists(self, request):
        """
        Public/Staff endpoint: returns eligible stylists for a service, style, or category.
        Never exposes stylists from another salon.
        """
        salon = resolve_appointment_salon(request)
        if not salon:
            return Response({'error': 'Salon tenant could not be identified.'}, status=status.HTTP_400_BAD_REQUEST)

        branch_id = request.query_params.get('branch_id') or request.query_params.get('branch')
        branch = Branch.objects.filter(salon=salon, id=branch_id).first() if branch_id else None

        service_id = request.query_params.get('service_id') or request.query_params.get('service')
        style_id = request.query_params.get('style_id') or request.query_params.get('style')
        category_id = request.query_params.get('category_id') or request.query_params.get('category')

        eligible_staff_qs = get_eligible_stylists(
            salon=salon,
            branch=branch,
            category_id=category_id,
            service_id=service_id,
            style_id=style_id
        )

        return Response(StaffProfileSerializer(eligible_staff_qs, many=True).data)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def calendar(self, request):
        """
        Returns appointments formatted for calendar view within a date range.
        Query params: start_date, end_date, staff_id, branch_id
        """
        salon_id = request.user.salon_id if (request.user.is_authenticated and request.user.salon_id) else 'public'
        qstr = request.META.get('QUERY_STRING', '')
        ckey = f"appt_cal_{salon_id}_{qstr}"
        cached = cache.get(ckey)
        if cached is not None:
            return Response(cached)

        qs = self.get_queryset()
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not start_date or not end_date:
            today = timezone.now().date()
            start_date = str(today.replace(day=1))
            end_date = str(today + datetime.timedelta(days=35))

        qs = qs.filter(date__range=[start_date, end_date])
        data = AppointmentSerializer(qs, many=True).data
        cache.set(ckey, data, timeout=20)
        return Response(data)


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