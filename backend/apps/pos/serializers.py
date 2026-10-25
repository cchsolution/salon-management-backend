from rest_framework import serializers
from apps.pos.models import (
    Invoice, InvoiceItem, Payment, ExpenseCategory, Expense, CashRegister
)
from apps.customers.serializers import CustomerSerializer
from apps.core.serializers import StaffProfileSerializer

class InvoiceItemSerializer(serializers.ModelSerializer):
    staff_name = serializers.ReadOnlyField(source='staff.user.get_full_name')

    class Meta:
        model = InvoiceItem
        fields = [
            'id', 'item_type', 'service', 'item_name', 'quantity',
            'unit_price', 'discount_amount', 'tax_amount', 'total_price',
            'staff', 'staff_name'
        ]
        read_only_fields = ['id']


class PaymentSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.ReadOnlyField(source='recorded_by.get_full_name')

    class Meta:
        model = Payment
        fields = [
            'id', 'invoice', 'amount', 'payment_method',
            'transaction_reference', 'recorded_by', 'recorded_by_name',
            'is_refunded', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    customer_details = CustomerSerializer(source='customer', read_only=True)
    balance_due = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    branch_name = serializers.ReadOnlyField(source='branch.name')

    class Meta:
        model = Invoice
        fields = [
            'id', 'salon', 'branch', 'branch_name', 'customer', 'customer_details',
            'appointment', 'invoice_number', 'subtotal', 'discount_amount',
            'tax_amount', 'total_amount', 'paid_amount', 'balance_due',
            'status', 'notes', 'items', 'payments', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'invoice_number', 'created_at', 'updated_at']


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ['id', 'salon', 'name', 'description']
        read_only_fields = ['id']


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')
    branch_name = serializers.ReadOnlyField(source='branch.name')

    class Meta:
        model = Expense
        fields = [
            'id', 'salon', 'branch', 'branch_name', 'category', 'category_name',
            'title', 'amount', 'payment_method', 'date', 'receipt_image',
            'notes', 'created_by', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class CashRegisterSerializer(serializers.ModelSerializer):
    branch_name = serializers.ReadOnlyField(source='branch.name')

    class Meta:
        model = CashRegister
        fields = [
            'id', 'salon', 'branch', 'branch_name', 'date', 'opening_balance',
            'closing_balance', 'cash_sales', 'cash_expenses', 'expected_cash',
            'actual_cash', 'difference', 'is_closed', 'opened_by', 'closed_by',
            'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
