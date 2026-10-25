from django.db import models
from apps.core.models import TenantModel, Branch, User

class ProductCategory(TenantModel):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        unique_together = ('salon', 'name')

    def __str__(self):
        return self.name


class Product(TenantModel):
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=100, db_index=True)
    barcode = models.CharField(max_length=100, blank=True)
    brand = models.CharField(max_length=100, blank=True)
    unit = models.CharField(
        max_length=30,
        choices=[
            ('PCS', 'Pieces'),
            ('BOTTLE', 'Bottle'),
            ('ML', 'Milliliters (ml)'),
            ('G', 'Grams (g)'),
            ('BOX', 'Box'),
            ('KIT', 'Kit'),
        ],
        default='PCS'
    )
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_retail = models.BooleanField(default=True) # Retail sale vs internal salon consumable
    low_stock_threshold = models.PositiveIntegerField(default=5)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('salon', 'sku')

    def __str__(self):
        return f"{self.name} ({self.sku})"


class StockLevel(TenantModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_levels')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='stock_levels')
    quantity_on_hand = models.IntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=5)

    class Meta:
        unique_together = ('product', 'branch')

    def __str__(self):
        return f"{self.product.name} at {self.branch.name}: {self.quantity_on_hand} {self.product.unit}"

    @property
    def is_low_stock(self):
        return self.quantity_on_hand <= self.reorder_level


class StockMovementType(models.TextChoices):
    PURCHASE_IN = 'PURCHASE_IN', 'Purchase Received'
    SALE_OUT = 'SALE_OUT', 'Retail POS Sale'
    SERVICE_USAGE = 'SERVICE_USAGE', 'In-Salon Service Usage'
    ADJUSTMENT = 'ADJUSTMENT', 'Manual Adjustment'
    TRANSFER_IN = 'TRANSFER_IN', 'Branch Transfer In'
    TRANSFER_OUT = 'TRANSFER_OUT', 'Branch Transfer Out'


class StockMovement(TenantModel):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='stock_movements')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='movements')
    movement_type = models.CharField(max_length=30, choices=StockMovementType.choices)
    quantity = models.IntegerField() # Positive for stock in, negative for stock out
    balance_after = models.IntegerField()
    reference_id = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.movement_type}: {self.quantity} of {self.product.name} at {self.branch.name}"


class Supplier(TenantModel):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class PurchaseOrder(TenantModel):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='purchase_orders')
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='purchase_orders')
    po_number = models.CharField(max_length=100)
    status = models.CharField(
        max_length=30,
        choices=[
            ('DRAFT', 'Draft'),
            ('ORDERED', 'Ordered'),
            ('RECEIVED', 'Goods Received'),
            ('CANCELLED', 'Cancelled')
        ],
        default='DRAFT'
    )
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    expected_date = models.DateField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.po_number} - {self.supplier.name} (${self.total_cost})"


class PurchaseOrderItem(TenantModel):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"
