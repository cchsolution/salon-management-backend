import os
import re
import uuid
import json
from pathlib import Path
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.db import transaction
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from apps.website_builder.models import (
    Website, WebsiteTheme, WebsitePage, WebsiteSection, WebsiteVersion,
    WebsiteMediaAsset, SectionType
)
from apps.website_builder.serializers import (
    WebsiteSerializer, WebsiteThemeSerializer, WebsitePageSerializer,
    WebsiteSectionSerializer, WebsiteVersionSerializer
)
from apps.core.models import Salon, Branch, StaffProfile, UserRole
from apps.core.serializers import SalonSerializer, BranchSerializer, StaffProfileSerializer
from apps.catalog.models import Service, ServiceCategory
from apps.catalog.serializers import ServiceSerializer, ServiceCategorySerializer
from apps.tenants.permissions import IsSalonOwner


def get_default_section_schema(section_type, salon_name=None):
    """
    Returns the professional canonical default content schema for each section type,
    localized for the Indian salon market.
    """
    name = salon_name or "Ruhi Beauty Salon"
    
    if section_type == SectionType.HERO:
        return {
            'badge_text': 'Top Rated Luxury Salon in Gujarat 2026',
            'headline': f'Elevate Your Elegance at {name}',
            'subheadline': 'Where artistry meets luxury hair styling, radiant bridal transformations, and rejuvenating spa rituals in Himmatnagar & Ahmedabad.',
            'cta_text': 'Book Your Appointment',
            'cta_link': '#booking',
            'secondary_cta_text': 'Explore Services',
            'secondary_cta_link': '#services',
            'background_image': '',  # Empty indicates system default image
            'overlay_enabled': True,
            'overlay_color': '#0F091E',
            'overlay_opacity': 65,
            'text_alignment': 'center',
            'hero_height': 'large',
            'primary_button_bg': '#6D28D9',
            'primary_button_text': '#FFFFFF',
            'primary_button_border': '#7C3AED',
            'primary_button_radius': 'rounded-xl',
            'secondary_button_bg': 'transparent',
            'secondary_button_text': '#FFFFFF',
            'secondary_button_border': '#FFFFFF',
            'secondary_button_radius': 'rounded-xl',
            'heading_color': '#FFFFFF',
            'description_color': '#F1F5F9',
            'badge_color': '#10B981',
        }
    elif section_type == SectionType.ABOUT_US:
        return {
            'title': f'The Philosophy of {name}',
            'subtitle': 'Founded with Passion & Care',
            'story': 'We believe every woman deserves personalized beauty care in a serene, hygienic, and luxurious environment. Our collective of certified hair stylists, aesthetic specialists, and bridal artists combine authentic botanical treatments with modern techniques to curate a bespoke experience just for you.',
            'main_image': '',
            'secondary_image': '',
            'experience_number': '12+',
            'experience_text': 'Years of Excellence in Hair & Bridal Care',
            'stats': [
                {'label': 'Delighted Guests', 'value': '15,000+'},
                {'label': 'Expert Specialists', 'value': '6 Artists'},
                {'label': 'Five-Star Reviews', 'value': '99%'},
            ],
            'feature_points': [
                'Certified Master Stylists & International Colorists',
                'Medical-grade sanitization for all scissors, brushes & tools',
                'Exclusive private bridal dressing suite with dedicated lounge',
                '100% genuine dermatological & organic herbal blends',
            ],
            'cta_text': 'Discover Our Story & Team',
            'cta_link': '#team',
        }
    elif section_type == SectionType.SERVICES_GRID:
        return {
            'heading': 'Signature Treatments & Services',
            'subheading': 'Crafted with premium dermatological and hair-nourishing botanicals in Indian Rupees.',
            'grid_columns': 3,
            'max_services': 12,
            'show_prices': True,
            'show_duration': True,
            'show_description': True,
            'filter_by_category': True,
            'show_booking_button': True,
            'booking_button_text': 'Book Service',
            'card_style': 'elevated',
        }
    elif section_type == SectionType.STYLISTS_TEAM:
        return {
            'heading': 'Meet Our Expert Stylists & Artists',
            'subheading': 'Certified master hair colorists, beauticians, and bridal makeup specialists.',
            'show_bio': True,
            'show_social_links': True,
            'members_override': []
        }
    elif section_type == SectionType.GALLERY:
        return {
            'heading': 'Salon Portfolio & Bridal Transformations',
            'subheading': 'Real client results from our Himmatnagar and Ahmedabad studios.',
            'grid_columns': 4,
            'aspect_ratio': 'square',
            'images': []
        }
    elif section_type == SectionType.TESTIMONIALS:
        return {
            'heading': 'Loved by Our Guests',
            'subheading': f'Read verified reviews from clients who trust {name}.',
            'testimonials': [
                {
                    'client': 'Ayesha Sheikh',
                    'role': 'Bridal Client, Ahmedabad',
                    'quote': 'Ruhi and her team did my bridal makeup and hair styling for my wedding. Absolutely magical experience and lasted the entire day through all rituals!',
                    'rating': 5,
                    'avatar': ''
                },
                {
                    'client': 'Neha Patel',
                    'role': 'Entrepreneur, Himmatnagar',
                    'quote': 'Best hair spa and keratin treatment in Himmatnagar. Incredibly polite staff, clean salon, and reasonable prices.',
                    'rating': 5,
                    'avatar': ''
                },
                {
                    'client': 'Zoya Patel',
                    'role': 'College Student, Himmatnagar',
                    'quote': 'Always a wonderful experience for facials and waxing. Super hygienic salon and such a calm, peaceful ambience.',
                    'rating': 5,
                    'avatar': ''
                }
            ]
        }
    elif section_type == SectionType.FAQ:
        return {
            'heading': 'Frequently Asked Questions',
            'subheading': 'Everything you need to know about booking, visits, and hygiene.',
            'faqs': [
                {'question': 'How far in advance should I book bridal makeup?', 'answer': 'We recommend booking 3-4 weeks in advance for bridal and wedding packages, although date consultations are available anytime.'},
                {'question': 'What are your hygiene and sanitization standards?', 'answer': 'We maintain strict medical-grade sterilization for all tools and single-use consumables for threading, waxing, and facials.'},
                {'question': 'Can I select my preferred stylist for an appointment?', 'answer': 'Yes! You can choose your preferred stylist directly during online booking or when calling our desk.'},
                {'question': 'Can I reschedule or cancel my appointment?', 'answer': 'Appointments can be easily rescheduled up to 3 hours prior to the slot either online or via WhatsApp.'},
                {'question': 'Do you accept walk-ins without prior booking?', 'answer': 'Walk-ins are warmly welcomed subject to stylist availability; we recommend booking in advance on weekends.'}
            ]
        }
    elif section_type == SectionType.CONTACT_MAP:
        return {
            'heading': 'Visit Our Studios',
            'subheading': 'Conveniently located in Himmatnagar and Ahmedabad with ample customer parking.',
            'address_downtown': 'Shop 4-5, Shivalik Complex, Motipura, Himmatnagar, Gujarat 383001',
            'phone_downtown': '+91 98250 12345',
            'whatsapp_number': '+91 98250 12345',
            'email': 'care@ruhibeauty.com',
            'hours': 'Monday – Sunday: 9:00 AM – 8:00 PM',
            'map_embed_url': 'https://maps.google.com',
            'show_whatsapp_button': True,
            'whatsapp_button_text': 'Chat on WhatsApp',
            'show_booking_button': True,
            'booking_button_text': 'Book Studio Visit'
        }
    elif section_type == SectionType.FOOTER:
        return {
            'salon_name': name,
            'tagline': 'Luxury Hair Styling, Bridal Transformations & Herbal Facials in Gujarat.',
            'address': 'Shop 4-5, Shivalik Complex, Motipura, Himmatnagar, Gujarat 383001',
            'phone': '+91 98250 12345',
            'email': 'care@ruhibeauty.com',
            'copyright': f'© {timezone.now().year} {name}. All rights reserved.',
            'show_social_links': True,
            'show_quick_links': True,
            'social_links': {
                'instagram': 'https://instagram.com/ruhibeautysalon',
                'facebook': 'https://facebook.com/ruhibeautysalon',
                'whatsapp': 'https://wa.me/919825012345',
                'youtube': 'https://youtube.com/@ruhibeautysalon'
            }
        }
    return {}


