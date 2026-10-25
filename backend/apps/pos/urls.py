from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.pos.views import (
    InvoiceViewSet, ExpenseCategoryViewSet, ExpenseViewSet, CashRegisterViewSet
)

router = DefaultRouter()
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'expense-categories', ExpenseCategoryViewSet, basename='expense-category')
router.register(r'expenses', ExpenseViewSet, basename='expense')
router.register(r'cash-registers', CashRegisterViewSet, basename='cash-register')

urlpatterns = [
    path('', include(router.urls)),
]
