from django.contrib import admin
from apps.pos.models import Invoice, InvoiceItem, Payment, ExpenseCategory, Expense, CashRegister

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0

class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'salon', 'branch', 'customer', 'total_amount', 'paid_amount', 'status', 'created_at')
    search_fields = ('invoice_number', 'customer__first_name', 'customer__last_name')
    list_filter = ('salon', 'branch', 'status')
    inlines = [InvoiceItemInline, PaymentInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'invoice', 'amount', 'payment_method', 'transaction_reference', 'created_at')
    list_filter = ('salon', 'payment_method')


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'salon')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('title', 'salon', 'branch', 'category', 'amount', 'payment_method', 'date')
    list_filter = ('salon', 'branch', 'category', 'date')


@admin.register(CashRegister)
class CashRegisterAdmin(admin.ModelAdmin):
    list_display = ('branch', 'date', 'opening_balance', 'closing_balance', 'expected_cash', 'actual_cash', 'is_closed')
    list_filter = ('salon', 'branch', 'is_closed', 'date')
