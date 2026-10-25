from django.urls import path
from apps.analytics.views import dashboard_metrics_view, export_csv_report_view

urlpatterns = [
    path('metrics/', dashboard_metrics_view, name='analytics-metrics'),
    path('export/', export_csv_report_view, name='analytics-export'),
]
