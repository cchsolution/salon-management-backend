import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

class Salon(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    tagline = models.CharField(max_length=255, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=50)
    address = models.TextField(blank=True)
    currency = models.CharField(max_length=10, default='INR')
    timezone = models.CharField(max_length=50, default='Asia/Kolkata')
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=18.00) # Percentage (GST)
    logo = models.ImageField(upload_to='salons/logos/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    subscription_plan = models.CharField(
        max_length=50,
        choices=[
            ('STARTER', 'Starter'),
            ('PRO', 'Professional'),
            ('ENTERPRISE', 'Enterprise'),
        ],
        default='PRO'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = _('Salon')
        verbose_name_plural = _('Salons')

    def __str__(self):
        return self.name


class Branch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    salon = models.ForeignKey(Salon, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    opening_time = models.TimeField(default='09:00:00')
    closing_time = models.TimeField(default='20:00:00')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_primary', 'name']
        verbose_name = _('Branch')
        verbose_name_plural = _('Branches')
        unique_together = ('salon', 'name')

    def __str__(self):
        return f"{self.salon.name} - {self.name}"


class TenantModel(models.Model):
    """Abstract base model for strict tenant scoping."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    salon = models.ForeignKey(Salon, on_delete=models.CASCADE, related_name='%(class)ss', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserRole(models.TextChoices):
    SUPERADMIN = 'SUPERADMIN', _('Platform Super Admin')
    SALON_OWNER = 'SALON_OWNER', _('Salon Owner')
    SALON_MANAGER = 'SALON_MANAGER', _('Salon Manager')
    RECEPTIONIST = 'RECEPTIONIST', _('Receptionist')
    STYLIST = 'STYLIST', _('Stylist / Beautician')
    INVENTORY_MANAGER = 'INVENTORY_MANAGER', _('Inventory Manager')
    CUSTOMER = 'CUSTOMER', _('Customer')


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=50, blank=True)
    role = models.CharField(max_length=30, choices=UserRole.choices, default=UserRole.CUSTOMER)
    salon = models.ForeignKey(Salon, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        ordering = ['email']

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"

    @property
    def is_salon_admin(self):
        return self.role in [UserRole.SUPERADMIN, UserRole.SALON_OWNER, UserRole.SALON_MANAGER]

    @property
    def is_salon_staff(self):
        return self.role in [
            UserRole.SUPERADMIN,
            UserRole.SALON_OWNER,
            UserRole.SALON_MANAGER,
            UserRole.RECEPTIONIST,
            UserRole.STYLIST,
            UserRole.INVENTORY_MANAGER,
        ]


class StaffProfile(TenantModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='staff_members')
    title = models.CharField(max_length=100, default='Senior Stylist')
    bio = models.TextField(blank=True)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=15.00) # % commission
    is_bookable = models.BooleanField(default=True)
    color_code = models.CharField(max_length=20, default='#0F5FC2') # Calendar color tag
    employment_start = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['user__first_name', 'user__last_name']
        verbose_name = _('Staff Profile')
        verbose_name_plural = _('Staff Profiles')

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.title}"


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    salon = models.ForeignKey(Salon, on_delete=models.CASCADE, related_name='audit_logs', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_entries')
    action = models.CharField(max_length=100) # e.g., 'CREATE_APPOINTMENT', 'REFUND_INVOICE'
    entity_type = models.CharField(max_length=100) # e.g., 'Appointment', 'Invoice'
    entity_id = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} on {self.entity_type} by {self.user} at {self.created_at}"
