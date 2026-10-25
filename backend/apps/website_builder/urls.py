from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.website_builder.views import (
    WebsiteViewSet, WebsiteThemeViewSet, WebsiteSectionViewSet,
    public_storefront_view, upload_website_image_view
)

router = DefaultRouter()
router.register(r'site', WebsiteViewSet, basename='website')
router.register(r'theme', WebsiteThemeViewSet, basename='website-theme')
router.register(r'sections', WebsiteSectionViewSet, basename='website-section')

urlpatterns = [
    path('upload/', upload_website_image_view, name='builder-upload-image'),
    path('public/<slug:salon_slug>/', public_storefront_view, name='public-storefront'),
    path('', include(router.urls)),
]

