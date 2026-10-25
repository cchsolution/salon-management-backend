import datetime
from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from apps.core.models import Salon, Branch, User, StaffProfile, UserRole
from apps.catalog.models import ServiceCategory, Service
from apps.customers.models import Customer
from apps.appointments.models import Appointment, AppointmentStatus, BookingSource
from apps.appointments.services import check_appointment_conflict
from apps.pos.models import Invoice, InvoiceStatus, InvoiceItem, Payment
from apps.inventory.models import ProductCategory, Product
from apps.website_builder.models import Website, WebsiteTheme, WebsitePage, WebsiteSection, SectionType


class SalonSaaSTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Salon A
        self.salon_a = Salon.objects.create(
            name='Salon Alpha',
            slug='salon-alpha',
            email='alpha@test.com',
            tax_rate=Decimal('10.00')
        )
        self.branch_a = Branch.objects.create(
            salon=self.salon_a,
            name='Alpha Main',
            address='123 Alpha St',
            city='Alpha City',
            is_primary=True
        )
        self.owner_a = User.objects.create_user(
            username='owner_a@test.com',
            email='owner_a@test.com',
            password='password123',
            role=UserRole.SALON_OWNER,
            salon=self.salon_a,
            branch=self.branch_a
        )
        self.staff_a = StaffProfile.objects.create(
            salon=self.salon_a,
            user=self.owner_a,
            title='Lead Stylist',
            is_bookable=True
        )
        self.customer_a = Customer.objects.create(
            salon=self.salon_a,
            first_name='Alice',
            last_name='Alpha',
            phone='1112223333'
        )

        # Salon B (for tenant isolation verification)
        self.salon_b = Salon.objects.create(
            name='Salon Beta',
            slug='salon-beta',
            email='beta@test.com',
            tax_rate=Decimal('5.00')
        )
        self.branch_b = Branch.objects.create(
            salon=self.salon_b,
            name='Beta Main',
            address='456 Beta Ave',
            city='Beta City',
            is_primary=True
        )
        self.owner_b = User.objects.create_user(
            username='owner_b@test.com',
            email='owner_b@test.com',
            password='password123',
            role=UserRole.SALON_OWNER,
            salon=self.salon_b,
            branch=self.branch_b
        )
        self.customer_b = Customer.objects.create(
            salon=self.salon_b,
            first_name='Bob',
            last_name='Beta',
            phone='4445556666'
        )

        # Service for Salon A
        self.service_a = Service.objects.create(
            salon=self.salon_a,
            name='Alpha Cut',
            slug='alpha-cut',
            price=Decimal('50.00'),
            duration_minutes=60
        )
        self.service_a.qualified_staff.add(self.staff_a)

    def test_tenant_data_isolation(self):
        """Owner A must never see Salon B's customers or records."""
        self.client.force_authenticate(user=self.owner_a)
        response = self.client.get('/api/crm/clients/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        client_ids = [c['id'] for c in response.data.get('results', response.data)]
        self.assertIn(str(self.customer_a.id), client_ids)
        self.assertNotIn(str(self.customer_b.id), client_ids)

    def test_double_booking_prevention(self):
        """Overlapping appointment booking must be rejected with 409 conflict."""
        today = datetime.date.today() + datetime.timedelta(days=1)
        start_time = datetime.time(10, 0)
        end_time = datetime.time(11, 0)

        # Existing appointment
        Appointment.objects.create(
            salon=self.salon_a,
            branch=self.branch_a,
            customer=self.customer_a,
            staff=self.staff_a,
            date=today,
            start_time=start_time,
            end_time=end_time,
            status=AppointmentStatus.CONFIRMED,
            total_amount=Decimal('50.00')
        )

        # Direct service conflict check
        self.assertTrue(check_appointment_conflict(self.staff_a, today, datetime.time(10, 30), datetime.time(11, 30)))
        self.assertFalse(check_appointment_conflict(self.staff_a, today, datetime.time(11, 0), datetime.time(12, 0)))

        # API conflict test
        self.client.force_authenticate(user=self.owner_a)
        payload = {
            'branch': str(self.branch_a.id),
            'staff': str(self.staff_a.id),
            'customer': str(self.customer_a.id),
            'service_ids': [str(self.service_a.id)],
            'date': today.isoformat(),
            'start_time': '10:30',
        }
        res = self.client.post('/api/appointments/bookings/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_invoice_creation_and_payment_math(self):
        """Invoice calculation with tax and payment settlement."""
        self.client.force_authenticate(user=self.owner_a)
        payload = {
            'branch': str(self.branch_a.id),
            'customer': str(self.customer_a.id),
            'items': [
                {
                    'item_name': 'Alpha Cut',
                    'service': str(self.service_a.id),
                    'quantity': 1,
                    'unit_price': '50.00',
                    'discount_amount': '0.00'
                }
            ]
        }
        res = self.client.post('/api/pos/invoices/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        invoice_id = res.data['id']
        total = Decimal(str(res.data['total_amount']))
        
        # Subtotal 50 + 10% tax (5) = 55.00
        self.assertEqual(total, Decimal('55.00'))

        # Record full payment
        pay_res = self.client.post(f'/api/pos/invoices/{invoice_id}/record_payment/', {
            'amount': '55.00',
            'payment_method': 'CARD'
        }, format='json')
        self.assertEqual(pay_res.status_code, status.HTTP_200_OK)
        self.assertEqual(pay_res.data['status'], InvoiceStatus.PAID)
        self.assertEqual(Decimal(str(pay_res.data['paid_amount'])), Decimal('55.00'))

    def test_website_builder_draft_and_publish(self):
        """Draft changes must not appear on public storefront until published."""
        self.client.force_authenticate(user=self.owner_a)
        
        # 1. Fetch current website builder setup
        res = self.client.get('/api/builder/site/current/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        page_id = res.data['pages'][0]['id']

        # 2. Create draft section
        sec_res = self.client.post('/api/builder/sections/', {
            'page': page_id,
            'section_type': SectionType.HERO,
            'order': 0,
            'content': {'headline': 'Unpublished Draft Headline'}
        }, format='json')
        self.assertEqual(sec_res.status_code, status.HTTP_201_CREATED)

        # 3. Public storefront before publishing
        pub_res_before = self.client.get(f'/api/builder/public/{self.salon_a.slug}/')
        self.assertEqual(pub_res_before.status_code, status.HTTP_200_OK)
        sections = pub_res_before.data['website']['pages'][0]['sections']
        hero_sec = [s for s in sections if s['section_type'] == SectionType.HERO][0]
        # published_content is still empty dict
        self.assertEqual(hero_sec['content'], {})

        # 4. Trigger Publish
        publish_res = self.client.post('/api/builder/site/publish/')
        self.assertEqual(publish_res.status_code, status.HTTP_200_OK)

        # 5. Public storefront after publishing
        pub_res_after = self.client.get(f'/api/builder/public/{self.salon_a.slug}/')
        sections_after = pub_res_after.data['website']['pages'][0]['sections']
        hero_after = [s for s in sections_after if s['section_type'] == SectionType.HERO][0]
        self.assertEqual(hero_after['content']['headline'], 'Unpublished Draft Headline')


class RoleBasedAccessControlTestCase(TestCase):
    """
    Comprehensive Security and RBAC Test Suite verifying:
    - Salon Owner full management capabilities
    - Hair Stylist strict restrictions and assigned customer access
    - Receptionist front-desk capabilities and restricted admin denial
    - Multi-tenant object-level isolation (Owner A vs Owner B, Stylist A vs Salon B)
    - Unauthenticated 401 and unauthorized 403 status codes
    - Seed demo user authentication and token issuance
    """
    def setUp(self):
        self.client = APIClient()

        # 1. Superadmin User
        self.superadmin = User.objects.create_user(
            username='admin@luxesalon.local',
            email='admin@luxesalon.local',
            password='Admin@123',
            role=UserRole.SUPERADMIN,
            is_staff=True,
            is_superuser=True
        )

        # 2. Salon A (Ruhi Beauty Salon)
        self.salon_a = Salon.objects.create(
            name='Ruhi Beauty Salon',
            slug='ruhi-beauty-salon',
            email='owner@ruhibeauty.local',
            tax_rate=Decimal('18.00'),
            is_active=True
        )
        self.branch_a = Branch.objects.create(
            salon=self.salon_a,
            name='Himmatnagar Studio',
            address='Shivalik Complex',
            city='Himmatnagar',
            is_primary=True
        )

        # Salon A Owner
        self.owner_a = User.objects.create_user(
            username='owner@ruhibeauty.local',
            email='owner@ruhibeauty.local',
            password='Owner@123',
            role=UserRole.SALON_OWNER,
            salon=self.salon_a,
            branch=self.branch_a
        )

        # Salon A Stylist
        self.stylist_user_a = User.objects.create_user(
            username='ayesha@ruhibeauty.local',
            email='ayesha@ruhibeauty.local',
            password='Stylist@123',
            role=UserRole.STYLIST,
            salon=self.salon_a,
            branch=self.branch_a
        )
        self.stylist_profile_a = StaffProfile.objects.create(
            salon=self.salon_a,
            user=self.stylist_user_a,
            branch=self.branch_a,
            title='Master Hair Stylist',
            is_bookable=True
        )

        # Salon A Receptionist
        self.receptionist_a = User.objects.create_user(
            username='reception@ruhibeauty.local',
            email='reception@ruhibeauty.local',
            password='Staff@123',
            role=UserRole.RECEPTIONIST,
            salon=self.salon_a,
            branch=self.branch_a
        )

        # Salon A Customer
        self.customer_a = Customer.objects.create(
            salon=self.salon_a,
            first_name='Pooja',
            last_name='Patel',
            phone='+91 99000 11111'
        )

        # Salon A Service
        self.service_a = Service.objects.create(
            salon=self.salon_a,
            name='Signature Hair Cut',
            slug='signature-hair-cut',
            price=Decimal('500.00'),
            duration_minutes=45
        )
        self.service_a.qualified_staff.add(self.stylist_profile_a)

        # Salon A Appointment assigned to stylist_a
        self.appointment_a = Appointment.objects.create(
            salon=self.salon_a,
            branch=self.branch_a,
            customer=self.customer_a,
            staff=self.stylist_profile_a,
            date=datetime.date.today(),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(10, 45),
            status=AppointmentStatus.CONFIRMED,
            total_amount=Decimal('500.00')
        )

        # Salon A Product & Category
        self.cat_a = ProductCategory.objects.create(
            salon=self.salon_a,
            name='Hair Care'
        )
        self.product_a = Product.objects.create(
            salon=self.salon_a,
            category=self.cat_a,
            name='Moroccanoil Treatment',
            sku='OIL-001',
            selling_price=Decimal('1800.00')
        )

        # Salon A Invoice
        self.invoice_a = Invoice.objects.create(
            salon=self.salon_a,
            branch=self.branch_a,
            customer=self.customer_a,
            invoice_number='INV-2026-0001',
            total_amount=Decimal('500.00'),
            paid_amount=Decimal('500.00'),
            status=InvoiceStatus.PAID
        )

        # Salon A Website
        self.website_a = Website.objects.create(
            salon=self.salon_a,
            title='Ruhi Beauty Official Site',
            is_published=True
        )

        # 3. Salon B (Tenant Isolation verification)
        self.salon_b = Salon.objects.create(
            name='Bliss Unisex Salon',
            slug='bliss-unisex-salon',
            email='owner@bliss.local',
            tax_rate=Decimal('18.00'),
            is_active=True
        )
        self.branch_b = Branch.objects.create(
            salon=self.salon_b,
            name='Bliss Studio',
            address='Ring Road',
            city='Surat',
            is_primary=True
        )
        self.owner_b = User.objects.create_user(
            username='owner@bliss.local',
            email='owner@bliss.local',
            password='Owner@123',
            role=UserRole.SALON_OWNER,
            salon=self.salon_b,
            branch=self.branch_b
        )
        self.customer_b = Customer.objects.create(
            salon=self.salon_b,
            first_name='Rahul',
            last_name='Mehta',
            phone='+91 99000 22222'
        )
        self.staff_profile_b = StaffProfile.objects.create(
            salon=self.salon_b,
            user=self.owner_b,
            branch=self.branch_b,
            title='Salon B Director',
            is_bookable=True
        )
        self.invoice_b = Invoice.objects.create(
            salon=self.salon_b,
            branch=self.branch_b,
            customer=self.customer_b,
            invoice_number='INV-2026-9999',
            total_amount=Decimal('1200.00'),
            paid_amount=Decimal('1200.00'),
            status=InvoiceStatus.PAID
        )
        self.appointment_b = Appointment.objects.create(
            salon=self.salon_b,
            branch=self.branch_b,
            customer=self.customer_b,
            staff=self.staff_profile_b,
            date=datetime.date.today(),
            start_time=datetime.time(14, 0),
            end_time=datetime.time(15, 0),
            status=AppointmentStatus.CONFIRMED,
            total_amount=Decimal('1200.00')
        )


    # --- 1. SALON OWNER PERMISSIONS ---
    def test_owner_can_access_owner_apis(self):
        """Salon Owner should have full access to management APIs for their salon."""
        self.client.force_authenticate(user=self.owner_a)

        # Website Builder
        res = self.client.get('/api/builder/site/current/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        res_alias = self.client.get('/api/website-builder/site/current/')
        self.assertEqual(res_alias.status_code, status.HTTP_200_OK)

        # Reports & Analytics
        res_metrics = self.client.get('/api/analytics/metrics/')
        self.assertEqual(res_metrics.status_code, status.HTTP_200_OK)

        res_reports = self.client.get('/api/reports/metrics/')
        self.assertEqual(res_reports.status_code, status.HTTP_200_OK)

        # Inventory
        res_inv = self.client.get('/api/inventory/products/')
        self.assertEqual(res_inv.status_code, status.HTTP_200_OK)

        # Orders / Sales / Invoices
        res_invc = self.client.get('/api/pos/invoices/')
        self.assertEqual(res_invc.status_code, status.HTTP_200_OK)

        # Customers & Appointments
        res_crm = self.client.get('/api/crm/clients/')
        self.assertEqual(res_crm.status_code, status.HTTP_200_OK)

        res_appts = self.client.get('/api/appointments/bookings/')
        self.assertEqual(res_appts.status_code, status.HTTP_200_OK)

        # Staff
        res_staff = self.client.get('/api/staff/')
        self.assertEqual(res_staff.status_code, status.HTTP_200_OK)

    # --- 2. HAIR STYLIST PERMISSION RESTRICTIONS ---
    def test_stylist_cannot_access_website_builder(self):
        """Hair Stylist must receive HTTP 403 for Website Builder APIs."""
        self.client.force_authenticate(user=self.stylist_user_a)

        res = self.client.get('/api/builder/site/current/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        res_alias = self.client.get('/api/website-builder/site/current/')
        self.assertEqual(res_alias.status_code, status.HTTP_403_FORBIDDEN)

        res_theme = self.client.get('/api/builder/theme/')
        self.assertEqual(res_theme.status_code, status.HTTP_403_FORBIDDEN)

        res_sec = self.client.get('/api/builder/sections/')
        self.assertEqual(res_sec.status_code, status.HTTP_403_FORBIDDEN)

    def test_stylist_cannot_access_reports_and_analytics(self):
        """Hair Stylist must receive HTTP 403 for Reports and Analytics."""
        self.client.force_authenticate(user=self.stylist_user_a)

        res_m = self.client.get('/api/analytics/metrics/')
        self.assertEqual(res_m.status_code, status.HTTP_403_FORBIDDEN)

        res_r = self.client.get('/api/reports/metrics/')
        self.assertEqual(res_r.status_code, status.HTTP_403_FORBIDDEN)

        res_exp = self.client.get('/api/analytics/export/')
        self.assertEqual(res_exp.status_code, status.HTTP_403_FORBIDDEN)

    def test_stylist_cannot_access_inventory_and_pos(self):
        """Hair Stylist must receive HTTP 403 for Inventory administration, POS, and Staff modification."""
        self.client.force_authenticate(user=self.stylist_user_a)

        # Inventory
        res_inv = self.client.get('/api/inventory/products/')
        self.assertEqual(res_inv.status_code, status.HTTP_403_FORBIDDEN)

        res_cats = self.client.get('/api/inventory/product-categories/')
        self.assertEqual(res_cats.status_code, status.HTTP_403_FORBIDDEN)

        # POS / Invoices / Financial data
        res_pos = self.client.get('/api/pos/invoices/')
        self.assertEqual(res_pos.status_code, status.HTTP_403_FORBIDDEN)

        res_exp = self.client.get('/api/pos/expenses/')
        self.assertEqual(res_exp.status_code, status.HTTP_403_FORBIDDEN)

        res_cash = self.client.get('/api/pos/cash-registers/')
        self.assertEqual(res_cash.status_code, status.HTTP_403_FORBIDDEN)

        # Staff administration
        res_staff_create = self.client.post('/api/staff/', {
            'title': 'Unauthorized Hire',
            'commission_rate': '30.00'
        }, format='json')
        self.assertEqual(res_staff_create.status_code, status.HTTP_403_FORBIDDEN)

    # --- 3. RECEPTIONIST PERMISSION RESTRICTIONS & GRANTS ---
    def test_receptionist_cannot_access_website_builder(self):
        """Receptionist must receive HTTP 403 for Website Builder APIs."""
        self.client.force_authenticate(user=self.receptionist_a)

        res = self.client.get('/api/builder/site/current/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        res_alias = self.client.get('/api/website-builder/site/current/')
        self.assertEqual(res_alias.status_code, status.HTTP_403_FORBIDDEN)

    def test_receptionist_cannot_access_reports_and_analytics(self):
        """Receptionist must receive HTTP 403 for Reports and Analytics APIs."""
        self.client.force_authenticate(user=self.receptionist_a)

        res_m = self.client.get('/api/analytics/metrics/')
        self.assertEqual(res_m.status_code, status.HTTP_403_FORBIDDEN)

        res_r = self.client.get('/api/reports/metrics/')
        self.assertEqual(res_r.status_code, status.HTTP_403_FORBIDDEN)

        res_exp = self.client.get('/api/analytics/export/')
        self.assertEqual(res_exp.status_code, status.HTTP_403_FORBIDDEN)

    def test_receptionist_allowed_front_desk_and_denied_admin(self):
        """Receptionist has front-desk booking/pos access, but is denied administrative/inventory APIs."""
        self.client.force_authenticate(user=self.receptionist_a)

        # Allowed Front Desk APIs
        res_appts = self.client.get('/api/appointments/bookings/')
        self.assertEqual(res_appts.status_code, status.HTTP_200_OK)

        res_crm = self.client.get('/api/crm/clients/')
        self.assertEqual(res_crm.status_code, status.HTTP_200_OK)

        res_invoices = self.client.get('/api/pos/invoices/')
        self.assertEqual(res_invoices.status_code, status.HTTP_200_OK)

        res_cash = self.client.get('/api/pos/cash-registers/')
        self.assertEqual(res_cash.status_code, status.HTTP_200_OK)

        res_services = self.client.get('/api/catalog/services/')
        self.assertEqual(res_services.status_code, status.HTTP_200_OK)

        # Denied Administrative APIs
        res_inv = self.client.get('/api/inventory/products/')
        self.assertEqual(res_inv.status_code, status.HTTP_403_FORBIDDEN)

        res_exp = self.client.get('/api/pos/expenses/')
        self.assertEqual(res_exp.status_code, status.HTTP_403_FORBIDDEN)

        res_staff_create = self.client.post('/api/staff/', {
            'title': 'Receptionist Hires Stylist'
        }, format='json')
        self.assertEqual(res_staff_create.status_code, status.HTTP_403_FORBIDDEN)

    # --- 4. MULTI-TENANCY & OBJECT-LEVEL SECURITY ---
    def test_stylist_cannot_access_another_salon_customer(self):
        """Stylist from Salon A must never be able to access Salon B's customer."""
        self.client.force_authenticate(user=self.stylist_user_a)

        # Direct retrieval by ID must return 404 (hidden) or 403
        res = self.client.get(f'/api/crm/clients/{self.customer_b.id}/')
        self.assertIn(res.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

        res_alias = self.client.get(f'/api/customers/clients/{self.customer_b.id}/')
        self.assertIn(res_alias.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

        # Listing must not leak customer B
        list_res = self.client.get('/api/crm/clients/')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        ids = [c['id'] for c in list_res.data.get('results', list_res.data)]
        self.assertNotIn(str(self.customer_b.id), ids)

    def test_receptionist_cannot_access_another_salon_data(self):
        """Receptionist from Salon A must never access Salon B's customer, invoice, or appointment."""
        self.client.force_authenticate(user=self.receptionist_a)

        # Cross-salon Customer
        res_c = self.client.get(f'/api/crm/clients/{self.customer_b.id}/')
        self.assertIn(res_c.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

        # Cross-salon Invoice
        res_i = self.client.get(f'/api/pos/invoices/{self.invoice_b.id}/')
        self.assertIn(res_i.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

        # Cross-salon Appointment
        res_a = self.client.get(f'/api/appointments/bookings/{self.appointment_b.id}/')
        self.assertIn(res_a.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

    def test_owner_cannot_access_another_salon_data(self):
        """Owner of Salon A must never access Salon B's records."""
        self.client.force_authenticate(user=self.owner_a)

        # Cross-salon Customer
        res_c = self.client.get(f'/api/crm/clients/{self.customer_b.id}/')
        self.assertIn(res_c.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

        # Cross-salon Invoice
        res_i = self.client.get(f'/api/pos/invoices/{self.invoice_b.id}/')
        self.assertIn(res_i.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

        # Cross-salon Appointment
        res_a = self.client.get(f'/api/appointments/bookings/{self.appointment_b.id}/')
        self.assertIn(res_a.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

    # --- 5. UNAUTHENTICATED REQUESTS RETURN 401 ---
    def test_unauthenticated_requests_return_401(self):
        """Unauthenticated requests to protected endpoints must return HTTP 401."""
        self.client.force_authenticate(user=None)

        endpoints = [
            '/api/builder/site/current/',
            '/api/analytics/metrics/',
            '/api/inventory/products/',
            '/api/pos/invoices/',
            '/api/crm/clients/',
            '/api/audit-logs/',
        ]
        for url in endpoints:
            res = self.client.get(url)
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED, f"Expected 401 for {url}, got {res.status_code}")

    # --- 6. AUTH RESPONSE & DEMO USERS CONTINUITY ---
    def test_demo_users_login_and_auth_response(self):
        """Demo credentials must authenticate successfully and return role & salon without exposing passwords."""
        demo_accounts = [
            ('owner@ruhibeauty.local', 'Owner@123', UserRole.SALON_OWNER),
            ('ayesha@ruhibeauty.local', 'Stylist@123', UserRole.STYLIST),
            ('reception@ruhibeauty.local', 'Staff@123', UserRole.RECEPTIONIST),
            ('admin@luxesalon.local', 'Admin@123', UserRole.SUPERADMIN),
        ]

        for email, password, expected_role in demo_accounts:
            res = self.client.post('/api/auth/login/', {
                'email': email,
                'password': password
            }, format='json')

            self.assertEqual(res.status_code, status.HTTP_200_OK, f"Login failed for {email}: {res.data}")
            self.assertIn('token', res.data)
            self.assertIn('user', res.data)
            user_data = res.data['user']
            self.assertEqual(user_data['email'], email)
            self.assertEqual(user_data['role'], expected_role)
            self.assertIn('permissions', user_data)
            self.assertIsInstance(user_data['permissions'], list)

            # Security: Ensure password is never in response
            self.assertNotIn('password', user_data)
            self.assertNotIn('password', res.data)

