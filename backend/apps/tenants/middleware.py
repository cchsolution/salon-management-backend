import time
from django.utils.deprecation import MiddlewareMixin
from apps.core.models import Salon

_SALON_CACHE = {}  # key -> (salon, expire_time)
_SALON_CACHE_TTL = 60  # seconds

class TenantMiddleware(MiddlewareMixin):
    """
    Resolves the current Salon tenant from:
    1. Authenticated user's associated salon
    2. Header: X-Salon-Slug or X-Salon-Id
    3. Query parameter: salon_slug
    Caches resolved salon in memory for 60s to eliminate repeated WAN roundtrips on every HTTP request.
    """
    def process_request(self, request):
        request.salon = None
        now = time.time()

        # 1. From authenticated user
        if getattr(request, 'user', None) and request.user.is_authenticated:
            if request.user.salon:
                request.salon = request.user.salon
                return

        # 2. From request headers
        salon_slug = request.headers.get('X-Salon-Slug') or request.GET.get('salon_slug')
        salon_id = request.headers.get('X-Salon-Id')

        if salon_slug:
            cached = _SALON_CACHE.get(salon_slug)
            if cached and now < cached[1]:
                request.salon = cached[0]
                return
            try:
                salon = Salon.objects.filter(slug=salon_slug, is_active=True).first()
                if salon:
                    _SALON_CACHE[salon_slug] = (salon, now + _SALON_CACHE_TTL)
                request.salon = salon
                return
            except Exception:
                pass

        if salon_id:
            cached = _SALON_CACHE.get(str(salon_id))
            if cached and now < cached[1]:
                request.salon = cached[0]
                return
            try:
                salon = Salon.objects.filter(id=salon_id, is_active=True).first()
                if salon:
                    _SALON_CACHE[str(salon_id)] = (salon, now + _SALON_CACHE_TTL)
                request.salon = salon
                return
            except Exception:
                pass
