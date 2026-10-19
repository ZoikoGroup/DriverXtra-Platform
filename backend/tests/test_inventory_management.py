import importlib
import pytest
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import User, RoleChoices
from apps.organisations.models import (
    Organisation,
    OrganisationMembership,
    OrganisationRoleChoices,
    OrganisationTypeChoices,
)
from apps.catalogue.models import PartCategory
from apps.marketplace.models import (
    SparePartListing,
    StockMovement,
    StockMovementReasonChoices,
    ListingStatusChoices,
)
from apps.marketplace.services import adjust_stock
from platform_core.audit.models import AuditLog


@pytest.fixture
def test_category(db):
    return PartCategory.objects.create(name='Braking Systems', slug='braking-systems-inv')


@pytest.fixture
def other_seller(db):
    user = User.objects.create_user(
        email='other_seller@driverxtra.com',
        password='SecurePassword123!',
        first_name='Other',
        last_name='Seller',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def other_seller_auth_client(other_seller):
    client = APIClient()
    client.force_authenticate(user=other_seller)
    return client


@pytest.fixture
def org_with_members(db, seller_user):
    org = Organisation.objects.create(
        name='Apex Dealership Group',
        type=OrganisationTypeChoices.DEALER_GROUP,
        jurisdiction='GB-ENG',
        created_by=seller_user,
    )
    # seller_user is OWNER
    OrganisationMembership.objects.create(
        organisation=org,
        user=seller_user,
        role=OrganisationRoleChoices.OWNER,
        is_active=True,
    )
    # create org ADMIN
    admin_member = User.objects.create_user(
        email='org_admin@driverxtra.com',
        password='SecurePassword123!',
        first_name='Org',
        last_name='Admin',
        is_email_verified=True,
    )
    admin_member.add_role(RoleChoices.SELLER)
    OrganisationMembership.objects.create(
        organisation=org,
        user=admin_member,
        role=OrganisationRoleChoices.ADMIN,
        is_active=True,
    )
    # create read-only MEMBER
    readonly_member = User.objects.create_user(
        email='readonly_member@driverxtra.com',
        password='SecurePassword123!',
        first_name='Read',
        last_name='Only',
        is_email_verified=True,
    )
    readonly_member.add_role(RoleChoices.SELLER)
    OrganisationMembership.objects.create(
        organisation=org,
        user=readonly_member,
        role=OrganisationRoleChoices.MEMBER,
        is_active=True,
    )
    return org, admin_member, readonly_member


@pytest.mark.django_db
class TestInventoryManagementServiceAndAPI:

    # 1. Zero delta rejected
    def test_zero_delta_rejected(self, seller_auth_client, seller_user, test_category):
        listing = SparePartListing.objects.create(
            seller=seller_user,
            name='Brake Pads',
            brand='Ferodo',
            mpn='FDB-001',
            category=test_category,
            price=45.00,
            stock_quantity=5,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        res = seller_auth_client.post(
            f'/api/v1/marketplace/parts/{listing.id}/stock/',
            {'delta': 0, 'reason': 'ADJUSTMENT'},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        body = res.json()
        assert body['status'] == 'error'
        assert body['code'] == 400
        assert 'delta' in str(body).lower()

        # Service level rejection
        with pytest.raises(DjangoValidationError) as exc_info:
            adjust_stock(listing=listing, delta=0, reason=StockMovementReasonChoices.ADJUSTMENT, actor=seller_user)
        assert 'cannot be zero' in str(exc_info.value).lower()

    # 2. No negative stock
    def test_negative_stock_rejected(self, seller_auth_client, seller_user, test_category):
        listing = SparePartListing.objects.create(
            seller=seller_user,
            name='Brake Discs',
            brand='Brembo',
            mpn='BD-001',
            category=test_category,
            price=95.00,
            stock_quantity=3,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # Attempting to decrement by 4 when stock is 3
        res = seller_auth_client.post(
            f'/api/v1/marketplace/parts/{listing.id}/stock/',
            {'delta': -4, 'reason': 'ADJUSTMENT'},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        body = res.json()
        assert body['status'] == 'error'
        assert body['code'] == 400
        assert 'negative' in str(body).lower()

        listing.refresh_from_db()
        assert listing.stock_quantity == 3

        # Service level check
        with pytest.raises(DjangoValidationError) as exc_info:
            adjust_stock(listing=listing, delta=-10, reason=StockMovementReasonChoices.ADJUSTMENT, actor=seller_user)
        assert 'negative' in str(exc_info.value).lower()

    # 3. INITIAL, SALE, and RETURN reasons rejected by the stock endpoint
    def test_stock_endpoint_rejects_initial_sale_return(self, seller_auth_client, seller_user, test_category):
        listing = SparePartListing.objects.create(
            seller=seller_user,
            name='Brake Fluid DOT4',
            brand='Castrol',
            mpn='BF-004',
            category=test_category,
            price=12.00,
            stock_quantity=10,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        for forbidden_reason in ['INITIAL', 'SALE', 'RETURN', 'INVALID_REASON']:
            res = seller_auth_client.post(
                f'/api/v1/marketplace/parts/{listing.id}/stock/',
                {'delta': 2, 'reason': forbidden_reason},
                format='json',
            )
            assert res.status_code == status.HTTP_400_BAD_REQUEST
            body = res.json()
            assert body['status'] == 'error'
            assert body['code'] == 400
            assert 'reason' in str(body).lower()

        # ADJUSTMENT and CORRECTION are permitted
        res_adj = seller_auth_client.post(
            f'/api/v1/marketplace/parts/{listing.id}/stock/',
            {'delta': 2, 'reason': 'ADJUSTMENT', 'note': 'Delivery'},
            format='json',
        )
        assert res_adj.status_code == status.HTTP_200_OK

        res_corr = seller_auth_client.post(
            f'/api/v1/marketplace/parts/{listing.id}/stock/',
            {'delta': -1, 'reason': 'CORRECTION', 'note': 'Inventory check'},
            format='json',
        )
        assert res_corr.status_code == status.HTTP_200_OK

    # 4. Listing create records initial stock exactly once with INITIAL movement
    def test_listing_create_records_initial_stock_exactly_once(self, seller_auth_client, test_category):
        payload = {
            'name': 'Performance Air Filter',
            'brand': 'K&N',
            'mpn': 'KN-33-2070',
            'category': str(test_category.id),
            'price': 65.00,
            'stock_quantity': 5,
            'low_stock_threshold': 2,
            'condition': 'NEW',
            'description': 'High-flow filter',
        }
        res = seller_auth_client.post('/api/v1/marketplace/parts/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        listing_id = res.json()['id']

        listing = SparePartListing.objects.get(id=listing_id)
        assert listing.stock_quantity == 5

        movements = StockMovement.objects.filter(listing=listing)
        assert movements.count() == 1
        mov = movements.first()
        assert mov.delta == 5
        assert mov.resulting_quantity == 5
        assert mov.reason == StockMovementReasonChoices.INITIAL
        assert mov.actor == listing.seller

    # 5. Permission isolation: Other seller denied, read-only member denied, OWNER/ADMIN allowed
    def test_permission_isolation_and_org_roles(
        self, seller_user, other_seller_auth_client, org_with_members, test_category
    ):
        org, admin_member, readonly_member = org_with_members

        # Individual listing owned by seller_user
        individual_part = SparePartListing.objects.create(
            seller=seller_user,
            name='Clutch Kit',
            brand='Sachs',
            mpn='CK-001',
            category=test_category,
            price=250.00,
            stock_quantity=4,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # Other seller denied from adjusting stock
        res_other = other_seller_auth_client.post(
            f'/api/v1/marketplace/parts/{individual_part.id}/stock/',
            {'delta': 2, 'reason': 'ADJUSTMENT'},
            format='json',
        )
        assert res_other.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

        # Other seller denied from viewing stock history
        res_other_hist = other_seller_auth_client.get(
            f'/api/v1/marketplace/parts/{individual_part.id}/stock-history/'
        )
        assert res_other_hist.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

        # Org listing
        org_part = SparePartListing.objects.create(
            seller=seller_user,
            organisation=org,
            name='Flywheel Dual Mass',
            brand='LuK',
            mpn='LUK-DMF-01',
            category=test_category,
            price=400.00,
            stock_quantity=2,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # Read-only org member client
        readonly_client = APIClient()
        readonly_client.force_authenticate(user=readonly_member)

        res_ro = readonly_client.post(
            f'/api/v1/marketplace/parts/{org_part.id}/stock/',
            {'delta': 1, 'reason': 'ADJUSTMENT'},
            format='json',
        )
        assert res_ro.status_code == status.HTTP_403_FORBIDDEN

        res_ro_hist = readonly_client.get(
            f'/api/v1/marketplace/parts/{org_part.id}/stock-history/'
        )
        assert res_ro_hist.status_code == status.HTTP_403_FORBIDDEN

        # Org ADMIN member client
        admin_client = APIClient()
        admin_client.force_authenticate(user=admin_member)

        res_adm = admin_client.post(
            f'/api/v1/marketplace/parts/{org_part.id}/stock/',
            {'delta': 3, 'reason': 'ADJUSTMENT', 'note': 'Restocked by admin'},
            format='json',
        )
        assert res_adm.status_code == status.HTTP_200_OK
        assert res_adm.json()['listing']['stock_quantity'] == 5

        res_adm_hist = admin_client.get(
            f'/api/v1/marketplace/parts/{org_part.id}/stock-history/'
        )
        assert res_adm_hist.status_code == status.HTTP_200_OK
        assert len(res_adm_hist.json()) >= 1

    # 6. Stock change on an APPROVED listing keeps it APPROVED (no re-review triggered)
    def test_stock_change_on_approved_listing_keeps_it_approved(
        self, seller_auth_client, seller_user, test_category
    ):
        listing = SparePartListing.objects.create(
            seller=seller_user,
            name='Approved Exhaust Pipe',
            brand='Milltek',
            mpn='MIL-EXH-01',
            category=test_category,
            price=600.00,
            stock_quantity=5,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # Adjust stock down to 0
        res = seller_auth_client.post(
            f'/api/v1/marketplace/parts/{listing.id}/stock/',
            {'delta': -5, 'reason': 'ADJUSTMENT', 'note': 'Sold out locally'},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['listing']['status'] == ListingStatusChoices.APPROVED
        assert data['listing']['stock_quantity'] == 0
        assert data['listing']['availability'] == 'OUT_OF_STOCK'

        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.APPROVED
        assert listing.stock_quantity == 0

    # 7. Direct PATCH with stock_quantity returns structured 400
    def test_patch_with_stock_quantity_returns_structured_400(
        self, seller_auth_client, seller_user, test_category
    ):
        listing = SparePartListing.objects.create(
            seller=seller_user,
            name='Alternator',
            brand='Bosch',
            mpn='ALT-12V',
            category=test_category,
            price=180.00,
            stock_quantity=2,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        res = seller_auth_client.patch(
            f'/api/v1/marketplace/parts/{listing.id}/',
            {'stock_quantity': 10},
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        body = res.json()
        assert body['status'] == 'error'
        assert body['code'] == 400
        assert 'stock_quantity' in str(body).lower()

    # 8. Availability boundaries: 0 -> OUT_OF_STOCK, <= threshold -> LOW_STOCK, > threshold -> IN_STOCK
    def test_availability_boundaries(self, seller_auth_client, seller_user, test_category):
        threshold = 3

        # Boundary 1: stock == 0 -> OUT_OF_STOCK
        part_0 = SparePartListing.objects.create(
            seller=seller_user,
            name='Part Out Of Stock',
            brand='BrandX',
            mpn='BX-0',
            category=test_category,
            price=20.00,
            stock_quantity=0,
            low_stock_threshold=threshold,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )
        res_0 = seller_auth_client.get(f'/api/v1/marketplace/parts/{part_0.id}/')
        assert res_0.json()['availability'] == 'OUT_OF_STOCK'

        # Boundary 2: stock == 1 <= threshold -> LOW_STOCK
        part_1 = SparePartListing.objects.create(
            seller=seller_user,
            name='Part Low 1',
            brand='BrandX',
            mpn='BX-1',
            category=test_category,
            price=20.00,
            stock_quantity=1,
            low_stock_threshold=threshold,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )
        res_1 = seller_auth_client.get(f'/api/v1/marketplace/parts/{part_1.id}/')
        assert res_1.json()['availability'] == 'LOW_STOCK'

        # Boundary 3: stock == threshold (3) -> LOW_STOCK
        part_thresh = SparePartListing.objects.create(
            seller=seller_user,
            name='Part Equal Threshold',
            brand='BrandX',
            mpn='BX-3',
            category=test_category,
            price=20.00,
            stock_quantity=3,
            low_stock_threshold=threshold,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )
        res_thresh = seller_auth_client.get(f'/api/v1/marketplace/parts/{part_thresh.id}/')
        assert res_thresh.json()['availability'] == 'LOW_STOCK'

        # Boundary 4: stock == threshold + 1 (4) -> IN_STOCK
        part_in = SparePartListing.objects.create(
            seller=seller_user,
            name='Part In Stock',
            brand='BrandX',
            mpn='BX-4',
            category=test_category,
            price=20.00,
            stock_quantity=4,
            low_stock_threshold=threshold,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )
        res_in = seller_auth_client.get(f'/api/v1/marketplace/parts/{part_in.id}/')
        assert res_in.json()['availability'] == 'IN_STOCK'

    # 9. Low-stock list correctness
    def test_low_stock_list_correctness(self, seller_auth_client, seller_user, test_category):
        # Clean up or isolate
        threshold = 3
        # Part with stock 2 (<= 3) -> should appear in low-stock
        low_part = SparePartListing.objects.create(
            seller=seller_user,
            name='Low Stock Item',
            brand='BrandY',
            mpn='BY-02',
            category=test_category,
            price=30.00,
            stock_quantity=2,
            low_stock_threshold=threshold,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )
        # Part with stock 0 (<= 3) -> should appear in low-stock
        zero_part = SparePartListing.objects.create(
            seller=seller_user,
            name='Zero Stock Item',
            brand='BrandY',
            mpn='BY-00',
            category=test_category,
            price=30.00,
            stock_quantity=0,
            low_stock_threshold=threshold,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )
        # Part with stock 10 (> 3) -> should NOT appear in low-stock
        high_part = SparePartListing.objects.create(
            seller=seller_user,
            name='High Stock Item',
            brand='BrandY',
            mpn='BY-10',
            category=test_category,
            price=30.00,
            stock_quantity=10,
            low_stock_threshold=threshold,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        res = seller_auth_client.get('/api/v1/marketplace/parts/low-stock/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        items = data if isinstance(data, list) else data.get('results', [])
        ids = [item['id'] for item in items]
        assert str(low_part.id) in ids
        assert str(zero_part.id) in ids
        assert str(high_part.id) not in ids

    # 10. OUT_OF_STOCK approved listing still appears in public browse
    def test_out_of_stock_approved_listing_still_appears_in_browse(
        self, api_client, seller_user, test_category
    ):
        out_part = SparePartListing.objects.create(
            seller=seller_user,
            name='Rare Classic Carburetor',
            brand='Weber',
            mpn='WEB-40-DCOE',
            category=test_category,
            price=450.00,
            stock_quantity=0,
            low_stock_threshold=2,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        res = api_client.get('/api/v1/marketplace/browse/parts/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        browse_items = data if isinstance(data, list) else data.get('results', [])
        item = next((i for i in browse_items if i['id'] == str(out_part.id)), None)
        assert item is not None
        assert item['stock_quantity'] == 0
        assert item['availability'] == 'OUT_OF_STOCK'

    # 11. Audit entry written on stock adjustment
    def test_audit_entry_written_on_stock_adjustment(
        self, seller_auth_client, seller_user, test_category
    ):
        listing = SparePartListing.objects.create(
            seller=seller_user,
            name='Spark Plugs Set',
            brand='NGK',
            mpn='NGK-ILZKR7B',
            category=test_category,
            price=35.00,
            stock_quantity=4,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        seller_auth_client.post(
            f'/api/v1/marketplace/parts/{listing.id}/stock/',
            {'delta': 6, 'reason': 'ADJUSTMENT', 'note': 'Restocked from distributor'},
            format='json',
        )

        audit = AuditLog.objects.filter(
            resource_type='SparePartListing',
            resource_id=str(listing.id),
            event_type='inventory.stock.adjusted',
        ).first()

        assert audit is not None
        assert audit.action == 'marketplace:stock.adjust'
        assert audit.actor_id == seller_user.id
        assert audit.metadata['delta'] == 6
        assert audit.metadata['previous_quantity'] == 4
        assert audit.metadata['resulting_quantity'] == 10
        assert audit.metadata['reason'] == 'ADJUSTMENT'
        assert audit.metadata['note'] == 'Restocked from distributor'

    # 12. StockMovement immutability guards
    def test_stock_movement_immutability(self, seller_user, test_category):
        listing = SparePartListing.objects.create(
            seller=seller_user,
            name='Fuel Pump',
            brand='Walbro',
            mpn='WAL-255',
            category=test_category,
            price=90.00,
            stock_quantity=5,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        movement = StockMovement.objects.create(
            listing=listing,
            delta=5,
            resulting_quantity=5,
            reason=StockMovementReasonChoices.INITIAL,
            actor=seller_user,
            note='Initial stock',
        )

        # Attempt to modify
        movement.delta = 999
        with pytest.raises(ValueError) as exc_save:
            movement.save()
        assert 'append-only' in str(exc_save.value).lower() or 'cannot be updated' in str(exc_save.value).lower()

        # Attempt to delete
        with pytest.raises(ValueError) as exc_del:
            movement.delete()
        assert 'cannot be deleted' in str(exc_del.value).lower() or 'append-only' in str(exc_del.value).lower()


@pytest.mark.django_db(transaction=True)
class TestStockBackfillMigration:

    def test_backfill_migration_forward_idempotent_and_reverse(self):
        """Tests 0003_backfill_initial_stock_movements using Django's MigrationExecutor on isolated test database."""
        executor = MigrationExecutor(connection)

        # 1. Migrate back to state 0002 (before backfill)
        state_0002 = executor.migrate([('marketplace', '0002_add_low_stock_threshold_and_stock_movement')])

        OldListing = state_0002.apps.get_model('marketplace', 'SparePartListing')
        OldMovement = state_0002.apps.get_model('marketplace', 'StockMovement')
        OldCategory = state_0002.apps.get_model('catalogue', 'PartCategory')
        OldUser = state_0002.apps.get_model('identity', 'User')

        category = OldCategory.objects.create(name='Braking Mig', slug='braking-mig-isolated')
        user_kwargs = {'email': 'seller_mig_isolated@driverxtra.com'}
        if any(f.name == 'is_email_verified' for f in OldUser._meta.fields):
            user_kwargs['is_email_verified'] = True
        user = OldUser.objects.create(**user_kwargs)

        # Case A: Listing with stock > 0, no movements -> needs backfill
        listing_needs_backfill = OldListing.objects.create(
            seller=user,
            name='Part Needs Backfill',
            brand='Brembo',
            mpn='MIG-BF-01',
            category=category,
            price=120.00,
            stock_quantity=8,
            low_stock_threshold=3,
            status='APPROVED',
            is_active=True,
        )

        # Case B: Listing with stock 0 -> must NOT get backfill
        listing_zero_stock = OldListing.objects.create(
            seller=user,
            name='Part Zero Stock',
            brand='Brembo',
            mpn='MIG-BF-02',
            category=category,
            price=80.00,
            stock_quantity=0,
            low_stock_threshold=3,
            status='APPROVED',
            is_active=True,
        )

        # Case C: Listing with stock > 0 that ALREADY has a StockMovement -> must NOT be duplicated
        listing_has_existing_movement = OldListing.objects.create(
            seller=user,
            name='Part Already Moved',
            brand='Brembo',
            mpn='MIG-BF-03',
            category=category,
            price=150.00,
            stock_quantity=6,
            low_stock_threshold=3,
            status='APPROVED',
            is_active=True,
        )
        OldMovement.objects.create(
            listing=listing_has_existing_movement,
            delta=6,
            resulting_quantity=6,
            reason='INITIAL',
            actor=None,
            note='Pre-existing manual entry',
        )

        # 2. Run Forward Migration to 0003
        executor = MigrationExecutor(connection)
        state_0003 = executor.migrate([('marketplace', '0003_backfill_initial_stock_movements')])

        NewListing = state_0003.apps.get_model('marketplace', 'SparePartListing')
        NewMovement = state_0003.apps.get_model('marketplace', 'StockMovement')

        # Verify: listing_needs_backfill has exactly 1 INITIAL movement created with note='Backfill'
        bf_movs = NewMovement.objects.filter(listing_id=listing_needs_backfill.id)
        assert bf_movs.count() == 1
        m = bf_movs.first()
        assert m.delta == 8
        assert m.resulting_quantity == 8
        assert m.reason == 'INITIAL'
        assert m.actor is None
        assert m.note == 'Backfill'

        # Verify: listing_zero_stock has 0 movements
        assert NewMovement.objects.filter(listing_id=listing_zero_stock.id).count() == 0

        # Verify: listing_has_existing_movement was skipped and still has only 1 movement
        assert NewMovement.objects.filter(listing_id=listing_has_existing_movement.id).count() == 1
        assert NewMovement.objects.filter(listing_id=listing_has_existing_movement.id).first().note == 'Pre-existing manual entry'

        # Verify: Stock quantities are preserved exactly
        assert NewListing.objects.get(id=listing_needs_backfill.id).stock_quantity == 8
        assert NewListing.objects.get(id=listing_zero_stock.id).stock_quantity == 0
        assert NewListing.objects.get(id=listing_has_existing_movement.id).stock_quantity == 6

        # 3. Test Rerun/Idempotency: running backfill function again creates nothing
        mig_module = importlib.import_module('apps.marketplace.migrations.0003_backfill_initial_stock_movements')
        mig_module.backfill_initial_stock_movements(state_0003.apps, None)

        assert NewMovement.objects.filter(listing_id=listing_needs_backfill.id).count() == 1
        assert NewMovement.objects.filter(listing_id=listing_zero_stock.id).count() == 0
        assert NewMovement.objects.filter(listing_id=listing_has_existing_movement.id).count() == 1

        # 4. Test Reverse Migration: deletes only the backfilled movements (marked with note='Backfill')
        executor = MigrationExecutor(connection)
        state_rev = executor.migrate([('marketplace', '0002_add_low_stock_threshold_and_stock_movement')])

        RevMovement = state_rev.apps.get_model('marketplace', 'StockMovement')
        RevListing = state_rev.apps.get_model('marketplace', 'SparePartListing')

        # The backfilled movement is deleted
        assert RevMovement.objects.filter(listing_id=listing_needs_backfill.id).count() == 0
        # The pre-existing movement is preserved!
        assert RevMovement.objects.filter(listing_id=listing_has_existing_movement.id).count() == 1
        assert RevMovement.objects.filter(listing_id=listing_has_existing_movement.id).first().note == 'Pre-existing manual entry'

        # Stock quantity remains untouched
        assert RevListing.objects.get(id=listing_needs_backfill.id).stock_quantity == 8

        # 5. Restore executor to latest state for subsequent tests
        executor = MigrationExecutor(connection)
        executor.migrate([('marketplace', '0003_backfill_initial_stock_movements')])
