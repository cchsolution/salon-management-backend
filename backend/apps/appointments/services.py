import datetime
import zoneinfo
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from apps.appointments.models import Appointment, AppointmentStatus, StylistShift, StylistLeave
from apps.core.models import StaffProfile, UserRole
from apps.catalog.models import Service, ServiceCategory, ServiceStyle

def get_salon_timezone(salon):
    """
    Returns the ZoneInfo for the salon, defaulting to Asia/Kolkata.
    """
    tz_name = getattr(salon, 'timezone', None) or 'Asia/Kolkata'
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        return zoneinfo.ZoneInfo('Asia/Kolkata')


def get_current_salon_datetime(salon):
    """
    Returns current timezone-aware datetime in the salon's local timezone.
    """
    tz = get_salon_timezone(salon)
    return timezone.now().astimezone(tz)


def get_eligible_stylists(salon, branch=None, category_id=None, service_id=None, style_id=None):
    """
    Returns stylists belonging exclusively to the specified salon who are active, bookable,
    and qualified for the selected style, service, or category.
    Never exposes stylists from another salon.
    """
    if not salon:
        return StaffProfile.objects.none()

    qs = StaffProfile.objects.filter(
        salon=salon,
        is_bookable=True,
        user__is_active=True
    ).select_related('user', 'branch', 'salon')

    if branch:
        qs = qs.filter(Q(branch=branch) | Q(branch__isnull=True))

    # 1. Style-level qualification (most specific)
    if style_id:
        style = ServiceStyle.objects.filter(salon=salon, id=style_id).first()
        if style and style.qualified_staff.exists():
            return qs.filter(id__in=style.qualified_staff.values_list('id', flat=True))
        # If style has no specific stylist restriction, fall back to its parent service
        if style and not service_id:
            service_id = style.service_id

    # 2. Service-level qualification
    if service_id:
        service = Service.objects.filter(salon=salon, id=service_id).first()
        if service and service.qualified_staff.exists():
            return qs.filter(id__in=service.qualified_staff.values_list('id', flat=True))
        if service and not category_id and service.category_id:
            category_id = service.category_id

    # 3. Category-level qualification
    if category_id:
        category = ServiceCategory.objects.filter(salon=salon, id=category_id).first()
        if category and category.qualified_staff.exists():
            return qs.filter(id__in=category.qualified_staff.values_list('id', flat=True))

    return qs


def check_appointment_conflict(staff, date, start_time, end_time, exclude_appointment_id=None, select_for_update=False):
    """
    Checks if there is an overlapping active appointment for the given staff member.
    Uses select_for_update inside transactions for concurrency safety when specified.
    """
    qs = Appointment.objects.filter(
        staff=staff,
        date=date
    ).exclude(
        status__in=[AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]
    )

    if exclude_appointment_id:
        qs = qs.exclude(id=exclude_appointment_id)

    from django.db import connection
    if select_for_update and connection.in_atomic_block:
        qs = qs.select_for_update()

    # Overlap condition: (StartA < EndB) and (EndA > StartB)
    overlapping = qs.filter(
        start_time__lt=end_time,
        end_time__gt=start_time
    )

    return overlapping.exists()


