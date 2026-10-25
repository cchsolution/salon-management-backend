from django.utils.deprecation import MiddlewareMixin
from apps.core.models import Salon

class TenantMiddleware(MiddlewareMixin):
    """
    Resolves the current Salon tenant from:
    1. Authenticated user's associated salon
    2. Header: X-Salon-Slug or X-Salon-Id
    3. Query parameter: salon_slug
    """
    def process_request(self, request):
        request.salon = None
        
        # 1. From authenticated user
        if getattr(request, 'user', None) and request.user.is_authenticated:
            if request.user.salon:
                request.salon = request.user.salon
                return

        # 2. From request headers
        salon_slug = request.headers.get('X-Salon-Slug') or request.GET.get('salon_slug')
        salon_id = request.headers.get('X-Salon-Id')

        if salon_slug:
            try:
                request.salon = Salon.objects.filter(slug=salon_slug, is_active=True).first()
                return
            except Exception:
                pass
        
        if salon_id:
            try:
                request.salon = Salon.objects.filter(id=salon_id, is_active=True).first()
                return
            except Exception:
                pass
