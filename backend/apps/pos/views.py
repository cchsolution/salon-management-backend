import datetime
import logging
import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction, models
from django.db.models import Max
from django.http import HttpResponse
from django.core.cache import cache
from django.utils import timezone
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response

logger = logging.getLogger(__name__)

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
from apps.core.models import Branch, StaffProfile, UserRole, AuditLog, Salon
from apps.customers.models import Customer, CustomerActivity
from apps.appointments.models import Appointment, AppointmentStatus
from apps.catalog.models import Service
from apps.inventory.models import Product, StockLevel, StockMovement, StockMovementType
from apps.inventory.serializers import ProductSerializer
from apps.tenants.permissions import IsSalonOwner, IsOwnerOrReceptionist, IsTenantMember
from apps.tenants.utils import get_authenticated_salon, get_authenticated_branch

def safe_uuid(val):
    if not val:
        return None
    if isinstance(val, dict):
        val = val.get('id') or val.get('pk')
    try:
        return uuid.UUID(str(val).strip())
    except (ValueError, AttributeError, TypeError):
        return None

def resolve_pos_branch(request, salon, branch_val=None):
    return get_authenticated_branch(request, salon, branch_val)


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
    existing_invoices = list(Invoice.objects.filter(salon=salon, invoice_number__startswith=prefix).values_list('invoice_number', flat=True))
    max_num = 0
    for inv_no in existing_invoices:
        suffix = inv_no.replace(prefix, '').strip()
        if suffix.isdigit():
            max_num = max(max_num, int(suffix))

    next_num = max(max_num + 1, len(existing_invoices) + 1)
    candidate = f"{prefix}{next_num:04d}"
    while Invoice.objects.filter(salon=salon, invoice_number=candidate).exists():
        next_num += 1
        candidate = f"{prefix}{next_num:04d}"
    return candidate


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
        Includes current stock on hand at the specified/requested branch.
        Synchronized with inventory StockLevel model so stock is consistent across POS and Inventory.
        """
        user = request.user
        salon = user.salon
        if not salon and (user.role == UserRole.SUPERADMIN or user.is_superuser):
            salon = Salon.objects.first()

        if not salon:
            return Response({'error': 'Active salon is required.'}, status=status.HTTP_400_BAD_REQUEST)

        branch = resolve_pos_branch(request, salon)
        branch_id_str = str(branch.id) if branch else 'default'
        search = (request.query_params.get('search') or request.query_params.get('q') or '').strip()

        cache_key = f"pos_retail_prods_{salon.id}_{branch_id_str}_{search}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        products = Product.objects.filter(
            salon=salon,
            is_retail=True,
            is_active=True
        ).select_related('category').prefetch_related('stock_levels__branch')

        if search:
            products = products.filter(
                models.Q(name__icontains=search) |
                models.Q(sku__icontains=search) |
                models.Q(barcode__icontains=search) |
                models.Q(brand__icontains=search)
            )

        data = []
        for p in products:
            all_stock_levels = list(p.stock_levels.all())
            branch_stock_level = next((sl for sl in all_stock_levels if sl.branch_id == branch.id), None) if branch else None
            stock = branch_stock_level.quantity_on_hand if branch_stock_level else 0
            total_stock_all_branches = sum(sl.quantity_on_hand for sl in all_stock_levels)
            low_threshold = p.low_stock_threshold if p.low_stock_threshold is not None else 5

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
                'total_stock': stock,  # POS cart uses product.total_stock to set available_stock
                'available_stock': stock,
                'all_branches_total_stock': total_stock_all_branches,
                'branch_id': str(branch.id) if branch else None,
                'branch_name': branch.name if branch else None,
                'is_low_stock': stock <= low_threshold,
                'low_stock_threshold': low_threshold,
                'is_retail': p.is_retail,
                'image': p.image.url if p.image else None,
                'category_name': p.category.name if p.category else 'General',
                'stock_levels': [
                    {
                        'id': str(sl.id),
                        'branch': str(sl.branch_id),
                        'branch_name': sl.branch.name,
                        'quantity_on_hand': sl.quantity_on_hand,
                        'reorder_level': sl.reorder_level,
                        'is_low_stock': sl.is_low_stock,
                    }
                    for sl in all_stock_levels
                ]
            })

        cache.set(cache_key, data, timeout=60)
        return Response(data)

    def create(self, request, *args, **kwargs):
        data = request.data
        user = request.user
        salon = user.salon
        if not salon and (user.role == UserRole.SUPERADMIN or user.is_superuser):
            salon = Salon.objects.first()

        if not salon:
            return Response({'error': 'Active salon is required to create an invoice.'}, status=status.HTTP_400_BAD_REQUEST)

        branch = resolve_pos_branch(request, salon, data.get('branch') or data.get('branch_id'))
        if not branch:
            return Response({'error': 'A valid salon branch is required.'}, status=status.HTTP_400_BAD_REQUEST)

        customer = None
        c_id = safe_uuid(data.get('customer') or data.get('customer_id'))
        if c_id:
            customer = Customer.objects.filter(salon=salon, id=c_id).first()

        appointment = None
        a_id = safe_uuid(data.get('appointment') or data.get('appointment_id'))
        if a_id:
            appointment = Appointment.objects.filter(salon=salon, id=a_id).first()

        items_data = data.get('items', [])
        if not items_data:
            return Response({'error': 'Bill must contain at least one item.'}, status=status.HTTP_400_BAD_REQUEST)

        # Duplicate submission protection within 5 seconds
        recent_duplicate = Invoice.objects.filter(
            salon=salon,
            branch=branch,
            customer=customer,
            created_by=user,
            created_at__gte=timezone.now() - datetime.timedelta(seconds=5)
        ).first()
        if recent_duplicate and recent_duplicate.items.count() == len(items_data):
            return Response(InvoiceSerializer(recent_duplicate).data, status=status.HTTP_200_OK)

        # 1. Parse and validate items & aggregate product quantities
        validated_items = []
        product_quantities = {}  # {product_id: total_qty}
        products_map = {}        # {product_id: product_instance}
        subtotal = Decimal('0.00')

        for it in items_data:
            item_type = it.get('item_type')
            if not item_type:
                if it.get('service') or it.get('service_id'):
                    item_type = 'SERVICE'
                else:
                    item_type = 'PRODUCT'
            item_type = item_type.upper()

            try:
                qty = int(it.get('quantity', 1))
            except (ValueError, TypeError):
                qty = 1

            if qty <= 0:
                return Response({'error': 'Quantity must be greater than zero.'}, status=status.HTTP_400_BAD_REQUEST)

            product = None
            service = None
            item_name = it.get('item_name')

            if item_type == 'PRODUCT' or it.get('product') or it.get('product_id'):
                p_id = safe_uuid(it.get('product') or it.get('product_id'))
                if p_id:
                    product = Product.objects.filter(salon=salon, id=p_id, is_active=True).first()
                if not product and it.get('item_name'):
                    product = Product.objects.filter(salon=salon, name__iexact=str(it.get('item_name')).strip(), is_active=True).first()
                if not product and it.get('sku'):
                    product = Product.objects.filter(salon=salon, sku__iexact=str(it.get('sku')).strip(), is_active=True).first()

                if product:
                    if not product.is_retail:
                        return Response({'error': f'Product "{product.name}" is designated as internal consumable and not available for retail sale.'}, status=status.HTTP_400_BAD_REQUEST)

                    item_name = product.name
                    unit_price = Decimal(str(it.get('unit_price') or product.selling_price))
                    product_quantities[product.id] = product_quantities.get(product.id, 0) + qty
                    products_map[product.id] = product
                else:
                    item_name = str(it.get('item_name') or 'Retail Product').strip()
                    unit_price = Decimal(str(it.get('unit_price', '0.00')))
            elif item_type == 'SERVICE' or it.get('service') or it.get('service_id'):
                s_id = safe_uuid(it.get('service') or it.get('service_id'))
                service = Service.objects.filter(salon=salon, id=s_id).first() if s_id else None
                if not service:
                    return Response({'error': 'Service was not found.'}, status=status.HTTP_400_BAD_REQUEST)
                item_name = service.name
                unit_price = Decimal(str(it.get('unit_price') or service.effective_price))
            else:
                unit_price = Decimal(str(it.get('unit_price', 0)))
                item_name = it.get('item_name', 'Retail Product')

            item_disc = Decimal(str(it.get('discount_amount', 0)))
            line_subtotal = max((unit_price * qty) - item_disc, Decimal('0.00'))
            subtotal += line_subtotal

            staff = None
            st_id = safe_uuid(it.get('staff') or it.get('staff_id'))
            if st_id:
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
        raw_discount_type = data.get('discount_type')
        discount_type = 'FIXED'
        if isinstance(raw_discount_type, str):
            discount_type = raw_discount_type.strip().upper()
        if discount_type not in ['PERCENTAGE', 'FIXED', 'NONE']:
            discount_type = 'FIXED'

        raw_val = (
            data.get('discount_value')
            if data.get('discount_value') is not None
            else data.get('discount_amount')
        )
        if raw_val is None or raw_val == '':
            raw_val = data.get('discount')
        if raw_val is None or raw_val == '':
            raw_val = '0.00'

        try:
            discount_val = Decimal(str(raw_val).strip())
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
                return Response({'error': 'Discount cannot be negative.'}, status=status.HTTP_400_BAD_REQUEST)
            discount_amount = min(discount_val, subtotal).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            discount_amount = Decimal('0.00')
            discount_percentage = Decimal('0.00')

        if discount_amount is None:
            discount_amount = Decimal('0.00')
        if discount_percentage is None:
            discount_percentage = Decimal('0.00')

        taxable_amount = max(subtotal - discount_amount, Decimal('0.00'))
        tax_rate = (salon.tax_rate / Decimal('100.0')) if not salon.tax_rate == 0 else Decimal('0.00')
        tax_total = (taxable_amount * tax_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        total_amount = taxable_amount + tax_total

        # 3. Database Transaction: Lock Rows, Validate Stock, Create Invoice, Deduct Stock
        with transaction.atomic():
            locked_stock_levels = {}
            # Lock rows in deterministic sorted UUID order to prevent deadlocks
            for p_id in sorted(product_quantities.keys(), key=lambda x: str(x)):
                p_obj = products_map[p_id]
                sl, _ = StockLevel.objects.select_for_update().get_or_create(
                    salon=salon,
                    product=p_obj,
                    branch=branch,
                    defaults={'quantity_on_hand': 0, 'reorder_level': p_obj.low_stock_threshold or 5}
                )
                locked_stock_levels[p_id] = sl

            # Authoritative Stock Validation before confirming invoice
            for p_id, req_qty in product_quantities.items():
                sl = locked_stock_levels[p_id]
                p_obj = products_map[p_id]
                if sl.quantity_on_hand < req_qty:
                    return Response(
                        {'error': f'Insufficient stock for "{p_obj.name}". Available: {sl.quantity_on_hand}, Requested: {req_qty}.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # 4. Create Invoice Record
            invoice_num = generate_invoice_number(salon)
            invoice = Invoice.objects.create(
                salon=salon,
                branch=branch,
                customer=customer,
                appointment=appointment,
                invoice_number=invoice_num,
                subtotal=subtotal if subtotal is not None else Decimal('0.00'),
                discount_type=discount_type or 'FIXED',
                discount_percentage=discount_percentage if discount_percentage is not None else Decimal('0.00'),
                discount_amount=discount_amount if discount_amount is not None else Decimal('0.00'),
                tax_amount=tax_total if tax_total is not None else Decimal('0.00'),
                total_amount=total_amount if total_amount is not None else Decimal('0.00'),
                paid_amount=Decimal('0.00'),
                status=InvoiceStatus.UNPAID,
                notes=data.get('notes', '') or '',
                created_by=user
            )

            # 5. Create InvoiceItems
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

            # 6. Deduct Stock Only After Successful Invoice Creation
            for p_id, req_qty in product_quantities.items():
                sl = locked_stock_levels[p_id]
                p_obj = products_map[p_id]
                sl.quantity_on_hand -= req_qty
                sl.save(update_fields=['quantity_on_hand'])

                StockMovement.objects.create(
                    salon=salon,
                    branch=branch,
                    product=p_obj,
                    movement_type=StockMovementType.SALE_OUT,
                    quantity=-req_qty,
                    balance_after=sl.quantity_on_hand,
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

        cache.clear()
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
        try:
            invoice = self.get_object()
            pdf_bytes = generate_invoice_pdf(invoice)
            filename = f"{invoice.invoice_number}.pdf"
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            return response
        except Exception as e:
            logger.error("Failed to generate PDF for invoice %s: %s", pk, str(e), exc_info=True)
            return Response({'error': f'Failed to generate invoice PDF: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
