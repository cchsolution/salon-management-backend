import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'salon_core.settings')
import django
django.setup()

from rest_framework.test import APIClient
from apps.core.models import User, Salon, Branch, StaffProfile
from apps.catalog.models import Service, ServiceStyle
from apps.inventory.models import Product, StockLevel

client = APIClient()
user = User.objects.filter(email='owner@ruhibeauty.local').first()
client.force_authenticate(user=user)
salon = user.salon
branch = Branch.objects.filter(salon=salon).first()
svc = Service.objects.filter(salon=salon, is_active=True).first()
staff = StaffProfile.objects.filter(salon=salon, is_bookable=True, user__is_active=True).first()
prod = Product.objects.filter(salon=salon, is_retail=True).first()

print("User:", user.email, "Salon:", salon.name)
print("Service:", svc.name, svc.id)
print("Staff:", staff.user.get_full_name(), staff.id)
print("Branch:", branch.name, branch.id)
print("Product:", prod.name, prod.id)

# TEST 1: POS Creation with frontend payload (item_name only, no product ID)
pos_payload_1 = {
    'branch': str(branch.id),
    'customer': None,
    'discount_amount': 0,
    'notes': 'POS test bill 1',
    'items': [
        {
            'item_type': 'PRODUCT',
            'service': None,
            'item_name': prod.name,
            'quantity': 1,
            'unit_price': float(prod.selling_price),
            'discount_amount': 0
        }
    ]
}
res = client.post('/api/pos/invoices/', pos_payload_1, format='json')
print("\n[POS Test 1] Status:", res.status_code)
if res.status_code >= 400:
    print("Data:", res.data)

# TEST 2: POS Creation with product ID passed
pos_payload_2 = {
    'branch': str(branch.id),
    'customer': None,
    'discount_amount': 0,
    'notes': 'POS test bill 2',
    'items': [
        {
            'item_type': 'PRODUCT',
            'product': str(prod.id),
            'item_name': prod.name,
            'quantity': 1,
            'unit_price': float(prod.selling_price),
            'discount_amount': 0
        }
    ]
}
res2 = client.post('/api/pos/invoices/', pos_payload_2, format='json')
print("\n[POS Test 2] Status:", res2.status_code)
if res2.status_code >= 400:
    print("Data:", res2.data)
else:
    print("Invoice ID:", res2.data.get('id'), "Invoice #:", res2.data.get('invoice_number'))

# TEST 3: POS Payment QR
if res2.status_code == 201:
    inv_id = res2.data.get('id')
    res_qr = client.get(f'/api/pos/invoices/{inv_id}/payment_qr/')
    print("\n[POS Test 3: QR] Status:", res_qr.status_code)

# TEST 4: POS Record Payment
if res2.status_code == 201:
    inv_id = res2.data.get('id')
    res_pay = client.post(f'/api/pos/invoices/{inv_id}/record_payment/', {
        'amount': res2.data.get('total_amount'),
        'payment_method': 'UPI',
        'transaction_reference': 'POS-UPI-123456'
    }, format='json')
    print("\n[POS Test 4: Record Payment] Status:", res_pay.status_code)
    if res_pay.status_code >= 400:
        print("Data:", res_pay.data)

# TEST 5: Appointments with various payloads
# Scenario A: Walk-in (no customer ID, first_name + phone)
appt_payload_a = {
    'branch': str(branch.id),
    'staff': str(staff.id),
    'service_ids': [str(svc.id)],
    'date': '2026-11-06',
    'start_time': '14:00',
    'first_name': 'Walk-in Client',
    'phone': '0000000000'
}
res_a = client.post('/api/appointments/bookings/', appt_payload_a, format='json')
print("\n[Appt Test A: Walk-in] Status:", res_a.status_code)
if res_a.status_code >= 400:
    print("Data:", res_a.data)

# Scenario B: Branch is null/omitted
appt_payload_b = {
    'staff': str(staff.id),
    'service_ids': [str(svc.id)],
    'date': '2026-11-06',
    'start_time': '15:00',
    'first_name': 'Walk-in Client',
    'phone': '0000000000'
}
res_b = client.post('/api/appointments/bookings/', appt_payload_b, format='json')
print("\n[Appt Test B: Branch omitted] Status:", res_b.status_code)
if res_b.status_code >= 400:
    print("Data:", res_b.data)

# Scenario C: Branch is empty string ""
appt_payload_c = {
    'branch': '',
    'staff': str(staff.id),
    'service_ids': [str(svc.id)],
    'date': '2026-11-06',
    'start_time': '16:00',
    'first_name': 'Walk-in Client',
    'phone': '0000000000'
}
res_c = client.post('/api/appointments/bookings/', appt_payload_c, format='json')
print("\n[Appt Test C: Branch empty string] Status:", res_c.status_code)
if res_c.status_code >= 400:
    print("Data:", res_c.data)

# Scenario D: Customer ID is empty string ""
appt_payload_d = {
    'branch': str(branch.id),
    'customer': '',
    'staff': str(staff.id),
    'service_ids': [str(svc.id)],
    'date': '2026-11-06',
    'start_time': '17:00',
    'first_name': 'Walk-in Client',
    'phone': '0000000000'
}
res_d = client.post('/api/appointments/bookings/', appt_payload_d, format='json')
print("\n[Appt Test D: Customer empty string] Status:", res_d.status_code)
if res_d.status_code >= 400:
    print("Data:", res_d.data)

# Scenario E: Staff ID is empty string ""
appt_payload_e = {
    'branch': str(branch.id),
    'staff': '',
    'service_ids': [str(svc.id)],
    'date': '2026-11-06',
    'start_time': '18:00',
    'first_name': 'Walk-in Client',
    'phone': '0000000000'
}
res_e = client.post('/api/appointments/bookings/', appt_payload_e, format='json')
print("\n[Appt Test E: Staff empty string] Status:", res_e.status_code)
if res_e.status_code >= 400:
    print("Data:", res_e.data)

# Scenario F: Style is empty string ""
appt_payload_f = {
    'branch': str(branch.id),
    'staff': str(staff.id),
    'style': '',
    'service_ids': [str(svc.id)],
    'date': '2026-11-06',
    'start_time': '19:00',
    'first_name': 'Walk-in Client',
    'phone': '0000000000'
}
res_f = client.post('/api/appointments/bookings/', appt_payload_f, format='json')
print("\n[Appt Test F: Style empty string] Status:", res_f.status_code)
if res_f.status_code >= 400:
    print("Data:", res_f.data)
