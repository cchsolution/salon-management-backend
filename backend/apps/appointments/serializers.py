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

    class Meta:
        model = AppointmentItem
        fields = ['id', 'service', 'service_name', 'price', 'duration_minutes']
        read_only_fields = ['id']


class AppointmentSerializer(serializers.ModelSerializer):
    items = AppointmentItemSerializer(many=True, read_only=True)
    customer_details = CustomerSerializer(source='customer', read_only=True)
    staff_details = StaffProfileSerializer(source='staff', read_only=True)
    branch_details = BranchSerializer(source='branch', read_only=True)
    salon_name = serializers.ReadOnlyField(source='salon.name')

    class Meta:
        model = Appointment
        fields = [
            'id', 'salon', 'salon_name', 'branch', 'branch_details',
            'customer', 'customer_details', 'staff', 'staff_details',
            'date', 'start_time', 'end_time', 'status', 'booking_source',
            'total_amount', 'total_duration_minutes', 'notes',
            'cancellation_reason', 'items', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


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
