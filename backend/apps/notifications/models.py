from django.db import models
from apps.core.models import TenantModel, User

class InAppNotification(TenantModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=30,
        choices=[
            ('BOOKING', 'Appointment Alert'),
            ('LOW_STOCK', 'Low Stock Warning'),
            ('PAYMENT', 'Payment Notice'),
            ('SYSTEM', 'System Update'),
        ],
        default='BOOKING'
    )
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.title} ({'Read' if self.is_read else 'Unread'})"
