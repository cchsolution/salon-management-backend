from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.pos.views import (
    InvoiceViewSet, ExpenseCategoryViewSet, ExpenseViewSet, CashRegisterViewSet
)

router = DefaultRouter()
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'bills', InvoiceViewSet, basename='bill')
router.register(r'expense-categories', ExpenseCategoryViewSet, basename='expense-category')
router.register(r'expenses', ExpenseViewSet, basename='expense')
router.register(r'cash-registers', CashRegisterViewSet, basename='cash-register')

urlpatterns = [
    path('retail-products/', InvoiceViewSet.as_view({'get': 'retail_products'}), name='pos-retail-products'),
    path('gateways/', InvoiceViewSet.as_view({'get': 'gateways'}), name='pos-gateways'),
    path('invoices/<uuid:pk>/payment-qr/', InvoiceViewSet.as_view({'get': 'payment_qr', 'post': 'payment_qr'}), name='pos-invoice-payment-qr'),
    path('invoices/<uuid:pk>/pdf/', InvoiceViewSet.as_view({'get': 'pdf'}), name='pos-invoice-pdf'),
    path('', include(router.urls)),
]
