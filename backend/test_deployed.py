import urllib.request
import urllib.parse
import json

BASE_URL = 'https://salon-management-backend-7xj0qfafq.vercel.app/api'

def req(url, method='GET', data=None, headers=None):
    headers = headers or {}
    encoded_data = None
    if data is not None:
        encoded_data = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    
    req_obj = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req_obj) as resp:
            body = resp.read().decode('utf-8')
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        return e.code, body
    except Exception as e:
        return 0, str(e)

# 1. Login
status, body = req(f"{BASE_URL}/auth/login/", method='POST', data={
    'email': 'owner@ruhibeauty.local',
    'password': 'Owner@123'
})
print("Login status:", status)
login_data = json.loads(body)
token = login_data.get('token')
print("Token:", token[:15] if token else "No token")

headers = {
    'Authorization': f"Bearer {token}",
    'X-Salon-Slug': 'ruhi-beauty-salon'
}

# 2. Get me
status, body = req(f"{BASE_URL}/auth/me/", headers=headers)
print("\n/auth/me/ status:", status)

# 3. Test POS retail products
status, body = req(f"{BASE_URL}/pos/invoices/retail_products/", headers=headers)
print("\nGET /pos/invoices/retail_products/ status:", status)
print("POS retail products body:", body[:200])

# 4. Test POS invoice creation
status, body = req(f"{BASE_URL}/pos/invoices/", method='POST', headers=headers, data={
    'discount_amount': 0,
    'notes': 'Test pos from deployed script',
    'items': [
        {
            'item_type': 'PRODUCT',
            'item_name': 'Kérastase Elixir Ultime Hair Oil (100ml)',
            'quantity': 1,
            'unit_price': 1200.0,
            'discount_amount': 0
        }
    ]
})
print("\nPOST /pos/invoices/ status:", status)
print("POS invoice response:", body[:300])

# 5. Test Appointment available slots
status, body = req(f"{BASE_URL}/appointments/bookings/available_slots/?date=2026-11-05&duration=30", headers=headers)
print("\nGET /appointments/bookings/available_slots/ status:", status)
print("Slots response:", body[:200])

# 6. Test Appointment creation
status, body = req(f"{BASE_URL}/catalog/services/", headers=headers)
svc_list = json.loads(body) if status == 200 else []
status, body = req(f"{BASE_URL}/catalog/staff/", headers=headers)
staff_list = json.loads(body) if status == 200 else []

svc_id = (svc_list[0]['id'] if isinstance(svc_list, list) and len(svc_list) > 0 else (svc_list.get('results', [{}])[0].get('id') if isinstance(svc_list, dict) else None))
staff_id = (staff_list[0]['id'] if isinstance(staff_list, list) and len(staff_list) > 0 else (staff_list.get('results', [{}])[0].get('id') if isinstance(staff_list, dict) else None))

print(f"\nUsing svc_id={svc_id}, staff_id={staff_id}")

status, body = req(f"{BASE_URL}/appointments/bookings/", method='POST', headers=headers, data={
    'staff': staff_id,
    'service_ids': [svc_id],
    'date': '2026-11-05',
    'start_time': '10:00',
    'notes': 'Deployed test booking',
    'first_name': 'Walk-in Client',
    'phone': '0000000000'
})
print("\nPOST /appointments/bookings/ status:", status)
print("Appt create response:", body[:300])