def get_available_slots(salon, branch, staff, target_date, duration_minutes=60):
    """
    Calculates bookable time slots for a given staff member on a specific date.
    Strictly enforces:
    - Salon timezone (Asia/Kolkata)
    - Past date rejection
    - Past time rejection for today
    - Staff leaves
    - Staff shifts & branch opening/closing hours
    - Existing appointments overlap check
    """
    if not salon or not staff or not target_date:
        return []

    # 1. Timezone-aware past checks
    now_salon = get_current_salon_datetime(salon)
    today_salon = now_salon.date()

    if target_date < today_salon:
        # Cannot book in the past
        return []

    # 2. Check if staff is on approved leave
    on_leave = StylistLeave.objects.filter(
        staff=staff,
        start_date__lte=target_date,
        end_date__gte=target_date,
        is_approved=True
    ).exists()

    if on_leave:
        return []

    # 3. Get staff shift for the day of the week
    weekday = target_date.weekday()  # 0 = Monday, 6 = Sunday
    shift = StylistShift.objects.filter(
        staff=staff,
        day_of_week=weekday
    ).first()

    if shift:
        if not shift.is_working:
            # Stylist is off on this day
            return []
        shift_start = shift.start_time
        shift_end = shift.end_time
    else:
        # Fall back to branch operating hours if no specific shift configured
        if branch:
            shift_start = branch.opening_time or datetime.time(9, 0)
            shift_end = branch.closing_time or datetime.time(20, 0)
        else:
            shift_start = datetime.time(9, 0)
            shift_end = datetime.time(20, 0)

    # 4. Retrieve existing appointments for the day
    existing_appointments = list(
        Appointment.objects.filter(
            staff=staff,
            date=target_date
        ).exclude(
            status__in=[AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]
        ).values_list('start_time', 'end_time')
    )

    # 5. Generate 30-minute candidate slots
    slots = []
    current_dt = datetime.datetime.combine(target_date, shift_start)
    closing_dt = datetime.datetime.combine(target_date, shift_end)

    slot_delta = datetime.timedelta(minutes=30)
    service_duration = datetime.timedelta(minutes=duration_minutes)

    while current_dt + service_duration <= closing_dt:
        cand_start = current_dt.time()
        cand_end = (current_dt + service_duration).time()

        # Check if slot is already in the past for today
        if target_date == today_salon and cand_start <= now_salon.time():
            current_dt += slot_delta
            continue

        # Check overlap against all existing bookings
        conflict = False
        for ex_start, ex_end in existing_appointments:
            if hasattr(ex_start, 'time') and callable(ex_start.time):
                ex_start = ex_start.time()
            elif isinstance(ex_start, str):
                ex_start = datetime.time.fromisoformat(ex_start)

            if hasattr(ex_end, 'time') and callable(ex_end.time):
                ex_end = ex_end.time()
            elif isinstance(ex_end, str):
                ex_end = datetime.time.fromisoformat(ex_end)

            if cand_start < ex_end and cand_end > ex_start:
                conflict = True
                break

        if not conflict:
            slots.append(cand_start.strftime('%H:%M'))

        current_dt += slot_delta

    return slots


def validate_appointment_booking(salon, branch, staff, target_date, start_time, duration_minutes,
                                 service_ids=None, style_id=None, exclude_appointment_id=None):
    """
    Validates complete booking feasibility authoritative on backend.
    Returns: (is_valid, error_message, end_time)
    """
    now_salon = get_current_salon_datetime(salon)
    today_salon = now_salon.date()

    # 1. Past checks
    if target_date < today_salon:
        return False, "Appointments cannot be booked for past dates.", None

    if target_date == today_salon and start_time <= now_salon.time():
        return False, f"The requested time slot ({start_time.strftime('%H:%M')}) has already passed today.", None

    # 2. Staff validity and salon scoping
    if staff.salon_id != salon.id:
        return False, "Selected stylist does not belong to this salon.", None

    if not staff.is_bookable or not staff.user.is_active:
        return False, f"Stylist {staff.user.get_full_name()} is currently not available for bookings.", None

    # 3. Check leave
    on_leave = StylistLeave.objects.filter(
        staff=staff,
        start_date__lte=target_date,
        end_date__gte=target_date,
        is_approved=True
    ).exists()
    if on_leave:
        return False, f"Stylist {staff.user.get_full_name()} is on leave on {target_date}.", None

    # 4. Check shifts & hours
    weekday = target_date.weekday()
    shift = StylistShift.objects.filter(staff=staff, day_of_week=weekday).first()
    if shift:
        if not shift.is_working:
            return False, f"Stylist {staff.user.get_full_name()} is not scheduled to work on this day.", None
        allowed_start = shift.start_time
        allowed_end = shift.end_time
    elif branch:
        allowed_start = branch.opening_time or datetime.time(9, 0)
        allowed_end = branch.closing_time or datetime.time(20, 0)
    else:
        allowed_start = datetime.time(9, 0)
        allowed_end = datetime.time(20, 0)

    start_dt = datetime.datetime.combine(target_date, start_time)
    end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)
    end_time = end_dt.time()

    if start_time < allowed_start:
        return False, f"Appointment start time ({start_time.strftime('%H:%M')}) is before operating hours ({allowed_start.strftime('%H:%M')}).", None

    if end_time > allowed_end:
        return False, f"Appointment duration ({duration_minutes}m) extends past closing time ({allowed_end.strftime('%H:%M')}).", None

    # 5. Check stylist eligibility for service / style
    if service_ids:
        eligible_stylists_qs = get_eligible_stylists(salon, branch=branch, service_id=service_ids[0], style_id=style_id)
        if not eligible_stylists_qs.filter(id=staff.id).exists():
            return False, f"Stylist {staff.user.get_full_name()} is not assigned or qualified for the selected service/style.", None

    # 6. Check concurrency conflict
    if check_appointment_conflict(staff, target_date, start_time, end_time, exclude_appointment_id=exclude_appointment_id, select_for_update=True):
        return False, f"Stylist {staff.user.get_full_name()} is already booked between {start_time.strftime('%H:%M')} and {end_time.strftime('%H:%M')}. Please choose another time slot.", None

    return True, "", end_time
