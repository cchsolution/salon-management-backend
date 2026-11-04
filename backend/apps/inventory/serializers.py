from rest_framework import serializers
from apps.inventory.models import (
    ProductCategory, Product, StockLevel, StockMovement,
    Supplier, PurchaseOrder, PurchaseOrderItem
)

class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ['id', 'salon', 'name', 'description']
        read_only_fields = ['id', 'salon']


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
    quantity_on_hand = serializers.SerializerMethodField()
    is_low_stock = serializers.SerializerMethodField()
    opening_stock = serializers.IntegerField(required=False, write_only=True, default=0, min_value=0)
    branch_id = serializers.UUIDField(required=False, write_only=True, allow_null=True)

    class Meta:
        model = Product
        fields = [
            'id', 'salon', 'category', 'category_name', 'name', 'sku',
            'barcode', 'brand', 'unit', 'purchase_price', 'selling_price',
            'is_retail', 'low_stock_threshold', 'image', 'is_active',
            'opening_stock', 'branch_id',
            'stock_levels', 'total_stock', 'quantity_on_hand', 'is_low_stock',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'salon', 'created_at', 'updated_at']

    def validate(self, attrs):
        request = self.context.get('request')
        salon = None
        if request and hasattr(request, 'user') and getattr(request.user, 'salon', None):
            salon = request.user.salon
        elif self.instance:
            salon = self.instance.salon

        sku = attrs.get('sku')
        if sku and salon:
            qs = Product.objects.filter(salon=salon, sku__iexact=sku.strip())
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({'sku': ['A product with this SKU already exists in your salon.']})

        category = attrs.get('category')
        if category and salon and category.salon_id != salon.id:
            raise serializers.ValidationError({'category': ['Selected category does not belong to your salon.']})

        purchase_price = attrs.get('purchase_price')
        if purchase_price is not None and purchase_price < 0:
            raise serializers.ValidationError({'purchase_price': ['Purchase price cannot be negative.']})

        selling_price = attrs.get('selling_price')
        if selling_price is not None and selling_price < 0:
            raise serializers.ValidationError({'selling_price': ['Selling price cannot be negative.']})

        return attrs

    def get_total_stock(self, obj):
        return sum(sl.quantity_on_hand for sl in obj.stock_levels.all())

    def get_quantity_on_hand(self, obj):
        request = self.context.get('request')
        if not request:
            return self.get_total_stock(obj)
        branch_id = (
            request.query_params.get('branch_id') or
            request.query_params.get('branch') or
            request.headers.get('X-Branch-Id') or
            getattr(getattr(request, 'user', None), 'branch_id', None)
        )
        if branch_id:
            st = next((sl for sl in obj.stock_levels.all() if str(sl.branch_id) == str(branch_id)), None)
            return st.quantity_on_hand if st else 0
        return self.get_total_stock(obj)

    def get_is_low_stock(self, obj):
        qty = self.get_quantity_on_hand(obj)
        threshold = obj.low_stock_threshold if obj.low_stock_threshold is not None else 5
        return qty <= threshold


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
        read_only_fields = ['id', 'salon']


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
        read_only_fields = ['id', 'salon', 'created_at', 'updated_at']
