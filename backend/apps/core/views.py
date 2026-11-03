from rest_framework import viewsets, status, permissions
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.db import transaction
from django.utils.text import slugify
from django.core.cache import cache

from apps.core.models import Salon, Branch, User, StaffProfile, AuditLog, UserRole
from apps.core.serializers import (
    SalonSerializer, BranchSerializer, UserSerializer,
    StaffProfileSerializer, AuditLogSerializer,
    RegisterSerializer, LoginSerializer
)
from apps.tenants.permissions import IsSuperAdmin, IsSalonOwner, IsSalonStaff, IsTenantMember

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    email = data['email'].lower().strip()
    if User.objects.filter(email=email).exists():
        return Response(
            {'error': 'A user with this email address already exists.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    with transaction.atomic():
        role = data.get('role', UserRole.CUSTOMER)
        salon = None
        branch = None

        if role == UserRole.SALON_OWNER:
            salon_name = data.get('salon_name') or f"{data['first_name']}'s Salon"
            raw_slug = data.get('salon_slug') or slugify(salon_name)
            slug = raw_slug
            counter = 1
            while Salon.objects.filter(slug=slug).exists():
                slug = f"{raw_slug}-{counter}"
                counter += 1

            salon = Salon.objects.create(
                name=salon_name,
                slug=slug,
                email=email,
                phone=data.get('phone', ''),
            )
            branch = Branch.objects.create(
                salon=salon,
                name='Main Branch',
                address=salon.address or 'Primary Studio',
                city='Metro',
                is_primary=True,
            )
        elif request.headers.get('X-Salon-Slug'):
            salon = Salon.objects.filter(slug=request.headers.get('X-Salon-Slug')).first()

        user = User.objects.create_user(
            username=email,
            email=email,
            password=data['password'],
            first_name=data['first_name'],
            last_name=data.get('last_name', ''),
            phone=data.get('phone', ''),
            role=role,
            salon=salon,
            branch=branch,
        )

        if role in [UserRole.SALON_OWNER, UserRole.STYLIST, UserRole.SALON_MANAGER] and salon:
            StaffProfile.objects.create(
                salon=salon,
                branch=branch,
                user=user,
                title='Salon Director' if role == UserRole.SALON_OWNER else 'Stylist'
            )

        token, _ = Token.objects.get_or_create(user=user)

        AuditLog.objects.create(
            salon=salon,
            user=user,
            action='USER_REGISTER',
            entity_type='User',
            entity_id=str(user.id),
            details={'email': user.email, 'role': user.role}
        )

        return Response({
            'token': token.key,
            'access': token.key,
            'access_token': token.key,
            'refresh': token.key,
            'refresh_token': token.key,
            'token_type': 'Bearer',
            'user': UserSerializer(user).data,
            'salon': SalonSerializer(salon).data if salon else None,
            'message': 'Account created successfully.'
        }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    raw_email = serializer.validated_data['email']
    email = raw_email.lower().strip()
    password = serializer.validated_data['password']

    user = authenticate(request, username=email, password=password)
    if not user and raw_email != email:
        user = authenticate(request, username=raw_email, password=password)

    if not user:
        # Robust fallback: case-insensitive match on email or username
        user_obj = (
            User.objects.filter(email__iexact=email).first()
            or User.objects.filter(username__iexact=email).first()
            or User.objects.filter(email__iexact=raw_email).first()
            or User.objects.filter(username__iexact=raw_email).first()
        )
        if user_obj and user_obj.check_password(password):
            user = user_obj

    if not user:
        return Response({'error': 'Invalid email or password.'}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
        return Response({'error': 'This account has been deactivated.'}, status=status.HTTP_403_FORBIDDEN)


    token, _ = Token.objects.get_or_create(user=user)

    salon_data = None
    if user.salon:
        salon_data = SalonSerializer(user.salon).data
    elif request.headers.get('X-Salon-Slug'):
        public_salon = Salon.objects.filter(slug=request.headers.get('X-Salon-Slug')).first()
        if public_salon:
            salon_data = SalonSerializer(public_salon).data

    AuditLog.objects.create(
        salon=user.salon,
        user=user,
        action='USER_LOGIN',
        entity_type='User',
        entity_id=str(user.id),
        details={'email': user.email}
    )

    return Response({
        'token': token.key,
        'access': token.key,
        'access_token': token.key,
        'refresh': token.key,
        'refresh_token': token.key,
        'token_type': 'Bearer',
        'user': UserSerializer(user).data,
        'salon': salon_data,
        'message': 'Logged in successfully.'
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def me_view(request):
    user = request.user
    salon_data = SalonSerializer(user.salon).data if user.salon else None
    branch_data = BranchSerializer(user.branch).data if user.branch else None
    return Response({
        'user': UserSerializer(user).data,
        'salon': salon_data,
        'branch': branch_data
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def logout_view(request):
    if hasattr(request.user, 'auth_token'):
        request.user.auth_token.delete()
    return Response({'message': 'Logged out successfully.'})


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def refresh_token_view(request):
    """
    Validates or refreshes an existing authentication token.
    Accepts token via Authorization header (Token/Bearer) or JSON payload: {'token': '...'} or {'refresh': '...'}
    """
    token_str = (
        request.data.get('token')
        or request.data.get('refresh')
        or request.data.get('access')
        or request.data.get('refresh_token')
    )
    if not token_str:
        from rest_framework.authentication import get_authorization_header
        auth = get_authorization_header(request).split()
        if len(auth) >= 2:
            token_str = auth[1].decode(errors='ignore')
        elif request.headers.get('X-Auth-Token'):
            token_str = request.headers.get('X-Auth-Token')

    if not token_str:
        if request.user and request.user.is_authenticated:
            token, _ = Token.objects.get_or_create(user=request.user)
            return Response({
                'token': token.key,
                'access': token.key,
                'access_token': token.key,
                'refresh': token.key,
                'token_type': 'Bearer',
                'user': UserSerializer(request.user).data,
                'message': 'Token refreshed successfully.'
            })
        return Response({'error': 'Token or refresh token is required.'}, status=status.HTTP_400_BAD_REQUEST)

    clean_key = str(token_str).strip().strip('"').strip("'")
    token = Token.objects.filter(key=clean_key).select_related('user').first()
    if not token or not token.user.is_active:
        return Response({'error': 'Invalid or expired token.'}, status=status.HTTP_401_UNAUTHORIZED)

    return Response({
        'token': token.key,
        'access': token.key,
        'access_token': token.key,
        'refresh': token.key,
        'token_type': 'Bearer',
        'user': UserSerializer(token.user).data,
        'message': 'Token refreshed successfully.'
    })


class SalonViewSet(viewsets.ModelViewSet):
    serializer_class = SalonSerializer
    lookup_field = 'slug'

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [IsSalonOwner()]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role == UserRole.SUPERADMIN:
            return Salon.objects.all()
        if user.is_authenticated and user.salon:
            return Salon.objects.filter(id=user.salon.id)
        # Public lookup by slug
        return Salon.objects.filter(is_active=True)


class BranchViewSet(viewsets.ModelViewSet):
    serializer_class = BranchSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [IsSalonOwner()]

    def get_queryset(self):
        user = self.request.user
        salon = getattr(self.request, 'salon', None)
        if user.is_authenticated and user.role == UserRole.SUPERADMIN:
            return Branch.objects.all()
        if user.is_authenticated and user.salon:
            return Branch.objects.filter(salon=user.salon)
        if salon:
            return Branch.objects.filter(salon=salon, is_active=True)
        return Branch.objects.none()

    def perform_create(self, serializer):
        serializer.save(salon=self.request.user.salon)


class StaffProfileViewSet(viewsets.ModelViewSet):
    serializer_class = StaffProfileSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'eligible']:
            return [permissions.AllowAny()]
        return [IsSalonOwner()]

    def get_queryset(self):
        user = self.request.user
        salon = getattr(self.request, 'salon', None)
        if not salon and self.request.query_params.get('salon_slug'):
            salon = Salon.objects.filter(slug=self.request.query_params.get('salon_slug'), is_active=True).first()

        qs = StaffProfile.objects.select_related(
            'user', 'branch', 'salon'
        ).prefetch_related(
            'qualified_categories', 'qualified_services', 'qualified_styles'
        )

        if user.is_authenticated and user.role == UserRole.SUPERADMIN:
            pass
        elif user.is_authenticated and user.salon:
            qs = qs.filter(salon=user.salon)
        elif salon:
            qs = qs.filter(salon=salon, is_bookable=True, user__is_active=True)
        else:
            return StaffProfile.objects.none()

        branch_id = self.request.query_params.get('branch') or self.request.query_params.get('branch_id')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        bookable = self.request.query_params.get('is_bookable')
        if bookable in ['true', '1']:
            qs = qs.filter(is_bookable=True)

        return qs

    def list(self, request, *args, **kwargs):
        salon_id = request.user.salon_id if (request.user.is_authenticated and request.user.salon_id) else 'public'
        qstr = request.META.get('QUERY_STRING', '')
        ckey = f"staff_list_{salon_id}_{qstr}"
        cached = cache.get(ckey)
        if cached is not None:
            return Response(cached)
        res = super().list(request, *args, **kwargs)
        cache.set(ckey, res.data, timeout=120)
        return res

    @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny])
    def eligible(self, request):
        from apps.appointments.services import get_eligible_stylists
        salon = getattr(request, 'salon', None)
        if not salon and request.user.is_authenticated and request.user.salon:
            salon = request.user.salon
        if not salon and request.query_params.get('salon_slug'):
            salon = Salon.objects.filter(slug=request.query_params.get('salon_slug'), is_active=True).first()
        if not salon and request.headers.get('X-Salon-Slug'):
            salon = Salon.objects.filter(slug=request.headers.get('X-Salon-Slug'), is_active=True).first()

        if not salon:
            return Response({'error': 'Salon tenant could not be identified.'}, status=status.HTTP_400_BAD_REQUEST)

        branch_id = request.query_params.get('branch_id') or request.query_params.get('branch')
        branch = Branch.objects.filter(salon=salon, id=branch_id).first() if branch_id else None

        service_id = request.query_params.get('service_id') or request.query_params.get('service')
        style_id = request.query_params.get('style_id') or request.query_params.get('style')
        category_id = request.query_params.get('category_id') or request.query_params.get('category')

        eligible_staff_qs = get_eligible_stylists(
            salon=salon,
            branch=branch,
            category_id=category_id,
            service_id=service_id,
            style_id=style_id
        )

        return Response(StaffProfileSerializer(eligible_staff_qs, many=True).data)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [IsSalonOwner]

    def get_queryset(self):
        user = self.request.user
        if user.role == UserRole.SUPERADMIN:
            return AuditLog.objects.all().select_related('user')
        if user.salon:
            return AuditLog.objects.filter(salon=user.salon).select_related('user')
        return AuditLog.objects.none()
