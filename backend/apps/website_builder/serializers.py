from rest_framework import serializers
from apps.website_builder.models import (
    Website, WebsiteTheme, WebsitePage, WebsiteSection, WebsiteVersion
)

class WebsiteSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebsiteSection
        fields = [
            'id', 'salon', 'page', 'section_type', 'order',
            'is_enabled', 'content', 'published_content',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'salon', 'created_at', 'updated_at']


class WebsitePageSerializer(serializers.ModelSerializer):
    sections = WebsiteSectionSerializer(many=True, read_only=True)

    class Meta:
        model = WebsitePage
        fields = [
            'id', 'salon', 'website', 'title', 'slug', 'meta_title',
            'meta_description', 'is_active', 'is_home', 'sections',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'salon', 'created_at', 'updated_at']


class WebsiteThemeSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebsiteTheme
        fields = [
            'id', 'salon', 'website', 'primary_color', 'secondary_color',
            'accent_color', 'background_color', 'text_color', 'font_heading',
            'font_body', 'header_style', 'button_border_radius',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'salon', 'created_at', 'updated_at']


class WebsiteSerializer(serializers.ModelSerializer):
    theme = WebsiteThemeSerializer(read_only=True)
    pages = WebsitePageSerializer(many=True, read_only=True)
    salon_name = serializers.ReadOnlyField(source='salon.name')
    salon_slug = serializers.ReadOnlyField(source='salon.slug')

    class Meta:
        model = Website
        fields = [
            'id', 'salon', 'salon_name', 'salon_slug', 'title',
            'meta_description', 'custom_domain', 'is_published',
            'published_at', 'theme', 'pages', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class WebsiteVersionSerializer(serializers.ModelSerializer):
    published_by_name = serializers.ReadOnlyField(source='published_by.get_full_name')

    class Meta:
        model = WebsiteVersion
        fields = [
            'id', 'salon', 'website', 'version_number', 'snapshot',
            'published_by', 'published_by_name', 'is_live', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
