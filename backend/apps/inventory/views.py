from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.inventory.models import (
    ProductCategory, Product, StockLevel, StockMovement,
    Supplier, PurchaseOrder, PurchaseOrderItem, StockMovementType
)
from apps.inventory.serializers import (
    ProductCategorySerializer, ProductSerializer, StockLevelSerializer,
    StockMovementSerializer, SupplierSerializer, PurchaseOrderSerializer
)
from apps.core.models import Branch, AuditLog, UserRole
from apps.tenants.permissions import IsSalonOwner

class ProductCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = ProductCategorySerializer
    permission_classes = [IsSalonOwner]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return ProductCategory.objects.none()
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return ProductCategory.objects.all()
        if user.salon:
            return ProductCategory.objects.filter(salon=user.salon)
        return ProductCategory.objects.none()

    def perform_create(self, serializer):
        serializer.save(salon=self.request.user.salon)


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsSalonOwner]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'sku', 'brand', 'barcode']
    ordering_fields = ['name', 'selling_price', 'created_at']

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return Product.objects.none()

        qs = Product.objects.select_related('category', 'salon').prefetch_related('stock_levels__branch')
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            pass
        elif user.salon:
            qs = qs.filter(salon=user.salon)
        else:
            return Product.objects.none()

        is_retail = self.request.query_params.get('retail')
        if is_retail in ['true', '1']:
            qs = qs.filter(is_retail=True)

        return qs


    def perform_create(self, serializer):
        product = serializer.save(salon=self.request.user.salon)
        # Create initial 0 stock level for primary branch
        branches = Branch.objects.filter(salon=self.request.user.salon)
        for b in branches:
            StockLevel.objects.get_or_create(
                salon=self.request.user.salon,
                product=product,
                branch=b,
                defaults={'quantity_on_hand': 0, 'reorder_level': product.low_stock_threshold}
            )

    @action(detail=True, methods=['post'], permission_classes=[IsSalonOwner])
    def adjust_stock(self, request, pk=None):
        product = self.get_object()
        branch_id = request.data.get('branch_id')
        delta = int(request.data.get('quantity_change', 0))
        movement_type = request.data.get('movement_type', StockMovementType.ADJUSTMENT)
        notes = request.data.get('notes', '')

        branch = Branch.objects.filter(salon=product.salon, id=branch_id).first()
        if not branch:
            branch = Branch.objects.filter(salon=product.salon, is_primary=True).first()

        with transaction.atomic():
            stock_level, _ = StockLevel.objects.get_or_create(
                salon=product.salon,
                product=product,
                branch=branch,
                defaults={'quantity_on_hand': 0}
            )
            new_qty = stock_level.quantity_on_hand + delta
            if new_qty < 0:
                return Response({'error': 'Insufficient stock; negative quantity not allowed.'}, status=status.HTTP_400_BAD_REQUEST)

            stock_level.quantity_on_hand = new_qty
            stock_level.save()

            movement = StockMovement.objects.create(
                salon=product.salon,
                branch=branch,
                product=product,
                movement_type=movement_type,
                quantity=delta,
                balance_after=new_qty,
                notes=notes,
                created_by=request.user
            )

        return Response({
            'message': 'Stock adjusted successfully.',
            'product': ProductSerializer(product).data,
            'movement': StockMovementSerializer(movement).data
        })


class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StockMovementSerializer
    permission_classes = [IsSalonOwner]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return StockMovement.objects.none()
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return StockMovement.objects.all().select_related('product', 'branch', 'created_by')
        if user.salon:
            return StockMovement.objects.filter(salon=user.salon).select_related('product', 'branch', 'created_by')
        return StockMovement.objects.none()


class SupplierViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierSerializer
    permission_classes = [IsSalonOwner]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return Supplier.objects.none()
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return Supplier.objects.all()
        if user.salon:
            return Supplier.objects.filter(salon=user.salon)
        return Supplier.objects.none()

    def perform_create(self, serializer):
        serializer.save(salon=self.request.user.salon)


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsSalonOwner]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return PurchaseOrder.objects.none()
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return PurchaseOrder.objects.all().select_related('supplier', 'branch').prefetch_related('items__product')
        if user.salon:
            return PurchaseOrder.objects.filter(salon=user.salon).select_related('supplier', 'branch').prefetch_related('items__product')
        return PurchaseOrder.objects.none()

    def perform_create(self, serializer):
        salon = self.request.user.salon
        count = PurchaseOrder.objects.filter(salon=salon).count() + 1
        po_number = f"PO-{timezone.now().year}-{count:04d}"
        serializer.save(salon=salon, po_number=po_number)


    @action(detail=True, methods=['post'])
    def receive_order(self, request, pk=None):
        po = self.get_object()
        if po.status == 'RECEIVED':
            return Response({'error': 'This purchase order has already been received.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for it in po.items.all():
                stock_level, _ = StockLevel.objects.get_or_create(
                    salon=po.salon,
                    product=it.product,
                    branch=po.branch,
                    defaults={'quantity_on_hand': 0}
                )
                stock_level.quantity_on_hand += it.quantity
                stock_level.save()

                StockMovement.objects.create(
                    salon=po.salon,
                    branch=po.branch,
                    product=it.product,
                    movement_type=StockMovementType.PURCHASE_IN,
                    quantity=it.quantity,
                    balance_after=stock_level.quantity_on_hand,
                    reference_id=po.po_number,
                    notes=f"Received PO {po.po_number}",
                    created_by=request.user
                )

            po.status = 'RECEIVED'
            po.received_at = timezone.now()
            po.save(update_fields=['status', 'received_at'])

        return Response(PurchaseOrderSerializer(po).data)
