import time
from django.utils.deprecation import MiddlewareMixin
from apps.core.models import Salon, UserRole

_SALON_CACHE = {}  # key -> (salon, expire_time)
_SALON_CACHE_TTL = 60  # seconds

class TenantMiddleware(MiddlewareMixin):
    """
    Resolves the current Salon tenant from:
    1. Authenticated user's associated salon (authoritative for non-superadmin)
    2. Header: X-Salon-Slug or X-Salon-Id (only for public or superadmin requests)
    3. Query parameter: salon_slug
    Caches resolved salon in memory for 60s to eliminate repeated WAN roundtrips on every HTTP request.
    """
    def process_request(self, request):
        request.salon = None
        now = time.time()

        # Try early token authentication if request.user is Anonymous
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated):
            auth_header = request.headers.get('Authorization') or request.headers.get('authorization')
            token_key = None
            if auth_header:
                parts = auth_header.split()
                if len(parts) >= 2 and parts[0].lower() in ['token', 'bearer']:
                    token_key = parts[1].strip().strip('"').strip("'")
            elif request.headers.get('X-Auth-Token'):
                token_key = request.headers.get('X-Auth-Token').strip().strip('"').strip("'")

            if token_key:
                try:
                    from apps.core.authentication import UnifiedTokenAuthentication
                    auth = UnifiedTokenAuthentication()
                    auth_result = auth.authenticate_credentials(token_key)
                    if auth_result:
                        request.user = auth_result[0]
                        request._cached_user = auth_result[0]
                        user = auth_result[0]
                except Exception:
                    pass

        # 1. From authenticated user (authoritative for non-superadmin)
        if user and user.is_authenticated:
            if not (user.role == UserRole.SUPERADMIN or user.is_superuser):
                request.salon = user.salon
                return
            # For superadmin, let them optionally override via headers, otherwise fall back to user.salon
            if user.salon:
                request.salon = user.salon

        # 2. From request headers (for public or superadmin requests)
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
