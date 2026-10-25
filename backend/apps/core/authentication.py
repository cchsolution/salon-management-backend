import time
from rest_framework.authentication import TokenAuthentication, get_authorization_header
from rest_framework import exceptions
from django.utils.translation import gettext_lazy as _
from rest_framework.authtoken.models import Token

# In-memory cache for valid tokens to eliminate redundant WAN queries on concurrent requests
# Maps clean_key -> (user, token, expire_timestamp)
_TOKEN_AUTH_CACHE = {}
_TOKEN_CACHE_TTL = 30  # seconds

def clear_token_cache(key=None):
    if key:
        _TOKEN_AUTH_CACHE.pop(key, None)
    else:
        _TOKEN_AUTH_CACHE.clear()

class UnifiedTokenAuthentication(TokenAuthentication):
    """
    Extends Django REST Framework TokenAuthentication to:
    1. Accept both 'Bearer <key>' and 'Token <key>' Authorization header formats (case-insensitive).
    2. Support 'X-Auth-Token: <key>' header fallback.
    3. Clean and sanitize token strings (stripping surrounding quotes, whitespace).
    4. Provide uniform authentication across all protected API endpoints.
    5. Cache valid tokens in memory for 30s to prevent roundtrip latency spikes on concurrent bursts.
    """
    keyword = 'Token'

    def authenticate(self, request):
        auth = get_authorization_header(request).split()

        if not auth:
            # Fallback to X-Auth-Token header if present
            raw_header = request.headers.get('X-Auth-Token') or request.headers.get('x-auth-token')
            if raw_header:
                clean_key = raw_header.strip().strip('"').strip("'")
                return self.authenticate_credentials(clean_key)
            return None

        # Accept both 'token' and 'bearer' prefixes case-insensitively
        prefix = auth[0].lower()
        if prefix not in (b'token', b'bearer'):
            return None

        if len(auth) == 1:
            msg = _('Invalid token header. No credentials provided.')
            raise exceptions.AuthenticationFailed(msg)
        elif len(auth) > 2:
            token_str = b' '.join(auth[1:]).decode('utf-8', errors='ignore').strip().strip('"').strip("'")
        else:
            try:
                token_str = auth[1].decode().strip().strip('"').strip("'")
            except UnicodeError:
                msg = _('Invalid token header. Token string should not contain invalid characters.')
                raise exceptions.AuthenticationFailed(msg)

        return self.authenticate_credentials(token_str)

    def authenticate_credentials(self, key):
        clean_key = str(key).strip().strip('"').strip("'")
        now = time.time()

        cached = _TOKEN_AUTH_CACHE.get(clean_key)
        if cached:
            user, token, expire_time = cached
            if now < expire_time and user.is_active:
                return (user, token)
            else:
                _TOKEN_AUTH_CACHE.pop(clean_key, None)

        model = self.get_model()
        try:
            token = model.objects.select_related('user', 'user__salon', 'user__branch').get(key=clean_key)
        except model.DoesNotExist:
            raise exceptions.AuthenticationFailed(_('Invalid token.'))

        if not token.user.is_active:
            raise exceptions.AuthenticationFailed(_('User inactive or deleted.'))

        _TOKEN_AUTH_CACHE[clean_key] = (token.user, token, now + _TOKEN_CACHE_TTL)
        return (token.user, token)
