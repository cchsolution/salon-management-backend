import sys, os
from decimal import Decimal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'salon_core.settings')
import django
django.setup()

from rest_framework.test import APIClient
from apps.core.models import User, Salon, Branch, StaffProfile
from apps.customers.models import Customer
from apps.catalog.models import Service
from apps.appointments.models import Appointment

print("=" * 60)
print("TESTING PRODUCTION APPOINTMENT BOOKING FIX")
print("=" * 60)

client = APIClient()
user = User.objects.filter(email='owner@ruhibeauty.local').first()
client.force_authenticate(user=user)
print(f"Logged in as: {user.email} (Role: {user.role}, Salon: {user.salon.name})")

# Clean any existing appointments on test dates for a completely clean run
test_date = '2026-11-12'
Appointment.objects.filter(date__in=[test_date, '2026-11-13']).delete()

# 1. Test GET /api/catalog/styles/
print("\n[TEST 1] GET /api/catalog/styles/")
res_styles = client.get('/api/catalog/styles/')
print(f"Status: {res_styles.status_code}")
styles_list = res_styles.data if isinstance(res_styles.data, list) else res_styles.data.get('results', [])
print(f"Found {len(styles_list)} styles. Example: {styles_list[0]['name'] if styles_list else 'None'}")
assert res_styles.status_code == 200, f"Expected 200, got {res_styles.status_code}"

# 2. Test Captured Production Request with OMITTED discount
captured_payload = {
    "branch": "727c22be-9d37-4a1a-bb31-d4ce758fc92f",
    "customer": "be7ba825-d53c-4ee1-98e2-7f6742a88d52",
    "date": test_date,
    "notes": "Test without discount",
    "service_ids": [
        "372661c6-2d8c-4214-a258-4eb1e8aeaaa8"
    ],
    "staff": "33171b3a-5356-4533-ae87-60f81834e20b",
    "start_time": "10:00"
}

print("\n[TEST 2] POST /api/appointments/bookings/ (Discount OMITTED)")
res_book_1 = client.post('/api/appointments/bookings/', captured_payload, format='json')
print(f"Status: {res_book_1.status_code}")
assert res_book_1.status_code == 201, f"Expected 201, got {res_book_1.status_code}: {res_book_1.data}"
appt_data = res_book_1.data
appt_id = appt_data['id']
print(f"Created Appointment ID: {appt_id}")
print(f"Subtotal: {appt_data['subtotal']}")
print(f"Discount Type: {appt_data['discount_type']}")
print(f"Discount Amount: {appt_data['discount_amount']}")
print(f"Total Amount: {appt_data['total_amount']}")
print(f"Status: {appt_data['status']}")

# Verify in DB
db_appt = Appointment.objects.get(id=appt_id)
assert db_appt.discount_amount == Decimal('0.00'), f"Expected 0.00, got {db_appt.discount_amount}"
assert db_appt.subtotal == Decimal('7500.00')
assert db_appt.total_amount == Decimal('7500.00')
print("Database verification passed: discount_amount is 0.00 (NOT NULL satisfied)!")

# 3. Test With Explicit Percentage Discount (Bridal service is 180m, so 10:00-13:00 is taken, start at 13:30)
payload_pct_discount = {
    "branch": "727c22be-9d37-4a1a-bb31-d4ce758fc92f",
    "customer": "be7ba825-d53c-4ee1-98e2-7f6742a88d52",
    "date": test_date,
    "notes": "Test with 10% discount",
    "service_ids": [
        "372661c6-2d8c-4214-a258-4eb1e8aeaaa8"
    ],
    "staff": "33171b3a-5356-4533-ae87-60f81834e20b",
    "start_time": "13:30",
    "discount_type": "PERCENTAGE",
    "discount_value": "10.00"
}

