from rest_framework import viewsets, status, permissions
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.db import transaction
from django.utils.text import slugify

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
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [IsSalonOwner()]


    def get_queryset(self):
        user = self.request.user
        salon = getattr(self.request, 'salon', None)
        if user.is_authenticated and user.role == UserRole.SUPERADMIN:
            return StaffProfile.objects.select_related('user', 'branch', 'salon')
        if user.is_authenticated and user.salon:
            return StaffProfile.objects.filter(salon=user.salon).select_related('user', 'branch', 'salon')
        if salon:
            return StaffProfile.objects.filter(salon=salon, is_bookable=True).select_related('user', 'branch', 'salon')
        return StaffProfile.objects.none()


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
