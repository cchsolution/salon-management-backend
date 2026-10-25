import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from apps.core.models import Salon, Branch, User, StaffProfile, UserRole, AuditLog
from apps.catalog.models import ServiceCategory, Service, Resource
from apps.customers.models import Customer, CustomerActivity
from apps.appointments.models import Appointment, AppointmentItem, StylistShift, AppointmentStatus, BookingSource
from apps.pos.models import Invoice, InvoiceItem, Payment, ExpenseCategory, Expense, InvoiceStatus, PaymentMethod
from apps.inventory.models import ProductCategory, Product, StockLevel, StockMovement, Supplier, StockMovementType
from apps.loyalty.models import ServicePackage, MembershipPlan, Coupon
from apps.website_builder.models import Website, WebsiteTheme, WebsitePage, WebsiteSection, SectionType, WebsiteVersion
from apps.notifications.models import InAppNotification
from rest_framework.authtoken.models import Token

class Command(BaseCommand):
    help = 'Seeds a rich, realistic Indian salon environment (Ruhi Beauty Salon, Himmatnagar & Ahmedabad) with branches, staff, catalog, bookings, POS, inventory, and website builder content.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding Ruhi Beauty Salon (India/Gujarat) demo data..."))
        with transaction.atomic():
            # 1. Superadmin User
            admin_user, _ = User.objects.get_or_create(
                email='admin@luxesalon.local',
                defaults={
                    'username': 'admin@luxesalon.local',
                    'first_name': 'Platform',
                    'last_name': 'Superadmin',
                    'role': UserRole.SUPERADMIN,
                    'is_staff': True,
                    'is_superuser': True,
                    'is_active': True,
                }
            )
            admin_user.username = 'admin@luxesalon.local'
            admin_user.first_name = 'Platform'
            admin_user.last_name = 'Superadmin'
            admin_user.role = UserRole.SUPERADMIN
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.is_active = True
            admin_user.set_password('Admin@123')
            admin_user.save()
            Token.objects.get_or_create(user=admin_user)


            # 2. Salon Organization (Primary: ruhi-beauty-salon)
            # Find existing salon or create new
            salon = Salon.objects.filter(slug__in=['ruhi-beauty-salon', 'luxe-and-co']).first()
            if not salon:
                salon = Salon.objects.create(
                    slug='ruhi-beauty-salon',
                    name='Ruhi Beauty Salon',
                    tagline='Your Beauty, Our Passion',
                    email='hello@ruhibeauty.local',
                    phone='+91 98250 12345',
                    address='Shop 4-5, Shivalik Complex, Motipura, Himmatnagar, Gujarat 383001',
                    currency='INR',
                    timezone='Asia/Kolkata',
                    tax_rate=Decimal('18.00'),
                    is_active=True,
                    subscription_plan='PRO'
                )
            else:
                salon.name = 'Ruhi Beauty Salon'
                salon.slug = 'ruhi-beauty-salon'
                salon.tagline = 'Your Beauty, Our Passion'
                salon.email = 'hello@ruhibeauty.local'
                salon.phone = '+91 98250 12345'
                salon.address = 'Shop 4-5, Shivalik Complex, Motipura, Himmatnagar, Gujarat 383001'
                salon.currency = 'INR'
                salon.timezone = 'Asia/Kolkata'
                salon.tax_rate = Decimal('18.00')
                salon.save()

            # 3. Branches (Himmatnagar & Ahmedabad)
            branch_hmt, _ = Branch.objects.get_or_create(
                salon=salon,
                name='Himmatnagar Main Studio',
                defaults={
                    'code': 'HMT-01',
                    'phone': '+91 98250 12345',
                    'email': 'himmatnagar@ruhibeauty.local',
                    'address': 'Shop 4-5, Shivalik Complex, Motipura',
                    'city': 'Himmatnagar',
                    'is_primary': True,
                    'opening_time': '09:00:00',
                    'closing_time': '20:00:00',
                }
            )
            # Update in case it existed
            branch_hmt.code = 'HMT-01'
            branch_hmt.city = 'Himmatnagar'
            branch_hmt.address = 'Shop 4-5, Shivalik Complex, Motipura'
            branch_hmt.is_primary = True
            branch_hmt.save()

            branch_ahm, _ = Branch.objects.get_or_create(
                salon=salon,
                name='Ahmedabad CG Road Branch',
                defaults={
                    'code': 'AHM-02',
                    'phone': '+91 98251 67890',
                    'email': 'ahmedabad@ruhibeauty.local',
                    'address': '302 Sapphire Arcade, CG Road, Navrangpura',
                    'city': 'Ahmedabad',
                    'is_primary': False,
                    'opening_time': '10:00:00',
                    'closing_time': '20:00:00',
                }
            )
            branch_ahm.code = 'AHM-02'
            branch_ahm.city = 'Ahmedabad'
            branch_ahm.address = '302 Sapphire Arcade, CG Road, Navrangpura'
            branch_ahm.save()

            # Clean up old branches if any
            Branch.objects.filter(salon=salon).exclude(id__in=[branch_hmt.id, branch_ahm.id]).delete()

            # 4. Salon Owner User (Ruhi Shaikh)
            owner_user, _ = User.objects.get_or_create(
                email='owner@ruhibeauty.local',
                defaults={
                    'username': 'owner@ruhibeauty.local',
                    'first_name': 'Ruhi',
                    'last_name': 'Shaikh',
                    'role': UserRole.SALON_OWNER,
                    'salon': salon,
                    'branch': branch_hmt,
                }
            )
            owner_user.first_name = 'Ruhi'
            owner_user.last_name = 'Shaikh'
            owner_user.salon = salon
            owner_user.branch = branch_hmt
            owner_user.role = UserRole.SALON_OWNER
            owner_user.is_active = True
            owner_user.set_password('Owner@123')
            owner_user.save()
            Token.objects.get_or_create(user=owner_user)

            # Also maintain owner@luxeandco.local alias for backward-compatible demo login
            legacy_owner, _ = User.objects.get_or_create(
                email='owner@luxeandco.local',
                defaults={
                    'username': 'owner@luxeandco.local',
                    'first_name': 'Ruhi',
                    'last_name': 'Shaikh',
                    'role': UserRole.SALON_OWNER,
                    'salon': salon,
                    'branch': branch_hmt,
                }
            )
            legacy_owner.first_name = 'Ruhi'
            legacy_owner.last_name = 'Shaikh'
            legacy_owner.salon = salon
            legacy_owner.branch = branch_hmt
            legacy_owner.role = UserRole.SALON_OWNER
            legacy_owner.is_active = True
            legacy_owner.set_password('Owner@123')
            legacy_owner.save()
            Token.objects.get_or_create(user=legacy_owner)

            StaffProfile.objects.update_or_create(
                salon=salon,
                user=owner_user,
                defaults={
                    'branch': branch_hmt,
                    'title': 'Founder & Creative Director',
                    'bio': 'Master hair stylist and aesthetician with over 12 years of signature hair artistry and bridal styling experience in Gujarat.',
                    'commission_rate': Decimal('20.00'),
                    'is_bookable': True,
                    'color_code': '#6D28D9'
                }
            )

            # 5. Stylist Staff Users (Indian Staff)
            stylists_meta = [
                ('ayesha@ruhibeauty.local', 'ayesha@luxeandco.local', 'Ayesha', 'Patel', 'Master Hair Stylist & Colorist', '#6D28D9', branch_hmt),
                ('komal@ruhibeauty.local', 'komal@luxeandco.local', 'Komal', 'Shah', 'Senior Beautician & Skin Specialist', '#059669', branch_hmt),
                ('nisha@ruhibeauty.local', 'nisha@luxeandco.local', 'Nisha', 'Parmar', 'Bridal Makeup & Mehendi Artist', '#8B5CF6', branch_ahm),
                ('sana@ruhibeauty.local', 'sana@luxeandco.local', 'Sana', 'Sheikh', 'Nail Artist & Aesthetician', '#10B981', branch_ahm),
            ]

            stylist_profiles = []
            for email, legacy_email, fname, lname, title, color, branch in stylists_meta:
                u, _ = User.objects.get_or_create(
                    email=email,
                    defaults={
                        'username': email,
                        'first_name': fname,
                        'last_name': lname,
                        'role': UserRole.STYLIST,
                        'salon': salon,
                        'branch': branch,
                    }
                )
                u.first_name = fname
                u.last_name = lname
                u.salon = salon
                u.branch = branch
                u.role = UserRole.STYLIST
                u.is_active = True
                u.set_password('Stylist@123')
                u.save()
                Token.objects.get_or_create(user=u)

                # Legacy alias
                lu, _ = User.objects.get_or_create(
                    email=legacy_email,
                    defaults={
                        'username': legacy_email,
                        'first_name': fname,
                        'last_name': lname,
                        'role': UserRole.STYLIST,
                        'salon': salon,
                        'branch': branch,
                    }
                )
                lu.first_name = fname
                lu.last_name = lname
                lu.salon = salon
                lu.branch = branch
                lu.role = UserRole.STYLIST
                lu.is_active = True
                lu.set_password('Stylist@123')
                lu.save()
                Token.objects.get_or_create(user=lu)

                sp, _ = StaffProfile.objects.update_or_create(
                    salon=salon,
                    user=u,
                    defaults={
                        'branch': branch,
                        'title': title,
                        'commission_rate': Decimal('15.00'),
                        'is_bookable': True,
                        'color_code': color,
                        'bio': f'Specialized in signature treatments and client transformations at {salon.name}.'
                    }
                )
                stylist_profiles.append(sp)

                # Set regular shifts (Mon-Sat 09:00 - 19:00)
                for day in range(6):
                    StylistShift.objects.update_or_create(
                        salon=salon,
                        staff=sp,
                        branch=branch,
                        day_of_week=day,
                        defaults={
                            'start_time': '09:00:00',
                            'end_time': '19:00:00',
                            'is_working': True
                        }
                    )

            # 6. Receptionist User (Pooja Mehta)
            receptionist_user, _ = User.objects.get_or_create(
                email='reception@ruhibeauty.local',
                defaults={
                    'username': 'reception@ruhibeauty.local',
                    'first_name': 'Pooja',
                    'last_name': 'Mehta',
                    'role': UserRole.RECEPTIONIST,
                    'salon': salon,
                    'branch': branch_hmt,
                }
            )
            receptionist_user.first_name = 'Pooja'
            receptionist_user.last_name = 'Mehta'
            receptionist_user.salon = salon
            receptionist_user.branch = branch_hmt
            receptionist_user.role = UserRole.RECEPTIONIST
            receptionist_user.is_active = True
            receptionist_user.set_password('Staff@123')
            receptionist_user.save()
            Token.objects.get_or_create(user=receptionist_user)

            legacy_rec, _ = User.objects.get_or_create(
                email='reception@luxeandco.local',
                defaults={
                    'username': 'reception@luxeandco.local',
                    'first_name': 'Pooja',
                    'last_name': 'Mehta',
                    'role': UserRole.RECEPTIONIST,
                    'salon': salon,
                    'branch': branch_hmt,
                }
            )
            legacy_rec.first_name = 'Pooja'
            legacy_rec.last_name = 'Mehta'
            legacy_rec.salon = salon
            legacy_rec.branch = branch_hmt
            legacy_rec.role = UserRole.RECEPTIONIST
            legacy_rec.is_active = True
            legacy_rec.set_password('Staff@123')
            legacy_rec.save()
            Token.objects.get_or_create(user=legacy_rec)


            # 7. Service Categories & Realistic Indian Services
            cat_hair, _ = ServiceCategory.objects.get_or_create(
                salon=salon,
                slug='hair-services',
                defaults={'name': 'Hair Styling & Spa', 'description': 'Precision haircut, blow dry, hair spa, keratin treatment, and global hair color.'}
            )
            cat_skin, _ = ServiceCategory.objects.get_or_create(
                salon=salon,
                slug='skin-facials',
                defaults={'name': 'Skin Care & Facials', 'description': 'Herbal cleanup, fruit facial, gold radiance, diamond facial, and hydrafacial detan.'}
            )
            cat_makeup, _ = ServiceCategory.objects.get_or_create(
                salon=salon,
                slug='makeup-mehendi',
                defaults={'name': 'Bridal Makeup & Mehendi', 'description': 'Bridal makeover, engagement makeup, party styling, and bridal mehendi.'}
            )
            cat_beauty, _ = ServiceCategory.objects.get_or_create(
                salon=salon,
                slug='beauty-waxing-nails',
                defaults={'name': 'Beauty, Waxing & Nails', 'description': 'Full arms & legs waxing, threading, deluxe pedicure, and gel nail art.'}
            )

            services_data = [
                # (category, name, slug, price_inr, duration_minutes, is_featured)
                (cat_hair, 'Precision Haircut & Blow Dry', 'haircut-blow-dry', Decimal('600.00'), 45, True),
                (cat_hair, 'Hair Spa & Deep Conditioning', 'hair-spa-conditioning', Decimal('1200.00'), 60, True),
                (cat_hair, 'Keratin Smoothing Treatment', 'keratin-treatment', Decimal('3500.00'), 150, True),
                (cat_hair, 'Root Touch-up & Global Color', 'hair-coloring', Decimal('2200.00'), 120, False),
                (cat_skin, 'Herbal Glow Fruit Facial', 'herbal-fruit-facial', Decimal('800.00'), 45, True),
                (cat_skin, 'Gold Radiance Bridal Facial', 'gold-radiance-facial', Decimal('1500.00'), 60, True),
                (cat_skin, 'Hydrafacial & Detan Therapy', 'hydrafacial-detan', Decimal('2200.00'), 75, True),
                (cat_makeup, 'Bridal HD Makeup & Draping', 'bridal-makeup-package', Decimal('7500.00'), 180, True),
                (cat_makeup, 'Party Makeup & Hair Styling', 'party-makeup-styling', Decimal('2500.00'), 90, True),
                (cat_makeup, 'Bridal & Arabic Mehendi', 'bridal-mehendi', Decimal('2000.00'), 90, False),
                (cat_beauty, 'Full Arms & Full Legs Waxing', 'full-waxing-package', Decimal('950.00'), 45, True),
                (cat_beauty, 'Eyebrow & Upper Lip Threading', 'eyebrow-upper-lip', Decimal('150.00'), 15, False),
                (cat_beauty, 'Deluxe Spa Pedicure & Manicure', 'spa-manicure-pedicure', Decimal('1100.00'), 60, True),
            ]

            created_services = []
            for cat, name, slug, price, duration, featured in services_data:
                svc, _ = Service.objects.update_or_create(
                    salon=salon,
                    slug=slug,
                    defaults={
                        'category': cat,
                        'name': name,
                        'price': price,
                        'duration_minutes': duration,
                        'is_featured': featured,
                        'description': f'Signature service at Ruhi Beauty Salon formulated with premium dermatological and organic products.'
                    }
                )
                svc.qualified_staff.set(stylist_profiles)
                svc.branches.add(branch_hmt, branch_ahm)
                created_services.append(svc)

            # 8. Demo Customers (Indian Mix)
            customers_meta = [
                ('ayesha.sheikh@example.com', 'Ayesha', 'Sheikh', '+91 98250 11223', ['VIP', 'Bridal Client'], 450),
                ('sana.khan@example.com', 'Sana', 'Khan', '+91 98251 22334', ['Frequent', 'Hair Spa Fan'], 220),
                ('zoya.patel@example.com', 'Zoya', 'Patel', '+91 98252 33445', ['New Client'], 60),
                ('mariya.shaikh@example.com', 'Mariya', 'Shaikh', '+91 98253 44556', ['VIP', 'Keratin Fan'], 580),
                ('fatima.memon@example.com', 'Fatima', 'Memon', '+91 98254 55667', ['Frequent', 'Skin Regular'], 160),
                ('neha.patel@example.com', 'Neha', 'Patel', '+91 98255 66778', ['VIP', 'Gold Member'], 490),
                ('pooja.sharma@example.com', 'Pooja', 'Sharma', '+91 98256 77889', ['Regular'], 110),
                ('riya.shah@example.com', 'Riya', 'Shah', '+91 98257 88990', ['New Client'], 50),
                ('nisha.desai@example.com', 'Nisha', 'Desai', '+91 98258 99001', ['Frequent'], 190),
                ('aarohi.mehta@example.com', 'Aarohi', 'Mehta', '+91 98259 00112', ['VIP', 'Bridal Package'], 620),
            ]

            created_customers = []
            for email, fname, lname, phone, tags, points in customers_meta:
                c_user, _ = User.objects.get_or_create(
                    email=email,
                    defaults={
                        'username': email,
                        'first_name': fname,
                        'last_name': lname,
                        'phone': phone,
                        'role': UserRole.CUSTOMER,
                        'salon': salon,
                    }
                )
                c_user.first_name = fname
                c_user.last_name = lname
                c_user.phone = phone
                c_user.set_password('Customer@123')
                c_user.save()

                cust, _ = Customer.objects.update_or_create(
                    salon=salon,
                    phone=phone,
                    defaults={
                        'user': c_user,
                        'first_name': fname,
                        'last_name': lname,
                        'email': email,
                        'tags': tags,
                        'loyalty_points': points,
                        'total_spend': Decimal(str(points * 25)),
                        'visit_count': len(tags) * 3,
                        'last_visit': timezone.now() - datetime.timedelta(days=4),
                        'notes': f'Prefers gentle scalp massage and herbal tea during salon visits.'
                    }
                )
                created_customers.append(cust)

            # 9. Inventory: Categories, Products & Stock Levels
            pcat_retail, _ = ProductCategory.objects.get_or_create(salon=salon, name='Retail Hair & Skin Care')
            pcat_prof, _ = ProductCategory.objects.get_or_create(salon=salon, name='Professional Consumables')

            supplier_gujarat, _ = Supplier.objects.get_or_create(
                salon=salon,
                name='Gujarat Beauty & Salon Supplies, Ahmedabad',
                defaults={'contact_person': 'Rajesh Patel', 'email': 'orders@gujaratbeautysupplies.local', 'phone': '+91 98250 99887'}
            )

            products_data = [
                # (category, name, sku, unit, purchase_inr, selling_inr, is_retail, qty)
                (pcat_retail, 'L’Oréal Professionnel Hair Spa Cream (500g)', 'LOR-SPA-500', 'TUB', Decimal('650.00'), Decimal('950.00'), True, 16),
                (pcat_retail, 'Matrix Opti.Care Smooth Straight Shampoo (350ml)', 'MTX-SHM-350', 'BOTTLE', Decimal('290.00'), Decimal('420.00'), True, 14),
                (pcat_retail, 'Streax Professional Argan Secrets Serum (100ml)', 'STR-SRM-100', 'BOTTLE', Decimal('240.00'), Decimal('380.00'), True, 3), # Low stock (threshold 5)
                (pcat_prof, 'Cheryl’s Cosmeceuticals TanClear Facial Kit', 'CHR-TAN-KIT', 'KIT', Decimal('1200.00'), Decimal('1850.00'), False, 9),
                (pcat_prof, 'O3+ Bridal Glow Oxygenating Facial Kit', 'O3P-GLW-KIT', 'KIT', Decimal('1900.00'), Decimal('2800.00'), False, 6),
                (pcat_prof, 'L’Oréal Majirel Color Base 5.3 (50ml)', 'LOR-MAJ-53', 'TUBE', Decimal('280.00'), Decimal('0.00'), False, 24),
            ]

            for cat, name, sku, unit, p_price, s_price, is_ret, qty in products_data:
                prod, _ = Product.objects.update_or_create(
                    salon=salon,
                    sku=sku,
                    defaults={
                        'category': cat,
                        'name': name,
                        'unit': unit,
                        'purchase_price': p_price,
                        'selling_price': s_price,
                        'is_retail': is_ret,
                        'low_stock_threshold': 5
                    }
                )
                StockLevel.objects.update_or_create(
                    salon=salon,
                    product=prod,
                    branch=branch_hmt,
                    defaults={'quantity_on_hand': qty, 'reorder_level': 5}
                )

            # 10. Sample Appointments (Past completed, Today, Upcoming)
            today = datetime.date.today()
            sample_appts_data = [
                (created_customers[0], stylist_profiles[0], branch_hmt, today - datetime.timedelta(days=2), datetime.time(10, 0), AppointmentStatus.COMPLETED, created_services[0]),
                (created_customers[1], stylist_profiles[1], branch_hmt, today - datetime.timedelta(days=1), datetime.time(14, 0), AppointmentStatus.COMPLETED, created_services[1]),
                (created_customers[2], stylist_profiles[0], branch_hmt, today, datetime.time(11, 0), AppointmentStatus.CONFIRMED, created_services[0]),
                (created_customers[3], stylist_profiles[1], branch_hmt, today, datetime.time(15, 30), AppointmentStatus.IN_PROGRESS, created_services[4]),
                (created_customers[4], stylist_profiles[2], branch_ahm, today + datetime.timedelta(days=1), datetime.time(12, 0), AppointmentStatus.CONFIRMED, created_services[5]),
                (created_customers[5], stylist_profiles[0], branch_hmt, today + datetime.timedelta(days=3), datetime.time(16, 0), AppointmentStatus.CONFIRMED, created_services[2]),
            ]

            for cust, stf, brn, a_date, a_time, stat, svc in sample_appts_data:
                end_dt = datetime.datetime.combine(a_date, a_time) + datetime.timedelta(minutes=svc.duration_minutes)
                appt, created = Appointment.objects.get_or_create(
                    salon=salon,
                    customer=cust,
                    staff=stf,
                    date=a_date,
                    start_time=a_time,
                    defaults={
                        'branch': brn,
                        'end_time': end_dt.time(),
                        'status': stat,
                        'booking_source': BookingSource.ONLINE,
                        'total_amount': svc.effective_price,
                        'total_duration_minutes': svc.duration_minutes,
                        'notes': 'Client requested experienced stylist and organic products.'
                    }
                )
                if created:
                    AppointmentItem.objects.create(
                        salon=salon,
                        appointment=appt,
                        service=svc,
                        price=svc.effective_price,
                        duration_minutes=svc.duration_minutes
                    )

                    # Invoice for completed appointments
                    if stat == AppointmentStatus.COMPLETED:
                        inv_num = f"INV-{today.year}-{appt.id.hex[:6].upper()}"
                        subtotal = svc.effective_price
                        tax = (subtotal * Decimal('18.00')) / Decimal('100.00')
                        tot = subtotal + tax

                        inv = Invoice.objects.create(
                            salon=salon,
                            branch=brn,
                            customer=cust,
                            appointment=appt,
                            invoice_number=inv_num,
                            subtotal=subtotal,
                            tax_amount=tax,
                            total_amount=tot,
                            paid_amount=tot,
                            status=InvoiceStatus.PAID,
                            created_by=owner_user
                        )
                        InvoiceItem.objects.create(
                            salon=salon,
                            invoice=inv,
                            item_type='SERVICE',
                            service=svc,
                            item_name=svc.name,
                            quantity=1,
                            unit_price=svc.effective_price,
                            total_price=tot,
                            tax_amount=tax,
                            staff=stf
                        )
                        Payment.objects.create(
                            salon=salon,
                            invoice=inv,
                            amount=tot,
                            payment_method=PaymentMethod.UPI,
                            transaction_reference=f"UPI-TXN-{inv.id.hex[:8].upper()}",
                            recorded_by=owner_user
                        )

            # 11. Expenses
            exp_cat, _ = ExpenseCategory.objects.get_or_create(salon=salon, name='Salon Operations & Consumables')
            Expense.objects.update_or_create(
                salon=salon,
                branch=branch_hmt,
                title='Weekly Linen & Organic Towel Laundry Service',
                defaults={
                    'category': exp_cat,
                    'amount': Decimal('1500.00'),
                    'payment_method': PaymentMethod.UPI,
                    'date': today - datetime.timedelta(days=2),
                    'created_by': owner_user
                }
            )

            # 12. Membership Plans & Coupons
            MembershipPlan.objects.update_or_create(
                salon=salon,
                name='Ruhi VIP Beauty Club',
                tier='GOLD',
                defaults={
                    'price': Decimal('999.00'),
                    'billing_cycle': 'MONTHLY',
                    'discount_percentage': Decimal('15.00'),
                    'free_services_count': 1,
                    'description': '15% off all hair and spa services, plus 1 complimentary signature hair wash & blowout each month.'
                }
            )

            Coupon.objects.update_or_create(
                salon=salon,
                code='WELCOME20',
                defaults={
                    'description': '20% off for first-time website bookings',
                    'discount_type': 'PERCENTAGE',
                    'discount_value': Decimal('20.00'),
                    'min_spend': Decimal('500.00'),
                    'valid_from': today - datetime.timedelta(days=30),
                    'valid_to': today + datetime.timedelta(days=180),
                    'usage_limit': 500,
                    'used_count': 42
                }
            )

            # 13. Website Builder & Published Salon Website
            website, _ = Website.objects.get_or_create(
                salon=salon,
                defaults={
                    'title': 'Ruhi Beauty Salon | Premier Luxury Salon in Gujarat',
                    'meta_description': 'Experience signature haircuts, hair spa, keratin treatments, radiant bridal makeup, and herbal facials in Himmatnagar & Ahmedabad.',
                    'is_published': True,
                    'published_at': timezone.now()
                }
            )
            website.title = 'Ruhi Beauty Salon | Premier Luxury Salon in Gujarat'
            website.meta_description = 'Experience signature haircuts, hair spa, keratin treatments, radiant bridal makeup, and herbal facials in Himmatnagar & Ahmedabad.'
            website.save()

            theme, _ = WebsiteTheme.objects.update_or_create(
                website=website,
                salon=salon,
                defaults={
                    'primary_color': '#6D28D9',
                    'secondary_color': '#059669',
                    'accent_color': '#10B981',
                    'background_color': '#F8FAFC',
                    'text_color': '#1E1B2E',
                    'font_heading': 'Playfair Display',
                    'font_body': 'Inter',
                    'header_style': 'sticky',
                    'button_border_radius': 'rounded-xl'
                }
            )

            home_page, _ = WebsitePage.objects.get_or_create(
                website=website,
                salon=salon,
                slug='home',
                defaults={'title': 'Home', 'is_home': True, 'is_active': True}
            )

            sections_spec = [
                (
                    SectionType.HERO,
                    0,
                    {
                        'headline': 'Your Beauty, Our Passion',
                        'subheadline': 'Where artistry meets luxury hair care, bridal transformations, and rejuvenating spa rituals in Himmatnagar and Ahmedabad.',
                        'cta_text': 'Book Your Appointment',
                        'cta_link': '#booking',
                        'secondary_cta_text': 'Explore Services',
                        'secondary_cta_link': '#services',
                        'background_image': 'https://images.unsplash.com/photo-1560066984-138dadb4c035?auto=format&fit=crop&w=1800&q=80',
                        'badge_text': 'Top Rated Luxury Salon in Gujarat 2026'
                    }
                ),
                (
                    SectionType.ABOUT_US,
                    1,
                    {
                        'title': 'The Philosophy of Ruhi Beauty Salon',
                        'subtitle': 'Founded by Ruhi Shaikh',
                        'story': 'We believe every woman deserves personalized beauty care in a serene, hygienic, and luxurious environment. Our collective of certified hair stylists, aesthetic specialists, and bridal artists combine authentic botanical treatments with modern techniques to curate a bespoke experience just for you.',
                        'stats': [
                            {'label': 'Happy Clients', 'value': '15,000+'},
                            {'label': 'Expert Stylists', 'value': '6 Specialists'},
                            {'label': 'Five-Star Reviews', 'value': '99%'},
                        ],
                        'image': 'https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?auto=format&fit=crop&w=1000&q=80'
                    }
                ),
                (
                    SectionType.SERVICES_GRID,
                    2,
                    {
                        'heading': 'Signature Treatments & Services',
                        'subheading': 'Crafted with premium dermatological and hair-nourishing botanicals in Indian Rupees.',
                        'show_prices': True,
                        'show_duration': True,
                        'filter_by_category': True,
                    }
                ),
                (
                    SectionType.STYLISTS_TEAM,
                    3,
                    {
                        'heading': 'Meet Our Expert Stylists & Artists',
                        'subheading': 'Certified master hair colorists, beauticians, and bridal makeup specialists.',
                    }
                ),
                (
                    SectionType.GALLERY,
                    4,
                    {
                        'heading': 'Salon Portfolio & Bridal Transformations',
                        'subheading': 'Real client results from our Himmatnagar and Ahmedabad studios.',
                        'images': [
                            'https://images.unsplash.com/photo-1562322140-8baeececf3df?auto=format&fit=crop&w=800&q=80',
                            'https://images.unsplash.com/photo-1580618672591-eb180b1a973f?auto=format&fit=crop&w=800&q=80',
                            'https://images.unsplash.com/photo-1595476108010-b4d1f102b1b1?auto=format&fit=crop&w=800&q=80',
                            'https://images.unsplash.com/photo-1521590832167-7bcbfaa6381f?auto=format&fit=crop&w=800&q=80',
                        ]
                    }
                ),
                (
                    SectionType.TESTIMONIALS,
                    5,
                    {
                        'heading': 'Loved by Our Guests',
                        'subheading': 'Read verified reviews from clients who trust Ruhi Beauty Salon.',
                        'testimonials': [
                            {
                                'client': 'Ayesha Sheikh',
                                'role': 'Bridal Client, Ahmedabad',
                                'quote': 'Ruhi did my bridal makeup and hair styling for my wedding. Absolutely magical experience and lasted the entire day through all rituals!',
                                'rating': 5
                            },
                            {
                                'client': 'Neha Patel',
                                'role': 'Entrepreneur, Himmatnagar',
                                'quote': 'Best hair spa and keratin treatment in Himmatnagar. Incredibly polite staff, clean salon, and reasonable prices.',
                                'rating': 5
                            },
                            {
                                'client': 'Zoya Patel',
                                'role': 'College Student, Himmatnagar',
                                'quote': 'Always a wonderful experience for facials and waxing. Super hygienic salon and such a calm, peaceful ambience.',
                                'rating': 5
                            }
                        ]
                    }
                ),
                (
                    SectionType.FAQ,
                    6,
                    {
                        'heading': 'Frequently Asked Questions',
                        'faqs': [
                            {'question': 'How far in advance should I book bridal makeup?', 'answer': 'We recommend booking 3-4 weeks in advance for bridal and wedding packages, although date consultations are available anytime.'},
                            {'question': 'What are your hygiene and sanitization standards?', 'answer': 'We maintain strict medical-grade sterilization for all tools and single-use consumables for threading, waxing, and facials.'},
                            {'question': 'Can I select my preferred stylist for an appointment?', 'answer': 'Yes! You can choose your preferred stylist directly during online booking or when calling our desk.'}
                        ]
                    }
                ),
                (
                    SectionType.CONTACT_MAP,
                    7,
                    {
                        'heading': 'Visit Our Studios',
                        'address_downtown': 'Shop 4-5, Shivalik Complex, Motipura, Himmatnagar, Gujarat 383001',
                        'phone_downtown': '+91 98250 12345',
                        'hours': 'Monday – Sunday: 9:00 AM – 8:00 PM',
                        'map_embed_url': 'https://maps.google.com'
                    }
                ),
                (
                    SectionType.FOOTER,
                    8,
                    {
                        'copyright': f'© {today.year} Ruhi Beauty Salon. All rights reserved.',
                        'social_links': {
                            'instagram': 'https://instagram.com/ruhibeautysalon',
                            'facebook': 'https://facebook.com/ruhibeautysalon',
                            'whatsapp': 'https://wa.me/919825012345'
                        }
                    }
                )
            ]

            for s_type, ord_idx, content in sections_spec:
                WebsiteSection.objects.update_or_create(
                    salon=salon,
                    page=home_page,
                    section_type=s_type,
                    defaults={
                        'order': ord_idx,
                        'is_enabled': True,
                        'content': content,
                        'published_content': content
                    }
                )

            # In-App Notification
            InAppNotification.objects.update_or_create(
                salon=salon,
                user=owner_user,
                title='Welcome to Ruhi Beauty Salon Platform',
                defaults={
                    'message': 'Your Indian salon environment has been initialized with Himmatnagar and Ahmedabad branches, verified Indian staff, services in INR, and website builder content.',
                    'notification_type': 'SYSTEM',
                    'is_read': False
                }
            )

        self.stdout.write(self.style.SUCCESS("Demo data successfully seeded for Ruhi Beauty Salon!"))
        self.stdout.write(self.style.SUCCESS("--- DEMO LOGIN CREDENTIALS ---"))
        self.stdout.write("Salon Owner: owner@ruhibeauty.local (or owner@luxeandco.local) / Owner@123")
        self.stdout.write("Stylist: ayesha@ruhibeauty.local / Stylist@123")
        self.stdout.write("Receptionist: reception@ruhibeauty.local / Staff@123")
        self.stdout.write("Customer: ayesha.sheikh@example.com / Customer@123")
        self.stdout.write("Public Storefront Slug: /s/ruhi-beauty-salon")
