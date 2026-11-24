import json
import pytest
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from rest_framework.test import APIClient
from rest_framework import status

from apps.identity.models import User, RoleChoices
from apps.organisations.models import (
    Organisation,
    OrganisationMembership,
    OrganisationTypeChoices,
    OrganisationRoleChoices,
)
from apps.catalogue.models import PartCategory
from apps.marketplace.models import (
    SparePartListing,
    ListingStatusChoices,
    DealerTier,
    DealerTierChoices,
    DealerOrganisationProfile,
    DealerOrganisationStatusChoices,
    Order,
    OrderItem,
    OrderStatusChoices,
)
from apps.marketplace.b2b_pricing_service import (
    DealerPricingService,
    DealerEligibilityError,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def category_brakes(db):
    return PartCategory.objects.create(name='Braking Systems', slug='braking-systems-onboarding')


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(
        email='staff_verifier@driverxtra.com',
        password='Password123!',
        first_name='Verifier',
        last_name='Staff',
        is_staff=True,
    )
    user.add_role(RoleChoices.ADMIN)
    return user


@pytest.fixture
def dealer_owner(db):
    user = User.objects.create_user(
        email='owner@prestigemotors.co.uk',
        password='Password123!',
        first_name='Prestige',
        last_name='Owner',
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def dealer_member(db):
    user = User.objects.create_user(
        email='tech@prestigemotors.co.uk',
        password='Password123!',
        first_name='Prestige',
        last_name='Technician',
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def other_dealer_owner(db):
    user = User.objects.create_user(
        email='owner@rivalmotors.co.uk',
        password='Password123!',
        first_name='Rival',
        last_name='Owner',
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def dealer_org(db, dealer_owner, dealer_member):
    org = Organisation.objects.create(
        name='Prestige Motors UK Ltd',
        type=OrganisationTypeChoices.DEALER_GROUP,
        country='GB',
        jurisdiction='GB-ENG',
        created_by=dealer_owner,
        is_active=True,
    )
    org.add_member(dealer_owner, role=OrganisationRoleChoices.OWNER)
    org.add_member(dealer_member, role=OrganisationRoleChoices.MEMBER)
    return org


@pytest.fixture
def other_dealer_org(db, other_dealer_owner):
    org = Organisation.objects.create(
        name='Rival Motors UK Ltd',
        type=OrganisationTypeChoices.DEALER_GROUP,
        country='GB',
        jurisdiction='GB-ENG',
        created_by=other_dealer_owner,
        is_active=True,
    )
    org.add_member(other_dealer_owner, role=OrganisationRoleChoices.OWNER)
    return org


@pytest.fixture
def tier_silver(db):
    return DealerPricingService.get_or_create_default_tier(DealerTierChoices.SILVER)


@pytest.fixture
def tier_gold(db):
    return DealerPricingService.get_or_create_default_tier(DealerTierChoices.GOLD)


@pytest.fixture
def supplier_user(db):
    user = User.objects.create_user(
        email='supplier@valeo.com',
        password='Password123!',
        first_name='Valeo',
        last_name='Supplier',
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def test_part(db, supplier_user, category_brakes):
    return SparePartListing.objects.create(
        seller=supplier_user,
        name='Valeo Premium Brake Discs Pair',
        brand='Valeo',
        mpn='VAL-8821',
        category=category_brakes,
        price=Decimal('200.00'),  # Retail: £200.00
        currency='GBP',
        stock_quantity=100,
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        hsn_code='870830',
        gst_rate=Decimal('20.00'),
    )


@pytest.mark.django_db
class TestDealerOnboardingWorkflow:

    def test_dealer_application_submission_by_owner(self, api_client, dealer_owner, dealer_org):
        api_client.force_authenticate(user=dealer_owner)

        payload = {
            'organisation_id': str(dealer_org.id),
            'company_registration_number': '12345678',
            'tax_id': 'GB998877665',
            'website_url': 'https://prestigemotors.co.uk',
            'contact_email': 'trade@prestigemotors.co.uk',
            'contact_phone': '+44 20 7946 0912',
            'notes': 'Independent multi-franchise dealer group requesting trade account.',
            'requested_tier': DealerTierChoices.SILVER,
        }

        response = api_client.post('/api/v1/marketplace/b2b/applications/', payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        data = response.data

        assert data['status'] == DealerOrganisationStatusChoices.PENDING
        assert data['is_verified_dealer'] is False
        assert data['tier'] is None

        # Verify DB record
        profile = DealerOrganisationProfile.objects.get(organisation=dealer_org)
        assert profile.status == DealerOrganisationStatusChoices.PENDING
        assert profile.is_verified_dealer is False
        app_meta = profile.get_application_data()
        assert app_meta['company_registration_number'] == '12345678'
        assert app_meta['tax_id'] == 'GB998877665'
        assert app_meta['submitted_by_id'] == str(dealer_owner.id)

    def test_regular_member_cannot_submit_application(self, api_client, dealer_member, dealer_org):
        api_client.force_authenticate(user=dealer_member)

        payload = {
            'organisation_id': str(dealer_org.id),
            'company_registration_number': '12345678',
        }

        response = api_client.post('/api/v1/marketplace/b2b/applications/', payload, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN
        error_msg = response.data.get('error') or response.data.get('detail', '')
        assert 'OWNER or ADMIN' in error_msg

    def test_duplicate_application_prevention(self, api_client, dealer_owner, dealer_org):
        api_client.force_authenticate(user=dealer_owner)

        payload = {
            'organisation_id': str(dealer_org.id),
            'company_registration_number': '12345678',
        }
        # First submission
        res1 = api_client.post('/api/v1/marketplace/b2b/applications/', payload, format='json')
        assert res1.status_code == status.HTTP_201_CREATED

        # Duplicate submission while pending
        res2 = api_client.post('/api/v1/marketplace/b2b/applications/', payload, format='json')
        assert res2.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already pending review' in res2.data['error'].lower()

    def test_already_verified_dealer_cannot_reapply(self, api_client, dealer_owner, dealer_org, tier_silver):
        DealerPricingService.assign_dealer_tier(
            organisation=dealer_org,
            tier_code=DealerTierChoices.SILVER,
            actor=dealer_owner,
            status=DealerOrganisationStatusChoices.ACTIVE,
            is_verified=True,
        )

        api_client.force_authenticate(user=dealer_owner)
        payload = {
            'organisation_id': str(dealer_org.id),
            'company_registration_number': '12345678',
        }
        response = api_client.post('/api/v1/marketplace/b2b/applications/', payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already an active verified dealer' in response.data['error'].lower()

    def test_unverified_organisation_denied_dealer_pricing(self, api_client, dealer_owner, dealer_org, test_part):
        # Create pending application
        DealerPricingService.request_dealer_verification(
            organisation=dealer_org,
            applicant=dealer_owner,
            business_data={'company_registration_number': '12345678'},
        )

        is_eligible, reason, org, profile, tier = DealerPricingService.evaluate_dealer_eligibility(user=dealer_owner)
        assert is_eligible is False
        assert 'pending' in reason.lower()

        calc = DealerPricingService.calculate_item_price(
            listing=test_part,
            quantity=1,
            user=dealer_owner,
        )
        assert calc['is_dealer_pricing_applied'] is False
        assert calc['dealer_unit_price'] == Decimal('200.00')  # Standard retail

    def test_admin_can_view_applications_and_search(self, api_client, admin_user, dealer_owner, dealer_org):
        DealerPricingService.request_dealer_verification(
            organisation=dealer_org,
            applicant=dealer_owner,
            business_data={'company_registration_number': '12345678'},
        )

        api_client.force_authenticate(user=admin_user)
        response = api_client.get('/api/v1/marketplace/b2b/admin/applications/?status=PENDING')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
        assert response.data[0]['organisation_name'] == 'Prestige Motors UK Ltd'

        # Search filter
        search_res = api_client.get('/api/v1/marketplace/b2b/admin/applications/?search=Prestige')
        assert search_res.status_code == status.HTTP_200_OK
        assert len(search_res.data) >= 1

    def test_admin_can_approve_application_and_assign_tier(
        self,
        api_client,
        admin_user,
        dealer_owner,
        dealer_org,
        tier_silver,
        test_part,
    ):
        DealerPricingService.request_dealer_verification(
            organisation=dealer_org,
            applicant=dealer_owner,
            business_data={'company_registration_number': '12345678'},
        )

        api_client.force_authenticate(user=admin_user)
        review_payload = {
            'action': 'APPROVE',
            'tier_code': DealerTierChoices.SILVER,
            'admin_notes': 'Verified against Companies House. Approved for Silver Tier.',
            'custom_discount_cap': Decimal('25.00'),
        }

        response = api_client.post(
            f'/api/v1/marketplace/b2b/admin/applications/{dealer_org.id}/review/',
            review_payload,
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data['status'] == DealerOrganisationStatusChoices.ACTIVE
        assert data['is_verified_dealer'] is True
        assert data['tier_details']['code'] == DealerTierChoices.SILVER

        # Profile in database
        profile = DealerOrganisationProfile.objects.get(organisation=dealer_org)
        assert profile.status == DealerOrganisationStatusChoices.ACTIVE
        assert profile.is_verified_dealer is True
        assert profile.verified_by == admin_user
        assert profile.verified_at is not None

        # Verify pricing is now active: Silver tier baseline is 10% off (£200 -> £180)
        calc = DealerPricingService.calculate_item_price(
            listing=test_part,
            quantity=1,
            user=dealer_owner,
        )
        assert calc['is_dealer_pricing_applied'] is True
        assert calc['dealer_unit_price'] == Decimal('180.00')
        assert calc['discount_amount_per_unit'] == Decimal('20.00')

    def test_admin_can_reject_application_with_mandatory_reason(
        self,
        api_client,
        admin_user,
        dealer_owner,
        dealer_org,
        test_part,
    ):
        DealerPricingService.request_dealer_verification(
            organisation=dealer_org,
            applicant=dealer_owner,
            business_data={'company_registration_number': '12345678'},
        )

        api_client.force_authenticate(user=admin_user)

        # 1. Reject without reason -> 400 Bad Request
        fail_res = api_client.post(
            f'/api/v1/marketplace/b2b/admin/applications/{dealer_org.id}/review/',
            {'action': 'REJECT', 'rejection_reason': ''},
            format='json',
        )
        assert fail_res.status_code == status.HTTP_400_BAD_REQUEST

        # 2. Reject with reason -> 200 OK
        ok_res = api_client.post(
            f'/api/v1/marketplace/b2b/admin/applications/{dealer_org.id}/review/',
            {'action': 'REJECT', 'rejection_reason': 'Company registration number does not match registered trade registry.'},
            format='json',
        )
        assert ok_res.status_code == status.HTTP_200_OK
        data = ok_res.data
        assert data['status'] == DealerOrganisationStatusChoices.REJECTED
        assert data['is_verified_dealer'] is False
        assert 'trade registry' in data['rejection_reason'].lower()

        # Dealer cannot receive pricing
        calc = DealerPricingService.calculate_item_price(
            listing=test_part,
            quantity=1,
            user=dealer_owner,
        )
        assert calc['is_dealer_pricing_applied'] is False
        assert calc['dealer_unit_price'] == Decimal('200.00')

    def test_applicant_cannot_approve_own_application(self, dealer_owner, dealer_org):
        DealerPricingService.request_dealer_verification(
            organisation=dealer_org,
            applicant=dealer_owner,
            business_data={'company_registration_number': '12345678'},
        )
        profile = DealerOrganisationProfile.objects.get(organisation=dealer_org)

        with pytest.raises(ValidationError) as exc:
            DealerPricingService.review_dealer_application(
                profile=profile,
                reviewer=dealer_owner,
                action='APPROVE',
            )
        assert 'cannot review their own' in str(exc.value).lower()

    def test_inactive_tier_denies_pricing_benefits(
        self,
        dealer_owner,
        dealer_org,
        test_part,
    ):
        custom_tier = DealerTier.objects.create(
            code='SPECIAL_INACTIVE',
            name='Special Tier',
            default_discount_percentage=Decimal('25.00'),
            priority=50,
            is_active=False,  # Inactive tier!
        )

        profile = DealerOrganisationProfile.objects.create(
            organisation=dealer_org,
            tier=custom_tier,
            is_verified_dealer=True,
            status=DealerOrganisationStatusChoices.ACTIVE,
        )

        is_eligible, reason, org, profile, tier = DealerPricingService.evaluate_dealer_eligibility(user=dealer_owner)
        assert is_eligible is False
        assert 'inactive' in reason.lower()

        calc = DealerPricingService.calculate_item_price(
            listing=test_part,
            quantity=1,
            user=dealer_owner,
        )
        assert calc['is_dealer_pricing_applied'] is False
        assert calc['dealer_unit_price'] == Decimal('200.00')

    def test_tier_change_affects_future_pricing(
        self,
        admin_user,
        dealer_owner,
        dealer_org,
        tier_silver,
        tier_gold,
        test_part,
    ):
        # 1. Assign Silver tier (10% off -> £180)
        DealerPricingService.assign_dealer_tier(
            organisation=dealer_org,
            tier_code=DealerTierChoices.SILVER,
            actor=admin_user,
        )
        calc1 = DealerPricingService.calculate_item_price(
            listing=test_part,
            quantity=1,
            user=dealer_owner,
        )
        assert calc1['dealer_unit_price'] == Decimal('180.00')

        # 2. Upgrade to Gold tier (15% off -> £170)
        DealerPricingService.assign_dealer_tier(
            organisation=dealer_org,
            tier_code=DealerTierChoices.GOLD,
            actor=admin_user,
        )
        calc2 = DealerPricingService.calculate_item_price(
            listing=test_part,
            quantity=1,
            user=dealer_owner,
        )
        assert calc2['dealer_unit_price'] == Decimal('170.00')
        assert calc2['discount_amount_per_unit'] == Decimal('30.00')

    def test_historical_order_price_snapshots_preserved(
        self,
        api_client,
        admin_user,
        dealer_owner,
        dealer_org,
        tier_silver,
        tier_gold,
        test_part,
    ):
        # Start at Silver tier (10% off: £200 -> £180)
        DealerPricingService.assign_dealer_tier(
            organisation=dealer_org,
            tier_code=DealerTierChoices.SILVER,
            actor=admin_user,
        )

        api_client.force_authenticate(user=dealer_owner)
        payload = {
            "items": [{"listing_id": str(test_part.id), "quantity": 1}],
            "shipping_name": "Prestige Motors UK",
            "shipping_phone": "+447911123456",
            "shipping_address_line1": "10 Commercial Way",
            "shipping_city": "London",
            "shipping_postal_code": "SW1A 1AA",
            "shipping_country": "United Kingdom",
            "currency": "GBP",
            "payment_method": "ONLINE",
            "organisation_id": str(dealer_org.id),
        }
        res = api_client.post('/api/v1/marketplace/orders/checkout/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        order_id = res.data["order"]["id"]
        order = Order.objects.get(id=order_id)
        assert order.subtotal_taxable_amount == Decimal('180.00')
        assert order.total_discount_amount == Decimal('20.00')

        # Upgrade dealer to Gold tier (15% off)
        DealerPricingService.assign_dealer_tier(
            organisation=dealer_org,
            tier_code=DealerTierChoices.GOLD,
            actor=admin_user,
        )

        # Verify historical order remains frozen at Silver rates
        order.refresh_from_db()
        assert order.subtotal_taxable_amount == Decimal('180.00')
        assert order.total_discount_amount == Decimal('20.00')
        item = order.items.first()
        assert item.unit_price == Decimal('180.00')
        assert item.discount_amount == Decimal('20.00')

    def test_organisation_level_data_isolation(
        self,
        api_client,
        dealer_owner,
        dealer_org,
        other_dealer_owner,
        other_dealer_org,
    ):
        # Create application for Prestige Motors
        DealerPricingService.request_dealer_verification(
            organisation=dealer_org,
            applicant=dealer_owner,
            business_data={'company_registration_number': 'PRESTIGE-123'},
        )

        # Rival Motors owner queries application detail for Prestige Motors
        api_client.force_authenticate(user=other_dealer_owner)
        res = api_client.get(f'/api/v1/marketplace/b2b/applications/me/?organisation_id={dealer_org.id}')
        assert res.status_code == status.HTTP_403_FORBIDDEN
