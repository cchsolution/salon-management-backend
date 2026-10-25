import datetime
from django.db import models
from apps.core.models import TenantModel
from apps.customers.models import Customer
from apps.catalog.models import Service

class ServicePackage(TenantModel):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    original_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    validity_days = models.PositiveIntegerField(default=90)
    included_services = models.ManyToManyField(Service, related_name='packages')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (${self.price})"


class CustomerPackage(TenantModel):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='purchased_packages')
    package = models.ForeignKey(ServicePackage, on_delete=models.CASCADE)
    purchase_date = models.DateField(default=datetime.date.today)
    expiry_date = models.DateField()
    total_credits = models.PositiveIntegerField(default=5)
    remaining_credits = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-purchase_date']

    def __str__(self):
        return f"{self.customer.full_name} - {self.package.name} ({self.remaining_credits} credits left)"


class MembershipTier(models.TextChoices):
    SILVER = 'SILVER', 'Silver Tier'
    GOLD = 'GOLD', 'Gold Tier'
    PLATINUM = 'PLATINUM', 'Platinum Tier'
    VIP = 'VIP', 'VIP Black Tier'


class MembershipPlan(TenantModel):
    name = models.CharField(max_length=150)
    tier = models.CharField(max_length=20, choices=MembershipTier.choices, default=MembershipTier.SILVER)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    billing_cycle = models.CharField(max_length=20, choices=[('MONTHLY', 'Monthly'), ('YEARLY', 'Yearly')], default='MONTHLY')
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    free_services_count = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['price']

    def __str__(self):
        return f"{self.name} ({self.tier}) - ${self.price}/{self.billing_cycle}"


class CustomerMembership(TenantModel):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='memberships')
    plan = models.ForeignKey(MembershipPlan, on_delete=models.CASCADE)
    start_date = models.DateField(default=datetime.date.today)
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.customer.full_name} - {self.plan.name}"


class Coupon(TenantModel):
    code = models.CharField(max_length=50, db_index=True)
    description = models.TextField(blank=True)
    discount_type = models.CharField(max_length=20, choices=[('PERCENTAGE', 'Percentage (%)'), ('FIXED', 'Fixed ($)')], default='PERCENTAGE')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_spend = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    valid_from = models.DateField(default=datetime.date.today)
    valid_to = models.DateField()
    usage_limit = models.PositiveIntegerField(default=100)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-valid_to']
        unique_together = ('salon', 'code')

    def __str__(self):
        return f"{self.code}: {self.discount_value}{'%' if self.discount_type == 'PERCENTAGE' else '$'}"