def resolve_builder_salon(request):
    user = request.user
    salon = getattr(user, 'salon', None) or getattr(request, 'salon', None)
    if not salon and (getattr(user, 'role', None) == UserRole.SUPERADMIN or getattr(user, 'is_superuser', False)):
        salon_id = request.query_params.get('salon_id')
        if salon_id:
            salon = Salon.objects.filter(id=salon_id).first()
        if not salon:
            salon_slug = request.headers.get('X-Salon-Slug')
            if salon_slug:
                salon = Salon.objects.filter(slug=salon_slug).first()
        if not salon:
            salon = Salon.objects.filter(is_active=True).first() or Salon.objects.first()
    return salon


class WebsiteViewSet(viewsets.ModelViewSet):
    serializer_class = WebsiteSerializer
    permission_classes = [IsSalonOwner]

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return Website.objects.none()
        qs = Website.objects.select_related('salon', 'theme').prefetch_related('pages__sections')
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            salon = resolve_builder_salon(self.request)
            if salon:
                return qs.filter(salon=salon)
            return qs
        if user.salon:
            return qs.filter(salon=user.salon)
        return Website.objects.none()

    @action(detail=False, methods=['get'])
    def current(self, request):
        """Returns the current salon's website with theme and draft sections for the builder."""
        salon = resolve_builder_salon(request)
        if not salon:
            return Response({'error': 'No salon associated with this user.'}, status=status.HTTP_400_BAD_REQUEST)

        website, _ = Website.objects.get_or_create(
            salon=salon,
            defaults={'title': f"{salon.name} Official Website"}
        )
        WebsiteTheme.objects.get_or_create(website=website, salon=salon)

        # Ensure home page exists
        home_page, _ = WebsitePage.objects.get_or_create(
            website=website,
            salon=salon,
            slug='home',
            defaults={'title': 'Home', 'is_home': True}
        )

        # Seed canonical sections if explicitly requested on empty pages
        if request.query_params.get('seed') == 'true' and not home_page.sections.exists():
            canonical_sections = [
                SectionType.HERO,
                SectionType.ABOUT_US,
                SectionType.SERVICES_GRID,
                SectionType.STYLISTS_TEAM,
                SectionType.GALLERY,
                SectionType.TESTIMONIALS,
                SectionType.FAQ,
                SectionType.CONTACT_MAP,
                SectionType.FOOTER,
            ]
            new_sections = []
            for order, stype in enumerate(canonical_sections):
                schema = get_default_section_schema(stype, salon.name)
                new_sections.append(
                    WebsiteSection(
                        salon=salon,
                        page=home_page,
                        section_type=stype,
                        order=order,
                        is_enabled=True,
                        content=schema,
                        published_content={}
                    )
                )
            WebsiteSection.objects.bulk_create(new_sections)

        website = Website.objects.select_related('salon', 'theme').prefetch_related(
            'pages__sections'
        ).get(id=website.id)

        return Response(WebsiteSerializer(website).data)

    @action(detail=False, methods=['post'])
    def publish(self, request):
        """Publishes all current draft section contents to the live storefront."""
        salon = resolve_builder_salon(request)
        if not salon:
            return Response({'error': 'No salon associated with this user.'}, status=status.HTTP_400_BAD_REQUEST)

        website = Website.objects.filter(salon=salon).first()
        if not website:
            return Response({'error': 'Website not found.'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            sections = WebsiteSection.objects.filter(salon=salon)
            for sec in sections:
                sec.published_content = sec.content
                sec.save(update_fields=['published_content'])

            website.is_published = True
            website.published_at = timezone.now()
            website.save(update_fields=['is_published', 'published_at'])

            latest_version = WebsiteVersion.objects.filter(website=website).first()
            new_version_num = (latest_version.version_number + 1) if latest_version else 1

            WebsiteVersion.objects.filter(website=website).update(is_live=False)
            WebsiteVersion.objects.create(
                salon=salon,
                website=website,
                version_number=new_version_num,
                snapshot=json.loads(json.dumps(WebsiteSerializer(website).data, cls=DjangoJSONEncoder)),
                published_by=request.user,
                is_live=True
            )

        return Response({
            'message': f'Website published successfully as version {new_version_num}!',
            'website': WebsiteSerializer(website).data
        })


@api_view(['POST'])
@permission_classes([IsSalonOwner])
@parser_classes([MultiPartParser, FormParser])
def upload_website_image_view(request):
    """
    Handles local image uploads for website sections.
    Validates file extension (jpg, jpeg, png, webp) and size (<= 10MB).
    Stores locally in Django MEDIA_ROOT/website_uploads/<salon_slug>/
    Returns the media URL for use in sections without base64 or external paid hosting.
    """
    salon = request.user.salon
    if not salon:
        return Response({'error': 'No salon associated with this user.'}, status=status.HTTP_400_BAD_REQUEST)

    file_obj = request.FILES.get('image') or request.FILES.get('file')
    if not file_obj:
        return Response({'error': 'No image file provided.'}, status=status.HTTP_400_BAD_REQUEST)

    # Validate file extension
    ext = os.path.splitext(file_obj.name)[1].lower()
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.webp']
    if ext not in allowed_extensions:
        return Response({
            'error': f'Invalid file format "{ext}". Allowed formats are JPG, JPEG, PNG, WEBP.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Validate file size (10 MB = 10 * 1024 * 1024 bytes)
    max_size_bytes = 10 * 1024 * 1024
    if file_obj.size > max_size_bytes:
        return Response({
            'error': 'Image size must be less than 10 MB.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Clean filename
    clean_stem = re.sub(r'[^a-zA-Z0-9_\-]', '', os.path.splitext(file_obj.name)[0])[:30]
    unique_filename = f"{uuid.uuid4().hex[:10]}_{clean_stem}{ext}"

    # Target directory under MEDIA_ROOT
    upload_dir = Path(settings.MEDIA_ROOT) / 'website_uploads' / salon.slug
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination_path = upload_dir / unique_filename

    # Save to disk
    with open(destination_path, 'wb+') as destination:
        for chunk in file_obj.chunks():
            destination.write(chunk)

    # Media URL path
    relative_url = f"/media/website_uploads/{salon.slug}/{unique_filename}"

    # Record in WebsiteMediaAsset
    asset = WebsiteMediaAsset.objects.create(
        salon=salon,
        file_url=relative_url,
        original_filename=file_obj.name,
        file_size=file_obj.size,
        mime_type=file_obj.content_type or 'image/jpeg',
        section_type=request.data.get('section_type', '')
    )

    return Response({
        'success': True,
        'url': relative_url,
        'filename': file_obj.name,
        'size': file_obj.size,
        'id': str(asset.id),
        'message': 'Image uploaded successfully.'
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def public_storefront_view(request, salon_slug):
    """
    Public dynamic rendering endpoint for /s/:salon_slug storefront.
    Returns published pages, sections, theme, services, staff, branches.
    """
    salon = Salon.objects.filter(slug=salon_slug, is_active=True).first()
    if not salon:
        return Response({'error': f"Salon '{salon_slug}' was not found."}, status=status.HTTP_404_NOT_FOUND)

    website = Website.objects.filter(salon=salon).first()
    theme = getattr(website, 'theme', None) if website else None

    # Fetch published sections
    pages_data = []
    if website:
        for page in website.pages.filter(is_active=True):
            sections = page.sections.filter(is_enabled=True).order_by('order')
            sections_data = []
            for sec in sections:
                sections_data.append({
                    'id': str(sec.id),
                    'section_type': sec.section_type,
                    'order': sec.order,
                    'content': sec.published_content if sec.published_content else {}
                })
            pages_data.append({
                'id': str(page.id),
                'title': page.title,
                'slug': page.slug,
                'is_home': page.is_home,
                'sections': sections_data
            })

    services = Service.objects.filter(salon=salon, is_active=True).select_related('category')
    categories = ServiceCategory.objects.filter(salon=salon, is_active=True)
    staff = StaffProfile.objects.filter(salon=salon, is_bookable=True).select_related('user')
    branches = Branch.objects.filter(salon=salon, is_active=True)

    return Response({
        'salon': SalonSerializer(salon).data,
        'website': {
            'title': website.title if website else salon.name,
            'meta_description': website.meta_description if website else '',
            'is_published': bool(website and website.is_published),
            'theme': WebsiteThemeSerializer(theme).data if theme else None,
            'pages': pages_data
        },
        'catalog': {
            'services': ServiceSerializer(services, many=True).data,
            'categories': ServiceCategorySerializer(categories, many=True).data
        },
        'team': StaffProfileSerializer(staff, many=True).data,
        'branches': BranchSerializer(branches, many=True).data
    })


class WebsiteThemeViewSet(viewsets.ModelViewSet):
    serializer_class = WebsiteThemeSerializer
    permission_classes = [IsSalonOwner]
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return WebsiteTheme.objects.none()
        salon = resolve_builder_salon(self.request)
        if salon:
            return WebsiteTheme.objects.filter(salon=salon).select_related('salon', 'website')
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return WebsiteTheme.objects.all().select_related('salon', 'website')
        return WebsiteTheme.objects.none()


class WebsiteSectionViewSet(viewsets.ModelViewSet):
    serializer_class = WebsiteSectionSerializer
    permission_classes = [IsSalonOwner]
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        if not (user and user.is_authenticated):
            return WebsiteSection.objects.none()
        salon = resolve_builder_salon(self.request)
        if salon:
            return WebsiteSection.objects.filter(salon=salon).select_related('salon', 'page').order_by('order')
        if user.role == UserRole.SUPERADMIN or user.is_superuser:
            return WebsiteSection.objects.all().select_related('salon', 'page').order_by('order')
        return WebsiteSection.objects.none()

    def perform_create(self, serializer):
        salon = resolve_builder_salon(self.request)
        serializer.save(salon=salon)

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        """Accepts an array of { id, order } and updates section ordering."""
        order_list = request.data.get('orders', [])
        salon = resolve_builder_salon(request)
        with transaction.atomic():
            for item in order_list:
                WebsiteSection.objects.filter(salon=salon, id=item['id']).update(order=item['order'])
        return Response({'message': 'Sections reordered successfully.'})

    @action(detail=True, methods=['post'])
    def reset_default(self, request, pk=None):
        """Resets the section's draft content back to canonical default content."""
        section = self.get_object()
        salon = resolve_builder_salon(request) or section.salon
        default_content = get_default_section_schema(section.section_type, salon.name if salon else None)
        section.content = default_content
        section.save(update_fields=['content', 'updated_at'])
        return Response({
            'message': f'{section.get_section_type_display()} has been reset to default.',
            'section': WebsiteSectionSerializer(section).data
        })

