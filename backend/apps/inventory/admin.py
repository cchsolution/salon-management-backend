from django.contrib import admin
from apps.inventory.models import (
    ProductCategory, Product, StockLevel, StockMovement, Supplier, PurchaseOrder, PurchaseOrderItem
)

class StockLevelInline(admin.TabularInline):
    model = StockLevel
    extra = 0

class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 0

@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'salon')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'salon', 'sku', 'brand', 'purchase_price', 'selling_price', 'is_retail', 'is_active')
    search_fields = ('name', 'sku', 'brand', 'barcode')
    list_filter = ('salon', 'is_retail', 'is_active', 'category')
    inlines = [StockLevelInline]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('product', 'branch', 'movement_type', 'quantity', 'balance_after', 'created_at')
    list_filter = ('salon', 'branch', 'movement_type')


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'salon', 'contact_person', 'phone', 'email')


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('po_number', 'salon', 'supplier', 'branch', 'status', 'total_cost', 'created_at')
    list_filter = ('salon', 'branch', 'status')
    inlines = [PurchaseOrderItemInline]
