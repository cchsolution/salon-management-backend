import csv
import datetime
from decimal import Decimal
from django.http import HttpResponse
from django.core.cache import cache
from django.db.models import Sum, Count, Avg, Q, F
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.models import Branch, StaffProfile, UserRole, Salon
from apps.appointments.models import Appointment, AppointmentStatus, AppointmentItem
from apps.pos.models import Invoice, InvoiceStatus, InvoiceItem, Payment
from apps.customers.models import Customer
from apps.inventory.models import StockLevel
from apps.tenants.permissions import IsSalonOwner

@api_view(['GET'])
@permission_classes([IsSalonOwner])
def dashboard_metrics_view(request):
    """
    Returns authentic aggregated metrics for the Salon Owner Dashboard.
    Supports filtering by branch_id and date range.
    Hair Stylists and Receptionists receive HTTP 403 Forbidden.
    """
    salon = request.user.salon
    if not salon and (request.user.role == UserRole.SUPERADMIN or request.user.is_superuser):
        salon_id = request.query_params.get('salon_id')
        if salon_id:
            salon = Salon.objects.filter(id=salon_id).first()
        else:
            salon = Salon.objects.first()

    if not salon:
        return Response({'error': 'User has no active salon.'}, status=status.HTTP_400_BAD_REQUEST)


    branch_id = request.query_params.get('branch')
    cache_key = f"dashboard_metrics_{salon.id}_{branch_id or 'all'}"
    cached_metrics = cache.get(cache_key)
    if cached_metrics:
        return Response(cached_metrics)

    today = datetime.date.today()

    # Scope querysets
    appts = Appointment.objects.filter(salon=salon)
    invoices = Invoice.objects.filter(salon=salon)
    customers = Customer.objects.filter(salon=salon)
    stock_levels = StockLevel.objects.filter(salon=salon)

    if branch_id:
        appts = appts.filter(branch_id=branch_id)
        invoices = invoices.filter(branch_id=branch_id)
        stock_levels = stock_levels.filter(branch_id=branch_id)

    # 1. Today's and Overall Invoice metrics in a single aggregated query
    inv_stats = invoices.aggregate(
        today_revenue=Sum('total_amount', filter=Q(created_at__date=today, status=InvoiceStatus.PAID)),
        total_revenue=Sum('total_amount', filter=Q(status=InvoiceStatus.PAID)),
        avg_bill=Avg('total_amount', filter=Q(status=InvoiceStatus.PAID)),
        pending_total=Sum('total_amount', filter=Q(status__in=[InvoiceStatus.UNPAID, InvoiceStatus.PARTIALLY_PAID])),
        pending_paid=Sum('paid_amount', filter=Q(status__in=[InvoiceStatus.UNPAID, InvoiceStatus.PARTIALLY_PAID])),
    )
    today_revenue = inv_stats['today_revenue'] or Decimal('0.00')
    total_revenue = inv_stats['total_revenue'] or Decimal('0.00')
    avg_bill = inv_stats['avg_bill'] or Decimal('0.00')
    pending_payments = (inv_stats['pending_total'] or Decimal('0.00')) - (inv_stats['pending_paid'] or Decimal('0.00'))

    # 2. Today's appointments metrics in a single aggregated query
    today_appt_stats = appts.filter(date=today).aggregate(
        total=Count('id'),
        completed=Count('id', filter=Q(status=AppointmentStatus.COMPLETED)),
        pending=Count('id', filter=Q(status__in=[AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED])),
        cancelled=Count('id', filter=Q(status=AppointmentStatus.CANCELLED)),
    )
    today_appts_count = today_appt_stats['total']
    completed_today = today_appt_stats['completed']
    pending_today = today_appt_stats['pending']
    cancelled_today = today_appt_stats['cancelled']

    # 3. Customer counts in a single query
    month_start = today.replace(day=1)
    cust_stats = customers.aggregate(
        total_clients=Count('id'),
        new_clients=Count('id', filter=Q(created_at__date__gte=month_start))
    )
    total_clients = cust_stats['total_clients']
    new_clients_month = cust_stats['new_clients']

    # 4. Low stock count using ORM filter instead of Python loop
    low_stock_count = stock_levels.filter(quantity_on_hand__lte=F('reorder_level')).count()

    # 5. 7-day revenue & appointments chart using grouped queries (2 queries instead of 14)
    start_7d = today - datetime.timedelta(days=6)
    daily_rev_qs = invoices.filter(
        created_at__date__gte=start_7d,
        created_at__date__lte=today,
        status=InvoiceStatus.PAID
    ).values('created_at__date').annotate(rev=Sum('total_amount'))
    daily_rev_map = {item['created_at__date']: item['rev'] for item in daily_rev_qs}

    daily_appt_qs = appts.filter(
        date__gte=start_7d,
        date__lte=today
    ).values('date').annotate(cnt=Count('id'))
    daily_appt_map = {item['date']: item['cnt'] for item in daily_appt_qs}

    chart_days = []
    for i in range(6, -1, -1):
        day = today - datetime.timedelta(days=i)
        chart_days.append({
            'date': day.strftime('%a, %b %d'),
            'iso_date': day.isoformat(),
            'revenue': float(daily_rev_map.get(day) or Decimal('0.00')),
            'appointments': daily_appt_map.get(day, 0)
        })

    # 6. Most popular services
    popular_services_qs = AppointmentItem.objects.filter(salon=salon)
    if branch_id:
        popular_services_qs = popular_services_qs.filter(appointment__branch_id=branch_id)
    popular_services_qs = popular_services_qs.values(
        'service__name'
    ).annotate(
        booking_count=Count('id'),
        total_revenue=Sum('price')
    ).order_by('-booking_count')[:5]

    popular_services = [
        {
            'name': item['service__name'] or 'Custom Service',
            'bookings': item['booking_count'],
            'revenue': float(item['total_revenue'] or 0)
        }
        for item in popular_services_qs
    ]

    # 7. Staff Performance using grouped appointment aggregation (2 queries total instead of 2 * N)
    staff_qs = StaffProfile.objects.filter(salon=salon).select_related('user', 'branch')
    if branch_id:
        staff_qs = staff_qs.filter(branch_id=branch_id)

    staff_appt_stats = appts.values('staff_id').annotate(
        total_cnt=Count('id'),
        completed_rev=Sum('total_amount', filter=Q(status=AppointmentStatus.COMPLETED))
    )
    staff_stats_map = {item['staff_id']: item for item in staff_appt_stats}

    staff_performance = []
    for sp in staff_qs:
        s_stats = staff_stats_map.get(sp.id, {})
        s_count = s_stats.get('total_cnt', 0)
        s_rev = s_stats.get('completed_rev') or Decimal('0.00')
        commission = (s_rev * sp.commission_rate) / Decimal('100.0')
        staff_performance.append({
            'id': str(sp.id),
            'name': sp.user.get_full_name() or sp.user.username,
            'title': sp.title,
            'branch': sp.branch.name if sp.branch else 'All Branches',
            'appointments_count': s_count,
            'revenue_generated': float(s_rev),
            'commission_earned': float(commission),
            'commission_rate': float(sp.commission_rate)
        })

    # 8. Branch comparisons using grouped aggregations (2 queries total instead of 2 * N)
    branch_qs = Branch.objects.filter(salon=salon)
    branch_rev_qs = Invoice.objects.filter(salon=salon, status=InvoiceStatus.PAID).values('branch_id').annotate(
        rev=Sum('total_amount')
    )
    branch_rev_map = {item['branch_id']: item['rev'] for item in branch_rev_qs}

    branch_appt_qs = Appointment.objects.filter(salon=salon).values('branch_id').annotate(
        cnt=Count('id')
    )
    branch_appt_map = {item['branch_id']: item['cnt'] for item in branch_appt_qs}

    branch_comparison = []
    for b in branch_qs:
        b_rev = branch_rev_map.get(b.id) or Decimal('0.00')
        b_cnt = branch_appt_map.get(b.id, 0)
        branch_comparison.append({
            'id': str(b.id),
            'name': b.name,
            'city': b.city,
            'revenue': float(b_rev),
            'appointments': b_cnt
        })

    # Recent Transactions
    recent_invoices_qs = invoices.select_related('customer').order_by('-created_at')[:5]
    recent_transactions = [
        {
            'id': str(inv.id),
            'invoice_number': inv.invoice_number,
            'customer_name': inv.customer.full_name if inv.customer else 'Walk-in',
            'amount': float(inv.total_amount),
            'status': inv.status,
            'date': inv.created_at.strftime('%b %d, %Y %H:%M')
        }
        for inv in recent_invoices_qs
    ]

    # Upcoming Appointments
    upcoming_appts_qs = appts.filter(
        date__gte=today
    ).exclude(
        status__in=[AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED]
    ).select_related('customer', 'staff__user').order_by('date', 'start_time')[:5]

    upcoming_appointments = [
        {
            'id': str(a.id),
            'customer_name': a.customer.full_name,
            'staff_name': a.staff.user.get_full_name(),
            'date': a.date.isoformat(),
            'time': a.start_time.strftime('%H:%M'),
            'status': a.status,
            'amount': float(a.total_amount)
        }
        for a in upcoming_appts_qs
    ]

    response_payload = {
        'summary': {
            'today_revenue': float(today_revenue),
            'today_appointments': today_appts_count,
            'completed_today': completed_today,
            'pending_today': pending_today,
            'cancelled_today': cancelled_today,
            'total_revenue': float(total_revenue),
            'avg_bill_value': float(avg_bill),
            'pending_payments': float(pending_payments),
            'total_clients': total_clients,
            'new_clients_this_month': new_clients_month,
            'low_stock_count': low_stock_count,
        },
        'revenue_chart': chart_days,
        'popular_services': popular_services,
        'staff_performance': staff_performance,
        'branch_comparison': branch_comparison,
        'recent_transactions': recent_transactions,
        'upcoming_appointments': upcoming_appointments
    }
    cache.set(cache_key, response_payload, timeout=20)
    return Response(response_payload)


