from django.contrib import admin
from apps.appointments.models import Appointment, AppointmentItem, StylistShift, StylistLeave

class AppointmentItemInline(admin.TabularInline):
    model = AppointmentItem
    extra = 0


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'salon', 'branch', 'customer', 'staff', 'date', 'start_time', 'status', 'total_amount')
    search_fields = ('customer__first_name', 'customer__last_name', 'staff__user__first_name', 'staff__user__last_name')
    list_filter = ('salon', 'branch', 'status', 'date')
    inlines = [AppointmentItemInline]


@admin.register(StylistShift)
class StylistShiftAdmin(admin.ModelAdmin):
    list_display = ('staff', 'salon', 'branch', 'day_of_week', 'start_time', 'end_time', 'is_working')
    list_filter = ('salon', 'branch', 'day_of_week', 'is_working')


@admin.register(StylistLeave)
class StylistLeaveAdmin(admin.ModelAdmin):
    list_display = ('staff', 'salon', 'start_date', 'end_date', 'reason', 'is_approved')
    list_filter = ('salon', 'is_approved')
