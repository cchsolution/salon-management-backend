import datetime
from decimal import Decimal
from django.db import transaction
from django.db.models import Max
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.pos.models import (
    Invoice, InvoiceItem, Payment, ExpenseCategory, Expense, CashRegister,
    InvoiceStatus, PaymentMethod
)
from apps.pos.serializers import (
    InvoiceSerializer, InvoiceItemSerializer, PaymentSerializer,
    ExpenseCategorySerializer, ExpenseSerializer, CashRegisterSerializer
)
from apps.core.models import Branch, StaffProfile, UserRole, AuditLog
from apps.customers.models import Customer, CustomerActivity
from apps.appointments.models import Appointment, AppointmentStatus
from apps.catalog.models import Service
from apps.tenants.permissions import IsSalonOwner, IsOwnerOrReceptionist, IsTenantMember


class CanAccessInvoices(permissions.BasePermission):
    """
    Grants invoice access to Superadmin, Salon Owner, Salon Manager, and Receptionist.
    Explicitly denies Hair Stylist (HTTP 403). Safe methods permitted for authenticated Customers on own invoices.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role in [
            UserRole.SUPERADMIN,
            UserRole.SALON_OWNER,
            UserRole.SALON_MANAGER,
            UserRole.RECEPTIONIST
        ] or request.user.is_superuser:
            return True
        if request.user.role == UserRole.CUSTOMER and request.method in permissions.SAFE_METHODS:
            return True
        return False

    def has_object_permission(self, request, view, obj):
        if request.user.role == UserRole.SUPERADMIN or request.user.is_superuser:
            return True
        if request.user.role in [UserRole.SALON_OWNER, UserRole.SALON_MANAGER, UserRole.RECEPTIONIST]:
            return bool(request.user.salon and obj.salon == request.user.salon)
        if request.user.role == UserRole.CUSTOMER:
            return bool(obj.customer and obj.customer.user == request.user)
        return False


def generate_invoice_number(salon):
    year = datetime.date.today().year
    prefix = f"INV-{year}-"
    latest = Invoice.objects.filter(salon=salon, invoice_number__startswith=prefix).aggregate(Max('invoice_number'))
    latest_val = latest['invoice_number__max']
    if latest_val:
        try:
            num = int(latest_val.split('-')[-1]) + 1
        except Exception:
            num = 1
    else:
        num = 1
    return f"{prefix}{num:04d}"


class InvoiceViewSet(viewsets.ModelViewSet):
    serializer_class = InvoiceSerializer
    permission_classes = [CanAccessInvoices, IsTenantMember]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'total_amount']

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return Invoice.objects.none()

        qs = Invoice.objects.select_related('salon', 'branch', 'customer').prefetch_related('items', 'payments')

        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            pass
        elif user.role in [UserRole.SALON_OWNER, UserRole.SALON_MANAGER, UserRole.RECEPTIONIST] and user.salon:
            qs = qs.filter(salon=user.salon)
        elif user.role == UserRole.CUSTOMER:
            # Customer only sees their own bills
            qs = qs.filter(customer__user=user)
        else:
            return Invoice.objects.none()

        # Filters
        branch_id = self.request.query_params.get('branch')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        return qs


    def create(self, request, *args, **kwargs):
        data = request.data
        user = request.user
        salon = user.salon

        if not salon:
            return Response({'error': 'Active salon is required to create an invoice.'}, status=status.HTTP_400_BAD_REQUEST)

        branch_id = data.get('branch')
        branch = Branch.objects.filter(salon=salon, id=branch_id).first()
        if not branch:
            branch = Branch.objects.filter(salon=salon, is_primary=True).first()

        customer = None
        if data.get('customer'):
            customer = Customer.objects.filter(salon=salon, id=data['customer']).first()

        appointment = None
        if data.get('appointment'):
            appointment = Appointment.objects.filter(salon=salon, id=data['appointment']).first()

        items_data = data.get('items', [])
        if not items_data:
            return Response({'error': 'Invoice must contain at least one item.'}, status=status.HTTP_400_BAD_REQUEST)

        subtotal = Decimal('0.00')
        tax_total = Decimal('0.00')
        discount_total = Decimal(str(data.get('discount_amount', '0.00')))

        with transaction.atomic():
            invoice_num = generate_invoice_number(salon)
            invoice = Invoice.objects.create(
                salon=salon,
                branch=branch,
                customer=customer,
                appointment=appointment,
                invoice_number=invoice_num,
                subtotal=Decimal('0.00'),
                tax_amount=Decimal('0.00'),
                discount_amount=discount_total,
                total_amount=Decimal('0.00'),
                paid_amount=Decimal('0.00'),
                status=InvoiceStatus.UNPAID,
                notes=data.get('notes', ''),
                created_by=user
            )

            for it in items_data:
                unit_price = Decimal(str(it.get('unit_price', 0)))
                qty = int(it.get('quantity', 1))
                item_disc = Decimal(str(it.get('discount_amount', 0)))
                line_subtotal = (unit_price * qty) - item_disc
                # Salon tax percentage
                tax_rate = salon.tax_rate / Decimal('100.0')
                line_tax = line_subtotal * tax_rate
                line_total = line_subtotal + line_tax

                subtotal += line_subtotal
                tax_total += line_tax

                staff = None
                if it.get('staff'):
                    staff = StaffProfile.objects.filter(salon=salon, id=it['staff']).first()

                service = None
                if it.get('service'):
                    service = Service.objects.filter(salon=salon, id=it['service']).first()

                InvoiceItem.objects.create(
                    salon=salon,
                    invoice=invoice,
                    item_type=it.get('item_type', 'SERVICE'),
                    service=service,
                    item_name=it.get('item_name', 'Salon Service'),
                    quantity=qty,
                    unit_price=unit_price,
                    discount_amount=item_disc,
                    tax_amount=line_tax,
                    total_price=line_total,
                    staff=staff
                )

            total_amount = max(subtotal + tax_total - discount_total, Decimal('0.00'))
            invoice.subtotal = subtotal
            invoice.tax_amount = tax_total
            invoice.total_amount = total_amount
            invoice.save(update_fields=['subtotal', 'tax_amount', 'total_amount'])

            # If appointment exists, mark completed
            if appointment and appointment.status != AppointmentStatus.COMPLETED:
                appointment.status = AppointmentStatus.COMPLETED
                appointment.save(update_fields=['status'])

            AuditLog.objects.create(
                salon=salon,
                user=user,
                action='CREATE_INVOICE',
                entity_type='Invoice',
                entity_id=str(invoice.id),
                details={'invoice_number': invoice.invoice_number, 'total': str(total_amount)}
            )

        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsOwnerOrReceptionist])
    def record_payment(self, request, pk=None):
        invoice = self.get_object()
        amount = Decimal(str(request.data.get('amount', invoice.balance_due)))
        method = request.data.get('payment_method', PaymentMethod.CASH)
        ref = request.data.get('transaction_reference', '')

        if amount <= Decimal('0.00'):
            return Response({'error': 'Payment amount must be greater than zero.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            payment = Payment.objects.create(
                salon=invoice.salon,
                invoice=invoice,
                amount=amount,
                payment_method=method,
                transaction_reference=ref,
                recorded_by=request.user
            )

            new_paid = invoice.paid_amount + amount
            invoice.paid_amount = new_paid
            if new_paid >= invoice.total_amount:
                invoice.status = InvoiceStatus.PAID
            elif new_paid > Decimal('0.00'):
                invoice.status = InvoiceStatus.PARTIALLY_PAID
            invoice.save(update_fields=['paid_amount', 'status'])

            # Update customer spend & reward loyalty points (1 point per $10 spent)
            if invoice.customer:
                customer = invoice.customer
                customer.total_spend += amount
                points_earned = int(amount / Decimal('10.0'))
                if points_earned > 0:
                    customer.loyalty_points += points_earned
                customer.save(update_fields=['total_spend', 'loyalty_points'])

                CustomerActivity.objects.create(
                    salon=invoice.salon,
                    customer=customer,
                    activity_type='PURCHASE',
                    title=f"Payment of ${amount} via {method}",
                    description=f"Settled for invoice {invoice.invoice_number}.",
                    metadata={'invoice_id': str(invoice.id), 'payment_id': str(payment.id)}
                )

        return Response(InvoiceSerializer(invoice).data)


class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseCategorySerializer
    permission_classes = [IsSalonOwner]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return ExpenseCategory.objects.none()
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return ExpenseCategory.objects.all()
        if user.salon:
            return ExpenseCategory.objects.filter(salon=user.salon)
        return ExpenseCategory.objects.none()

    def perform_create(self, serializer):
        serializer.save(salon=self.request.user.salon)


class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer
    permission_classes = [IsSalonOwner]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return Expense.objects.none()
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return Expense.objects.all().select_related('branch', 'category')
        if user.salon:
            return Expense.objects.filter(salon=user.salon).select_related('branch', 'category')
        return Expense.objects.none()

    def perform_create(self, serializer):
        serializer.save(salon=self.request.user.salon, created_by=self.request.user)


class CashRegisterViewSet(viewsets.ModelViewSet):
    serializer_class = CashRegisterSerializer
    permission_classes = [IsOwnerOrReceptionist]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return CashRegister.objects.none()
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return CashRegister.objects.all().select_related('branch')
        if user.salon:
            return CashRegister.objects.filter(salon=user.salon).select_related('branch')
        return CashRegister.objects.none()


    @action(detail=False, methods=['post'])
    def open_register(self, request):
        salon = request.user.salon
        branch_id = request.data.get('branch')
        opening_bal = Decimal(str(request.data.get('opening_balance', '0.00')))
        branch = Branch.objects.filter(salon=salon, id=branch_id).first() or Branch.objects.filter(salon=salon, is_primary=True).first()

        today = datetime.date.today()
        register, created = CashRegister.objects.get_or_create(
            salon=salon,
            branch=branch,
            date=today,
            defaults={
                'opening_balance': opening_bal,
                'opened_by': request.user,
                'is_closed': False
            }
        )
        return Response(CashRegisterSerializer(register).data)

    @action(detail=True, methods=['post'])
    def close_register(self, request, pk=None):
        register = self.get_object()
        actual_cash = Decimal(str(request.data.get('actual_cash', '0.00')))
        notes = request.data.get('notes', '')

        # Calculate cash payments recorded today for this branch
        cash_sales = Payment.objects.filter(
            salon=register.salon,
            invoice__branch=register.branch,
            payment_method=PaymentMethod.CASH,
            created_at__date=register.date
        ).aggregate(models.Sum('amount'))['amount__sum'] or Decimal('0.00')

        # Calculate cash expenses recorded today
        cash_expenses = Expense.objects.filter(
            salon=register.salon,
            branch=register.branch,
            payment_method=PaymentMethod.CASH,
            date=register.date
        ).aggregate(models.Sum('amount'))['amount__sum'] or Decimal('0.00')

        expected_cash = register.opening_balance + cash_sales - cash_expenses
        diff = actual_cash - expected_cash

        register.cash_sales = cash_sales
        register.cash_expenses = cash_expenses
        register.expected_cash = expected_cash
        register.actual_cash = actual_cash
        register.closing_balance = actual_cash
        register.difference = diff
        register.is_closed = True
        register.closed_by = request.user
        register.notes = notes
        register.save()

        return Response(CashRegisterSerializer(register).data)
