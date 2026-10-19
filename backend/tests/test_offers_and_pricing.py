import uuid
from decimal import Decimal
from unittest.mock import patch
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from django.conf import settings
from django.db import transaction

from apps.identity.models import User, RoleChoices
from apps.organisations.models import (
    Organisation,
    OrganisationMembership,
    OrganisationRoleChoices,
    OrganisationTypeChoices,
)
from apps.catalogue.models import PartCategory, Part
from apps.marketplace.models import (
    SparePartListing,
    PriceChange,
    ListingStatusChoices,
    ImmutableRecordError,
)
from apps.marketplace.services import change_price
from apps.marketplace.serializers import compute_price_flags
from platform_core.audit.models import AuditLog


@pytest.fixture
def test_category(db):
    return PartCategory.objects.create(name='Braking Systems', slug='braking-systems-offers')


@pytest.fixture
def catalogue_part(db, test_category):
    return Part.objects.create(
        name='Brembo Brake Disc (Front)',
        brand='Brembo',
        mpn='09.C398.13',
        category=test_category,
        is_active=True,
    )


@pytest.fixture
def inactive_catalogue_part(db, test_category):
    return Part.objects.create(
        name='Legacy Brake Disc (Inactive)',
        brand='Bosch',
        mpn='0986479001',
        category=test_category,
        is_active=False,
    )


@pytest.fixture
def other_catalogue_part(db, test_category):
    return Part.objects.create(
        name='Ferodo Brake Pads',
        brand='Ferodo',
        mpn='FDB1001',
        category=test_category,
        is_active=True,
    )


