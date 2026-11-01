import datetime
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction, models
from django.db.models import Max
from django.http import HttpResponse
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
from apps.pos.payment_service import PaymentGatewayProvider
from apps.pos.pdf_service import generate_invoice_pdf
from apps.core.models import Branch, StaffProfile, UserRole, AuditLog
from apps.customers.models import Customer, CustomerActivity
from apps.appointments.models import Appointment, AppointmentStatus
from apps.catalog.models import Service
from apps.inventory.models import Product, StockLevel, StockMovement, StockMovementType
from apps.inventory.serializers import ProductSerializer
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

        qs = Invoice.objects.select_related('salon', 'branch', 'customer').prefetch_related(
            'items__product', 'items__service', 'payments'
        )

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

    @action(detail=False, methods=['get'])
    def retail_products(self, request):
        """
        Returns strictly active retail products for the current salon.
        Excludes salon services completely.
        Includes current stock on hand at the specified/primary branch.
        """
        user = request.user
        salon = user.salon
        if not salon:
            return Response({'error': 'Active salon is required.'}, status=status.HTTP_400_BAD_REQUEST)

        branch_id = request.query_params.get('branch_id') or request.query_params.get('branch')
        branch = Branch.objects.filter(salon=salon, id=branch_id).first() if branch_id else Branch.objects.filter(salon=salon, is_primary=True).first()

        products = Product.objects.filter(
            salon=salon,
            is_retail=True,
            is_active=True
        ).select_related('category').prefetch_related('stock_levels')

        search = request.query_params.get('search') or request.query_params.get('q')
        if search:
            products = products.filter(
                models.Q(name__icontains=search) |
                models.Q(sku__icontains=search) |
                models.Q(barcode__icontains=search) |
                models.Q(brand__icontains=search)
            )

        data = []
        for p in products:
            stock = 0
            if branch:
                st = p.stock_levels.filter(branch=branch).first()
                if st:
                    stock = st.quantity_on_hand

            data.append({
                'id': str(p.id),
                'name': p.name,
                'sku': p.sku,
                'barcode': p.barcode,
                'brand': p.brand,
                'unit': p.unit,
                'selling_price': str(p.selling_price),
                'currency': salon.currency,
                'currency_symbol': '₹',
                'quantity_on_hand': stock,
                'is_low_stock': stock <= p.low_stock_threshold,
                'image': p.image.url if p.image else None,
                'category_name': p.category.name if p.category else 'General'
            })

        return Response(data)

    def create(self, request, *args, **kwargs):
        data = request.data
        user = request.user
        salon = user.salon

        if not salon:
            return Response({'error': 'Active salon is required to create an invoice.'}, status=status.HTTP_400_BAD_REQUEST)

        branch_id = data.get('branch') or data.get('branch_id')
        branch = Branch.objects.filter(salon=salon, id=branch_id).first()
        if not branch:
            branch = Branch.objects.filter(salon=salon, is_primary=True).first() or Branch.objects.filter(salon=salon).first()
        if not branch:
            return Response({'error': 'A valid salon branch is required.'}, status=status.HTTP_400_BAD_REQUEST)

        customer = None
        if data.get('customer') or data.get('customer_id'):
            c_id = data.get('customer') or data.get('customer_id')
            customer = Customer.objects.filter(salon=salon, id=c_id).first()

        appointment = None
        if data.get('appointment') or data.get('appointment_id'):
            a_id = data.get('appointment') or data.get('appointment_id')
            appointment = Appointment.objects.filter(salon=salon, id=a_id).first()

        items_data = data.get('items', [])
        if not items_data:
            return Response({'error': 'Bill must contain at least one item.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Parse and validate items & stock
        validated_items = []
        subtotal = Decimal('0.00')

        with transaction.atomic():
            for it in items_data:
                item_type = it.get('item_type')
                if not item_type:
                    if it.get('service') or it.get('service_id'):
                        item_type = 'SERVICE'
                    else:
                        item_type = 'PRODUCT'
                item_type = item_type.upper()

                qty = int(it.get('quantity', 1))
                if qty <= 0:
                    return Response({'error': 'Quantity must be greater than zero.'}, status=status.HTTP_400_BAD_REQUEST)

                product = None
                service = None
                item_name = it.get('item_name')

                if item_type == 'PRODUCT' or it.get('product') or it.get('product_id'):
                    p_id = it.get('product') or it.get('product_id')
                    product = Product.objects.filter(salon=salon, id=p_id, is_active=True).first()
                    if not product:
                        return Response({'error': f'Product {p_id} was not found or is inactive.'}, status=status.HTTP_400_BAD_REQUEST)
                    if not product.is_retail:
                        return Response({'error': f'Product "{product.name}" is designated as internal consumable and not available for retail sale.'}, status=status.HTTP_400_BAD_REQUEST)

                    item_name = product.name
                    unit_price = Decimal(str(it.get('unit_price') or product.selling_price))

                    # Validate Stock
                    stock_level, _ = StockLevel.objects.select_for_update().get_or_create(
                        salon=salon,
                        product=product,
                        branch=branch,
                        defaults={'quantity_on_hand': 0, 'reorder_level': product.low_stock_threshold}
                    )
                    if stock_level.quantity_on_hand < qty:
                        return Response(
                            {'error': f'Insufficient stock for "{product.name}". Available: {stock_level.quantity_on_hand}, Requested: {qty}.'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                elif item_type == 'SERVICE' or it.get('service') or it.get('service_id'):
                    s_id = it.get('service') or it.get('service_id')
                    service = Service.objects.filter(salon=salon, id=s_id).first()
                    if not service:
                        return Response({'error': f'Service {s_id} was not found.'}, status=status.HTTP_400_BAD_REQUEST)
                    item_name = service.name
                    unit_price = Decimal(str(it.get('unit_price') or service.effective_price))
                else:
                    unit_price = Decimal(str(it.get('unit_price', 0)))
                    item_name = it.get('item_name', 'Retail Product')

                item_disc = Decimal(str(it.get('discount_amount', 0)))
                line_subtotal = max((unit_price * qty) - item_disc, Decimal('0.00'))
                subtotal += line_subtotal

                staff = None
                if it.get('staff') or it.get('staff_id'):
                    st_id = it.get('staff') or it.get('staff_id')
                    staff = StaffProfile.objects.filter(salon=salon, id=st_id).first()

                validated_items.append({
                    'item_type': item_type,
                    'product': product,
                    'service': service,
                    'item_name': item_name,
                    'quantity': qty,
                    'unit_price': unit_price,
                    'discount_amount': item_disc,
                    'line_subtotal': line_subtotal,
                    'staff': staff
                })

            # 2. Overall Discount Calculation (Safe Decimal)
            discount_type = data.get('discount_type', 'FIXED').upper()
            if discount_type not in ['PERCENTAGE', 'FIXED', 'NONE']:
                discount_type = 'FIXED'

            discount_val = Decimal(str(data.get('discount_value') or data.get('discount_amount') or '0.00'))
            discount_percentage = Decimal('0.00')
            discount_amount = Decimal('0.00')

            if discount_type == 'PERCENTAGE':
                if discount_val < Decimal('0.00') or discount_val > Decimal('100.00'):
                    return Response({'error': 'Percentage discount must be between 0 and 100.'}, status=status.HTTP_400_BAD_REQUEST)
                discount_percentage = discount_val
                discount_amount = (subtotal * discount_percentage / Decimal('100.0')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            elif discount_type == 'FIXED':
                if discount_val < Decimal('0.00'):
                    return Response({'error': 'Discount cannot be negative.'}, status=status.HTTP_400_BAD_REQUEST)
                discount_amount = min(discount_val, subtotal).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            taxable_amount = max(subtotal - discount_amount, Decimal('0.00'))
            tax_rate = (salon.tax_rate / Decimal('100.0')) if not salon.tax_rate == 0 else Decimal('0.00')
            tax_total = (taxable_amount * tax_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            total_amount = taxable_amount + tax_total

            # 3. Create Invoice
            invoice_num = generate_invoice_number(salon)
            invoice = Invoice.objects.create(
                salon=salon,
                branch=branch,
                customer=customer,
                appointment=appointment,
                invoice_number=invoice_num,
                subtotal=subtotal,
                discount_type=discount_type,
                discount_percentage=discount_percentage,
                discount_amount=discount_amount,
                tax_amount=tax_total,
                total_amount=total_amount,
                paid_amount=Decimal('0.00'),
                status=InvoiceStatus.UNPAID,
                notes=data.get('notes', ''),
                created_by=user
            )

            # 4. Create Items & Deduct Retail Stock Safely
            for vit in validated_items:
                line_tax = (vit['line_subtotal'] * tax_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                line_total = vit['line_subtotal'] + line_tax

                InvoiceItem.objects.create(
                    salon=salon,
                    invoice=invoice,
                    item_type=vit['item_type'],
                    product=vit['product'],
                    service=vit['service'],
                    item_name=vit['item_name'],
                    quantity=vit['quantity'],
                    unit_price=vit['unit_price'],
                    discount_amount=vit['discount_amount'],
                    tax_amount=line_tax,
                    total_price=line_total,
                    staff=vit['staff']
                )

                # Deduct inventory for retail products
                if vit['product']:
                    st_level = StockLevel.objects.get(salon=salon, product=vit['product'], branch=branch)
                    st_level.quantity_on_hand -= vit['quantity']
                    st_level.save(update_fields=['quantity_on_hand'])

                    StockMovement.objects.create(
                        salon=salon,
                        branch=branch,
                        product=vit['product'],
                        movement_type=StockMovementType.SALE_OUT,
                        quantity=-vit['quantity'],
                        balance_after=st_level.quantity_on_hand,
                        reference_id=invoice.invoice_number,
                        notes=f"POS Sale Invoice #{invoice.invoice_number}",
                        created_by=user
                    )

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

    @action(detail=True, methods=['get', 'post'], permission_classes=[CanAccessInvoices])
    def payment_qr(self, request, pk=None):
        """
        Generates standard dynamic UPI QR request for this invoice.
        Enables seamless mobile scan & pay (GPay, PhonePe, Paytm) in INR.
        """
        invoice = self.get_object()
        amount_to_pay = invoice.balance_due
        if amount_to_pay <= Decimal('0.00'):
            return Response({'message': 'This invoice has already been fully paid.', 'paid': True})

        vpa = request.data.get('vpa') if request.method == 'POST' else request.query_params.get('vpa')
        qr_data = PaymentGatewayProvider.generate_upi_payment_qr(
            salon=invoice.salon,
            amount=amount_to_pay,
            invoice_number=invoice.invoice_number,
            vpa=vpa
        )
        return Response(qr_data)

    @action(detail=False, methods=['get'], permission_classes=[CanAccessInvoices])
    def gateways(self, request):
        """
        Returns the audit status of configured payment gateways (UPI, Razorpay, PhonePe).
        """
        return Response(PaymentGatewayProvider.get_configured_gateways())

    @action(detail=True, methods=['get'], permission_classes=[CanAccessInvoices])
    def pdf(self, request, pk=None):
        """
        Generates and downloads a clean, branded PDF invoice.
        """
        invoice = self.get_object()
        pdf_bytes = generate_invoice_pdf(invoice)
        filename = f"{invoice.invoice_number}.pdf"
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response

    @action(detail=True, methods=['post'], permission_classes=[IsOwnerOrReceptionist])
    def record_payment(self, request, pk=None):
        invoice = self.get_object()
        amount = Decimal(str(request.data.get('amount', invoice.balance_due)))
        method = request.data.get('payment_method', PaymentMethod.UPI)
        ref = request.data.get('transaction_reference') or request.data.get('reference_id') or ''

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

            # Update customer spend & reward loyalty points (1 point per ₹100 spent)
            if invoice.customer:
                customer = invoice.customer
                customer.total_spend += amount
                points_earned = int(amount / Decimal('100.0'))
                if points_earned > 0:
                    customer.loyalty_points += points_earned
                customer.save(update_fields=['total_spend', 'loyalty_points'])

                CustomerActivity.objects.create(
                    salon=invoice.salon,
                    customer=customer,
                    activity_type='PURCHASE',
                    title=f"Payment of ₹{amount} via {method}",
                    description=f"Settled for invoice {invoice.invoice_number}. Ref: {ref}",
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