@api_view(['GET'])
@permission_classes([IsSalonOwner])
def export_csv_report_view(request):
    """
    Generates and downloads a CSV export of invoices for accounting and audits.
    Restricted to Salon Owner / SuperAdmin.
    """
    salon = request.user.salon
    if not salon and (request.user.role == UserRole.SUPERADMIN or request.user.is_superuser):
        salon_id = request.query_params.get('salon_id')
        if salon_id:
            salon = Salon.objects.filter(id=salon_id).first()
        else:
            salon = Salon.objects.first()

    if not salon:
        return Response({'error': 'User has no active salon.'}, status=status.HTTP_400_BAD_REQUEST)

    report_type = request.query_params.get('type', 'invoices')

    response = HttpResponse(content_type='text/csv')
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')


    if report_type == 'staff_commission':
        response['Content-Disposition'] = f'attachment; filename="salon_staff_commissions_{timestamp}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Staff Name', 'Title', 'Branch', 'Appointments Count', 'Revenue Generated ($)', 'Commission Rate (%)', 'Commission Earned ($)'])
        for sp in StaffProfile.objects.filter(salon=salon).select_related('user', 'branch'):
            s_appts = Appointment.objects.filter(staff=sp)
            s_rev = s_appts.filter(status=AppointmentStatus.COMPLETED).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
            commission = (s_rev * sp.commission_rate) / Decimal('100.0')
            writer.writerow([
                sp.user.get_full_name(),
                sp.title,
                sp.branch.name if sp.branch else 'All',
                s_appts.count(),
                f"{s_rev:.2f}",
                f"{sp.commission_rate:.1f}",
                f"{commission:.2f}"
            ])
    else:
        # Default: Invoices
        response['Content-Disposition'] = f'attachment; filename="salon_invoices_{timestamp}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Invoice #', 'Date', 'Customer Name', 'Phone', 'Branch', 'Subtotal', 'Tax', 'Discount', 'Total', 'Paid', 'Status'])
        for inv in Invoice.objects.filter(salon=salon).select_related('customer', 'branch').order_by('-created_at'):
            writer.writerow([
                inv.invoice_number,
                inv.created_at.strftime('%Y-%m-%d %H:%M'),
                inv.customer.full_name if inv.customer else 'Walk-in',
                inv.customer.phone if inv.customer else '',
                inv.branch.name if inv.branch else '',
                f"{inv.subtotal:.2f}",
                f"{inv.tax_amount:.2f}",
                f"{inv.discount_amount:.2f}",
                f"{inv.total_amount:.2f}",
                f"{inv.paid_amount:.2f}",
                inv.status
            ])

    return response
