from rest_framework import serializers
from apps.inventory.models import (
    ProductCategory, Product, StockLevel, StockMovement,
    Supplier, PurchaseOrder, PurchaseOrderItem
)

class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ['id', 'salon', 'name', 'description']
        read_only_fields = ['id']


class StockLevelSerializer(serializers.ModelSerializer):
    branch_name = serializers.ReadOnlyField(source='branch.name')

    class Meta:
        model = StockLevel
        fields = ['id', 'branch', 'branch_name', 'quantity_on_hand', 'reorder_level', 'is_low_stock']
        read_only_fields = ['id', 'is_low_stock']


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')
    stock_levels = StockLevelSerializer(many=True, read_only=True)
    total_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'salon', 'category', 'category_name', 'name', 'sku',
            'barcode', 'brand', 'unit', 'purchase_price', 'selling_price',
            'is_retail', 'low_stock_threshold', 'image', 'is_active',
            'stock_levels', 'total_stock', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_total_stock(self, obj):
        return sum(sl.quantity_on_hand for sl in obj.stock_levels.all())


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.name')
    branch_name = serializers.ReadOnlyField(source='branch.name')
    created_by_name = serializers.ReadOnlyField(source='created_by.get_full_name')

    class Meta:
        model = StockMovement
        fields = [
            'id', 'salon', 'branch', 'branch_name', 'product', 'product_name',
            'movement_type', 'quantity', 'balance_after', 'reference_id',
            'notes', 'created_by', 'created_by_name', 'created_at'
        ]
        read_only_fields = ['id', 'balance_after', 'created_at']


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'salon', 'name', 'contact_person', 'email', 'phone', 'address']
        read_only_fields = ['id']


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.name')

    class Meta:
        model = PurchaseOrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'unit_cost', 'total_cost']
        read_only_fields = ['id']


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    supplier_name = serializers.ReadOnlyField(source='supplier.name')
    branch_name = serializers.ReadOnlyField(source='branch.name')

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'salon', 'branch', 'branch_name', 'supplier', 'supplier_name',
            'po_number', 'status', 'total_cost', 'expected_date',
            'received_at', 'notes', 'items', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