@pytest.fixture
def other_seller(db):
    user = User.objects.create_user(
        email='other_seller_pricing@driverxtra.com',
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
def org_with_roles(db, seller_user):
    org = Organisation.objects.create(
        name='Apex Performance Parts Ltd',
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
        email='org_admin_pricing@driverxtra.com',
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
        email='readonly_member_pricing@driverxtra.com',
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
class TestPriceValidationAndCatalogueLinking:
    """Tests 1, 2: Price and compare_at_price validation, MAX_LISTING_PRICE, catalogue_part validation."""

    def test_compare_at_price_must_be_greater_than_price(
        self, seller_auth_client, test_category, catalogue_part
    ):
        # Case A: compare_at_price == price -> reject 400
        res_eq = seller_auth_client.post(
            '/api/v1/marketplace/parts/',
            {
                'name': 'Brembo Disc',
                'brand': 'Brembo',
                'mpn': 'BRM-01',
                'category': str(test_category.id),
                'price': '100.00',
                'compare_at_price': '100.00',
                'stock_quantity': 5,
            },
            format='json',
        )
        assert res_eq.status_code == status.HTTP_400_BAD_REQUEST
        body_eq = res_eq.json()
        assert body_eq['status'] == 'error'
        assert body_eq['code'] == 400
        assert 'compare_at_price' in str(body_eq)

        # Case B: compare_at_price < price -> reject 400
        res_lt = seller_auth_client.post(
            '/api/v1/marketplace/parts/',
            {
                'name': 'Brembo Disc',
                'brand': 'Brembo',
                'mpn': 'BRM-02',
                'category': str(test_category.id),
                'price': '100.00',
                'compare_at_price': '80.00',
                'stock_quantity': 5,
            },
            format='json',
        )
        assert res_lt.status_code == status.HTTP_400_BAD_REQUEST

        # Case C: compare_at_price <= 0 -> reject 400
        res_zero = seller_auth_client.post(
            '/api/v1/marketplace/parts/',
            {
                'name': 'Brembo Disc',
                'brand': 'Brembo',
                'mpn': 'BRM-03',
                'category': str(test_category.id),
                'price': '100.00',
                'compare_at_price': '0.00',
                'stock_quantity': 5,
            },
            format='json',
        )
        assert res_zero.status_code == status.HTTP_400_BAD_REQUEST

        # Case D: compare_at_price > price -> succeeds 201
        res_ok = seller_auth_client.post(
            '/api/v1/marketplace/parts/',
            {
                'name': 'Brembo Disc Valid',
                'brand': 'Brembo',
                'mpn': 'BRM-04',
                'category': str(test_category.id),
                'price': '100.00',
                'compare_at_price': '149.99',
                'stock_quantity': 5,
            },
            format='json',
        )
        assert res_ok.status_code == status.HTTP_201_CREATED
        data = res_ok.json()
        assert Decimal(str(data['price'])) == Decimal('100.00')
        assert Decimal(str(data['compare_at_price'])) == Decimal('149.99')

    def test_price_must_be_positive_and_not_exceed_max_listing_price(
        self, seller_auth_client, test_category
    ):
        # Case A: price <= 0
        res_neg = seller_auth_client.post(
            '/api/v1/marketplace/parts/',
            {
                'name': 'Negative Part',
                'brand': 'Test',
                'mpn': 'NEG-01',
                'category': str(test_category.id),
                'price': '-10.00',
                'stock_quantity': 5,
            },
            format='json',
        )
        assert res_neg.status_code == status.HTTP_400_BAD_REQUEST
        assert 'price' in str(res_neg.json())

        res_zero = seller_auth_client.post(
            '/api/v1/marketplace/parts/',
            {
                'name': 'Zero Part',
                'brand': 'Test',
                'mpn': 'ZERO-01',
                'category': str(test_category.id),
                'price': '0.00',
                'stock_quantity': 5,
            },
            format='json',
        )
        assert res_zero.status_code == status.HTTP_400_BAD_REQUEST

        # Case B: price > MAX_LISTING_PRICE (default 100000)
        res_max = seller_auth_client.post(
            '/api/v1/marketplace/parts/',
            {
                'name': 'Overpriced Part',
                'brand': 'Test',
                'mpn': 'OVER-01',
                'category': str(test_category.id),
                'price': '100000.01',
                'stock_quantity': 5,
            },
            format='json',
        )
        assert res_max.status_code == status.HTTP_400_BAD_REQUEST
        body_max = res_max.json()
        assert body_max['status'] == 'error'
        assert body_max['code'] == 400
        assert 'price' in str(body_max).lower()

    def test_catalogue_part_validation_create_and_update(
        self, seller_auth_client, seller_user, test_category, catalogue_part, inactive_catalogue_part
    ):
        # Case A: Unknown UUID -> 400
        random_id = str(uuid.uuid4())
        res_unknown = seller_auth_client.post(
            '/api/v1/marketplace/parts/',
            {
                'name': 'Unknown Catalogue Part Link',
                'brand': 'Brembo',
                'mpn': 'BRM-UNK',
                'category': str(test_category.id),
                'catalogue_part': random_id,
                'price': '50.00',
                'stock_quantity': 5,
            },
            format='json',
        )
        assert res_unknown.status_code == status.HTTP_400_BAD_REQUEST
        assert 'catalogue_part' in str(res_unknown.json())

        # Case B: Inactive catalogue part on create -> 400
        res_inactive = seller_auth_client.post(
            '/api/v1/marketplace/parts/',
            {
                'name': 'Inactive Catalogue Part Link',
                'brand': 'Bosch',
                'mpn': 'BOSCH-INACT',
                'category': str(test_category.id),
                'catalogue_part': str(inactive_catalogue_part.id),
                'price': '50.00',
                'stock_quantity': 5,
            },
            format='json',
        )
        assert res_inactive.status_code == status.HTTP_400_BAD_REQUEST
        assert 'only active catalogue parts' in str(res_inactive.json()).lower()

        # Case C: Active catalogue part on create -> 201
        res_active = seller_auth_client.post(
            '/api/v1/marketplace/parts/',
            {
                'name': 'Active Catalogue Part Link',
                'brand': 'Brembo',
                'mpn': 'BRM-ACT',
                'category': str(test_category.id),
                'catalogue_part': str(catalogue_part.id),
                'price': '50.00',
                'stock_quantity': 5,
            },
            format='json',
        )
        assert res_active.status_code == status.HTTP_201_CREATED
        listing_id = res_active.json()['id']

        # Case D: PATCH with inactive catalogue part -> 400
        res_patch_inactive = seller_auth_client.patch(
            f'/api/v1/marketplace/parts/{listing_id}/',
            {'catalogue_part': str(inactive_catalogue_part.id)},
            format='json',
        )
        assert res_patch_inactive.status_code == status.HTTP_400_BAD_REQUEST
        assert 'only active catalogue parts' in str(res_patch_inactive.json()).lower()

        # Case E: PATCH with invalid compare_at_price on update -> 400
        res_patch_cmp = seller_auth_client.patch(
            f'/api/v1/marketplace/parts/{listing_id}/',
            {'compare_at_price': '40.00'},  # price is 50.00
            format='json',
        )
        assert res_patch_cmp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestPriceChangeServiceAndLedger:
    """Tests 3, 4, 5, 6, 7: change_price service, PriceChange append-only immutability, demotion, audit."""

    def test_first_price_set_on_create_not_recorded_in_history(
        self, seller_auth_client, test_category
    ):
        res = seller_auth_client.post(
            '/api/v1/marketplace/parts/',
            {
                'name': 'New Disc',
                'brand': 'Brembo',
                'mpn': 'BRM-FIRST',
                'category': str(test_category.id),
                'price': '100.00',
                'compare_at_price': '120.00',
                'stock_quantity': 10,
            },
            format='json',
        )
        assert res.status_code == status.HTTP_201_CREATED
        listing_id = res.json()['id']
        assert PriceChange.objects.filter(listing_id=listing_id).count() == 0

    def test_approved_listing_demoted_on_price_compare_at_or_catalogue_part_change(
        self, seller_auth_client, seller_user, test_category, catalogue_part, other_catalogue_part
    ):
        # Setup: APPROVED listing
        listing = SparePartListing.objects.create(
            seller=seller_user,
            name='Approved Rotor',
            brand='Brembo',
            mpn='BRM-APP-01',
            category=test_category,
            price=Decimal('100.00'),
            compare_at_price=Decimal('130.00'),
            catalogue_part=catalogue_part,
            stock_quantity=10,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # 1. Price change demotes to PENDING_APPROVAL
        res_price = seller_auth_client.patch(
            f'/api/v1/marketplace/parts/{listing.id}/',
            {'price': '95.00'},
            format='json',
        )
        assert res_price.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.PENDING_APPROVAL
        assert listing.price == Decimal('95.00')
        assert PriceChange.objects.filter(listing=listing).count() == 1

        # Re-approve for next test
        listing.status = ListingStatusChoices.APPROVED
        listing.save(update_fields=['status'])

        # 2. Compare_at_price change demotes to PENDING_APPROVAL
        res_cmp = seller_auth_client.patch(
            f'/api/v1/marketplace/parts/{listing.id}/',
            {'compare_at_price': '140.00'},
            format='json',
        )
        assert res_cmp.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.PENDING_APPROVAL
        assert listing.compare_at_price == Decimal('140.00')
        assert PriceChange.objects.filter(listing=listing).count() == 2

        # Re-approve for next test
        listing.status = ListingStatusChoices.APPROVED
        listing.save(update_fields=['status'])

        # 3. Catalogue part change demotes to PENDING_APPROVAL (no price change -> no PriceChange)
        res_cat = seller_auth_client.patch(
            f'/api/v1/marketplace/parts/{listing.id}/',
            {'catalogue_part': str(other_catalogue_part.id)},
            format='json',
        )
        assert res_cat.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.PENDING_APPROVAL
        assert listing.catalogue_part == other_catalogue_part
        # PriceChange count remains 2 because price fields did not change
        assert PriceChange.objects.filter(listing=listing).count() == 2

        # Re-approve for next test
        listing.status = ListingStatusChoices.APPROVED
        listing.save(update_fields=['status'])

        # 4. Stock change via /stock/ keeps listing APPROVED (non-material)
        res_stock = seller_auth_client.post(
            f'/api/v1/marketplace/parts/{listing.id}/stock/',
            {'delta': 2, 'reason': 'ADJUSTMENT'},
            format='json',
        )
        assert res_stock.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.APPROVED
        assert listing.stock_quantity == 12

        # 5. Low stock threshold update keeps listing APPROVED (non-material)
        res_thresh = seller_auth_client.patch(
            f'/api/v1/marketplace/parts/{listing.id}/',
            {'low_stock_threshold': 5},
            format='json',
        )
        assert res_thresh.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        assert listing.status == ListingStatusChoices.APPROVED

    def test_no_op_save_writes_no_price_change_and_does_not_demote(
        self, seller_auth_client, seller_user, test_category, catalogue_part
    ):
        listing = SparePartListing.objects.create(
            seller=seller_user,
            name='No-Op Part',
            brand='Brembo',
            mpn='BRM-NOOP',
            category=test_category,
            price=Decimal('100.00'),
            compare_at_price=Decimal('120.00'),
            catalogue_part=catalogue_part,
            stock_quantity=5,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        res = seller_auth_client.patch(
            f'/api/v1/marketplace/parts/{listing.id}/',
            {
                'price': '100.00',
                'compare_at_price': '120.00',
                'catalogue_part': str(catalogue_part.id),
            },
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        # Stays APPROVED
        assert listing.status == ListingStatusChoices.APPROVED
        # No PriceChange written
        assert PriceChange.objects.filter(listing=listing).count() == 0

    def test_patch_changing_price_and_description_together_produces_one_price_change_and_one_transition(
        self, seller_auth_client, seller_user, test_category
    ):
        listing = SparePartListing.objects.create(
            seller=seller_user,
            name='Dual Edit Part',
            brand='Bosch',
            mpn='BOSCH-DUAL',
            category=test_category,
            price=Decimal('50.00'),
            description='Original description',
            stock_quantity=5,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        res = seller_auth_client.patch(
            f'/api/v1/marketplace/parts/{listing.id}/',
            {
                'price': '55.00',
                'description': 'Updated technical description with new specs',
            },
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        listing.refresh_from_db()
        assert listing.price == Decimal('55.00')
        assert listing.description == 'Updated technical description with new specs'
        assert listing.status == ListingStatusChoices.PENDING_APPROVAL
        # Exactly one PriceChange
        assert PriceChange.objects.filter(listing=listing).count() == 1
        pc = PriceChange.objects.get(listing=listing)
        assert pc.old_price == Decimal('50.00')
        assert pc.new_price == Decimal('55.00')
        assert pc.actor == seller_user

        # AuditLog entry written
        audit = AuditLog.objects.filter(
            resource_type='SparePartListing',
            resource_id=str(listing.id),
            action='marketplace:price.change',
        ).first()
        assert audit is not None
        assert audit.metadata['old_price'] == '50.00'
        assert audit.metadata['new_price'] == '55.00'

    def test_atomicity_forced_failure_rolls_back_price_history_and_status(
        self, seller_user, test_category
    ):
        """A forced failure after PriceChange insert rolls back price, history and status.

        Audit Writer connection behavior:
        record_audit_entry executes within the same atomic transaction block on the default connection.
        When record_audit_entry raises an exception, the entire atomic transaction block rolls back,
        ensuring that the listing row, PriceChange row, and audit record are restored to their pre-call state.
        """
        listing = SparePartListing.objects.create(
            seller=seller_user,
            name='Atomic Part',
            brand='Brembo',
            mpn='BRM-ATOM',
            category=test_category,
            price=Decimal('100.00'),
            compare_at_price=Decimal('150.00'),
            stock_quantity=5,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # Mock record_audit_entry inside apps.marketplace.services to raise an exception
        with patch('apps.marketplace.services.record_audit_entry', side_effect=RuntimeError('Database connection broken during audit write')):
            with pytest.raises(RuntimeError, match='Database connection broken during audit write'):
                change_price(
                    listing=listing,
                    new_price=Decimal('120.00'),
                    new_compare_at_price=Decimal('160.00'),
                    actor=seller_user,
                    note='Attempted price update that must roll back',
                )

        # Verification after rollback
        listing.refresh_from_db()
        assert listing.price == Decimal('100.00')
        assert listing.compare_at_price == Decimal('150.00')
        assert listing.status == ListingStatusChoices.APPROVED
        assert PriceChange.objects.filter(listing=listing).count() == 0

    def test_price_change_append_only_immutability(self, seller_user, test_category):
        listing = SparePartListing.objects.create(
            seller=seller_user,
            name='Immutable Part',
            brand='Brembo',
            mpn='BRM-IMM',
            category=test_category,
            price=Decimal('80.00'),
            stock_quantity=5,
        )

        change_price(listing, new_price=Decimal('85.00'), actor=seller_user, note='Price bump')
        pc = PriceChange.objects.get(listing=listing)

        # 1. Block instance update
        with pytest.raises((ImmutableRecordError, NotImplementedError)):
            pc.new_price = Decimal('999.00')
            pc.save()

        # 2. Block instance delete
        with pytest.raises((ImmutableRecordError, NotImplementedError)):
            pc.delete()

        # 3. Block queryset bulk update()
        with pytest.raises((ImmutableRecordError, NotImplementedError)):
            PriceChange.objects.filter(id=pc.id).update(new_price=Decimal('999.00'))

        # 4. Block queryset bulk delete()
        with pytest.raises((ImmutableRecordError, NotImplementedError)):
            PriceChange.objects.filter(id=pc.id).delete()

        # 5. Block queryset bulk_update()
        with pytest.raises((ImmutableRecordError, NotImplementedError)):
            PriceChange.objects.bulk_update([pc], ['new_price'])


@pytest.mark.django_db
class TestPublicOffersEndpoint:
    """Test 8: GET /api/v1/marketplace/browse/parts/catalogue/<catalogue_part_id>/offers/"""

    def test_offers_endpoint_filters_sorting_and_unauthenticated_access(
        self, seller_user, other_seller, test_category, catalogue_part, other_catalogue_part
    ):
        # Listing 1: APPROVED, £120.00, in stock, linked to catalogue_part
        l1 = SparePartListing.objects.create(
            seller=seller_user,
            name='Offer 1 - Moderate Price',
            brand='Brembo',
            mpn='09.C398.13',
            category=test_category,
            catalogue_part=catalogue_part,
            price=Decimal('120.00'),
            compare_at_price=Decimal('150.00'),
            condition='NEW',
            stock_quantity=5,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # Listing 2: APPROVED, £85.00, out of stock (stock=0), linked to catalogue_part
        l2 = SparePartListing.objects.create(
            seller=other_seller,
            name='Offer 2 - Low Price Out of Stock',
            brand='Brembo',
            mpn='09.C398.13',
            category=test_category,
            catalogue_part=catalogue_part,
            price=Decimal('85.00'),
            condition='REFURBISHED',
            stock_quantity=0,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # Listing 3: APPROVED, £150.00, linked to catalogue_part
        l3 = SparePartListing.objects.create(
            seller=seller_user,
            name='Offer 3 - High Price',
            brand='Brembo',
            mpn='09.C398.13',
            category=test_category,
            catalogue_part=catalogue_part,
            price=Decimal('150.00'),
            condition='NEW',
            stock_quantity=2,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # Excluded 1: DRAFT listing
        SparePartListing.objects.create(
            seller=seller_user,
            name='Offer Draft',
            brand='Brembo',
            mpn='09.C398.13',
            category=test_category,
            catalogue_part=catalogue_part,
            price=Decimal('50.00'),
            stock_quantity=10,
            status=ListingStatusChoices.DRAFT,
            is_active=True,
        )

        # Excluded 2: PENDING_APPROVAL listing
        SparePartListing.objects.create(
            seller=seller_user,
            name='Offer Pending',
            brand='Brembo',
            mpn='09.C398.13',
            category=test_category,
            catalogue_part=catalogue_part,
            price=Decimal('60.00'),
            stock_quantity=10,
            status=ListingStatusChoices.PENDING_APPROVAL,
            is_active=True,
        )

        # Excluded 3: REJECTED listing
        SparePartListing.objects.create(
            seller=seller_user,
            name='Offer Rejected',
            brand='Brembo',
            mpn='09.C398.13',
            category=test_category,
            catalogue_part=catalogue_part,
            price=Decimal('70.00'),
            stock_quantity=10,
            status=ListingStatusChoices.REJECTED,
            is_active=True,
        )

        # Excluded 4: is_active=False
        SparePartListing.objects.create(
            seller=seller_user,
            name='Offer Inactive',
            brand='Brembo',
            mpn='09.C398.13',
            category=test_category,
            catalogue_part=catalogue_part,
            price=Decimal('75.00'),
            stock_quantity=10,
            status=ListingStatusChoices.APPROVED,
            is_active=False,
        )

        # Excluded 5: Different catalogue part
        SparePartListing.objects.create(
            seller=seller_user,
            name='Offer Other Part',
            brand='Ferodo',
            mpn='FDB1001',
            category=test_category,
            catalogue_part=other_catalogue_part,
            price=Decimal('40.00'),
            stock_quantity=10,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )

        # Unauthenticated request
        anon_client = APIClient()
        res = anon_client.get(f'/api/v1/marketplace/browse/parts/catalogue/{catalogue_part.id}/offers/')
        assert res.status_code == status.HTTP_200_OK

        data = res.json()
        results = data['results'] if isinstance(data, dict) and 'results' in data else data
        assert len(results) == 3

        # Ordering check: price ascending (85.00, then 120.00, then 150.00)
        assert Decimal(str(results[0]['price'])) == Decimal('85.00')
        assert results[0]['id'] == str(l2.id)
        assert results[0]['stock_quantity'] == 0
        assert results[0]['availability'] == 'OUT_OF_STOCK'
        assert results[0]['is_available'] is False

        assert Decimal(str(results[1]['price'])) == Decimal('120.00')
        assert results[1]['id'] == str(l1.id)
        assert Decimal(str(results[1]['compare_at_price'])) == Decimal('150.00')
        assert results[1]['availability'] == 'IN_STOCK'
        assert results[1]['is_available'] is True

        assert Decimal(str(results[2]['price'])) == Decimal('150.00')
        assert results[2]['id'] == str(l3.id)

        # Sensitive field exposure verification: no seller emails, no internal notes
        for offer in results:
            assert 'email' not in offer
            assert 'user_id' not in offer
            assert 'admin_notes' not in offer
            assert 'rejection_reason' not in offer

    def test_offers_endpoint_unknown_or_inactive_catalogue_part_returns_404(
        self, inactive_catalogue_part
    ):
        anon_client = APIClient()

        # Unknown UUID -> 404
        res_unknown = anon_client.get(f'/api/v1/marketplace/browse/parts/catalogue/{uuid.uuid4()}/offers/')
        assert res_unknown.status_code == status.HTTP_404_NOT_FOUND

        # Inactive catalogue part -> 404
        res_inact = anon_client.get(f'/api/v1/marketplace/browse/parts/catalogue/{inactive_catalogue_part.id}/offers/')
        assert res_inact.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestPriceHistoryPermissions:
    """Test 9: GET /api/v1/marketplace/parts/<id>/price-history/"""

    def test_price_history_permission_isolation(
        self, seller_user, seller_auth_client, other_seller_auth_client, org_with_roles, test_category
    ):
        org, admin_member, readonly_member = org_with_roles

        # 1. Individual seller listing
        indiv_listing = SparePartListing.objects.create(
            seller=seller_user,
            name='Individual Disc',
            brand='Brembo',
            mpn='INDIV-01',
            category=test_category,
            price=Decimal('100.00'),
            stock_quantity=5,
        )
        change_price(indiv_listing, new_price=Decimal('110.00'), actor=seller_user, note='Price rise')

        # Seller allowed
        res_seller = seller_auth_client.get(f'/api/v1/marketplace/parts/{indiv_listing.id}/price-history/')
        assert res_seller.status_code == status.HTTP_200_OK
        assert len(res_seller.json()) == 1
        assert res_seller.json()[0]['new_price'] == '110.00'

        # Other seller denied (403 or 404 isolation)
        res_other = other_seller_auth_client.get(f'/api/v1/marketplace/parts/{indiv_listing.id}/price-history/')
        assert res_other.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

        # Unauthenticated denied 401
        res_anon = APIClient().get(f'/api/v1/marketplace/parts/{indiv_listing.id}/price-history/')
        assert res_anon.status_code == status.HTTP_401_UNAUTHORIZED

        # 2. Org listing
        org_listing = SparePartListing.objects.create(
            seller=seller_user,
            organisation=org,
            name='Org Rotor',
            brand='Brembo',
            mpn='ORG-01',
            category=test_category,
            price=Decimal('200.00'),
            stock_quantity=5,
        )
        change_price(org_listing, new_price=Decimal('220.00'), actor=seller_user, note='Org price change')

        # Org OWNER (seller_user) allowed
        res_owner = seller_auth_client.get(f'/api/v1/marketplace/parts/{org_listing.id}/price-history/')
        assert res_owner.status_code == status.HTTP_200_OK

        # Org ADMIN allowed
        admin_client = APIClient()
        admin_client.force_authenticate(user=admin_member)
        res_admin = admin_client.get(f'/api/v1/marketplace/parts/{org_listing.id}/price-history/')
        assert res_admin.status_code == status.HTTP_200_OK

        # Org read-only MEMBER denied 403
        ro_client = APIClient()
        ro_client.force_authenticate(user=readonly_member)
        res_ro = ro_client.get(f'/api/v1/marketplace/parts/{org_listing.id}/price-history/')
        assert res_ro.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestPriceFlagsComputation:
    """Test 10: Reviewer price flags (odd/even counts, threshold boundaries, currency isolation, zero median)."""

    def test_price_flags_scenarios(
        self, seller_user, admin_auth_client, test_category, catalogue_part
    ):
        # Target listing under review
        target_listing = SparePartListing.objects.create(
            seller=seller_user,
            name='Review Part Target',
            brand='Brembo',
            mpn='TARGET-01',
            category=test_category,
            catalogue_part=catalogue_part,
            price=Decimal('100.00'),
            currency='GBP',
            stock_quantity=5,
            status=ListingStatusChoices.PENDING_APPROVAL,
            is_active=True,
        )

        # 1. 0 comparables -> INSUFFICIENT_COMPARABLES
        flags_0 = compute_price_flags(target_listing)
        assert flags_0['flag'] == 'INSUFFICIENT_COMPARABLES'
        assert flags_0['comparable_count'] == 0
        assert flags_0['median'] is None

        # 2. Add 2 comparables (total 2 < 3) -> INSUFFICIENT_COMPARABLES
        c1 = SparePartListing.objects.create(
            seller=seller_user,
            name='Comp 1',
            brand='Brembo',
            mpn='COMP-01',
            category=test_category,
            catalogue_part=catalogue_part,
            price=Decimal('100.00'),
            currency='GBP',
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )
        c2 = SparePartListing.objects.create(
            seller=seller_user,
            name='Comp 2',
            brand='Brembo',
            mpn='COMP-02',
            category=test_category,
            catalogue_part=catalogue_part,
            price=Decimal('110.00'),
            currency='GBP',
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )
        flags_2 = compute_price_flags(target_listing)
        assert flags_2['flag'] == 'INSUFFICIENT_COMPARABLES'
        assert flags_2['comparable_count'] == 2

        # 3. Add a different-currency listing (EUR) -> must NOT be counted as comparable for GBP listing
        c_eur = SparePartListing.objects.create(
            seller=seller_user,
            name='Comp EUR',
            brand='Brembo',
            mpn='COMP-EUR',
            category=test_category,
            catalogue_part=catalogue_part,
            price=Decimal('105.00'),
            currency='EUR',
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )
        flags_eur = compute_price_flags(target_listing)
        assert flags_eur['flag'] == 'INSUFFICIENT_COMPARABLES'
        assert flags_eur['comparable_count'] == 2  # EUR listing ignored

        # 4. Add 3rd GBP comparable: odd count (3 items: 100, 110, 120 -> median = 110.00)
        c3 = SparePartListing.objects.create(
            seller=seller_user,
            name='Comp 3',
            brand='Brembo',
            mpn='COMP-03',
            category=test_category,
            catalogue_part=catalogue_part,
            price=Decimal('120.00'),
            currency='GBP',
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )
        flags_3 = compute_price_flags(target_listing)
        assert flags_3['comparable_count'] == 3
        assert flags_3['median'] == Decimal('110.00')
        # Target price is 100.00, deviation = |100 - 110| / 110 = 10 / 110 = 0.0909 <= 0.5 -> flag is None
        assert flags_3['flag'] is None

        # 5. Add 4th GBP comparable: even count (4 items: 100, 110, 120, 130 -> median = (110 + 120) / 2 = 115.00)
        c4 = SparePartListing.objects.create(
            seller=seller_user,
            name='Comp 4',
            brand='Brembo',
            mpn='COMP-04',
            category=test_category,
            catalogue_part=catalogue_part,
            price=Decimal('130.00'),
            currency='GBP',
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        )
        flags_4 = compute_price_flags(target_listing)
        assert flags_4['comparable_count'] == 4
        assert flags_4['median'] == Decimal('115.00')

        # 6. Threshold boundary testing (PRICE_OUTLIER_THRESHOLD = 0.5)
        # Median is 100.00.
        # Set all 3 comparables to 100.00 so median is exactly 100.00.
        c1.price = Decimal('100.00')
        c1.save()
        c2.price = Decimal('100.00')
        c2.save()
        c3.price = Decimal('100.00')
        c3.save()
        c4.delete()

        # Case A: Deviation exactly at threshold 0.5 (price = 150.00 -> deviation = 50 / 100 = 0.50000000)
        target_listing.price = Decimal('150.00')
        target_listing.save()
        flags_exact = compute_price_flags(target_listing)
        assert flags_exact['comparable_count'] == 3
        assert flags_exact['median'] == Decimal('100.00')
        assert flags_exact['deviation'] == Decimal('0.5')
        # Deviation is not strictly greater than 0.5 -> NO flag
        assert flags_exact['flag'] is None

        # Case B: Deviation just over threshold (price = 150.01 -> deviation = 50.01 / 100 = 0.5001 > 0.5)
        target_listing.price = Decimal('150.01')
        target_listing.save()
        flags_over = compute_price_flags(target_listing)
        assert flags_over['comparable_count'] == 3
        assert flags_over['flag'] == 'OUTLIER_VS_MEDIAN'
        assert flags_over['deviation'] > Decimal('0.5')

        # 7. Zero-median guard returns MEDIAN_UNAVAILABLE and never raises ZeroDivisionError
        c1.price = Decimal('0.00')
        c1.save()
        c2.price = Decimal('0.00')
        c2.save()
        c3.price = Decimal('0.00')
        c3.save()
        flags_zero = compute_price_flags(target_listing)
        assert flags_zero['flag'] == 'MEDIAN_UNAVAILABLE'
        assert flags_zero['median'] == Decimal('0.00')
        assert flags_zero['deviation'] is None

        # 8. Approval is never blocked by price flags
        # Set listing back to outlier price
        c1.price = Decimal('100.00')
        c1.save()
        c2.price = Decimal('100.00')
        c2.save()
        c3.price = Decimal('100.00')
        c3.save()
        target_listing.price = Decimal('250.00')  # deviation 1.5 > 0.5
        target_listing.status = ListingStatusChoices.PENDING_APPROVAL
        target_listing.save()

        # Admin review endpoint
        res_review = admin_auth_client.post(
            f'/api/v1/marketplace/admin/parts/{target_listing.id}/review/',
            {
                'action': 'APPROVE',
                'admin_notes': 'Approved despite price outlier flag',
            },
            format='json',
        )
        assert res_review.status_code == status.HTTP_200_OK
        target_listing.refresh_from_db()
        assert target_listing.status == ListingStatusChoices.APPROVED
