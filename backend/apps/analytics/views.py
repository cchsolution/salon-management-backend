import csv
import datetime
from decimal import Decimal
from django.http import HttpResponse
from django.db.models import Sum, Count, Avg, Q
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

    # Today's metrics
    today_invoices = invoices.filter(created_at__date=today)
    today_revenue = today_invoices.filter(status=InvoiceStatus.PAID).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')

    today_appts = appts.filter(date=today)
    today_appts_count = today_appts.count()
    completed_today = today_appts.filter(status=AppointmentStatus.COMPLETED).count()
    pending_today = today_appts.filter(status__in=[AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]).count()
    cancelled_today = today_appts.filter(status=AppointmentStatus.CANCELLED).count()

    # Overall Metrics
    total_revenue = invoices.filter(status=InvoiceStatus.PAID).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
    avg_bill = invoices.filter(status=InvoiceStatus.PAID).aggregate(Avg('total_amount'))['total_amount__avg'] or Decimal('0.00')
    pending_payments = invoices.filter(status__in=[InvoiceStatus.UNPAID, InvoiceStatus.PARTIALLY_PAID]).aggregate(
        balance=Sum('total_amount') - Sum('paid_amount')
    )['balance'] or Decimal('0.00')

    # Customer counts
    total_clients = customers.count()
    month_start = today.replace(day=1)
    new_clients_month = customers.filter(created_at__date__gte=month_start).count()

    # Low stock alerts count
    low_stock_count = 0
    for sl in stock_levels.select_related('product'):
        if sl.quantity_on_hand <= sl.reorder_level:
            low_stock_count += 1

    # 7-day revenue & appointments chart
    chart_days = []
    for i in range(6, -1, -1):
        day = today - datetime.timedelta(days=i)
        day_rev = invoices.filter(created_at__date=day, status=InvoiceStatus.PAID).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
        day_cnt = appts.filter(date=day).count()
        chart_days.append({
            'date': day.strftime('%a, %b %d'),
            'iso_date': day.isoformat(),
            'revenue': float(day_rev),
            'appointments': day_cnt
        })

    # Most popular services
    popular_services_qs = AppointmentItem.objects.filter(salon=salon).values(
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

    # Staff Performance
    staff_qs = StaffProfile.objects.filter(salon=salon).select_related('user', 'branch')
    staff_performance = []
    for sp in staff_qs:
        s_appts = Appointment.objects.filter(staff=sp)
        s_count = s_appts.count()
        s_rev = s_appts.filter(status=AppointmentStatus.COMPLETED).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
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

    # Branch comparisons
    branch_qs = Branch.objects.filter(salon=salon)
    branch_comparison = []
    for b in branch_qs:
        b_rev = invoices.filter(branch=b, status=InvoiceStatus.PAID).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0.00')
        b_cnt = appts.filter(branch=b).count()
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

    return Response({
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
    })


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
