from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
import pytest
from rest_framework import status
from rest_framework.test import APIClient
from apps.identity.models import User, RoleChoices, AccountStatusChoices
from apps.onboarding.models import SellerApplication, SellerApplicationStatusChoices, BusinessTypeChoices
from apps.workshops.models import WorkshopProfile
from apps.organisations.models import Organisation, OrganisationTypeChoices, OrganisationMembership, OrganisationRoleChoices
from apps.catalogue.models import PartCategory, VehicleMake, VehicleModel
from apps.marketplace.models import (
    VehicleListing,
    SparePartListing,
    ListingStatusChoices,
    Order,
    OrderItem,
    VehicleOrder,
    VehiclePurchaseOffer,
    VehicleOfferStatusChoices,
    VehicleOrderStatusChoices,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
)


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def buyer_client(buyer_user):
    client = APIClient()
    client.force_authenticate(user=buyer_user)
    return client


class TestAdminAccountManagement:

    def test_admin_overview_metrics(self, admin_client, buyer_user, seller_user, workshop_user):
        res = admin_client.get('/api/v1/admin/overview/metrics/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert 'metrics' in data
        metrics = data['metrics']
        assert metrics['total_buyers'] >= 1
        assert metrics['total_sellers'] >= 1
        assert 'pending_seller_applications' in metrics
        assert 'total_orders' in metrics
        assert 'pending_disputes' in metrics
        assert 'pending_tasks' in data
        assert 'recent_activity' in data

    def test_admin_seller_list_pagination_and_search(self, admin_client, db):
        # Create 25 seller accounts to verify server-side pagination (default 20)
        for i in range(25):
            u = User.objects.create_user(
                email=f'seller_pag_{i:02d}@driverxtra.com',
                password='SecurePassword123!',
                first_name=f'Dealer{i}',
                last_name='Test',
                is_email_verified=True,
            )
            u.add_role(RoleChoices.SELLER)
            SellerApplication.objects.create(
                user=u,
                business_name=f'Dealer Business {i}',
                business_type=BusinessTypeChoices.DEALER,
                status=SellerApplicationStatusChoices.APPROVED if i % 2 == 0 else SellerApplicationStatusChoices.PENDING,
                contact_email=u.email,
                contact_phone='+447000000000',
            )

        # 1. Page 1 default size (20)
        res1 = admin_client.get('/api/v1/admin/sellers/?page=1&page_size=20')
        assert res1.status_code == status.HTTP_200_OK
        data1 = res1.json()
        assert data1['count'] >= 25
        assert len(data1['results']) == 20
        assert data1['current_page'] == 1
        assert data1['page_size'] == 20
        assert data1['total_pages'] >= 2

        # 2. Page 2
        res2 = admin_client.get('/api/v1/admin/sellers/?page=2&page_size=20')
        assert res2.status_code == status.HTTP_200_OK
        data2 = res2.json()
        assert len(data2['results']) >= 5

        # 3. Custom page size 50
        res50 = admin_client.get('/api/v1/admin/sellers/?page=1&page_size=50')
        assert res50.status_code == status.HTTP_200_OK
        assert len(res50.json()['results']) >= 25

        # 4. Search by business name
        search_res = admin_client.get('/api/v1/admin/sellers/?q=Dealer Business 5')
        assert search_res.status_code == status.HTTP_200_OK
        assert len(search_res.json()['results']) >= 1
        assert any(item['business_name'] == 'Dealer Business 5' for item in search_res.json()['results'])

        # 5. Filter by verification status
        app_res = admin_client.get('/api/v1/admin/sellers/?verification_status=APPROVED')
        assert app_res.status_code == status.HTTP_200_OK
        for item in app_res.json()['results']:
            assert item['verification_status'] == 'APPROVED'

    def test_admin_seller_detail_and_suspend_reactivate(self, admin_client, seller_user):
        # 1. Detail endpoint
        detail_res = admin_client.get(f'/api/v1/admin/sellers/{seller_user.id}/')
        assert detail_res.status_code == status.HTTP_200_OK
        data = detail_res.json()
        assert data['seller']['id'] == str(seller_user.id)
        assert data['seller']['email'] == seller_user.email
        assert 'metrics' in data

        # 2. Suspend seller
        suspend_res = admin_client.post(
            f'/api/v1/admin/sellers/{seller_user.id}/status/',
            {'action': 'SUSPEND', 'reason': 'Compliance check pending'},
            format='json'
        )
        assert suspend_res.status_code == status.HTTP_200_OK
        seller_user.refresh_from_db()
        assert seller_user.status == AccountStatusChoices.SUSPENDED
        assert seller_user.is_active is False

        # 3. Reactivate seller
        reactivate_res = admin_client.post(
            f'/api/v1/admin/sellers/{seller_user.id}/status/',
            {'action': 'REACTIVATE', 'reason': 'Compliance check passed'},
            format='json'
        )
        assert reactivate_res.status_code == status.HTTP_200_OK
        seller_user.refresh_from_db()
        assert seller_user.status == AccountStatusChoices.ACTIVE
        assert seller_user.is_active is True

    def test_admin_workshop_list_and_status_update(self, admin_client, workshop_user, db):
        org = Organisation.objects.create(
            name='Precision Workshop',
            slug='precision-workshop',
            type=OrganisationTypeChoices.WORKSHOP,
            created_by=workshop_user,
        )
        wp = WorkshopProfile.objects.create(
            organisation=org,
            business_name='Precision Workshop Ltd',
            slug='precision-workshop-ltd',
            contact_email='precision@driverxtra.com',
            city='Manchester',
            is_verified=False,
        )

        # 1. List workshops
        list_res = admin_client.get('/api/v1/admin/workshops/')
        assert list_res.status_code == status.HTTP_200_OK
        assert list_res.json()['count'] >= 1

        # 2. Detail workshop
        detail_res = admin_client.get(f'/api/v1/admin/workshops/{wp.id}/')
        assert detail_res.status_code == status.HTTP_200_OK
        assert detail_res.json()['workshop']['business_name'] == 'Precision Workshop Ltd'

        # 3. Verify workshop
        verify_res = admin_client.post(
            f'/api/v1/admin/workshops/{wp.id}/status/',
            {'action': 'VERIFY', 'reason': 'Trade certification confirmed'},
            format='json'
        )
        assert verify_res.status_code == status.HTTP_200_OK
        wp.refresh_from_db()
        assert wp.is_verified is True

        # 4. Suspend workshop bookings
        suspend_res = admin_client.post(
            f'/api/v1/admin/workshops/{wp.id}/status/',
            {'action': 'SUSPEND', 'reason': 'Annual safety audit'},
            format='json'
        )
        assert suspend_res.status_code == status.HTTP_200_OK
        wp.refresh_from_db()
        assert wp.is_accepting_bookings is False

    def test_admin_buyer_list_and_suspend(self, admin_client, buyer_user):
        # 1. List buyers
        list_res = admin_client.get('/api/v1/admin/buyers/')
        assert list_res.status_code == status.HTTP_200_OK
        assert list_res.json()['count'] >= 1

        # 2. Detail buyer
        detail_res = admin_client.get(f'/api/v1/admin/buyers/{buyer_user.id}/')
        assert detail_res.status_code == status.HTTP_200_OK
        assert detail_res.json()['buyer']['email'] == buyer_user.email

        # 3. Suspend buyer
        suspend_res = admin_client.post(
            f'/api/v1/admin/buyers/{buyer_user.id}/status/',
            {'action': 'SUSPEND', 'reason': 'Suspected abusive activity'},
            format='json'
        )
        assert suspend_res.status_code == status.HTTP_200_OK
        buyer_user.refresh_from_db()
        assert buyer_user.status == AccountStatusChoices.SUSPENDED

    def test_unauthorized_user_denied_admin_management(self, buyer_client):
        # Ordinary buyer cannot access admin overview or account management
        res_overview = buyer_client.get('/api/v1/admin/overview/metrics/')
        assert res_overview.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

        res_sellers = buyer_client.get('/api/v1/admin/sellers/')
        assert res_sellers.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

        res_workshops = buyer_client.get('/api/v1/admin/workshops/')
        assert res_workshops.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

        res_buyers = buyer_client.get('/api/v1/admin/buyers/')
        assert res_buyers.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_pure_admin_cannot_create_seller_inventory_without_role(self, admin_client, admin_user):
        # Administrator does NOT hold SELLER or WORKSHOP role
        assert not admin_user.has_role(RoleChoices.SELLER)
        assert not admin_user.has_role(RoleChoices.WORKSHOP)

        # Attempting to submit vehicle inventory as seller should be denied
        create_res = admin_client.post('/api/v1/marketplace/vehicles/', {
            'title': 'Unauthorized Admin Vehicle Listing',
            'price': '25000.00',
        }, format='json')
        assert create_res.status_code == status.HTTP_403_FORBIDDEN
        assert 'operational role' in str(create_res.json()).lower()

    def test_admin_orders_monitoring_spare_part_order_no_title_attribute_error(self, admin_client, buyer_user, seller_user, db):
        # Setup category and spare part listing with 'name', 'brand', 'mpn' (no 'title' field)
        category = PartCategory.objects.create(name="Braking Systems", slug="braking-systems")
        listing = SparePartListing.objects.create(
            seller=seller_user,
            category=category,
            name="Ceramic Front Brake Pads",
            brand="Brembo",
            mpn="BREM-BRK-991",
            price=Decimal("150.00"),
            currency="GBP",
            stock_quantity=20,
            status=ListingStatusChoices.APPROVED,
        )

        order = Order.objects.create(
            buyer=buyer_user,
            order_number="ORD-MONITOR-001",
            status=OrderStatusChoices.CONFIRMED,
            payment_method=PaymentMethodChoices.ONLINE,
            payment_status=PaymentStatusChoices.PAID,
            currency="GBP",
            subtotal_taxable_amount=Decimal("150.00"),
            total_tax_amount=Decimal("30.00"),
            total_amount=Decimal("180.00"),
            shipping_name="Jane Buyer",
            shipping_city="Manchester",
        )

        OrderItem.objects.create(
            order=order,
            listing=listing,
            item_type="PART",
            title=listing.name,
            brand=listing.brand,
            mpn=listing.mpn,
            unit_price=Decimal("150.00"),
            quantity=1,
            taxable_amount=Decimal("150.00"),
            tax_amount=Decimal("30.00"),
            total_amount=Decimal("180.00"),
        )

        # GET /api/v1/admin/orders/ MUST NOT raise AttributeError: 'SparePartListing' object has no attribute 'title'
        res = admin_client.get('/api/v1/admin/orders/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['count'] >= 1
        found = next((o for o in data['results'] if o['order_number'] == 'ORD-MONITOR-001'), None)
        assert found is not None
        assert found['order_type'] == 'SPARE_PART'
        assert found['order_type_display'] == 'Spare Part'
        assert found['total_amount'] == '180.00'
        assert found['payment_status'] == PaymentStatusChoices.PAID
        assert len(found['items_preview']) == 1
        item = found['items_preview'][0]
        assert item['title'] == "Ceramic Front Brake Pads"
        assert item['part_number'] == "BREM-BRK-991"
        assert item['seller_email'] == seller_user.email

    def test_admin_orders_monitoring_null_listing_does_not_crash(self, admin_client, buyer_user, db):
        # OrderItem where listing foreign key is NULL (e.g. seller deleted listing or historic catalogue snapshot)
        order = Order.objects.create(
            buyer=buyer_user,
            order_number="ORD-HISTORIC-NULL-002",
            status=OrderStatusChoices.COMPLETED,
            payment_method=PaymentMethodChoices.ONLINE,
            payment_status=PaymentStatusChoices.PAID,
            currency="GBP",
            subtotal_taxable_amount=Decimal("50.00"),
            total_tax_amount=Decimal("10.00"),
            total_amount=Decimal("60.00"),
        )

        OrderItem.objects.create(
            order=order,
            listing=None,  # Null listing
            item_type="PART",
            title="Archived Oil Filter",
            brand="Bosch",
            mpn="BOS-OIL-77",
            unit_price=Decimal("50.00"),
            quantity=1,
            taxable_amount=Decimal("50.00"),
            tax_amount=Decimal("10.00"),
            total_amount=Decimal("60.00"),
        )

        res = admin_client.get('/api/v1/admin/orders/?q=ORD-HISTORIC-NULL-002')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['count'] == 1
        item = data['results'][0]['items_preview'][0]
        assert item['title'] == "Archived Oil Filter"
        assert item['part_number'] == "BOS-OIL-77"

    def test_admin_orders_monitoring_vehicle_order(self, admin_client, buyer_user, seller_user, test_organisation, db):
        make = VehicleMake.objects.create(name="Aston Martin")
        model = VehicleModel.objects.create(make=make, name="DB11", year_start=2016)
        v_listing = VehicleListing.objects.create(
            seller=seller_user,
            organisation=test_organisation,
            title="2022 Aston Martin DB11 V8 Coupe",
            make=make,
            model=model,
            year=2022,
            price=Decimal("125000.00"),
            currency="GBP",
            status=ListingStatusChoices.APPROVED,
        )

        now = timezone.now()
        offer = VehiclePurchaseOffer.objects.create(
            listing=v_listing,
            buyer=buyer_user,
            seller=seller_user,
            status=VehicleOfferStatusChoices.ACCEPTED,
            expires_at=now + timedelta(days=3),
        )

        VehicleOrder.objects.create(
            order_number="VO-ADMIN-TEST-777",
            listing=v_listing,
            accepted_offer=offer,
            buyer=buyer_user,
            seller=seller_user,
            organisation=test_organisation,
            status=VehicleOrderStatusChoices.PAYMENT_CONFIRMED,
            agreed_price=Decimal("125000.00"),
            currency="GBP",
            handover_type="COLLECTION",
            payment_deadline=now + timedelta(days=7),
            payment_confirmed_at=now,
        )

        # Query all orders: should return vehicle order with order_type == 'VEHICLE'
        res = admin_client.get('/api/v1/admin/orders/?q=VO-ADMIN-TEST-777')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['count'] == 1
        vo_data = data['results'][0]
        assert vo_data['order_number'] == "VO-ADMIN-TEST-777"
        assert vo_data['order_type'] == "VEHICLE"
        assert vo_data['order_type_display'] == "Motor Vehicle"
        assert vo_data['total_amount'] == "125000.00"
        assert vo_data['payment_status'] == "PAID"
        assert vo_data['items_preview'][0]['title'] == "2022 Aston Martin DB11 V8 Coupe"
        assert vo_data['seller']['email'] == seller_user.email

    def test_admin_orders_monitoring_order_type_filtering(self, admin_client, buyer_user, seller_user, test_organisation, db):
        # Test filtering by order_type=VEHICLE vs order_type=SPARE_PART
        res_vehicles = admin_client.get('/api/v1/admin/orders/?order_type=VEHICLE')
        assert res_vehicles.status_code == status.HTTP_200_OK
        for r in res_vehicles.json()['results']:
            assert r['order_type'] == 'VEHICLE'

        res_parts = admin_client.get('/api/v1/admin/orders/?order_type=SPARE_PART')
        assert res_parts.status_code == status.HTTP_200_OK
        for r in res_parts.json()['results']:
            assert r['order_type'] == 'SPARE_PART'


