from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache
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
from apps.tenants.permissions import IsSalonOwner, IsOwnerOrReceptionist, IsTenantMember

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
        from apps.tenants.utils import get_authenticated_salon
        salon = get_authenticated_salon(self.request)
        serializer.save(salon=salon)


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
        from apps.tenants.utils import get_authenticated_salon
        salon = get_authenticated_salon(self.request)
        if not salon:
            raise serializers.ValidationError({'error': 'Active salon is required to create a product.'})

        opening_stock = serializer.validated_data.pop('opening_stock', 0)
        branch_id = serializer.validated_data.pop('branch_id', None)

        product = serializer.save(salon=salon)

        # Handle branch stock levels and optional opening stock
        branches = Branch.objects.filter(salon=salon)
        target_branch = None
        if branch_id:
            target_branch = branches.filter(id=branch_id).first()
        if not target_branch:
            target_branch = branches.filter(is_primary=True).first() or branches.first()

        for b in branches:
            qty = opening_stock if (target_branch and b.id == target_branch.id) else 0
            sl, _ = StockLevel.objects.get_or_create(
                salon=salon,
                product=product,
                branch=b,
                defaults={'quantity_on_hand': qty, 'reorder_level': product.low_stock_threshold or 5}
            )
            if qty > 0 and b.id == target_branch.id:
                sl.quantity_on_hand = qty
                sl.save(update_fields=['quantity_on_hand'])
                StockMovement.objects.create(
                    salon=salon,
                    branch=b,
                    product=product,
                    movement_type=StockMovementType.PURCHASE_IN,
                    quantity=qty,
                    balance_after=qty,
                    notes='Opening stock balance',
                    created_by=self.request.user if (self.request.user and self.request.user.is_authenticated) else None
                )
        cache.clear()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        cache.clear()

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        cache.clear()

    @action(detail=True, methods=['post'], permission_classes=[IsSalonOwner])
    def adjust_stock(self, request, pk=None):
        product = self.get_object()
        branch_id = request.data.get('branch_id') or request.headers.get('X-Branch-Id')
        
        raw_qty = request.data.get('quantity')
        if raw_qty is None:
            raw_qty = request.data.get('quantity_change', 0)
        try:
            qty_val = int(raw_qty)
        except (ValueError, TypeError):
            return Response({'error': 'Valid numeric quantity is required.'}, status=status.HTTP_400_BAD_REQUEST)

        movement_type = request.data.get('movement_type', StockMovementType.ADJUSTMENT)
        action_type = str(request.data.get('action', '')).lower()
        notes = request.data.get('notes', '')

        # Standardize delta based on direction / movement type
        if movement_type in ['SALE_OUT', 'SERVICE_USAGE', 'TRANSFER_OUT', 'REDUCTION', 'DAMAGE', 'EXPIRED', 'LOSS'] or action_type in ['subtract', 'reduce', 'remove']:
            delta = -abs(qty_val)
        elif movement_type in ['PURCHASE_IN', 'TRANSFER_IN', 'ADDITION', 'RESTOCK'] or action_type in ['add', 'addition']:
            delta = abs(qty_val)
        else:
            delta = qty_val

        if delta == 0:
            return Response({'error': 'Adjustment quantity cannot be zero.'}, status=status.HTTP_400_BAD_REQUEST)

        valid_types = [c[0] for c in StockMovementType.choices]
        if movement_type not in valid_types:
            movement_type = StockMovementType.ADJUSTMENT

        branch = Branch.objects.filter(salon=product.salon, id=branch_id).first() if branch_id else None
        if not branch:
            branch = Branch.objects.filter(salon=product.salon, is_primary=True).first() or Branch.objects.filter(salon=product.salon).first()

        if not branch:
            return Response({'error': 'Valid branch is required for stock adjustment.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            stock_level, _ = StockLevel.objects.select_for_update().get_or_create(
                salon=product.salon,
                product=product,
                branch=branch,
                defaults={'quantity_on_hand': 0, 'reorder_level': product.low_stock_threshold or 5}
            )
            new_qty = stock_level.quantity_on_hand + delta
            if new_qty < 0:
                return Response({'error': 'Insufficient stock; negative quantity not allowed.'}, status=status.HTTP_400_BAD_REQUEST)

            stock_level.quantity_on_hand = new_qty
            stock_level.save(update_fields=['quantity_on_hand'])

            movement = StockMovement.objects.create(
                salon=product.salon,
                branch=branch,
                product=product,
                movement_type=movement_type,
                quantity=delta,
                balance_after=new_qty,
                notes=notes,
                created_by=request.user if (request.user and request.user.is_authenticated) else None
            )

        cache.clear()
        return Response({
            'message': 'Stock adjusted successfully.',
            'product': ProductSerializer(product, context={'request': request}).data,
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
        from apps.tenants.utils import get_authenticated_salon
        salon = get_authenticated_salon(self.request)
        serializer.save(salon=salon)


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
        from apps.tenants.utils import get_authenticated_salon
        salon = get_authenticated_salon(self.request)
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
                stock_level, _ = StockLevel.objects.select_for_update().get_or_create(
                    salon=po.salon,
                    product=it.product,
                    branch=po.branch,
                    defaults={'quantity_on_hand': 0, 'reorder_level': it.product.low_stock_threshold or 5}
                )
                stock_level.quantity_on_hand += it.quantity
                stock_level.save(update_fields=['quantity_on_hand'])

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

        cache.clear()
        return Response(PurchaseOrderSerializer(po).data)
