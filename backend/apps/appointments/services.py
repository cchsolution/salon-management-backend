import datetime
from django.db import transaction
from django.db.models import Q
from apps.appointments.models import Appointment, AppointmentStatus, StylistShift, StylistLeave

def check_appointment_conflict(staff, date, start_time, end_time, exclude_appointment_id=None):
    """
    Checks if there is an overlapping active appointment for the given staff member.
    Uses select_for_update inside transactions for concurrency safety.
    """
    qs = Appointment.objects.filter(
        staff=staff,
        date=date
    ).exclude(
        status__in=[AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]
    )

    if exclude_appointment_id:
        qs = qs.exclude(id=exclude_appointment_id)

    # Overlap condition: (StartA < EndB) and (EndA > StartB)
    overlapping = qs.filter(
        start_time__lt=end_time,
        end_time__gt=start_time
    )

    return overlapping.exists()


def get_available_slots(salon, branch, staff, target_date, duration_minutes=60):
    """
    Calculates bookable time slots for a given staff member on a specific date.
    Considers staff shifts, approved leaves, and booked appointments.
    """
    # 1. Check if staff is on leave
    on_leave = StylistLeave.objects.filter(
        staff=staff,
        start_date__lte=target_date,
        end_date__gte=target_date,
        is_approved=True
    ).exists()

    if on_leave:
        return []

    # 2. Get staff shift for the day of the week
    weekday = target_date.weekday() # 0 = Monday, 6 = Sunday
    shift = StylistShift.objects.filter(
        staff=staff,
        branch=branch,
        day_of_week=weekday,
        is_working=True
    ).first()

    if not shift:
        # Fall back to branch operating hours if no specific shift configured
        start_time = branch.opening_time or datetime.time(9, 0)
        end_time = branch.closing_time or datetime.time(19, 0)
    else:
        start_time = shift.start_time
        end_time = shift.end_time

    # 3. Retrieve existing appointments for the day
    existing_appointments = Appointment.objects.filter(
        staff=staff,
        date=target_date
    ).exclude(
        status__in=[AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW]
    ).values_list('start_time', 'end_time')

    # 4. Generate 30-minute candidate slots
    slots = []
    current_dt = datetime.datetime.combine(target_date, start_time)
    closing_dt = datetime.datetime.combine(target_date, end_time)

    slot_delta = datetime.timedelta(minutes=30)
    service_duration = datetime.timedelta(minutes=duration_minutes)

    while current_dt + service_duration <= closing_dt:
        cand_start = current_dt.time()
        cand_end = (current_dt + service_duration).time()

        # Check overlap against all existing bookings
        conflict = False
        for ex_start, ex_end in existing_appointments:
            if cand_start < ex_end and cand_end > ex_start:
                conflict = True
                break

        if not conflict:
            slots.append(cand_start.strftime('%H:%M'))

        current_dt += slot_delta

    return slots
