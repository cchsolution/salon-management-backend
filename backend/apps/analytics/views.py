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
from apps.tenants.utils import get_authenticated_salon, get_authenticated_branch


@api_view(['GET'])
@permission_classes([IsSalonOwner])
def dashboard_metrics_view(request):
    """
    Returns authentic, tenant-isolated dynamic aggregated metrics for the Salon Owner Dashboard.
    Supports filtering by branch_id and period (7d or 30d).
    Calculates actual revenues, counts, top services with real percentages,
    and dynamically computed previous-period comparisons.
    """
    salon = get_authenticated_salon(request)
    if not salon:
        return Response({'error': 'Active salon organization could not be identified.'}, status=status.HTTP_400_BAD_REQUEST)

    raw_branch = request.query_params.get('branch') or request.query_params.get('branch_id')
    branch = get_authenticated_branch(request, salon, raw_branch) if raw_branch else None
    branch_id = str(branch.id) if branch else None

    # Support 7-day and 30-day filters
    raw_period = str(request.query_params.get('period') or request.query_params.get('days') or request.query_params.get('range') or '7d').lower().strip()
    if raw_period in ['30', '30d', 'month', '30_days', 'last_30']:
        num_days = 30
        period_label = '30d'
    else:
        num_days = 7
        period_label = '7d'

    cache_key = f"dash_metrics_{salon.id}_{branch_id or 'all'}_{period_label}"
    cached_metrics = cache.get(cache_key)
    if cached_metrics:
        return Response(cached_metrics)

    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=num_days - 1)
    prev_period_end = start_date - datetime.timedelta(days=1)
    prev_period_start = prev_period_end - datetime.timedelta(days=num_days - 1)

    # Base tenant-scoped querysets
    appts = Appointment.objects.filter(salon=salon)
    invoices = Invoice.objects.filter(salon=salon)
    customers = Customer.objects.filter(salon=salon)
    stock_levels = StockLevel.objects.filter(salon=salon)

    if branch:
        appts = appts.filter(branch=branch)
        invoices = invoices.filter(branch=branch)
        stock_levels = stock_levels.filter(branch=branch)

    # 1. Today's Revenue Calculation:
    # Includes:
    # a) Paid invoices created today
    # b) Paid invoices for appointments scheduled for today
    # c) Completed appointments scheduled for today without an invoice
    paid_inv_today_sum = invoices.filter(
        status=InvoiceStatus.PAID
    ).filter(
        Q(created_at__date=today) | Q(appointment__date=today)
    ).distinct().aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

    completed_appts_today_without_inv = appts.filter(
        date=today,
        status=AppointmentStatus.COMPLETED,
        invoice__isnull=True
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

    today_revenue = paid_inv_today_sum + completed_appts_today_without_inv

    # Overall revenue & invoice aggregates
    inv_stats = invoices.aggregate(
        total_revenue=Sum('total_amount', filter=Q(status=InvoiceStatus.PAID)),
        avg_bill=Avg('total_amount', filter=Q(status=InvoiceStatus.PAID)),
        pending_total=Sum('total_amount', filter=Q(status__in=[InvoiceStatus.UNPAID, InvoiceStatus.PARTIALLY_PAID])),
        pending_paid=Sum('paid_amount', filter=Q(status__in=[InvoiceStatus.UNPAID, InvoiceStatus.PARTIALLY_PAID])),
    )
    total_revenue = inv_stats['total_revenue'] or Decimal('0.00')
    avg_bill = inv_stats['avg_bill'] or Decimal('0.00')
    pending_payments = max((inv_stats['pending_total'] or Decimal('0.00')) - (inv_stats['pending_paid'] or Decimal('0.00')), Decimal('0.00'))

    # 2. Today's Bookings:
    today_appt_stats = appts.filter(date=today).aggregate(
        total=Count('id'),
        completed=Count('id', filter=Q(status=AppointmentStatus.COMPLETED)),
        pending=Count('id', filter=Q(status__in=[AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED, AppointmentStatus.IN_PROGRESS])),
        cancelled=Count('id', filter=Q(status=AppointmentStatus.CANCELLED)),
    )
    today_appts_count = today_appt_stats['total']
    completed_today = today_appt_stats['completed']
    pending_today = today_appt_stats['pending']
    cancelled_today = today_appt_stats['cancelled']

    # 3. Client Counts:
    month_start = today.replace(day=1)
    cust_stats = customers.aggregate(
        total_clients=Count('id'),
        active_clients=Count('id', filter=Q(is_active=True)),
        new_clients=Count('id', filter=Q(created_at__date__gte=month_start))
    )
    total_clients = cust_stats['total_clients']
    active_clients = cust_stats['active_clients']
    new_clients_month = cust_stats['new_clients']

    # 4. Inventory Alerts:
    low_stock_count = stock_levels.filter(quantity_on_hand__lte=F('reorder_level')).count()

    # 5. Revenue & Bookings Chart for Selected Period (7d or 30d):
    # Map revenue by booking date / invoice date
    # Query paid invoices in period
    paid_inv_qs = invoices.filter(
        status=InvoiceStatus.PAID
    ).filter(
        Q(created_at__date__gte=start_date, created_at__date__lte=today) |
        Q(appointment__date__gte=start_date, appointment__date__lte=today)
    ).select_related('appointment')

    daily_rev_map = {}
    for inv in paid_inv_qs:
        # Attribute date: appointment date if attached, otherwise invoice created date
        d = inv.appointment.date if (inv.appointment and inv.appointment.date) else inv.created_at.date()
        if start_date <= d <= today:
            daily_rev_map[d] = daily_rev_map.get(d, Decimal('0.00')) + inv.total_amount

    # Also include completed appointments in period without invoice
    completed_appts_qs = appts.filter(
        date__gte=start_date,
        date__lte=today,
        status=AppointmentStatus.COMPLETED,
        invoice__isnull=True
    ).values('date').annotate(tot=Sum('total_amount'))
    for item in completed_appts_qs:
        d = item['date']
        daily_rev_map[d] = daily_rev_map.get(d, Decimal('0.00')) + (item['tot'] or Decimal('0.00'))

    # Daily bookings (excluding cancelled bookings)
    daily_appt_qs = appts.filter(
        date__gte=start_date,
        date__lte=today
    ).exclude(
        status=AppointmentStatus.CANCELLED
    ).values('date').annotate(cnt=Count('id'))
    daily_appt_map = {item['date']: item['cnt'] for item in daily_appt_qs}

    chart_days = []
    current_period_revenue = Decimal('0.00')
    current_period_appointments = 0

    for i in range(num_days - 1, -1, -1):
        day = today - datetime.timedelta(days=i)
        day_rev = daily_rev_map.get(day, Decimal('0.00'))
        day_appts = daily_appt_map.get(day, 0)
        current_period_revenue += day_rev
        current_period_appointments += day_appts

        chart_days.append({
            'date': day.strftime('%a, %b %d') if num_days <= 7 else day.strftime('%b %d'),
            'iso_date': day.isoformat(),
            'revenue': float(day_rev),
            'appointments': day_appts
        })

    # 6. Previous Period Comparison / Trend Calculation:
    # Compute revenue for previous period
    prev_paid_inv_qs = invoices.filter(
        status=InvoiceStatus.PAID
    ).filter(
        Q(created_at__date__gte=prev_period_start, created_at__date__lte=prev_period_end) |
        Q(appointment__date__gte=prev_period_start, appointment__date__lte=prev_period_end)
    ).select_related('appointment')

    prev_period_revenue = Decimal('0.00')
    for inv in prev_paid_inv_qs:
        d = inv.appointment.date if (inv.appointment and inv.appointment.date) else inv.created_at.date()
        if prev_period_start <= d <= prev_period_end:
            prev_period_revenue += inv.total_amount

    prev_completed_appts_sum = appts.filter(
        date__gte=prev_period_start,
        date__lte=prev_period_end,
        status=AppointmentStatus.COMPLETED,
        invoice__isnull=True
    ).aggregate(tot=Sum('total_amount'))['tot'] or Decimal('0.00')
    prev_period_revenue += prev_completed_appts_sum

    prev_period_appointments = appts.filter(
        date__gte=prev_period_start,
        date__lte=prev_period_end
    ).exclude(
        status=AppointmentStatus.CANCELLED
    ).count()

    prev_new_clients = customers.filter(
        created_at__date__gte=prev_period_start,
        created_at__date__lte=prev_period_end
    ).count()
    curr_new_clients = customers.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=today
    ).count()

    def calc_trend(current_val, prev_val):
        c = float(current_val)
        p = float(prev_val)
        if p > 0:
            pct = round(((c - p) / p) * 100.0, 1)
            sign = '+' if pct > 0 else ''
            return {
                'percentage': pct,
                'formatted': f"{sign}{pct}%",
                'direction': 'up' if pct > 0 else ('down' if pct < 0 else 'neutral'),
                'is_neutral': False
            }
        elif c > 0:
            return {
                'percentage': 100.0,
                'formatted': "+100%",
                'direction': 'up',
                'is_neutral': False
            }
        else:
            return {
                'percentage': 0.0,
                'formatted': "0.0%",
                'direction': 'neutral',
                'is_neutral': True
            }

    revenue_trend = calc_trend(current_period_revenue, prev_period_revenue)
    appointments_trend = calc_trend(current_period_appointments, prev_period_appointments)
    clients_trend = calc_trend(curr_new_clients, prev_new_clients)

    # 7. Top Services with booking count and real percentage
    popular_services_qs = AppointmentItem.objects.filter(
        salon=salon,
        appointment__date__gte=start_date,
        appointment__date__lte=today
    ).exclude(
        appointment__status=AppointmentStatus.CANCELLED
    )
    if branch:
        popular_services_qs = popular_services_qs.filter(appointment__branch=branch)

    service_aggregates = list(
        popular_services_qs.values(
            'service__name'
        ).annotate(
            booking_count=Count('id'),
            total_revenue=Sum('price')
        ).order_by('-booking_count')[:5]
    )

    total_service_bookings = sum(it['booking_count'] for it in service_aggregates)

    popular_services = []
    for item in service_aggregates:
        b_cnt = item['booking_count']
        pct = round((b_cnt / total_service_bookings * 100.0), 1) if total_service_bookings > 0 else 0.0
        popular_services.append({
            'name': item['service__name'] or 'Custom Service',
            'bookings': b_cnt,
            'percentage': pct,
            'revenue': float(item['total_revenue'] or Decimal('0.00'))
        })

    # If no services booked in selected period, provide overall fallback without hardcoded fake data
    if not popular_services:
        overall_qs = AppointmentItem.objects.filter(
            salon=salon
        ).exclude(
            appointment__status=AppointmentStatus.CANCELLED
        )
        if branch:
            overall_qs = overall_qs.filter(appointment__branch=branch)
        overall_top = list(
            overall_qs.values('service__name').annotate(
                booking_count=Count('id'),
                total_revenue=Sum('price')
            ).order_by('-booking_count')[:5]
        )
        overall_total = sum(it['booking_count'] for it in overall_top)
        popular_services = [
            {
                'name': it['service__name'] or 'Custom Service',
                'bookings': it['booking_count'],
                'percentage': round((it['booking_count'] / overall_total * 100.0), 1) if overall_total > 0 else 0.0,
                'revenue': float(it['total_revenue'] or Decimal('0.00'))
            }
            for it in overall_top
        ]

    # 8. Staff Performance
    staff_qs = StaffProfile.objects.filter(salon=salon).select_related('user', 'branch')
    if branch:
        staff_qs = staff_qs.filter(branch=branch)

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

    # 9. Branch comparisons
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

    # 10. Recent Transactions
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

    # 11. Upcoming Appointments
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
            'today_bookings': today_appts_count,
            'completed_today': completed_today,
            'pending_today': pending_today,
            'cancelled_today': cancelled_today,
            'total_revenue': float(total_revenue),
            'avg_bill_value': float(avg_bill),
            'pending_payments': float(pending_payments),
            'total_clients': total_clients,
            'active_clients': active_clients,
            'new_clients_this_month': new_clients_month,
            'low_stock_count': low_stock_count,
            'inventory_alerts': low_stock_count,
            'revenue_change_percentage': revenue_trend['percentage'],
            'revenue_trend': revenue_trend['formatted'],
            'appointments_change_percentage': appointments_trend['percentage'],
            'appointments_trend': appointments_trend['formatted'],
            'clients_change_percentage': clients_trend['percentage'],
            'clients_trend': clients_trend['formatted'],
            'period': period_label,
            'period_days': num_days,
        },
        'trends': {
            'revenue': revenue_trend,
            'appointments': appointments_trend,
            'clients': clients_trend,
        },
        'revenue_chart': chart_days,
        'revenue_graph': chart_days,
        'popular_services': popular_services,
        'top_services': popular_services,
        'today_revenue': float(today_revenue),
        'today_bookings': today_appts_count,
        'active_clients': active_clients,
        'inventory_alerts': low_stock_count,
        'revenue_trend': revenue_trend['percentage'],
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
    salon = get_authenticated_salon(request)
    if not salon:
        return Response({'error': 'Active salon organization could not be identified.'}, status=status.HTTP_400_BAD_REQUEST)

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
