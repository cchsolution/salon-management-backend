from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.inventory.views import (
    ProductCategoryViewSet, ProductViewSet, StockMovementViewSet,
    SupplierViewSet, PurchaseOrderViewSet
)

router = DefaultRouter()
router.register(r'product-categories', ProductCategoryViewSet, basename='product-category')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'stock-movements', StockMovementViewSet, basename='stock-movement')
router.register(r'suppliers', SupplierViewSet, basename='supplier')
router.register(r'purchase-orders', PurchaseOrderViewSet, basename='purchase-order')

urlpatterns = [
    path('', include(router.urls)),
]
