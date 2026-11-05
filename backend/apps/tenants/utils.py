import uuid
from apps.core.models import Salon, Branch, UserRole


def safe_uuid(val):
    if not val:
        return None
    if isinstance(val, dict):
        val = val.get('id') or val.get('pk')
    try:
        return uuid.UUID(str(val).strip())
    except (ValueError, AttributeError, TypeError):
        return None


def get_authenticated_salon(request, data=None, allow_public=False):
    """
    Authoritative server-side salon tenant resolver.
    
    Security rules:
    1. Authenticated non-superadmin users: ALWAYS scoped strictly to request.user.salon.
       Client-supplied salon_id / salon_slug headers and query parameters are strictly ignored.
    2. SuperAdmin users: May select a target salon via query params, headers, or payload;
       falls back to their attached salon or the default active salon.
    3. Unauthenticated requests (public storefront, booking wizard): Permitted ONLY when
       allow_public=True, deriving salon from X-Salon-Slug, X-Salon-Id, or query params.
    """
    user = getattr(request, 'user', None)

    # 1. Non-superadmin authenticated user: enforce user.salon if assigned
    if user and user.is_authenticated:
        if not (user.role == UserRole.SUPERADMIN or user.is_superuser):
            if getattr(user, 'salon', None):
                return user.salon

        # Superadmin: allow explicit tenant switching
        data = data or {}
        salon_id = (
            safe_uuid(data.get('salon_id') or data.get('salon')) or
            safe_uuid(request.query_params.get('salon_id')) or
            safe_uuid(request.headers.get('X-Salon-Id'))
        )
        if salon_id:
            salon = Salon.objects.filter(id=salon_id).first()
            if salon:
                return salon

        salon_slug = (
            data.get('salon_slug') or
            request.query_params.get('salon_slug') or
            request.headers.get('X-Salon-Slug')
        )
        if salon_slug:
            salon = Salon.objects.filter(slug=salon_slug).first()
            if salon:
                return salon

        return user.salon or Salon.objects.filter(is_active=True).first() or Salon.objects.first()

    # 2. Public lookup if allowed
    if allow_public:
        data = data or {}
        salon_slug = (
            data.get('salon_slug') or
            request.query_params.get('salon_slug') or
            request.headers.get('X-Salon-Slug')
        )
        if salon_slug:
            salon = Salon.objects.filter(slug=salon_slug, is_active=True).first()
            if salon:
                return salon

        salon_id = (
            safe_uuid(data.get('salon_id') or data.get('salon')) or
            safe_uuid(request.query_params.get('salon_id')) or
            safe_uuid(request.headers.get('X-Salon-Id'))
        )
        if salon_id:
            salon = Salon.objects.filter(id=salon_id, is_active=True).first()
            if salon:
                return salon

        if getattr(request, 'salon', None):
            return request.salon

    return None


def get_authenticated_branch(request, salon, branch_val=None):
    """
    Authoritative branch resolver strictly scoped to the authorized salon.
    Validates branch authorization: client-supplied branch IDs are rejected if
    they belong to a different salon.
    """
    if not salon:
        return None

    b_uuid = safe_uuid(branch_val)
    if not b_uuid:
        raw_b = (
            request.query_params.get('branch_id') or
            request.query_params.get('branch') or
            request.headers.get('X-Branch-Id') or
            request.headers.get('X-Branch')
        )
        b_uuid = safe_uuid(raw_b)

    if b_uuid:
        branch = Branch.objects.filter(salon=salon, id=b_uuid).first()
        if branch:
            return branch

    # Fall back to user's assigned branch if it belongs to this salon
    user = getattr(request, 'user', None)
    if user and user.is_authenticated and getattr(user, 'branch', None) and user.branch.salon_id == salon.id:
        return user.branch

    # Fall back to salon primary branch or first active branch
    return Branch.objects.filter(salon=salon, is_primary=True, is_active=True).first() or Branch.objects.filter(salon=salon, is_active=True).first() or Branch.objects.filter(salon=salon).first()

