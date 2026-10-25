from django.db import models
from apps.core.models import TenantModel, User

class Customer(TenantModel):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_profile')
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50)
    gender = models.CharField(
        max_length=20,
        choices=[('FEMALE', 'Female'), ('MALE', 'Male'), ('OTHER', 'Other'), ('UNDISCLOSED', 'Prefer not to say')],
        default='UNDISCLOSED'
    )
    birth_date = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True) # Confidential stylist/salon notes
    preferences = models.JSONField(default=dict, blank=True) # e.g. {'preferred_stylist': 'Sarah', 'allergies': 'Bleach sensitive'}
    tags = models.JSONField(default=list, blank=True) # e.g. ['VIP', 'Color Specialist', 'Frequent']
    loyalty_points = models.PositiveIntegerField(default=0)
    total_spend = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    visit_count = models.PositiveIntegerField(default=0)
    last_visit = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-last_visit', 'first_name']
        unique_together = ('salon', 'phone')

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.phone})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class CustomerActivity(TenantModel):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(
        max_length=50,
        choices=[
            ('BOOKING', 'Appointment Booked'),
            ('CHECKIN', 'Customer Checked In'),
            ('COMPLETED', 'Appointment Completed'),
            ('CANCELLED', 'Appointment Cancelled'),
            ('PURCHASE', 'Product / Service Purchase'),
            ('NOTE', 'Staff Note Added'),
            ('POINTS', 'Loyalty Points Transacted'),
        ]
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.customer.full_name}: {self.title}"
