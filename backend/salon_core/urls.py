from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('apps.core.urls')),
    path('api/catalog/', include('apps.catalog.urls')),
    path('api/crm/', include('apps.customers.urls')),
    path('api/customers/', include('apps.customers.urls')),
    path('api/appointments/', include('apps.appointments.urls')),
    path('api/builder/', include('apps.website_builder.urls')),
    path('api/website-builder/', include('apps.website_builder.urls')),
    path('api/pos/', include('apps.pos.urls')),
    path('api/inventory/', include('apps.inventory.urls')),
    path('api/loyalty/', include('apps.loyalty.urls')),
    path('api/notifications/', include('apps.notifications.urls')),
    path('api/analytics/', include('apps.analytics.urls')),
    path('api/reports/', include('apps.analytics.urls')),
]


from django.views.static import serve
from django.urls import re_path

# Serving static and media files:
# Static files in production are handled by WhiteNoise middleware.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
else:
    # Fallback to serve uploaded media files locally when external cloud storage (e.g. S3) is not yet configured
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]

