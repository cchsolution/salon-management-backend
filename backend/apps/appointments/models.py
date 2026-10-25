from django.db import models
from apps.core.models import TenantModel, Branch, StaffProfile
from apps.customers.models import Customer
from apps.catalog.models import Service

class AppointmentStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Confirmation'
    CONFIRMED = 'CONFIRMED', 'Confirmed'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'
    NO_SHOW = 'NO_SHOW', 'No Show'


class BookingSource(models.TextChoices):
    ONLINE = 'ONLINE', 'Customer Website'
    WALK_IN = 'WALK_IN', 'Walk-In'
    PHONE = 'PHONE', 'Phone Call'
    APP = 'APP', 'Mobile App'


class Appointment(TenantModel):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='appointments')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='appointments')
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='assigned_appointments')
    date = models.DateField(db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(
        max_length=30,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.CONFIRMED,
        db_index=True
    )
    booking_source = models.CharField(
        max_length=20,
        choices=BookingSource.choices,
        default=BookingSource.ONLINE
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_duration_minutes = models.PositiveIntegerField(default=60)
    notes = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['date', 'start_time']
        indexes = [
            models.Index(fields=['salon', 'branch', 'date']),
            models.Index(fields=['staff', 'date']),
            models.Index(fields=['customer', 'date']),
        ]

    def __str__(self):
        return f"{self.customer.full_name} with {self.staff.user.get_full_name()} on {self.date} at {self.start_time}"


class AppointmentItem(TenantModel):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='items')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='appointment_items')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_minutes = models.PositiveIntegerField(default=60)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.service.name} (${self.price})"


class StylistShift(TenantModel):
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='shifts')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='staff_shifts')
    day_of_week = models.PositiveSmallIntegerField(
        choices=[
            (0, 'Monday'),
            (1, 'Tuesday'),
            (2, 'Wednesday'),
            (3, 'Thursday'),
            (4, 'Friday'),
            (5, 'Saturday'),
            (6, 'Sunday'),
        ]
    )
    start_time = models.TimeField(default='09:00:00')
    end_time = models.TimeField(default='18:00:00')
    is_working = models.BooleanField(default=True)

    class Meta:
        ordering = ['day_of_week', 'start_time']
        unique_together = ('staff', 'branch', 'day_of_week')

    def __str__(self):
        return f"{self.staff.user.get_full_name()} - Day {self.day_of_week} ({self.start_time}-{self.end_time})"


class StylistLeave(TenantModel):
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='leaves')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    is_approved = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.staff.user.get_full_name()} Leave: {self.start_date} to {self.end_date}"
