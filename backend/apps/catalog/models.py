from django.db import models
from django.utils.text import slugify
from apps.core.models import TenantModel, Branch, StaffProfile

class ServiceCategory(TenantModel):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    qualified_staff = models.ManyToManyField(StaffProfile, blank=True, related_name='qualified_categories')

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Service Category'
        verbose_name_plural = 'Service Categories'
        unique_together = ('salon', 'slug')

    def __str__(self):
        return f"{self.salon.name} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Service(TenantModel):
    category = models.ForeignKey(ServiceCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='services')
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    buffer_time_minutes = models.PositiveIntegerField(default=10)
    image = models.ImageField(upload_to='services/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    tax_exempt = models.BooleanField(default=False)
    branches = models.ManyToManyField(Branch, blank=True, related_name='available_services')
    qualified_staff = models.ManyToManyField(StaffProfile, blank=True, related_name='qualified_services')

    class Meta:
        ordering = ['name']
        unique_together = ('salon', 'slug')

    def __str__(self):
        return f"{self.name} (₹{self.price}, {self.duration_minutes}m)"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def effective_price(self):
        if self.discount_price and self.discount_price > 0:
            return self.discount_price
        return self.price


class ServiceStyle(TenantModel):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='styles')
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    image = models.ImageField(upload_to='styles/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    qualified_staff = models.ManyToManyField(StaffProfile, blank=True, related_name='qualified_styles')

    class Meta:
        ordering = ['sort_order', 'name']
        unique_together = ('service', 'name')
        verbose_name = 'Service Style'
        verbose_name_plural = 'Service Styles'

    def __str__(self):
        return f"{self.service.name} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        if not self.salon_id and self.service_id:
            self.salon_id = self.service.salon_id
        super().save(*args, **kwargs)

    @property
    def effective_price(self):
        if self.price is not None and self.price >= 0:
            return self.price
        return self.service.effective_price

    @property
    def effective_duration(self):
        if self.duration_minutes is not None and self.duration_minutes > 0:
            return self.duration_minutes
        return self.service.duration_minutes


class Resource(TenantModel):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='resources')
    name = models.CharField(max_length=150)
    resource_type = models.CharField(
        max_length=50,
        choices=[
            ('CHAIR', 'Styling Chair'),
            ('ROOM', 'Spa Treatment Room'),
            ('WASH', 'Shampoo Basin'),
            ('NAIL', 'Manicure Station'),
        ],
        default='CHAIR'
    )
    capacity = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.branch.name} - {self.name} ({self.resource_type})"
