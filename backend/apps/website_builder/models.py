from django.db import models
from django.core.serializers.json import DjangoJSONEncoder
from apps.core.models import TenantModel, Salon

class Website(TenantModel):
    salon = models.OneToOneField(Salon, on_delete=models.CASCADE, related_name='website')
    title = models.CharField(max_length=255, default='Luxury Salon & Spa')
    meta_description = models.TextField(blank=True, default='Experience premier salon and spa treatments tailored to your style.')
    custom_domain = models.CharField(max_length=255, blank=True, null=True, unique=True)
    is_published = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Website for {self.salon.name}"


class WebsiteTheme(TenantModel):
    website = models.OneToOneField(Website, on_delete=models.CASCADE, related_name='theme')
    primary_color = models.CharField(max_length=20, default='#0F5FC2')
    secondary_color = models.CharField(max_length=20, default='#0284C7')
    accent_color = models.CharField(max_length=20, default='#38BDF8')
    background_color = models.CharField(max_length=20, default='#F8FAFC')
    text_color = models.CharField(max_length=20, default='#0F172A')
    font_heading = models.CharField(max_length=50, default='Playfair Display')
    font_body = models.CharField(max_length=50, default='Inter')
    header_style = models.CharField(max_length=30, default='sticky')
    button_border_radius = models.CharField(max_length=20, default='rounded-full')

    def __str__(self):
        return f"Theme for {self.website.salon.name}"


class WebsitePage(TenantModel):
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name='pages')
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150)
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_home = models.BooleanField(default=False)

    class Meta:
        ordering = ['-is_home', 'slug']
        unique_together = ('website', 'slug')

    def __str__(self):
        return f"{self.website.salon.name} - {self.title} (/{self.slug})"


class SectionType(models.TextChoices):
    HERO = 'HERO', 'Hero Banner'
    SERVICES_GRID = 'SERVICES_GRID', 'Services Grid'
    STYLISTS_TEAM = 'STYLISTS_TEAM', 'Stylists Team'
    ABOUT_US = 'ABOUT_US', 'About Us Story'
    GALLERY = 'GALLERY', 'Photo Gallery'
    TESTIMONIALS = 'TESTIMONIALS', 'Client Testimonials'
    SPECIAL_OFFERS = 'SPECIAL_OFFERS', 'Special Offers & Packages'
    FAQ = 'FAQ', 'Frequently Asked Questions'
    CONTACT_MAP = 'CONTACT_MAP', 'Contact & Location Map'
    FOOTER = 'FOOTER', 'Footer'


class WebsiteSection(TenantModel):
    page = models.ForeignKey(WebsitePage, on_delete=models.CASCADE, related_name='sections')
    section_type = models.CharField(max_length=50, choices=SectionType.choices)
    order = models.PositiveIntegerField(default=0)
    is_enabled = models.BooleanField(default=True)
    # Draft content (active editing)
    content = models.JSONField(default=dict)
    # Published content (shown on live public website)
    published_content = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.page.title} - {self.section_type} (Order {self.order})"


class WebsiteVersion(TenantModel):
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField()
    snapshot = models.JSONField(encoder=DjangoJSONEncoder) # Complete snapshot of theme, pages, sections
    published_by = models.ForeignKey('core.User', on_delete=models.SET_NULL, null=True, blank=True)
    is_live = models.BooleanField(default=False)

    class Meta:
        ordering = ['-version_number']

    def __str__(self):
        return f"{self.website.salon.name} v{self.version_number} ({'Live' if self.is_live else 'Archived'})"


class WebsiteMediaAsset(TenantModel):
    file_url = models.CharField(max_length=500)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(default=0)
    mime_type = models.CharField(max_length=100, blank=True)
    section_type = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.original_filename} ({self.salon.name})"
