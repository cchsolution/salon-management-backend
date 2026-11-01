import datetime
from decimal import Decimal
import zoneinfo
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.core.models import Salon, Branch, User, StaffProfile, UserRole
from apps.catalog.models import ServiceCategory, Service, ServiceStyle
from apps.customers.models import Customer
from apps.appointments.models import Appointment, AppointmentStatus, BookingSource, StylistLeave, StylistShift
from apps.appointments.services import (
    get_salon_timezone, get_current_salon_datetime, get_available_slots,
    check_appointment_conflict, get_eligible_stylists, validate_appointment_booking
)
from apps.notifications.models import InAppNotification
from apps.pos.models import Invoice, InvoiceStatus, PaymentMethod
from apps.pos.payment_service import PaymentGatewayProvider
from apps.pos.pdf_service import generate_invoice_pdf
from apps.inventory.models import ProductCategory, Product, StockLevel, StockMovement, StockMovementType


class ComprehensiveSalonSaasWorkflowTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Salon A
        self.salon_a = Salon.objects.create(
            name='Royal Elegance Salon',
            slug='royal-elegance',
            email='care@royalelegance.com',
            currency='INR',
            timezone='Asia/Kolkata',
            tax_rate=Decimal('18.00'),
            is_active=True
        )
        self.branch_a = Branch.objects.create(
            salon=self.salon_a,
            name='Primary Studio',
            address='101 Luxury Mall',
            city='Ahmedabad',
            is_primary=True,
            opening_time=datetime.time(9, 0),
            closing_time=datetime.time(20, 0)
        )
        self.owner_a = User.objects.create_user(
            username='owner@royalelegance.com',
            email='owner@royalelegance.com',
            password='OwnerPassword123!',
            first_name='Royal',
            last_name='Owner',
            role=UserRole.SALON_OWNER,
            salon=self.salon_a,
            branch=self.branch_a
        )
        self.stylist_user_1 = User.objects.create_user(
            username='stylist1@royalelegance.com',
            email='stylist1@royalelegance.com',
            password='StylistPassword123!',
            first_name='Pooja',
            last_name='Sharma',
            role=UserRole.STYLIST,
            salon=self.salon_a,
            branch=self.branch_a
        )
        self.stylist_profile_1 = StaffProfile.objects.create(
            salon=self.salon_a,
            user=self.stylist_user_1,
            branch=self.branch_a,
            title='Senior Hair Artist',
            is_bookable=True
        )
        self.stylist_user_2 = User.objects.create_user(
            username='stylist2@royalelegance.com',
            email='stylist2@royalelegance.com',
            password='StylistPassword123!',
            first_name='Ayesha',
            last_name='Khan',
            role=UserRole.STYLIST,
            salon=self.salon_a,
            branch=self.branch_a
        )
        self.stylist_profile_2 = StaffProfile.objects.create(
            salon=self.salon_a,
            user=self.stylist_user_2,
            branch=self.branch_a,
            title='Bridal & Mehendi Artist',
            is_bookable=True
        )

        # Dynamic Catalog Hierarchy
        self.cat_hair = ServiceCategory.objects.create(
            salon=self.salon_a,
            name='Hair Care & Styling',
            slug='hair-care-styling'
        )
        self.cat_bridal = ServiceCategory.objects.create(
            salon=self.salon_a,
            name='Bridal Studio',
            slug='bridal-studio'
        )

        self.service_haircut = Service.objects.create(
            salon=self.salon_a,
            category=self.cat_hair,
            name='Designer Haircut',
            slug='designer-haircut',
            price=Decimal('800.00'),
            duration_minutes=45
        )
        self.service_haircut.qualified_staff.add(self.stylist_profile_1)

        self.style_layered = ServiceStyle.objects.create(
            salon=self.salon_a,
            service=self.service_haircut,
            name='Advanced Layered Cut',
            price=Decimal('950.00'),
            duration_minutes=50
        )
        self.style_layered.qualified_staff.add(self.stylist_profile_1)

        self.service_mehendi = Service.objects.create(
            salon=self.salon_a,
            category=self.cat_bridal,
            name='Bridal Mehendi',
            slug='bridal-mehendi',
            price=Decimal('4000.00'),
            duration_minutes=180
        )
        self.service_mehendi.qualified_staff.add(self.stylist_profile_2)

        # Customer in Salon A
        self.customer_a = Customer.objects.create(
            salon=self.salon_a,
            first_name='Rhea',
            last_name='Kapoor',
            phone='+91 98765 43210',
            email='rhea@example.com'
        )

        # Salon B for Isolation
        self.salon_b = Salon.objects.create(
            name='Bella Studio',
            slug='bella-studio',
            email='bella@studio.com',
            currency='INR',
            timezone='Asia/Kolkata',
            tax_rate=Decimal('18.00'),
            is_active=True
        )
        self.branch_b = Branch.objects.create(
            salon=self.salon_b,
            name='Bella Branch',
            city='Vadodara',
            is_primary=True
        )
        self.customer_b = Customer.objects.create(
            salon=self.salon_b,
            first_name='Diya',
            last_name='Patel',
            phone='+91 98989 89898'
        )

        # Retail Product in Salon A
        self.prod_cat = ProductCategory.objects.create(
            salon=self.salon_a,
            name='Hair Serums'
        )
        self.retail_product = Product.objects.create(
            salon=self.salon_a,
            category=self.prod_cat,
            name='Argan Hair Serum 100ml',
            sku='SERUM-ARG-100',
            selling_price=Decimal('1200.00'),
            is_retail=True,
            is_active=True
        )
        self.stock_level = StockLevel.objects.create(
            salon=self.salon_a,
            branch=self.branch_a,
            product=self.retail_product,
            quantity_on_hand=10,
            reorder_level=2
        )

        # Internal consumable (non-retail) product
        self.internal_product = Product.objects.create(
            salon=self.salon_a,
            category=self.prod_cat,
            name='Salon Developer 1000ml',
            sku='DEV-1000',
            selling_price=Decimal('600.00'),
            is_retail=False,
            is_active=True
        )

    # 1. Customer Search & Isolation
    def test_customer_search_and_isolation(self):
        self.client.force_authenticate(user=self.owner_a)

        # Search by phone
        res_phone = self.client.get('/api/customers/?phone=98765')
        self.assertEqual(res_phone.status_code, status.HTTP_200_OK)
        results = res_phone.data.get('results', res_phone.data)
        self.assertTrue(any(c['phone'] == '+91 98765 43210' for c in results))

        # Search by name
        res_name = self.client.get('/api/customers/?name=Rhea')
        self.assertEqual(res_name.status_code, status.HTTP_200_OK)
        results = res_name.data.get('results', res_name.data)
        self.assertTrue(any(c['first_name'] == 'Rhea' for c in results))

        # Isolation: Salon B's customer must never appear
        res_all = self.client.get('/api/customers/')
        ids = [c['id'] for c in res_all.data.get('results', res_all.data)]
        self.assertIn(str(self.customer_a.id), ids)
        self.assertNotIn(str(self.customer_b.id), ids)

    # 2. Dynamic Hierarchy: Salon -> Category -> Service -> Style
    def test_dynamic_service_category_and_style_hierarchy(self):
        # Category services endpoint
        res_cat_services = self.client.get(f'/api/catalog/categories/{self.cat_hair.id}/services/')
        self.assertEqual(res_cat_services.status_code, status.HTTP_200_OK)
        services = res_cat_services.data
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0]['name'], 'Designer Haircut')

        # Service styles endpoint
        res_serv_styles = self.client.get(f'/api/catalog/services/{self.service_haircut.id}/styles/')
        self.assertEqual(res_serv_styles.status_code, status.HTTP_200_OK)
        styles = res_serv_styles.data
        self.assertEqual(len(styles), 1)
        self.assertEqual(styles[0]['name'], 'Advanced Layered Cut')
        self.assertEqual(Decimal(str(styles[0]['price'])), Decimal('950.00'))

    # 3. Stylist Eligibility
    def test_stylist_eligibility_mapping(self):
        # Eligible stylists for haircut: should include stylist 1, exclude stylist 2
        res_hair = self.client.get(f'/api/appointments/eligible-stylists/?service_id={self.service_haircut.id}&salon_slug={self.salon_a.slug}')
        self.assertEqual(res_hair.status_code, status.HTTP_200_OK)
        stylist_ids = [s['id'] for s in res_hair.data]
        self.assertIn(str(self.stylist_profile_1.id), stylist_ids)
        self.assertNotIn(str(self.stylist_profile_2.id), stylist_ids)

        # Eligible stylists for mehendi: should include stylist 2, exclude stylist 1
        res_mehendi = self.client.get(f'/api/appointments/eligible-stylists/?service_id={self.service_mehendi.id}&salon_slug={self.salon_a.slug}')
        self.assertEqual(res_mehendi.status_code, status.HTTP_200_OK)
        stylist_ids = [s['id'] for s in res_mehendi.data]
        self.assertIn(str(self.stylist_profile_2.id), stylist_ids)
        self.assertNotIn(str(self.stylist_profile_1.id), stylist_ids)

    # 4. Past Date & Past Time Rejection
    def test_past_booking_rejections(self):
        self.client.force_authenticate(user=self.owner_a)
        tz = get_salon_timezone(self.salon_a)
        now_salon = timezone.now().astimezone(tz)
        yesterday = (now_salon - datetime.timedelta(days=1)).date()

        # Past Date Rejection
        payload_past_date = {
            'branch': str(self.branch_a.id),
            'staff': str(self.stylist_profile_1.id),
            'customer': str(self.customer_a.id),
            'service_id': str(self.service_haircut.id),
            'date': yesterday.isoformat(),
            'start_time': '11:00'
        }
        res_past = self.client.post('/api/appointments/', payload_past_date, format='json')
        self.assertEqual(res_past.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('past', res_past.data['error'].lower())

        # Past Time Slots for Today in available_slots
        slots = get_available_slots(self.salon_a, self.branch_a, self.stylist_profile_1, now_salon.date(), duration_minutes=45)
        for slot_time_str in slots:
            slot_t = datetime.time.fromisoformat(slot_time_str)
            self.assertGreater(slot_t, now_salon.time())

    # 5. Overlapping Appointment & Double Booking Rejection
    def test_same_stylist_conflict_rejection(self):
        future_date = (timezone.now() + datetime.timedelta(days=2)).date()

        # Existing appointment from 10:00 to 11:00
        Appointment.objects.create(
            salon=self.salon_a,
            branch=self.branch_a,
            customer=self.customer_a,
            staff=self.stylist_profile_1,
            date=future_date,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            status=AppointmentStatus.CONFIRMED,
            total_amount=Decimal('800.00'),
            total_duration_minutes=60
        )

        # Attempt to book overlapping time 10:30 - 11:15
        self.client.force_authenticate(user=self.owner_a)
        payload = {
            'branch': str(self.branch_a.id),
            'staff': str(self.stylist_profile_1.id),
            'customer': str(self.customer_a.id),
            'service_id': str(self.service_haircut.id),
            'date': future_date.isoformat(),
            'start_time': '10:30'
        }
        res = self.client.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('already booked', res.data['error'].lower())

    # 6. Manual Booking with Style, Discount, Immediate Visibility & Notification
    def test_manual_booking_with_style_and_discount(self):
        self.client.force_authenticate(user=self.owner_a)
        future_date = (timezone.now() + datetime.timedelta(days=3)).date()

        # Clear notifications
        InAppNotification.objects.filter(salon=self.salon_a).delete()

        payload = {
            'branch': str(self.branch_a.id),
            'staff': str(self.stylist_profile_1.id),
            'customer': str(self.customer_a.id),
            'service_id': str(self.service_haircut.id),
            'style_id': str(self.style_layered.id),
            'date': future_date.isoformat(),
            'start_time': '14:00',
            'discount_type': 'PERCENTAGE',
            'discount_value': '10.00',  # 10% off on ₹950 = ₹95 discount -> Final ₹855.00
            'booking_source': 'WALK_IN'
        }
        res = self.client.post('/api/appointments/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        appt_data = res.data
        self.assertEqual(Decimal(str(appt_data['subtotal'])), Decimal('950.00'))
        self.assertEqual(Decimal(str(appt_data['discount_amount'])), Decimal('95.00'))
        self.assertEqual(Decimal(str(appt_data['total_amount'])), Decimal('855.00'))
        self.assertEqual(appt_data['currency'], 'INR')
        self.assertEqual(appt_data['currency_symbol'], '₹')

        # Immediate Visibility in List and Calendar
        list_res = self.client.get(f'/api/appointments/?date={future_date.isoformat()}')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        appt_ids = [a['id'] for a in list_res.data.get('results', list_res.data)]
        self.assertIn(appt_data['id'], appt_ids)

        cal_res = self.client.get(f'/api/appointments/calendar/?start_date={future_date.isoformat()}&end_date={future_date.isoformat()}')
        self.assertEqual(cal_res.status_code, status.HTTP_200_OK)
        self.assertTrue(any(a['id'] == appt_data['id'] for a in cal_res.data))

        # Owner notification check
        notifs = InAppNotification.objects.filter(salon=self.salon_a, user=self.owner_a)
        self.assertTrue(notifs.exists())
        notif = notifs.first()
        self.assertIn('Walk-In Booking', notif.title)
        self.assertIn('Advanced Layered Cut', notif.message)
        self.assertEqual(notif.metadata['appointment_id'], appt_data['id'])

    # 7. Website Online Booking Workflow
    def test_public_website_booking_workflow(self):
        future_date = (timezone.now() + datetime.timedelta(days=4)).date()
        payload = {
            'first_name': 'Meera',
            'last_name': 'Joshi',
            'phone': '+91 97123 45678',
            'email': 'meera@test.com',
            'service_id': str(self.service_haircut.id),
            'staff_id': str(self.stylist_profile_1.id),
            'date': future_date.isoformat(),
            'start_time': '16:00',
        }
        res = self.client.post(f'/api/builder/public/{self.salon_a.slug}/book/', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['booking_source'], 'ONLINE')

        # Customer created in Salon A
        cust = Customer.objects.filter(salon=self.salon_a, phone='+91 97123 45678').first()
        self.assertIsNotNone(cust)
        self.assertEqual(cust.first_name, 'Meera')

        # Notification to Owner
        notif = InAppNotification.objects.filter(salon=self.salon_a, user=self.owner_a, metadata__customer_name__icontains='Meera').first()
        self.assertIsNotNone(notif)
        self.assertIn('Customer Website', notif.title)

    # 8. Appointment Reschedule and Cancel Workflows
    def test_appointment_reschedule_and_cancel(self):
        self.client.force_authenticate(user=self.owner_a)
        future_date_1 = (timezone.now() + datetime.timedelta(days=5)).date()
        future_date_2 = (timezone.now() + datetime.timedelta(days=6)).date()

        appt = Appointment.objects.create(
            salon=self.salon_a,
            branch=self.branch_a,
            customer=self.customer_a,
            staff=self.stylist_profile_1,
            date=future_date_1,
            start_time=datetime.time(11, 0),
            end_time=datetime.time(11, 45),
            status=AppointmentStatus.CONFIRMED,
            total_amount=Decimal('800.00'),
            total_duration_minutes=45
        )

        # Reschedule
        res_resched = self.client.post(f'/api/appointments/{appt.id}/reschedule/', {
            'date': future_date_2.isoformat(),
            'start_time': '15:00'
        }, format='json')
        self.assertEqual(res_resched.status_code, status.HTTP_200_OK)
        self.assertEqual(res_resched.data['date'], future_date_2.isoformat())
        self.assertEqual(res_resched.data['start_time'], '15:00:00')

        # Cancel
        res_cancel = self.client.post(f'/api/appointments/{appt.id}/cancel/', {
            'reason': 'Client family emergency'
        }, format='json')
        self.assertEqual(res_cancel.status_code, status.HTTP_200_OK)
        self.assertEqual(res_cancel.data['status'], AppointmentStatus.CANCELLED)
        self.assertEqual(res_cancel.data['cancellation_reason'], 'Client family emergency')

    # 9. POS & Billing: Retail Products Only, Stock Validation, Safe Deduction
    def test_pos_retail_only_billing_and_stock(self):
        self.client.force_authenticate(user=self.owner_a)

        # 1. Retail products endpoint excludes internal consumables & salon services
        res_retail = self.client.get('/api/pos/retail-products/')
        self.assertEqual(res_retail.status_code, status.HTTP_200_OK)
        prod_names = [p['name'] for p in res_retail.data]
        self.assertIn('Argan Hair Serum 100ml', prod_names)
        self.assertNotIn('Salon Developer 1000ml', prod_names)
        self.assertNotIn('Designer Haircut', prod_names)

        # 2. Reject billing when requested quantity exceeds stock
        payload_excess = {
            'branch': str(self.branch_a.id),
            'customer': str(self.customer_a.id),
            'items': [
                {
                    'item_type': 'PRODUCT',
                    'product': str(self.retail_product.id),
                    'quantity': 50,  # Only 10 in stock
                    'unit_price': '1200.00'
                }
            ]
        }
        res_excess = self.client.post('/api/pos/invoices/', payload_excess, format='json')
        self.assertEqual(res_excess.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Insufficient stock', res_excess.data['error'])

        # 3. Successful POS Bill with discount & safe stock deduction
        payload_valid = {
            'branch': str(self.branch_a.id),
            'customer': str(self.customer_a.id),
            'discount_type': 'FIXED',
            'discount_value': '200.00',  # ₹200 off
            'items': [
                {
                    'item_type': 'PRODUCT',
                    'product': str(self.retail_product.id),
                    'quantity': 2,
                    'unit_price': '1200.00'
                }
            ]
        }
        # Subtotal: 2 * 1200 = 2400
        # Discount: 200 => Taxable: 2200
        # Tax 18%: 2200 * 0.18 = 396.00
        # Total: 2596.00
        res_bill = self.client.post('/api/pos/invoices/', payload_valid, format='json')
        self.assertEqual(res_bill.status_code, status.HTTP_201_CREATED)
        invoice_data = res_bill.data
        self.assertEqual(Decimal(str(invoice_data['subtotal'])), Decimal('2400.00'))
        self.assertEqual(Decimal(str(invoice_data['discount_amount'])), Decimal('200.00'))
        self.assertEqual(Decimal(str(invoice_data['tax_amount'])), Decimal('396.00'))
        self.assertEqual(Decimal(str(invoice_data['total_amount'])), Decimal('2596.00'))

        # Verify stock safely decremented from 10 to 8
        self.stock_level.refresh_from_db()
        self.assertEqual(self.stock_level.quantity_on_hand, 8)

        # Verify stock movement logged
        mv = StockMovement.objects.filter(product=self.retail_product, movement_type=StockMovementType.SALE_OUT).first()
        self.assertIsNotNone(mv)
        self.assertEqual(mv.quantity, -2)
        self.assertEqual(mv.balance_after, 8)

        # 4. UPI Payment QR Generation
        res_qr = self.client.get(f"/api/pos/invoices/{invoice_data['id']}/payment-qr/")
        self.assertEqual(res_qr.status_code, status.HTTP_200_OK)
        self.assertEqual(res_qr.data['currency'], 'INR')
        self.assertEqual(Decimal(res_qr.data['amount']), Decimal('2596.00'))
        self.assertIn('upi://pay?', res_qr.data['upi_uri'])

        # 5. Settle Payment
        res_pay = self.client.post(f"/api/pos/invoices/{invoice_data['id']}/record_payment/", {
            'amount': '2596.00',
            'payment_method': 'UPI',
            'transaction_reference': 'UPI-REF-998877'
        }, format='json')
        self.assertEqual(res_pay.status_code, status.HTTP_200_OK)
        self.assertEqual(res_pay.data['status'], InvoiceStatus.PAID)

        # 6. Invoice PDF Generation
        inv_obj = Invoice.objects.get(id=invoice_data['id'])
        pdf_bytes = generate_invoice_pdf(inv_obj)
        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

        res_pdf_api = self.client.get(f"/api/pos/invoices/{invoice_data['id']}/pdf/")
        self.assertEqual(res_pdf_api.status_code, status.HTTP_200_OK)
        self.assertEqual(res_pdf_api['Content-Type'], 'application/pdf')
