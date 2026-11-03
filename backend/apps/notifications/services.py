import logging
from apps.core.models import User, UserRole
from apps.notifications.models import InAppNotification
from apps.notifications.serializers import invalidate_user_notification_cache

logger = logging.getLogger(__name__)

def create_appointment_notification(appointment, event_type='CREATED'):
    """
    Creates an in-app notification for the Salon Owner(s) and Salon Manager(s)
    whenever an appointment is booked (online or manual), rescheduled, or cancelled.
    
    Includes:
    - Customer name
    - Customer phone number
    - Service name(s) / Style(s)
    - Stylist name
    - Appointment date
    - Appointment time
    - Booking source
    - Appointment ID
    """
    try:
        salon = appointment.salon
        if not salon:
            return []

        # Find owner(s) and manager(s) of this salon
        recipients = list(User.objects.filter(
            salon=salon,
            role__in=[UserRole.SALON_OWNER, UserRole.SALON_MANAGER],
            is_active=True
        ))

        # If no owner found specifically attached, fallback to superusers/staff
        if not recipients:
            recipients = list(User.objects.filter(role=UserRole.SUPERADMIN, is_active=True))

        customer = appointment.customer
        customer_name = customer.full_name if customer else 'Walk-in Guest'
        customer_phone = customer.phone if customer else 'N/A'

        staff_user = appointment.staff.user if (appointment.staff and appointment.staff.user) else None
        stylist_name = staff_user.get_full_name() if staff_user else 'Assigned Stylist'

        # Get service names
        items = list(appointment.items.select_related('service', 'style').all())
        if items:
            service_desc_parts = []
            for item in items:
                part = item.service.name if item.service else 'Service'
                if item.style:
                    part += f" ({item.style.name})"
                service_desc_parts.append(part)
            services_summary = ', '.join(service_desc_parts)
        else:
            services_summary = 'Salon Services'

        date_str = appointment.date.strftime('%d %b %Y') if appointment.date else ''
        time_str = appointment.start_time.strftime('%I:%M %p') if appointment.start_time else ''
        booking_src = appointment.get_booking_source_display() if hasattr(appointment, 'get_booking_source_display') else appointment.booking_source

        event_titles = {
            'CREATED': f"New {booking_src} Booking: {customer_name}",
            'RESCHEDULED': f"Appointment Rescheduled: {customer_name}",
            'CANCELLED': f"Appointment Cancelled: {customer_name}",
            'COMPLETED': f"Appointment Completed: {customer_name}",
        }
        title = event_titles.get(event_type, f"Appointment Update: {customer_name}")

        message = (
            f"Customer: {customer_name} ({customer_phone})\n"
            f"Service: {services_summary}\n"
            f"Stylist: {stylist_name}\n"
            f"Date & Time: {date_str} at {time_str}\n"
            f"Source: {booking_src}\n"
            f"Appointment ID: #{str(appointment.id)[:8]}"
        )

        metadata = {
            'appointment_id': str(appointment.id),
            'event_type': event_type,
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'service': services_summary,
            'stylist': stylist_name,
            'date': str(appointment.date),
            'start_time': str(appointment.start_time),
            'booking_source': appointment.booking_source,
            'total_amount': str(appointment.total_amount),
            'status': appointment.status,
        }

        notifications = []
        for user in recipients:
            n = InAppNotification.objects.create(
                salon=salon,
                user=user,
                title=title,
                message=message,
                notification_type='BOOKING',
                is_read=False,
                metadata=metadata
            )
            notifications.append(n)
            invalidate_user_notification_cache(user.id)

        return notifications
    except Exception as e:
        logger.error(f"Failed to create appointment notification: {e}")
        return []

