import datetime
from django.db import models
from apps.core.models import TenantModel, Branch, StaffProfile, User
from apps.customers.models import Customer
from apps.appointments.models import Appointment
from apps.catalog.models import Service

class InvoiceStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    UNPAID = 'UNPAID', 'Unpaid'
    PARTIALLY_PAID = 'PARTIALLY_PAID', 'Partially Paid'
    PAID = 'PAID', 'Paid'
    REFUNDED = 'REFUNDED', 'Refunded'
    CANCELLED = 'CANCELLED', 'Cancelled'


class PaymentMethod(models.TextChoices):
    CASH = 'CASH', 'Cash'
    UPI = 'UPI', 'UPI / QR'
    CARD = 'CARD', 'Credit / Debit Card'
    LOYALTY_POINTS = 'LOYALTY_POINTS', 'Loyalty Points'
    BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer'


class Invoice(TenantModel):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='invoices')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    appointment = models.OneToOneField(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoice')
    invoice_number = models.CharField(max_length=100, db_index=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    status = models.CharField(
        max_length=30,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.UNPAID,
        db_index=True
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='issued_invoices')

    class Meta:
        ordering = ['-created_at']
        unique_together = ('salon', 'invoice_number')

    def __str__(self):
        return f"{self.invoice_number} - ${self.total_amount} ({self.status})"

    @property
    def balance_due(self):
        return max(self.total_amount - self.paid_amount, 0)


class InvoiceItem(TenantModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    item_type = models.CharField(
        max_length=20,
        choices=[('SERVICE', 'Service'), ('PRODUCT', 'Retail Product'), ('PACKAGE', 'Package')],
        default='SERVICE'
    )
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True)
    item_name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    staff = models.ForeignKey(StaffProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='billed_items')

    def __str__(self):
        return f"{self.item_name} x{self.quantity} (${self.total_price})"


class Payment(TenantModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=30, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    transaction_reference = models.CharField(max_length=150, blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    is_refunded = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.payment_method} ${self.amount} for {self.invoice.invoice_number}"


class ExpenseCategory(TenantModel):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        unique_together = ('salon', 'name')

    def __str__(self):
        return self.name


class Expense(TenantModel):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='expenses')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    title = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=30, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    date = models.DateField(default=datetime.date.today)
    receipt_image = models.ImageField(upload_to='expenses/receipts/', blank=True, null=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.title} - ${self.amount} on {self.date}"


class CashRegister(TenantModel):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='cash_registers')
    date = models.DateField(default=datetime.date.today)
    opening_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    closing_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    cash_sales = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    cash_expenses = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    expected_cash = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    actual_cash = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    difference = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_closed = models.BooleanField(default=False)
    opened_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='opened_registers')
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='closed_registers')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']
        unique_together = ('branch', 'date')

    def __str__(self):
        return f"{self.branch.name} Register {self.date} ({'Closed' if self.is_closed else 'Open'})"