print("\n[TEST 3] POST /api/appointments/bookings/ (10% Discount)")
res_book_2 = client.post('/api/appointments/bookings/', payload_pct_discount, format='json')
print(f"Status: {res_book_2.status_code}")
assert res_book_2.status_code == 201, f"Expected 201, got {res_book_2.status_code}: {res_book_2.data}"
d = res_book_2.data
print(f"Subtotal: {d['subtotal']}, Discount ({d['discount_percentage']}%): {d['discount_amount']}, Total: {d['total_amount']}")
db_appt_2 = Appointment.objects.get(id=d['id'])
expected_disc = (db_appt_2.subtotal * Decimal('0.10')).quantize(Decimal('0.01'))
assert db_appt_2.discount_amount == expected_disc, f"Expected {expected_disc}, got {db_appt_2.discount_amount}"
assert db_appt_2.total_amount == db_appt_2.subtotal - expected_disc
print("10% discount calculation verified correctly!")

# 4. Test With Explicit Fixed Amount Discount (Next day 2026-11-13 at 10:00)
payload_fixed_discount = {
    "branch": "727c22be-9d37-4a1a-bb31-d4ce758fc92f",
    "customer": "be7ba825-d53c-4ee1-98e2-7f6742a88d52",
    "date": "2026-11-13",
    "notes": "Test with Flat 500 discount",
    "service_ids": [
        "372661c6-2d8c-4214-a258-4eb1e8aeaaa8"
    ],
    "staff": "33171b3a-5356-4533-ae87-60f81834e20b",
    "start_time": "10:00",
    "discount_type": "FIXED",
    "discount_amount": "500.00"
}

print("\n[TEST 4] POST /api/appointments/bookings/ (Flat 500 Discount)")
res_book_3 = client.post('/api/appointments/bookings/', payload_fixed_discount, format='json')
print(f"Status: {res_book_3.status_code}")
assert res_book_3.status_code == 201, f"Expected 201, got {res_book_3.status_code}: {res_book_3.data}"
d = res_book_3.data
print(f"Subtotal: {d['subtotal']}, Discount: {d['discount_amount']}, Total: {d['total_amount']}")
db_appt_3 = Appointment.objects.get(id=d['id'])
assert db_appt_3.discount_amount == Decimal('500.00')
assert db_appt_3.total_amount == db_appt_3.subtotal - Decimal('500.00')
print("Fixed amount discount verified correctly!")

# 5. Verify Appointment Appears in List and Calendar
print("\n[TEST 5] Verify Appointment Listing and Calendar")
res_list = client.get(f'/api/appointments/bookings/?date={test_date}')
print(f"List endpoint status: {res_list.status_code}")
items = res_list.data if isinstance(res_list.data, list) else res_list.data.get('results', [])
found_ids = [it['id'] for it in items]
assert appt_id in found_ids, f"Appointment {appt_id} should appear in list"
print(f"Appointment {appt_id} confirmed in appointment list query!")

res_cal = client.get('/api/appointments/calendar/?start_date=2026-11-10&end_date=2026-11-15')
print(f"Calendar endpoint status: {res_cal.status_code}")
events = res_cal.data if isinstance(res_cal.data, list) else res_cal.data.get('events', [])
cal_ids = [ev.get('id') for ev in events]
assert appt_id in cal_ids, f"Appointment {appt_id} should appear in calendar"
print(f"Appointment {appt_id} confirmed in calendar query!")

# 6. Verify Duplicate Submission Guard (Within 30 seconds)
print("\n[TEST 6] Duplicate Booking Guard")
res_dup = client.post('/api/appointments/bookings/', captured_payload, format='json')
print(f"Duplicate call status: {res_dup.status_code}")
assert res_dup.status_code == 200, f"Expected duplicate 200 response, got {res_dup.status_code}"
assert res_dup.data['id'] == appt_id, "Should return existing appointment ID"
print(f"Duplicate intercepted cleanly! Returned original appointment {res_dup.data['id']}.")

print("\nALL PRODUCTION INTEGRATION TESTS PASSED PERFECTLY!")
