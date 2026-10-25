from django.contrib import admin
from apps.website_builder.models import (
    Website, WebsiteTheme, WebsitePage, WebsiteSection, WebsiteVersion
)

class WebsiteSectionInline(admin.StackedInline):
    model = WebsiteSection
    extra = 0

@admin.register(Website)
class WebsiteAdmin(admin.ModelAdmin):
    list_display = ('title', 'salon', 'is_published', 'published_at')


@admin.register(WebsiteTheme)
class WebsiteThemeAdmin(admin.ModelAdmin):
    list_display = ('website', 'primary_color', 'secondary_color', 'font_heading')


@admin.register(WebsitePage)
class WebsitePageAdmin(admin.ModelAdmin):
    list_display = ('title', 'website', 'slug', 'is_home', 'is_active')
    inlines = [WebsiteSectionInline]


@admin.register(WebsiteSection)
class WebsiteSectionAdmin(admin.ModelAdmin):
    list_display = ('section_type', 'page', 'order', 'is_enabled')
    list_filter = ('section_type', 'is_enabled')


@admin.register(WebsiteVersion)
class WebsiteVersionAdmin(admin.ModelAdmin):
    list_display = ('website', 'version_number', 'is_live', 'published_by', 'created_at')
