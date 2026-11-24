import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import User, RoleChoices
from apps.organisations.models import (
    Organisation,
    OrganisationMembership,
    OrganisationRoleChoices,
    OrganisationTypeChoices,
)
from apps.onboarding.models import (
    SellerApplication,
    SellerApplicationStatusChoices,
    BusinessTypeChoices,
)
from apps.catalogue.models import PartCategory
from apps.marketplace.models import (
    SparePartListing,
    ListingStatusChoices,
    Order,
    OrderItem,
    DealerTier,
    DealerTierChoices,
    DealerOrganisationProfile,
    DealerOrganisationStatusChoices,
    DealerPricingRule,
    DealerPricingRuleTypeChoices,
)
from apps.marketplace.b2b_pricing_service import (
    DealerPricingService,
    DealerEligibilityError,
    MinimumOrderQuantityError,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def category_brakes(db):
    return PartCategory.objects.create(name='Braking Systems', slug='braking-systems')


@pytest.fixture
def category_engine(db):
    return PartCategory.objects.create(name='Engine Parts', slug='engine-parts')


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(
        email='admin_b2b@driverxtra.com',
        password='Password123!',
        first_name='Admin',
        last_name='User',
        is_staff=True,
        is_superuser=True,
    )
    user.add_role(RoleChoices.ADMIN)
    return user


@pytest.fixture
def ordinary_buyer(db):
    user = User.objects.create_user(
        email='ordinary_buyer@driverxtra.com',
        password='Password123!',
        first_name='Ordinary',
        last_name='Buyer',
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def dealer_user_1(db):
    user = User.objects.create_user(
        email='dealer1@apexmotors.com',
        password='Password123!',
        first_name='Apex',
        last_name='Dealer',
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def dealer_user_2(db):
    user = User.objects.create_user(
        email='dealer2@zenithautos.com',
        password='Password123!',
        first_name='Zenith',
        last_name='Dealer',
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def seller_supplier(db):
    user = User.objects.create_user(
        email='parts_supplier@bosch.co.uk',
        password='Password123!',
        first_name='Bosch',
        last_name='Supplier',
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def dealer_org_1(db, dealer_user_1):
    org = Organisation.objects.create(
        name='Apex Motors Dealership',
        type=OrganisationTypeChoices.DEALER_GROUP,
        country='GB',
        jurisdiction='GB-ENG',
        created_by=dealer_user_1,
        is_active=True,
    )
    org.add_member(dealer_user_1, role=OrganisationRoleChoices.OWNER)
    return org


@pytest.fixture
def dealer_org_2(db, dealer_user_2):
    org = Organisation.objects.create(
        name='Zenith Autos Dealership',
        type=OrganisationTypeChoices.DEALER_GROUP,
        country='GB',
        jurisdiction='GB-ENG',
        created_by=dealer_user_2,
        is_active=True,
    )
    org.add_member(dealer_user_2, role=OrganisationRoleChoices.OWNER)
    return org


@pytest.fixture
def tier_standard(db):
    return DealerPricingService.get_or_create_default_tier(DealerTierChoices.STANDARD)


@pytest.fixture
def tier_silver(db):
    return DealerPricingService.get_or_create_default_tier(DealerTierChoices.SILVER)


@pytest.fixture
def tier_gold(db):
    return DealerPricingService.get_or_create_default_tier(DealerTierChoices.GOLD)


@pytest.fixture
def tier_platinum(db):
    return DealerPricingService.get_or_create_default_tier(DealerTierChoices.PLATINUM)


@pytest.fixture
def brake_pads_part(db, seller_supplier, category_brakes):
    return SparePartListing.objects.create(
        seller=seller_supplier,
        name='Brembo Ceramic Front Brake Pads',
        brand='Brembo',
        mpn='P85020',
        category=category_brakes,
        price=Decimal('100.00'),  # Retail price: £100.00
        currency='GBP',
        stock_quantity=500,
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        hsn_code='870830',
        gst_rate=Decimal('20.00'),
    )


@pytest.fixture
def oil_filter_part(db, seller_supplier, category_engine):
    return SparePartListing.objects.create(
        seller=seller_supplier,
        name='Mann Heavy Duty Oil Filter',
        brand='Mann Filter',
        mpn='HU7197X',
        category=category_engine,
        price=Decimal('20.00'),  # Retail price: £20.00
        currency='GBP',
        stock_quantity=200,
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        hsn_code='842123',
        gst_rate=Decimal('20.00'),
    )


# =============================================================================
# 1. Eligibility & Access Control Tests
# =============================================================================

@pytest.mark.django_db
class TestDealerEligibility:

    def test_ordinary_buyer_receives_retail_pricing(self, ordinary_buyer, brake_pads_part):
        is_eligible, reason, org, profile, tier = DealerPricingService.evaluate_dealer_eligibility(user=ordinary_buyer)
        assert is_eligible is False
        assert "dealer organisation" in reason.lower()

        calc = DealerPricingService.calculate_item_price(
            listing=brake_pads_part,
            quantity=1,
            user=ordinary_buyer,
        )
        assert calc["is_dealer_pricing_applied"] is False
        assert calc["dealer_unit_price"] == Decimal('100.00')
        assert calc["discount_amount_per_unit"] == Decimal('0.00')

    def test_verified_dealer_receives_dealer_pricing(self, dealer_user_1, dealer_org_1, tier_gold, brake_pads_part):
        # Assign gold tier to apex motors
        DealerPricingService.assign_dealer_tier(
            organisation=dealer_org_1,
            tier_code=DealerTierChoices.GOLD,
            actor=dealer_user_1,
        )

        is_eligible, reason, org, profile, tier = DealerPricingService.evaluate_dealer_eligibility(user=dealer_user_1)
        assert is_eligible is True
        assert reason is None
        assert org == dealer_org_1
        assert tier.code == DealerTierChoices.GOLD

        calc = DealerPricingService.calculate_item_price(
            listing=brake_pads_part,
            quantity=1,
            user=dealer_user_1,
        )
        assert calc["is_dealer_pricing_applied"] is True
        # Gold tier baseline is 15% off (£100 -> £85)
        assert calc["dealer_unit_price"] == Decimal('85.00')
        assert calc["discount_amount_per_unit"] == Decimal('15.00')
        assert calc["applied_tier"] == DealerTierChoices.GOLD

    def test_unverified_or_pending_dealer_denied_pricing(self, dealer_user_1, dealer_org_1, brake_pads_part):
        profile = DealerPricingService.get_or_provision_dealer_profile(dealer_org_1, user=dealer_user_1)
        profile.status = DealerOrganisationStatusChoices.PENDING
        profile.is_verified_dealer = False
        profile.save()

        is_eligible, reason, org, profile, tier = DealerPricingService.evaluate_dealer_eligibility(user=dealer_user_1)
        assert is_eligible is False
        assert "pending" in reason.lower() or "not verified" in reason.lower()

        calc = DealerPricingService.calculate_item_price(
            listing=brake_pads_part,
            quantity=1,
            user=dealer_user_1,
        )
        assert calc["is_dealer_pricing_applied"] is False
        assert calc["dealer_unit_price"] == Decimal('100.00')

    def test_suspended_dealer_denied_pricing(self, dealer_user_1, dealer_org_1, brake_pads_part):
        profile = DealerPricingService.get_or_provision_dealer_profile(dealer_org_1, user=dealer_user_1)
        profile.status = DealerOrganisationStatusChoices.SUSPENDED
        profile.save()

        is_eligible, reason, org, profile, tier = DealerPricingService.evaluate_dealer_eligibility(user=dealer_user_1)
        assert is_eligible is False
        assert "suspended" in reason.lower()

        calc = DealerPricingService.calculate_item_price(
            listing=brake_pads_part,
            quantity=1,
            user=dealer_user_1,
        )
        assert calc["is_dealer_pricing_applied"] is False
        assert calc["dealer_unit_price"] == Decimal('100.00')

    def test_user_cannot_access_another_organisations_pricing(self, ordinary_buyer, dealer_org_1, brake_pads_part):
        # Buyer attempts to pass Apex Motors org ID
        is_eligible, reason, org, profile, tier = DealerPricingService.evaluate_dealer_eligibility(
            user=ordinary_buyer,
            organisation_id=dealer_org_1.id,
        )
        assert is_eligible is False
        assert "access denied" in reason.lower()

        calc = DealerPricingService.calculate_item_price(
            listing=brake_pads_part,
            quantity=1,
            user=ordinary_buyer,
            organisation_id=dealer_org_1.id,
        )
        assert calc["is_dealer_pricing_applied"] is False
        assert calc["dealer_unit_price"] == Decimal('100.00')


# =============================================================================
# 2. Rule Precedence and Calculation Engine Tests
# =============================================================================

@pytest.mark.django_db
class TestRulePrecedenceAndCalculations:

    def test_precedence_hierarchy_full_chain(
        self,
        admin_user,
        dealer_user_1,
        dealer_org_1,
        tier_silver,
        tier_gold,
        brake_pads_part,
        category_brakes,
    ):
        """
        Tests the authoritative 5-level precedence hierarchy:
        1. Org-specific product price
        2. Org-specific category rule
        3. Tier-level product/category rule
        4. Quantity-based dealer volume discount
        5. Baseline tier default discount
        """
        # Assign Apex Motors to Gold tier
        DealerPricingService.assign_dealer_tier(
            organisation=dealer_org_1,
            tier_code=DealerTierChoices.GOLD,
            actor=admin_user,
        )

        # Baseline: Gold tier gives 15% off (£100 -> £85)
        calc_lvl5 = DealerPricingService.calculate_item_price(
            listing=brake_pads_part,
            quantity=1,
            user=dealer_user_1,
        )
        assert calc_lvl5["precedence_level"] == 5
        assert calc_lvl5["dealer_unit_price"] == Decimal('85.00')

        # Add Precedence 4: Quantity-based volume break (Qty 10+ gets 20% off)
        rule_qty_10 = DealerPricingRule.objects.create(
            name='Volume Break 10+ Units 20% off',
            dealer_tier=tier_gold,
            min_quantity=10,
            discount_percentage=Decimal('20.00'),
            created_by=admin_user,
            updated_by=admin_user,
        )
        # At qty 1, still level 5
        assert DealerPricingService.calculate_item_price(listing=brake_pads_part, quantity=5, user=dealer_user_1)["precedence_level"] == 5
        # At qty 10, triggers level 4 (£100 -> £80)
        calc_lvl4 = DealerPricingService.calculate_item_price(listing=brake_pads_part, quantity=10, user=dealer_user_1)
        assert calc_lvl4["precedence_level"] == 4
        assert calc_lvl4["dealer_unit_price"] == Decimal('80.00')

        # Add Precedence 3: Gold tier category rule for Braking Systems (25% off)
        rule_tier_cat = DealerPricingRule.objects.create(
            name='Gold Brakes Category 25% off',
            dealer_tier=tier_gold,
            category=category_brakes,
            min_quantity=1,
            discount_percentage=Decimal('25.00'),
            created_by=admin_user,
            updated_by=admin_user,
        )
        calc_lvl3 = DealerPricingService.calculate_item_price(listing=brake_pads_part, quantity=10, user=dealer_user_1)
        assert calc_lvl3["precedence_level"] == 3
        assert calc_lvl3["dealer_unit_price"] == Decimal('75.00')  # 25% off £100

        # Add Precedence 2: Organisation-specific category rule for Apex Motors (30% off)
        rule_org_cat = DealerPricingRule.objects.create(
            name='Apex Motors Brakes Category 30% off',
            organisation=dealer_org_1,
            category=category_brakes,
            min_quantity=1,
            discount_percentage=Decimal('30.00'),
            created_by=admin_user,
            updated_by=admin_user,
        )
        calc_lvl2 = DealerPricingService.calculate_item_price(listing=brake_pads_part, quantity=10, user=dealer_user_1)
        assert calc_lvl2["precedence_level"] == 2
        assert calc_lvl2["dealer_unit_price"] == Decimal('70.00')  # 30% off £100

        # Add Precedence 1: Organisation-specific exact product fixed price (£60.00)
        rule_org_prod = DealerPricingRule.objects.create(
            name='Apex Motors Brembo Pads Special Contract',
            rule_type=DealerPricingRuleTypeChoices.FIXED_PRICE,
            organisation=dealer_org_1,
            part_listing=brake_pads_part,
            min_quantity=1,
            fixed_price=Decimal('60.00'),
            created_by=admin_user,
            updated_by=admin_user,
        )
        calc_lvl1 = DealerPricingService.calculate_item_price(listing=brake_pads_part, quantity=10, user=dealer_user_1)
        assert calc_lvl1["precedence_level"] == 1
        assert calc_lvl1["dealer_unit_price"] == Decimal('60.00')
        assert calc_lvl1["discount_amount_per_unit"] == Decimal('40.00')

    def test_quantity_breaks_schedule_and_stepping(
        self,
        admin_user,
        dealer_user_1,
        dealer_org_1,
        tier_standard,
        oil_filter_part,
    ):
        """
        Verifies quantity tier stepped breaks:
        1-4 units: retail (£20.00) or tier base
        5-9 units: 10% off (£18.00)
        10-24 units: 20% off (£16.00)
        25+ units: fixed price £12.00
        """
        DealerPricingService.assign_dealer_tier(
            organisation=dealer_org_1,
            tier_code=DealerTierChoices.STANDARD,
            actor=admin_user,
        )

        DealerPricingRule.objects.create(
            name='Filters 5-9 units',
            part_listing=oil_filter_part,
            min_quantity=5,
            max_quantity=9,
            discount_percentage=Decimal('10.00'),
            created_by=admin_user,
        )
        DealerPricingRule.objects.create(
            name='Filters 10-24 units',
            part_listing=oil_filter_part,
            min_quantity=10,
            max_quantity=24,
            discount_percentage=Decimal('20.00'),
            created_by=admin_user,
        )
        DealerPricingRule.objects.create(
            name='Filters 25+ units',
            rule_type=DealerPricingRuleTypeChoices.FIXED_PRICE,
            part_listing=oil_filter_part,
            min_quantity=25,
            fixed_price=Decimal('12.00'),
            created_by=admin_user,
        )

        # Quantity 3 -> Standard tier 5% (£19.00)
        res_3 = DealerPricingService.calculate_item_price(listing=oil_filter_part, quantity=3, user=dealer_user_1)
        assert res_3["dealer_unit_price"] == Decimal('19.00')

        # Quantity 7 -> 10% off (£18.00)
        res_7 = DealerPricingService.calculate_item_price(listing=oil_filter_part, quantity=7, user=dealer_user_1)
        assert res_7["dealer_unit_price"] == Decimal('18.00')

        # Quantity 15 -> 20% off (£16.00)
        res_15 = DealerPricingService.calculate_item_price(listing=oil_filter_part, quantity=15, user=dealer_user_1)
        assert res_15["dealer_unit_price"] == Decimal('16.00')

        # Quantity 30 -> Fixed £12.00
        res_30 = DealerPricingService.calculate_item_price(listing=oil_filter_part, quantity=30, user=dealer_user_1)
        assert res_30["dealer_unit_price"] == Decimal('12.00')

    def test_minimum_order_quantity_enforcement(
        self,
        admin_user,
        dealer_user_1,
        dealer_org_1,
        tier_gold,
        brake_pads_part,
    ):
        DealerPricingService.assign_dealer_tier(dealer_org_1, DealerTierChoices.GOLD, admin_user)

        # Rule with MOQ = 5
        DealerPricingRule.objects.create(
            name='Pads Wholesale MOQ 5',
            part_listing=brake_pads_part,
            min_quantity=5,
            discount_percentage=Decimal('30.00'),
            created_by=admin_user,
        )

        # Check with quantity 2
        calc_2 = DealerPricingService.calculate_item_price(listing=brake_pads_part, quantity=2, user=dealer_user_1)
        # MOQ rule does not match for quantity 2; falls back to gold tier baseline
        assert calc_2["dealer_unit_price"] == Decimal('85.00')

        # Check with quantity 5
        calc_5 = DealerPricingService.calculate_item_price(listing=brake_pads_part, quantity=5, user=dealer_user_1)
        assert calc_5["dealer_unit_price"] == Decimal('70.00')
        assert calc_5["moq_satisfied"] is True

    def test_expired_and_inactive_rules_ignored(
        self,
        admin_user,
        dealer_user_1,
        dealer_org_1,
        tier_gold,
        brake_pads_part,
    ):
        DealerPricingService.assign_dealer_tier(dealer_org_1, DealerTierChoices.GOLD, admin_user)

        now = timezone.now()
        # Inactive rule
        DealerPricingRule.objects.create(
            name='Inactive Super Deal 50% off',
            part_listing=brake_pads_part,
            discount_percentage=Decimal('50.00'),
            is_active=False,
            created_by=admin_user,
        )
        # Expired rule
        DealerPricingRule.objects.create(
            name='Expired Black Friday 60% off',
            part_listing=brake_pads_part,
            discount_percentage=Decimal('60.00'),
            start_date=now - timedelta(days=30),
            end_date=now - timedelta(days=5),
            is_active=True,
            created_by=admin_user,
        )

        calc = DealerPricingService.calculate_item_price(listing=brake_pads_part, quantity=1, user=dealer_user_1)
        # Neither rule should apply; falls back to Gold baseline 15% off (£85.00)
        assert calc["dealer_unit_price"] == Decimal('85.00')


# =============================================================================
# 3. Checkout Integration and Immutability Tests
# =============================================================================

@pytest.mark.django_db
class TestCheckoutIntegration:

    def test_checkout_recalculates_price_and_applies_dealer_discount(
        self,
        api_client,
        admin_user,
        dealer_user_1,
        dealer_org_1,
        tier_platinum,
        brake_pads_part,
    ):
        # Assign Platinum tier (20% off: £100 -> £80)
        DealerPricingService.assign_dealer_tier(dealer_org_1, DealerTierChoices.PLATINUM, admin_user)

        api_client.force_authenticate(user=dealer_user_1)

        payload = {
            "items": [
                {
                    "listing_id": str(brake_pads_part.id),
                    "quantity": 2,
                }
            ],
            "shipping_name": "Apex Workshop Ltd",
            "shipping_phone": "+447911123456",
            "shipping_address_line1": "10 Commercial Way",
            "shipping_city": "London",
            "shipping_postal_code": "SW1A 1AA",
            "shipping_country": "United Kingdom",
            "currency": "GBP",
            "payment_method": "ONLINE",
            "organisation_id": str(dealer_org_1.id),
        }

        # 1. Preview calculation
        calc_response = api_client.post('/api/v1/marketplace/orders/calculate/', payload, format='json')
        assert calc_response.status_code == status.HTTP_200_OK
        data = calc_response.data
        assert data["is_dealer_order"] is True
        assert data["dealer_tier"] == DealerTierChoices.PLATINUM
        # 2 units * £80.00 = £160.00 taxable subtotal
        assert data["subtotal_taxable_amount"] == "160.00"
        # Total discount: 2 * £20.00 = £40.00
        assert data["total_discount_amount"] == "40.00"

        # 2. Checkout execution
        checkout_response = api_client.post('/api/v1/marketplace/orders/checkout/', payload, format='json')
        assert checkout_response.status_code == status.HTTP_201_CREATED
        order_data = checkout_response.data["order"]

        order = Order.objects.get(id=order_data["id"])
        assert order.is_dealer_order is True
        assert order.organisation == dealer_org_1
        assert order.total_discount_amount == Decimal('40.00')
        assert order.subtotal_taxable_amount == Decimal('160.00')

        item = order.items.first()
        assert item.unit_price == Decimal('80.00')
        assert item.retail_unit_price == Decimal('100.00')
        assert item.discount_amount == Decimal('20.00')
        assert item.pricing_tier == DealerTierChoices.PLATINUM

    def test_client_price_manipulation_is_rejected_and_overridden(
        self,
        api_client,
        dealer_user_1,
        dealer_org_1,
        brake_pads_part,
    ):
        """Even if client supplies fake unit_price, backend recalculates authoritatively."""
        api_client.force_authenticate(user=dealer_user_1)

        payload = {
            "items": [
                {
                    "listing_id": str(brake_pads_part.id),
                    "quantity": 1,
                    "unit_price": "5.00",  # Fake manipulated price
                }
            ],
            "shipping_name": "Apex Workshop Ltd",
            "shipping_phone": "+447911123456",
            "shipping_address_line1": "10 Commercial Way",
            "shipping_city": "London",
            "shipping_postal_code": "SW1A 1AA",
            "shipping_country": "United Kingdom",
            "currency": "GBP",
            "payment_method": "ONLINE",
            "organisation_id": str(dealer_org_1.id),
        }

        response = api_client.post('/api/v1/marketplace/orders/checkout/', payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        order = Order.objects.get(id=response.data["order"]["id"])
        # Standard tier 5% off £100 -> £95, NOT £5!
        assert order.items.first().unit_price == Decimal('95.00')

    def test_retail_checkout_remains_unaffected(
        self,
        api_client,
        ordinary_buyer,
        brake_pads_part,
    ):
        """Ordinary buyer pays standard retail price £100.00."""
        api_client.force_authenticate(user=ordinary_buyer)

        payload = {
            "items": [
                {
                    "listing_id": str(brake_pads_part.id),
                    "quantity": 1,
                }
            ],
            "shipping_name": "John Buyer",
            "shipping_phone": "+447911123456",
            "shipping_address_line1": "10 Residential Way",
            "shipping_city": "London",
            "shipping_postal_code": "SW1A 1AA",
            "shipping_country": "United Kingdom",
            "currency": "GBP",
            "payment_method": "ONLINE",
        }

        response = api_client.post('/api/v1/marketplace/orders/checkout/', payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        order = Order.objects.get(id=response.data["order"]["id"])
        assert order.is_dealer_order is False
        assert order.total_discount_amount == Decimal('0.00')
        assert order.items.first().unit_price == Decimal('100.00')

    def test_historical_order_immutability(
        self,
        api_client,
        admin_user,
        dealer_user_1,
        dealer_org_1,
        tier_gold,
        brake_pads_part,
    ):
        """Modifying or deleting pricing rules does NOT alter past orders."""
        DealerPricingService.assign_dealer_tier(dealer_org_1, DealerTierChoices.GOLD, admin_user)

        api_client.force_authenticate(user=dealer_user_1)
        payload = {
            "items": [{"listing_id": str(brake_pads_part.id), "quantity": 1}],
            "shipping_name": "Apex Workshop Ltd",
            "shipping_phone": "+447911123456",
            "shipping_address_line1": "10 Commercial Way",
            "shipping_city": "London",
            "shipping_postal_code": "SW1A 1AA",
            "shipping_country": "United Kingdom",
            "currency": "GBP",
            "payment_method": "ONLINE",
            "organisation_id": str(dealer_org_1.id),
        }
        res = api_client.post('/api/v1/marketplace/orders/checkout/', payload, format='json')
        order_id = res.data["order"]["id"]
        order = Order.objects.get(id=order_id)
        assert order.subtotal_taxable_amount == Decimal('85.00')

        # Admin changes tier or pricing rule
        tier = DealerTier.objects.get(code=DealerTierChoices.GOLD)
        tier.default_discount_percentage = Decimal('50.00')
        tier.save()

        # Reload past order: unchanged!
        order.refresh_from_db()
        assert order.subtotal_taxable_amount == Decimal('85.00')
        assert order.items.first().unit_price == Decimal('85.00')


# =============================================================================
# 4. Admin API & Security Tests
# =============================================================================

@pytest.mark.django_db
class TestAdminPricingAPIAndSecurity:

    def test_non_staff_cannot_create_or_modify_pricing_rules(
        self,
        api_client,
        ordinary_buyer,
        dealer_user_1,
        tier_gold,
        brake_pads_part,
    ):
        # Buyer attempt
        api_client.force_authenticate(user=ordinary_buyer)
        res_buyer = api_client.post('/api/v1/marketplace/b2b/pricing-rules/', {
            'name': 'Hacked 99% off',
            'discount_percentage': '99.00',
            'part_listing_id': str(brake_pads_part.id),
        }, format='json')
        assert res_buyer.status_code == status.HTTP_403_FORBIDDEN

        # Dealer attempt
        api_client.force_authenticate(user=dealer_user_1)
        res_dealer = api_client.post('/api/v1/marketplace/b2b/pricing-rules/', {
            'name': 'Dealer self-discount',
            'discount_percentage': '50.00',
            'part_listing_id': str(brake_pads_part.id),
        }, format='json')
        assert res_dealer.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_create_update_and_deactivate_pricing_rules(
        self,
        api_client,
        admin_user,
        tier_gold,
        brake_pads_part,
    ):
        api_client.force_authenticate(user=admin_user)

        # 1. Create rule
        create_res = api_client.post('/api/v1/marketplace/b2b/pricing-rules/', {
            'name': 'Gold Pads 25% off',
            'dealer_tier_id': str(tier_gold.id),
            'part_listing_id': str(brake_pads_part.id),
            'min_quantity': 1,
            'discount_percentage': '25.00',
            'priority': 10,
        }, format='json')
        assert create_res.status_code == status.HTTP_201_CREATED
        rule_id = create_res.data["id"]

        # 2. Update rule
        update_res = api_client.patch(f'/api/v1/marketplace/b2b/pricing-rules/{rule_id}/', {
            'discount_percentage': '30.00',
        }, format='json')
        assert update_res.status_code == status.HTTP_200_OK
        assert update_res.data["discount_percentage"] == "30.00"

        # 3. Deactivate rule
        del_res = api_client.delete(f'/api/v1/marketplace/b2b/pricing-rules/{rule_id}/')
        assert del_res.status_code == status.HTTP_200_OK
        rule = DealerPricingRule.objects.get(id=rule_id)
        assert rule.is_active is False

    def test_admin_can_assign_dealer_tier(
        self,
        api_client,
        admin_user,
        dealer_org_1,
        tier_platinum,
    ):
        api_client.force_authenticate(user=admin_user)

        response = api_client.post(f'/api/v1/marketplace/b2b/organisations/{dealer_org_1.id}/tier/', {
            'tier_code': DealerTierChoices.PLATINUM,
            'notes': 'Enterprise dealer partner verified by operations.',
            'status': 'ACTIVE',
            'is_verified': True,
        }, format='json')
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["tier_details"]["code"] == DealerTierChoices.PLATINUM
        assert data["is_verified_dealer"] is True

        profile = DealerOrganisationProfile.objects.get(organisation=dealer_org_1)
        assert profile.tier.code == DealerTierChoices.PLATINUM
        assert profile.verified_by == admin_user

    def test_b2b_price_quote_endpoint(
        self,
        api_client,
        dealer_user_1,
        dealer_org_1,
        brake_pads_part,
        oil_filter_part,
    ):
        api_client.force_authenticate(user=dealer_user_1)

        payload = {
            "items": [
                {"listing_id": str(brake_pads_part.id), "quantity": 5},
                {"listing_id": str(oil_filter_part.id), "quantity": 10},
            ],
            "organisation_id": str(dealer_org_1.id),
            "currency": "GBP",
            "shipping_country": "GB",
        }

        response = api_client.post('/api/v1/marketplace/b2b/quote/', payload, format='json')
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["is_dealer_eligible"] is True
        assert len(data["items"]) == 2
        assert Decimal(data["total_discount_savings"]) > Decimal('0.00')

    def test_listing_volume_discounts_endpoint(
        self,
        api_client,
        dealer_user_1,
        brake_pads_part,
    ):
        api_client.force_authenticate(user=dealer_user_1)

        response = api_client.get(f'/api/v1/marketplace/b2b/listings/{brake_pads_part.id}/volume-discounts/')
        assert response.status_code == status.HTTP_200_OK
        assert "volume_discount_schedule" in response.data
        assert len(response.data["volume_discount_schedule"]) >= 1

    def test_user_cannot_view_another_organisations_rule_detail(
        self,
        api_client,
        admin_user,
        ordinary_buyer,
        dealer_org_1,
        brake_pads_part,
    ):
        # Create an org-specific confidential rule for Apex Motors
        rule = DealerPricingRule.objects.create(
            name='Confidential Apex Motors Contract',
            organisation=dealer_org_1,
            part_listing=brake_pads_part,
            discount_percentage=Decimal('35.00'),
            created_by=admin_user,
        )

        # Ordinary buyer attempts to view rule details
        api_client.force_authenticate(user=ordinary_buyer)
        response = api_client.get(f'/api/v1/marketplace/b2b/pricing-rules/{rule.id}/')
        assert response.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

        # Admin user can view rule details
        api_client.force_authenticate(user=admin_user)
        response_admin = api_client.get(f'/api/v1/marketplace/b2b/pricing-rules/{rule.id}/')
        assert response_admin.status_code == status.HTTP_200_OK
        assert response_admin.data["id"] == str(rule.id)

    def test_checkout_rejects_unauthorized_organisation_id(
        self,
        api_client,
        ordinary_buyer,
        dealer_org_1,
        brake_pads_part,
    ):
        api_client.force_authenticate(user=ordinary_buyer)
        payload = {
            "items": [{"listing_id": str(brake_pads_part.id), "quantity": 1}],
            "currency": "GBP",
            "shipping_country": "United Kingdom",
            "shipping_address_line1": "10 Downing St",
            "shipping_city": "London",
            "shipping_postal_code": "SW1A 2AA",
            "billing_same_as_shipping": True,
            "place_of_supply": "London",
            "payment_method": "ONLINE",
            "organisation_id": str(dealer_org_1.id),
        }
        response = api_client.post('/api/v1/marketplace/orders/checkout/', payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data.get("code") == "DEALER_ORGANISATION_UNAUTHORIZED"

    def test_tier_product_rule_takes_precedence_over_tier_category_rule(
        self,
        admin_user,
        dealer_user_1,
        dealer_org_1,
        tier_gold,
        brake_pads_part,
        category_brakes,
    ):
        DealerPricingService.assign_dealer_tier(dealer_org_1, DealerTierChoices.GOLD, admin_user)

        # Broad category rule (20% off)
        DealerPricingRule.objects.create(
            name='Tier Category 20%',
            dealer_tier=tier_gold,
            category=category_brakes,
            discount_percentage=Decimal('20.00'),
            priority=50,
            created_by=admin_user,
        )

        # Specific product rule (30% off)
        DealerPricingRule.objects.create(
            name='Tier Product 30%',
            dealer_tier=tier_gold,
            part_listing=brake_pads_part,
            discount_percentage=Decimal('30.00'),
            priority=10,
            created_by=admin_user,
        )

        calc = DealerPricingService.calculate_item_price(listing=brake_pads_part, quantity=1, user=dealer_user_1)
        # Specific product rule wins despite lower priority number
        assert calc["dealer_unit_price"] == Decimal('70.00')
        assert calc["discount_amount_per_unit"] == Decimal('30.00')

    def test_fixed_price_higher_than_retail_is_safely_capped_at_retail(
        self,
        admin_user,
        dealer_user_1,
        dealer_org_1,
        brake_pads_part,
    ):
        # Create a rule with fixed price £150 on £100 retail part
        DealerPricingRule.objects.create(
            name='Anomalous Higher Fixed Price',
            rule_type=DealerPricingRuleTypeChoices.FIXED_PRICE,
            organisation=dealer_org_1,
            part_listing=brake_pads_part,
            fixed_price=Decimal('150.00'),
            created_by=admin_user,
        )
        calc = DealerPricingService.calculate_item_price(
            listing=brake_pads_part,
            quantity=1,
            user=dealer_user_1,
            organisation_id=dealer_org_1,
        )
        # Price must never exceed standard retail £100
        assert calc["dealer_unit_price"] == Decimal('100.00')
        assert calc["discount_amount_per_unit"] == Decimal('0.00')
