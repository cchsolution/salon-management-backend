from rest_framework import serializers
from apps.appointments.models import (
    Appointment, AppointmentItem, StylistShift, StylistLeave,
    AppointmentStatus, BookingSource
)
from apps.customers.serializers import CustomerSerializer
from apps.core.serializers import StaffProfileSerializer, BranchSerializer
from apps.catalog.models import Service

class AppointmentItemSerializer(serializers.ModelSerializer):
    service_name = serializers.ReadOnlyField(source='service.name')
    style_name = serializers.ReadOnlyField(source='style.name')

    class Meta:
        model = AppointmentItem
        fields = [
            'id', 'service', 'service_name', 'style', 'style_name',
            'price', 'discount_amount', 'duration_minutes'
        ]
        read_only_fields = ['id']


class AppointmentSerializer(serializers.ModelSerializer):
    items = AppointmentItemSerializer(many=True, read_only=True)
    customer_details = CustomerSerializer(source='customer', read_only=True)
    staff_details = StaffProfileSerializer(source='staff', read_only=True)
    branch_details = BranchSerializer(source='branch', read_only=True)
    salon_name = serializers.ReadOnlyField(source='salon.name')
    currency = serializers.ReadOnlyField(source='salon.currency', default='INR')
    currency_symbol = serializers.SerializerMethodField()
    services_summary = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            'id', 'salon', 'salon_name', 'branch', 'branch_details',
            'customer', 'customer_details', 'staff', 'staff_details',
            'date', 'start_time', 'end_time', 'status', 'booking_source',
            'subtotal', 'discount_type', 'discount_percentage', 'discount_amount',
            'total_amount', 'total_duration_minutes', 'currency', 'currency_symbol',
            'services_summary', 'notes', 'cancellation_reason', 'items',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_currency_symbol(self, obj):
        return '₹' if (getattr(obj.salon, 'currency', 'INR') == 'INR') else '$'

    def get_services_summary(self, obj):
        items = obj.items.all()
        if not items:
            return ""
        parts = []
        for it in items:
            p = it.service.name if it.service else "Service"
            if it.style:
                p += f" ({it.style.name})"
            parts.append(p)
        return ", ".join(parts)


class StylistShiftSerializer(serializers.ModelSerializer):
    staff_name = serializers.ReadOnlyField(source='staff.user.get_full_name')

    class Meta:
        model = StylistShift
        fields = [
            'id', 'salon', 'staff', 'staff_name', 'branch', 'day_of_week',
            'start_time', 'end_time', 'is_working', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class StylistLeaveSerializer(serializers.ModelSerializer):
    staff_name = serializers.ReadOnlyField(source='staff.user.get_full_name')

    class Meta:
        model = StylistLeave
        fields = [
            'id', 'salon', 'staff', 'staff_name', 'start_date', 'end_date',
            'reason', 'is_approved', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
