import json
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple, Union
from django.conf import settings
from django.db import transaction, models
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied

from apps.identity.models import User, RoleChoices
from apps.organisations.models import (
    Organisation,
    OrganisationMembership,
    OrganisationTypeChoices,
    OrganisationRoleChoices,
)
from apps.onboarding.models import (
    SellerApplication,
    SellerApplicationStatusChoices,
    BusinessTypeChoices,
)
from apps.marketplace.models import (
    SparePartListing,
    VehicleListing,
    ListingStatusChoices,
    DealerTier,
    DealerTierChoices,
    DealerOrganisationProfile,
    DealerOrganisationStatusChoices,
    DealerPricingRule,
    DealerPricingRuleTypeChoices,
)
from apps.marketplace.tax import quantize_currency
from apps.marketplace.pricing import (
    PriceCalculationError,
    resolve_authoritative_unit_price,
    calculate_item_tax_breakdown,
)
from apps.marketplace.services import record_audit_entry

logger = logging.getLogger(__name__)

# Absolute ceiling for any aggregate dealer discount to prevent pricing anomalies
MAX_PERMITTED_DISCOUNT_PERCENTAGE = Decimal('90.00')


class DealerEligibilityError(Exception):
    """Raised when an organisation or user fails dealer eligibility checks."""
    pass


class MinimumOrderQuantityError(Exception):
    """Raised when requested quantity is below the minimum order quantity requirement."""
    def __init__(self, message: str, min_quantity: int, current_quantity: int, listing_name: str = ''):
        super().__init__(message)
        self.message = message
        self.min_quantity = min_quantity
        self.current_quantity = current_quantity
        self.listing_name = listing_name


class DealerPricingService:
    """
    Centralized business service for B2B Dealer Eligibility, Pricing Rules,
    Volume Discounts, and Tier Governance.
    """

    # -------------------------------------------------------------------------
    # 1. Eligibility & Access Control
    # -------------------------------------------------------------------------

    @classmethod
    def get_or_provision_dealer_profile(
        cls,
        organisation: Organisation,
        user: Optional[User] = None,
    ) -> Optional[DealerOrganisationProfile]:
        """
        Retrieves the DealerOrganisationProfile for an organisation.
        If none exists but the organisation has verified trade standing (e.g. DEALER_GROUP
        or approved SellerApplication for dealer/trader roles), provisions a default STANDARD profile.
        """
        profile = getattr(organisation, 'dealer_profile', None)
        if profile:
            return profile

        # Check existing profile in database
        profile = DealerOrganisationProfile.objects.filter(organisation=organisation).select_related('tier').first()
        if profile:
            return profile

        # Evaluate if this organisation qualifies for automatic standard tier provisioning
        is_dealer_org = organisation.type == OrganisationTypeChoices.DEALER_GROUP
        has_approved_dealer_app = False

        if user and user.is_authenticated:
            has_approved_dealer_app = SellerApplication.objects.filter(
                user=user,
                organisation=organisation,
                status=SellerApplicationStatusChoices.APPROVED,
                business_type__in=[
                    BusinessTypeChoices.DEALER,
                    BusinessTypeChoices.PARTS_MERCHANT,
                    BusinessTypeChoices.INDIVIDUAL_TRADER,
                ],
            ).exists()

        if is_dealer_org or has_approved_dealer_app:
            default_tier = cls.get_or_create_default_tier(DealerTierChoices.STANDARD)
            with transaction.atomic():
                profile, _ = DealerOrganisationProfile.objects.get_or_create(
                    organisation=organisation,
                    defaults={
                        'tier': default_tier,
                        'is_verified_dealer': True,
                        'status': DealerOrganisationStatusChoices.ACTIVE,
                        'notes': "Auto-provisioned standard dealer profile based on verified organisation standing.",
                    },
                )
            return profile

        return None

    @classmethod
    def get_or_create_default_tier(cls, code: str = DealerTierChoices.STANDARD) -> DealerTier:
        """Retrieves or creates standard baseline dealer tiers."""
        tier_defaults = {
            DealerTierChoices.STANDARD: {
                'name': 'Standard Dealer',
                'description': 'Baseline verified dealer tier with standard trade discount.',
                'default_discount_percentage': Decimal('5.00'),
                'priority': 10,
            },
            DealerTierChoices.SILVER: {
                'name': 'Silver Dealer',
                'description': 'Silver trade tier with enhanced volume discount privileges.',
                'default_discount_percentage': Decimal('10.00'),
                'priority': 20,
            },
            DealerTierChoices.GOLD: {
                'name': 'Gold Dealer',
                'description': 'Gold trade tier with preferred wholesale margins and priority allocation.',
                'default_discount_percentage': Decimal('15.00'),
                'priority': 30,
            },
            DealerTierChoices.PLATINUM: {
                'name': 'Platinum Dealer',
                'description': 'Top-tier enterprise dealer with maximum volume discounts and custom rates.',
                'default_discount_percentage': Decimal('20.00'),
                'priority': 40,
            },
        }

        tier_info = tier_defaults.get(code, {
            'name': f"{code.title()} Dealer",
            'description': 'Custom dealer tier.',
            'default_discount_percentage': Decimal('0.00'),
            'priority': 0,
        })

        tier, _ = DealerTier.objects.get_or_create(
            code=code,
            defaults={
                'name': tier_info['name'],
                'description': tier_info['description'],
                'default_discount_percentage': tier_info['default_discount_percentage'],
                'priority': tier_info['priority'],
                'is_active': True,
            },
        )
        return tier

    @classmethod
    def evaluate_dealer_eligibility(
        cls,
        user: Optional[User],
        organisation_id: Optional[Union[str, Organisation]] = None,
    ) -> Tuple[bool, Optional[str], Optional[Organisation], Optional[DealerOrganisationProfile], Optional[DealerTier]]:
        """
        Validates whether a user and/or requested organisation is eligible for B2B dealer pricing.

        Rules:
        1. User must be authenticated and active.
        2. Organisation must exist and be active.
        3. If organisation_id is supplied, the requesting user MUST be an active member of that organisation
           with role in (OWNER, ADMIN, MEMBER). Arbitrary organisation IDs are strictly rejected.
        4. If organisation_id is not supplied, the user's primary/active dealer organisation is resolved.
        5. The organisation must be verified and have an ACTIVE (not SUSPENDED, not PENDING) dealer profile.
        6. Ordinary retail buyers without active dealer organisation membership receive (False, reason, ...).

        Returns:
            (is_eligible, reason_if_not, organisation, profile, tier)
        """
        if not user or not user.is_authenticated:
            return False, "User is not authenticated.", None, None, None

        if getattr(user, 'status', None) and user.status != 'ACTIVE':
            return False, "User account is not active.", None, None, None

        target_org = None

        if organisation_id:
            if isinstance(organisation_id, Organisation):
                target_org = organisation_id
            else:
                try:
                    target_org = Organisation.objects.filter(id=organisation_id).first()
                except Exception:
                    return False, "Invalid organisation ID.", None, None, None

            if not target_org:
                return False, f"Organisation '{organisation_id}' not found.", None, None, None

            # Enforce that user is an active member of this exact organisation
            is_member = target_org.memberships.filter(
                user=user,
                is_active=True,
                role__in=[
                    OrganisationRoleChoices.OWNER,
                    OrganisationRoleChoices.ADMIN,
                    OrganisationRoleChoices.MEMBER,
                ],
            ).exists()
            if not is_member:
                return False, "Access denied: You are not an authorized active member of this organisation.", None, None, None
        else:
            # Resolve user's active dealer organisation membership
            active_memberships = OrganisationMembership.objects.filter(
                user=user,
                is_active=True,
                organisation__is_active=True,
                role__in=[
                    OrganisationRoleChoices.OWNER,
                    OrganisationRoleChoices.ADMIN,
                    OrganisationRoleChoices.MEMBER,
                ],
            ).select_related('organisation')

            # Prioritize DEALER_GROUP or an organisation with an active DealerOrganisationProfile
            for m in active_memberships:
                org = m.organisation
                if org.type == OrganisationTypeChoices.DEALER_GROUP or hasattr(org, 'dealer_profile'):
                    target_org = org
                    break

            if not target_org and active_memberships.exists():
                # Check if any membership org has an approved seller application
                for m in active_memberships:
                    if SellerApplication.objects.filter(
                        user=user,
                        organisation=m.organisation,
                        status=SellerApplicationStatusChoices.APPROVED,
                    ).exists():
                        target_org = m.organisation
                        break

        if not target_org:
            return False, "No associated dealer organisation found for this user.", None, None, None

        if not target_org.is_active:
            return False, "Dealer organisation is inactive or deactivated.", target_org, None, None

        profile = cls.get_or_provision_dealer_profile(target_org, user=user)
        if not profile:
            return False, "Organisation does not have a verified dealer trade profile.", target_org, None, None

        if profile.status == DealerOrganisationStatusChoices.SUSPENDED:
            return False, "Dealer organisation trade privileges are currently suspended.", target_org, profile, None

        if profile.status == DealerOrganisationStatusChoices.REJECTED:
            return False, "Dealer organisation verification was rejected.", target_org, profile, None

        if profile.status == DealerOrganisationStatusChoices.PENDING:
            return False, "Dealer organisation is pending verification.", target_org, profile, None

        if not profile.is_verified_dealer:
            return False, "Dealer organisation is not verified.", target_org, profile, None

        tier = profile.tier
        if not tier:
            return False, "Dealer organisation does not have a pricing tier assigned.", target_org, profile, None
        if not tier.is_active:
            return False, f"Assigned dealer tier '{tier.name}' is currently inactive.", target_org, profile, None

        return True, None, target_org, profile, tier

    # -------------------------------------------------------------------------
    # 2. Rule Evaluation and Precedence Engine
    # -------------------------------------------------------------------------

    @classmethod
    def get_rules_for_entity(
        cls,
        organisation: Optional[Organisation] = None,
        tier: Optional[DealerTier] = None,
        currency: Optional[str] = None,
    ) -> List[DealerPricingRule]:
        """
        Fetches all active rules matching the entity context (organisation, tier, general).
        Useful for batch evaluations and preventing N+1 queries on catalog views.
        """
        now = timezone.now()
        rules_qs = DealerPricingRule.objects.filter(
            is_active=True,
        ).filter(
            models.Q(start_date__isnull=True) | models.Q(start_date__lte=now)
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=now)
        )
        if currency:
            rules_qs = rules_qs.filter(models.Q(currency='') | models.Q(currency__iexact=currency))

        entity_q = models.Q(organisation__isnull=True, dealer_tier__isnull=True)
        if organisation:
            entity_q |= models.Q(organisation=organisation)
        if tier:
            entity_q |= models.Q(dealer_tier=tier)

        return list(rules_qs.filter(entity_q).select_related(
            'organisation', 'dealer_tier', 'part_listing', 'vehicle_listing', 'category'
        ).order_by('-priority', 'id'))

    @classmethod
    def get_applicable_rules(
        cls,
        listing: Union[SparePartListing, VehicleListing],
        quantity: int,
        organisation: Optional[Organisation] = None,
        tier: Optional[DealerTier] = None,
        currency: Optional[str] = None,
        rules_pool: Optional[List[DealerPricingRule]] = None,
    ) -> List[DealerPricingRule]:
        """
        Queries all active, currently effective pricing rules matching the listing, quantity, and context.
        """
        now = timezone.now()
        is_part = isinstance(listing, SparePartListing)
        is_vehicle = isinstance(listing, VehicleListing)

        item_currency = (currency or getattr(listing, 'currency', 'GBP') or '').strip().upper()

        if rules_pool is not None:
            matching = []
            for r in rules_pool:
                if not r.is_active:
                    continue
                if r.min_quantity > quantity:
                    continue
                if r.max_quantity is not None and r.max_quantity < quantity:
                    continue
                if r.start_date and r.start_date > now:
                    continue
                if r.end_date and r.end_date < now:
                    continue
                if r.currency and r.currency.upper() != item_currency:
                    continue

                # Entity match
                is_entity_match = (
                    (r.organisation_id is None and r.dealer_tier_id is None)
                    or (organisation and r.organisation_id == organisation.id)
                    or (tier and r.dealer_tier_id == tier.id)
                )
                if not is_entity_match:
                    continue

                # Target match
                if is_part:
                    part_match = (
                        (r.part_listing_id is None and r.category_id is None and r.vehicle_listing_id is None)
                        or (r.part_listing_id == listing.id)
                        or (r.part_listing_id is None and getattr(listing, 'category_id', None) and r.category_id == listing.category_id)
                    )
                    if part_match:
                        matching.append(r)
                elif is_vehicle:
                    vehicle_match = (
                        (r.part_listing_id is None and r.category_id is None and r.vehicle_listing_id is None)
                        or (r.vehicle_listing_id == listing.id)
                    )
                    if vehicle_match:
                        matching.append(r)
            return matching

        rules_qs = DealerPricingRule.objects.filter(
            is_active=True,
            min_quantity__lte=quantity,
        ).filter(
            models.Q(max_quantity__isnull=True) | models.Q(max_quantity__gte=quantity)
        ).filter(
            models.Q(start_date__isnull=True) | models.Q(start_date__lte=now)
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=now)
        ).filter(
            models.Q(currency='') | models.Q(currency__iexact=item_currency)
        )

        # Build target filter: product match, category match, or generic
        target_q = models.Q(part_listing__isnull=True, vehicle_listing__isnull=True, category__isnull=True)
        if is_part:
            target_q |= models.Q(part_listing=listing)
            if getattr(listing, 'category_id', None):
                target_q |= models.Q(category_id=listing.category_id)
        elif is_vehicle:
            target_q |= models.Q(vehicle_listing=listing)

        rules_qs = rules_qs.filter(target_q)

        # Build entity filter: organisation match, tier match, or generic
        entity_q = models.Q(organisation__isnull=True, dealer_tier__isnull=True)
        if organisation:
            entity_q |= models.Q(organisation=organisation)
        if tier:
            entity_q |= models.Q(dealer_tier=tier)

        rules_qs = rules_qs.filter(entity_q).select_related('organisation', 'dealer_tier', 'part_listing', 'vehicle_listing', 'category')

        return list(rules_qs)

    @classmethod
    def resolve_best_rule(
        cls,
        listing: Union[SparePartListing, VehicleListing],
        quantity: int,
        retail_unit_price: Decimal,
        organisation: Optional[Organisation] = None,
        tier: Optional[DealerTier] = None,
        currency: Optional[str] = None,
        discount_cap: Optional[Decimal] = None,
        rules_pool: Optional[List[DealerPricingRule]] = None,
    ) -> Tuple[Optional[DealerPricingRule], int, Decimal, Decimal]:
        """
        Evaluates applicable pricing rules using authoritative precedence:

        Precedence Hierarchy:
        1. Organisation-specific product price (Specific Organisation + Specific Listing)
        2. Organisation-specific category rule (Specific Organisation + Category)
        3. Dealer-tier product or category rule (Dealer Tier + Product/Category)
        4. Quantity-based dealer discount (Quantity break rule for Tier, Organisation, or Global)
        5. Baseline Dealer Tier default discount (if tier configured)
        6. Standard retail price (Fallback: no discount applied)

        Within the same non-empty precedence bucket, the rule with the highest 'priority'
        is selected, breaking ties with the highest calculated discount.

        Returns:
            (winning_rule, precedence_level, unit_price, discount_amount_per_unit)
        """
        is_part = isinstance(listing, SparePartListing)
        applicable_rules = cls.get_applicable_rules(
            listing=listing,
            quantity=quantity,
            organisation=organisation,
            tier=tier,
            currency=currency,
            rules_pool=rules_pool,
        )

        # Classify rules into precedence buckets
        bucket_1: List[DealerPricingRule] = []   # Org-specific product
        bucket_2: List[DealerPricingRule] = []   # Org-specific category
        bucket_3a: List[DealerPricingRule] = []  # Tier product
        bucket_3b: List[DealerPricingRule] = []  # Tier category
        bucket_4: List[DealerPricingRule] = []   # Quantity breaks / generic dealer volume rules

        for r in applicable_rules:
            is_org_match = bool(organisation and r.organisation_id == organisation.id)
            is_tier_match = bool(tier and r.dealer_tier_id == tier.id)
            has_product = bool(r.part_listing_id or r.vehicle_listing_id)
            has_category = bool(is_part and r.category_id and getattr(listing, 'category_id', None) == r.category_id)

            if is_org_match and has_product:
                bucket_1.append(r)
            elif is_org_match and has_category:
                bucket_2.append(r)
            elif is_tier_match and has_product:
                bucket_3a.append(r)
            elif is_tier_match and has_category:
                bucket_3b.append(r)
            else:
                bucket_4.append(r)

        # Helper to compute savings for a rule
        effective_cap = min(discount_cap or MAX_PERMITTED_DISCOUNT_PERCENTAGE, MAX_PERMITTED_DISCOUNT_PERCENTAGE)

        def evaluate_rule_pricing(rule: DealerPricingRule) -> Tuple[Decimal, Decimal]:
            if rule.rule_type == DealerPricingRuleTypeChoices.FIXED_PRICE and rule.fixed_price is not None:
                fixed_unit = quantize_currency(rule.fixed_price)
                if fixed_unit <= Decimal('0.00'):
                    fixed_unit = Decimal('0.01')
                # Safety guard: B2B rule should never increase price above standard retail
                if fixed_unit > retail_unit_price:
                    fixed_unit = retail_unit_price
                disc_amount = max(Decimal('0.00'), retail_unit_price - fixed_unit)
                return fixed_unit, disc_amount
            else:
                pct = min(rule.discount_percentage, effective_cap)
                if pct < Decimal('0.00'):
                    pct = Decimal('0.00')
                disc_amount = quantize_currency(retail_unit_price * (pct / Decimal('100.00')))
                calc_unit = max(Decimal('0.01'), retail_unit_price - disc_amount)
                return calc_unit, disc_amount

        # Evaluate buckets in strict order 1 -> 2 -> 3a -> 3b -> 4
        for precedence_level, bucket in [(1, bucket_1), (2, bucket_2), (3, bucket_3a), (3, bucket_3b), (4, bucket_4)]:
            if bucket:
                # Sort bucket by priority DESC, then discount amount DESC
                def sort_key(rule: DealerPricingRule):
                    _, disc = evaluate_rule_pricing(rule)
                    return (rule.priority, disc)

                sorted_rules = sorted(bucket, key=sort_key, reverse=True)
                winning_rule = sorted_rules[0]
                unit_price, discount_unit = evaluate_rule_pricing(winning_rule)
                return winning_rule, precedence_level, unit_price, discount_unit

        # Precedence 5: Check baseline tier default discount
        if tier and tier.default_discount_percentage > Decimal('0.00'):
            pct = min(tier.default_discount_percentage, effective_cap)
            disc_amount = quantize_currency(retail_unit_price * (pct / Decimal('100.00')))
            calc_unit = max(Decimal('0.01'), retail_unit_price - disc_amount)
            return None, 5, calc_unit, disc_amount

        # Precedence 6: Standard retail fallback
        return None, 6, retail_unit_price, Decimal('0.00')

    # -------------------------------------------------------------------------
    # 3. Comprehensive Item Price Calculation
    # -------------------------------------------------------------------------

    @classmethod
    def calculate_item_price(
        cls,
        listing: Union[SparePartListing, VehicleListing],
        quantity: int = 1,
        user: Optional[User] = None,
        organisation_id: Optional[Union[str, Organisation]] = None,
        destination_currency: Optional[str] = None,
        destination_country: Optional[str] = None,
        rules_pool: Optional[List[DealerPricingRule]] = None,
    ) -> Dict[str, Any]:
        """
        Calculates authoritative pricing for an item, taking into account dealer eligibility,
        tier ranking, quantity breaks, and rule precedence.

        Guarantees:
        - Completely backend-calculated.
        - Strict Decimal arithmetic; no floating-point arithmetic.
        - Discounts are applied before tax calculation.
        - MOQ violations are surfaced explicitly.
        - Never produces negative unit prices.
        """
        if quantity <= 0:
            quantity = 1

        target_currency = (destination_currency or getattr(listing, 'currency', 'GBP') or 'GBP').strip().upper()

        # 1. Resolve authoritative retail base price
        retail_unit_price, orig_currency, is_converted = resolve_authoritative_unit_price(
            listing=listing,
            destination_currency=target_currency,
            destination_country=destination_country,
        )

        # 2. Evaluate Dealer Eligibility
        is_eligible, reason, org, profile, tier = cls.evaluate_dealer_eligibility(
            user=user,
            organisation_id=organisation_id,
        )

        custom_cap = profile.custom_discount_cap if profile else None

        if not is_eligible:
            # Non-dealer or ineligible user receives standard retail pricing
            return {
                "retail_unit_price": retail_unit_price,
                "dealer_unit_price": retail_unit_price,
                "quantity": quantity,
                "subtotal_taxable_amount": quantize_currency(retail_unit_price * quantity),
                "discount_amount_per_unit": Decimal('0.00'),
                "total_discount_amount": Decimal('0.00'),
                "discount_percentage": Decimal('0.00'),
                "is_dealer_pricing_applied": False,
                "ineligibility_reason": reason,
                "applied_tier": None,
                "applied_tier_name": None,
                "applied_rule": None,
                "applied_rule_id": None,
                "applied_rule_name": None,
                "precedence_level": 6,
                "minimum_order_quantity": 1,
                "moq_satisfied": True,
                "currency": target_currency,
                "organisation_id": None,
                "organisation_name": None,
            }

        # 3. Check Minimum Order Quantity across applicable rules
        # First check if there is an explicit MOQ configured for this item/category
        applicable_rules = cls.get_applicable_rules(
            listing=listing,
            quantity=quantity,
            organisation=org,
            tier=tier,
            currency=target_currency,
            rules_pool=rules_pool,
        )

        # 4. Resolve Best Rule & Precedence
        winning_rule, precedence_level, dealer_unit_price, discount_amount_per_unit = cls.resolve_best_rule(
            listing=listing,
            quantity=quantity,
            retail_unit_price=retail_unit_price,
            organisation=org,
            tier=tier,
            currency=target_currency,
            discount_cap=custom_cap,
            rules_pool=rules_pool,
        )

        # Calculate discount percentage relative to retail unit price
        if retail_unit_price > Decimal('0.00') and discount_amount_per_unit > Decimal('0.00'):
            discount_pct = quantize_currency((discount_amount_per_unit / retail_unit_price) * Decimal('100.00'))
        else:
            discount_pct = Decimal('0.00')

        total_discount = quantize_currency(discount_amount_per_unit * quantity)
        subtotal_taxable = quantize_currency(dealer_unit_price * quantity)

        # Determine effective MOQ from winning rule
        moq = winning_rule.min_quantity if winning_rule else 1
        moq_satisfied = quantity >= moq

        is_discount_applied = discount_amount_per_unit > Decimal('0.00')

        return {
            "retail_unit_price": retail_unit_price,
            "dealer_unit_price": dealer_unit_price,
            "quantity": quantity,
            "subtotal_taxable_amount": subtotal_taxable,
            "discount_amount_per_unit": discount_amount_per_unit,
            "total_discount_amount": total_discount,
            "discount_percentage": discount_pct,
            "is_dealer_pricing_applied": is_discount_applied,
            "ineligibility_reason": None,
            "applied_tier": tier.code if tier else None,
            "applied_tier_name": tier.name if tier else None,
            "applied_rule": winning_rule,
            "applied_rule_id": str(winning_rule.id) if winning_rule else None,
            "applied_rule_name": winning_rule.name if winning_rule else None,
            "precedence_level": precedence_level,
            "minimum_order_quantity": moq,
            "moq_satisfied": moq_satisfied,
            "currency": target_currency,
            "organisation_id": str(org.id) if org else None,
            "organisation_name": org.name if org else None,
        }

    # -------------------------------------------------------------------------
    # 4. Volume Discount & Quantity Break Inspection
    # -------------------------------------------------------------------------

    @classmethod
    def get_listing_volume_discount_schedule(
        cls,
        listing: Union[SparePartListing, VehicleListing],
        user: Optional[User] = None,
        organisation_id: Optional[Union[str, Organisation]] = None,
        destination_currency: Optional[str] = None,
        destination_country: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Returns all configured quantity breaks and volume discounts for a listing
        tailored to the requesting user/dealer organisation.
        """
        is_eligible, _, org, profile, tier = cls.evaluate_dealer_eligibility(
            user=user,
            organisation_id=organisation_id,
        )

        target_currency = (destination_currency or getattr(listing, 'currency', 'GBP') or 'GBP').strip().upper()
        retail_unit_price, _, _ = resolve_authoritative_unit_price(
            listing=listing,
            destination_currency=target_currency,
            destination_country=destination_country,
        )

        # Sample standard quantities and query explicit rules
        sample_quantities = {1, 5, 10, 25, 50, 100}

        # Also pull all min_quantity thresholds from active rules for this listing
        now = timezone.now()
        rules_qs = DealerPricingRule.objects.filter(
            is_active=True,
        ).filter(
            models.Q(start_date__isnull=True) | models.Q(start_date__lte=now)
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=now)
        ).filter(
            models.Q(currency='') | models.Q(currency__iexact=target_currency)
        )

        target_q = models.Q(part_listing__isnull=True, vehicle_listing__isnull=True, category__isnull=True)
        if isinstance(listing, SparePartListing):
            target_q |= models.Q(part_listing=listing)
            if getattr(listing, 'category_id', None):
                target_q |= models.Q(category_id=listing.category_id)
        elif isinstance(listing, VehicleListing):
            target_q |= models.Q(vehicle_listing=listing)

        rules_qs = rules_qs.filter(target_q)
        for r in rules_qs.values_list('min_quantity', flat=True):
            sample_quantities.add(r)

        schedule: List[Dict[str, Any]] = []
        seen_breaks = set()

        for qty in sorted(sample_quantities):
            calc = cls.calculate_item_price(
                listing=listing,
                quantity=qty,
                user=user,
                organisation_id=organisation_id,
                destination_currency=target_currency,
                destination_country=destination_country,
            )

            break_key = (calc["dealer_unit_price"], calc["discount_percentage"])
            if break_key not in seen_breaks or qty == 1:
                seen_breaks.add(break_key)
                schedule.append({
                    "min_quantity": qty,
                    "retail_unit_price": str(calc["retail_unit_price"]),
                    "dealer_unit_price": str(calc["dealer_unit_price"]),
                    "discount_percentage": str(calc["discount_percentage"]),
                    "discount_amount_per_unit": str(calc["discount_amount_per_unit"]),
                    "is_dealer_pricing_applied": calc["is_dealer_pricing_applied"],
                    "applied_tier": calc["applied_tier"],
                    "applied_rule_name": calc["applied_rule_name"],
                    "currency": target_currency,
                })

        return schedule

    # -------------------------------------------------------------------------
    # 5. Administrative Management & Audit
    # -------------------------------------------------------------------------

    @classmethod
    def request_dealer_verification(
        cls,
        organisation: Organisation,
        applicant: User,
        business_data: Dict[str, Any],
    ) -> DealerOrganisationProfile:
        """
        Allows an authorized organisation member (OWNER or ADMIN) to submit a dealer verification application.
        Captures business information in profile notes metadata and transitions status to PENDING.
        """
        if not applicant or not applicant.is_authenticated:
            raise PermissionDenied("Authentication required.")

        # Check organisation membership and role
        is_admin_or_owner = applicant.is_superuser or applicant.is_staff or organisation.memberships.filter(
            user=applicant,
            is_active=True,
            role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
        ).exists()

        if not is_admin_or_owner:
            raise PermissionDenied("Only organisation OWNER or ADMIN can submit a dealer verification request.")

        if not organisation.is_active:
            raise ValidationError("Cannot submit application for an inactive organisation.")

        # Prevent duplicate pending or already active applications
        profile = getattr(organisation, 'dealer_profile', None)
        if not profile:
            profile = DealerOrganisationProfile.objects.filter(organisation=organisation).first()

        if profile:
            if profile.status == DealerOrganisationStatusChoices.PENDING:
                raise ValidationError("A dealer verification application is already pending review for this organisation.")
            if profile.status == DealerOrganisationStatusChoices.ACTIVE and profile.is_verified_dealer:
                raise ValidationError("This organisation is already an active verified dealer.")

        # Validate regional business inputs
        tax_id = str(business_data.get('tax_id', '')).strip()
        reg_number = str(business_data.get('company_registration_number', '')).strip()
        website_url = str(business_data.get('website_url', '')).strip()
        contact_email = str(business_data.get('contact_email', '')).strip() or applicant.email
        contact_phone = str(business_data.get('contact_phone', '')).strip()
        applicant_notes = str(business_data.get('notes', '')).strip()
        requested_tier = str(business_data.get('requested_tier', 'STANDARD')).strip()

        # If country is India and tax_id is provided, validate GSTIN structure
        if organisation.country in ('IN', 'INDIA') and tax_id:
            from platform_core.regional import derive_jurisdiction_from_tax_id
            gst_jurisdiction = derive_jurisdiction_from_tax_id(tax_id, 'IN')
            if not gst_jurisdiction:
                raise ValidationError({"tax_id": f"Invalid Indian GSTIN format '{tax_id}'."})

        app_meta = {
            "company_registration_number": reg_number,
            "tax_id": tax_id,
            "website_url": website_url,
            "contact_email": contact_email,
            "contact_phone": contact_phone,
            "applicant_notes": applicant_notes,
            "requested_tier": requested_tier,
            "submitted_by_id": str(applicant.id),
            "submitted_by_name": getattr(applicant, 'full_name', '') or applicant.email,
            "submitted_at": timezone.now().isoformat(),
            "rejection_reason": "",
        }

        with transaction.atomic():
            if not profile:
                profile = DealerOrganisationProfile.objects.create(
                    organisation=organisation,
                    tier=None,
                    is_verified_dealer=False,
                    status=DealerOrganisationStatusChoices.PENDING,
                    notes=json.dumps(app_meta),
                )
            else:
                profile.tier = None
                profile.is_verified_dealer = False
                profile.status = DealerOrganisationStatusChoices.PENDING
                profile.verified_at = None
                profile.verified_by = None
                profile.notes = json.dumps(app_meta)
                profile.save()

            record_audit_entry(
                event_type="b2b.dealer.application_submitted",
                action="b2b:dealer.apply",
                resource_type="DealerOrganisationProfile",
                resource_id=str(profile.id),
                actor_id=applicant.id,
                metadata={
                    "organisation_id": str(organisation.id),
                    "organisation_name": organisation.name,
                    "applicant_id": str(applicant.id),
                    "status": DealerOrganisationStatusChoices.PENDING,
                },
            )

        return profile

    @classmethod
    def review_dealer_application(
        cls,
        profile: DealerOrganisationProfile,
        reviewer: User,
        action: str,
        rejection_reason: str = '',
        tier_code: str = 'STANDARD',
        admin_notes: str = '',
        custom_discount_cap: Optional[Decimal] = None,
    ) -> DealerOrganisationProfile:
        """
        Approve or reject a dealer application with mandatory audit logging and reviewer attribution.
        """
        if not reviewer or not reviewer.is_authenticated:
            raise PermissionDenied("Authentication required.")

        # Reviewer cannot be applicant / member of the organisation unless platform admin/superuser
        is_member = profile.organisation.is_member(reviewer)
        is_creator = profile.organisation.created_by_id == reviewer.id
        if (is_member or is_creator) and not (reviewer.is_platform_admin or reviewer.is_superuser):
            raise ValidationError("Applicants cannot review their own organisation's dealer application.")

        action = action.upper().strip()
        if action not in ('APPROVE', 'REJECT'):
            raise ValidationError(f"Invalid review action '{action}'. Supported actions are APPROVE or REJECT.")

        if profile.status not in (DealerOrganisationStatusChoices.PENDING, DealerOrganisationStatusChoices.SUSPENDED, DealerOrganisationStatusChoices.REJECTED):
            raise ValidationError(f"Only applications in PENDING status can be reviewed (current status: {profile.status}).")

        meta = profile.get_application_data()

        with transaction.atomic():
            if action == 'APPROVE':
                tier = DealerTier.objects.filter(code=tier_code).first()
                if not tier and tier_code in DealerTierChoices.values:
                    tier = cls.get_or_create_default_tier(tier_code)
                if not tier:
                    raise ValidationError(f"Selected tier '{tier_code}' does not exist.")
                if not tier.is_active:
                    raise ValidationError(f"Selected tier '{tier_code}' is currently inactive and cannot be assigned.")

                profile.is_verified_dealer = True
                profile.status = DealerOrganisationStatusChoices.ACTIVE
                profile.tier = tier
                profile.verified_at = timezone.now()
                profile.verified_by = reviewer
                if custom_discount_cap is not None:
                    profile.custom_discount_cap = custom_discount_cap

                meta['rejection_reason'] = ''
                meta['reviewed_by_id'] = str(reviewer.id)
                meta['reviewed_by_name'] = getattr(reviewer, 'full_name', '') or reviewer.email
                meta['reviewed_at'] = timezone.now().isoformat()
                meta['admin_notes'] = admin_notes
                profile.notes = json.dumps(meta)
                profile.save()

                # Ensure organisation type reflects DEALER_GROUP if currently individual
                if profile.organisation.type == OrganisationTypeChoices.INDIVIDUAL:
                    profile.organisation.type = OrganisationTypeChoices.DEALER_GROUP
                    profile.organisation.save(update_fields=['type'])

                record_audit_entry(
                    event_type="b2b.dealer.approved",
                    action="b2b:dealer.approve",
                    resource_type="DealerOrganisationProfile",
                    resource_id=str(profile.id),
                    actor_id=reviewer.id,
                    metadata={
                        "organisation_id": str(profile.organisation.id),
                        "organisation_name": profile.organisation.name,
                        "tier_code": tier.code,
                        "status": DealerOrganisationStatusChoices.ACTIVE,
                    },
                )
            else:
                # Reject
                clean_reason = (rejection_reason or '').strip()
                if not clean_reason:
                    raise ValidationError({'rejection_reason': 'A rejection reason is required when rejecting an application.'})

                profile.is_verified_dealer = False
                profile.status = DealerOrganisationStatusChoices.REJECTED
                profile.tier = None
                profile.verified_at = timezone.now()
                profile.verified_by = reviewer

                meta['rejection_reason'] = clean_reason
                meta['reviewed_by_id'] = str(reviewer.id)
                meta['reviewed_by_name'] = getattr(reviewer, 'full_name', '') or reviewer.email
                meta['reviewed_at'] = timezone.now().isoformat()
                meta['admin_notes'] = admin_notes
                profile.notes = json.dumps(meta)
                profile.save()

                record_audit_entry(
                    event_type="b2b.dealer.rejected",
                    action="b2b:dealer.reject",
                    resource_type="DealerOrganisationProfile",
                    resource_id=str(profile.id),
                    actor_id=reviewer.id,
                    metadata={
                        "organisation_id": str(profile.organisation.id),
                        "organisation_name": profile.organisation.name,
                        "rejection_reason": clean_reason,
                        "status": DealerOrganisationStatusChoices.REJECTED,
                    },
                )

        return profile

    @classmethod
    def assign_dealer_tier(
        cls,
        organisation: Organisation,
        tier_code: str,
        actor: User,
        notes: str = '',
        status: str = DealerOrganisationStatusChoices.ACTIVE,
        is_verified: bool = True,
        custom_discount_cap: Optional[Decimal] = None,
    ) -> DealerOrganisationProfile:
        """
        Assigns or updates the dealer tier for an organisation with mandatory audit logging.
        Validates that the selected tier exists and is active.
        """
        tier = DealerTier.objects.filter(code=tier_code).first()
        if not tier and tier_code in DealerTierChoices.values:
            tier = cls.get_or_create_default_tier(tier_code)
        if not tier:
            raise ValidationError(f"Dealer tier '{tier_code}' does not exist.")
        if not tier.is_active:
            raise ValidationError(f"Dealer tier '{tier_code}' is currently inactive and cannot be assigned.")

        with transaction.atomic():
            profile, created = DealerOrganisationProfile.objects.get_or_create(
                organisation=organisation,
                defaults={
                    'tier': tier,
                    'status': status,
                    'is_verified_dealer': is_verified,
                    'notes': notes,
                    'custom_discount_cap': custom_discount_cap,
                    'verified_at': timezone.now() if is_verified else None,
                    'verified_by': actor if is_verified else None,
                },
            )

            if not created:
                old_tier = profile.tier.code if profile.tier else None
                profile.tier = tier
                profile.status = status
                profile.is_verified_dealer = is_verified
                if custom_discount_cap is not None:
                    profile.custom_discount_cap = custom_discount_cap
                if notes:
                    profile.notes = notes
                if is_verified and not profile.verified_at:
                    profile.verified_at = timezone.now()
                    profile.verified_by = actor
                profile.save()

            record_audit_entry(
                event_type="b2b.dealer_tier.assigned",
                action="b2b:dealer_tier.assign",
                resource_type="DealerOrganisationProfile",
                resource_id=str(profile.id),
                actor_id=actor.id,
                metadata={
                    "organisation_id": str(organisation.id),
                    "organisation_name": organisation.name,
                    "tier_code": tier.code,
                    "status": status,
                    "is_verified": is_verified,
                },
            )

        return profile

        return profile

    @classmethod
    def create_pricing_rule(cls, data: Dict[str, Any], actor: User) -> DealerPricingRule:
        """
        Creates a new DealerPricingRule with validation and audit logging.
        """
        with transaction.atomic():
            rule = DealerPricingRule(
                name=data.get('name', '').strip(),
                rule_type=data.get('rule_type', DealerPricingRuleTypeChoices.PERCENTAGE_DISCOUNT),
                organisation_id=data.get('organisation_id'),
                dealer_tier_id=data.get('dealer_tier_id'),
                part_listing_id=data.get('part_listing_id'),
                vehicle_listing_id=data.get('vehicle_listing_id'),
                category_id=data.get('category_id'),
                min_quantity=data.get('min_quantity', 1),
                max_quantity=data.get('max_quantity'),
                discount_percentage=Decimal(str(data.get('discount_percentage', '0.00'))),
                fixed_price=Decimal(str(data['fixed_price'])) if data.get('fixed_price') is not None else None,
                currency=(data.get('currency', '') or '').strip().upper(),
                priority=data.get('priority', 0),
                start_date=data.get('start_date'),
                end_date=data.get('end_date'),
                is_active=data.get('is_active', True),
                created_by=actor,
                updated_by=actor,
            )
            rule.full_clean()
            rule.save()

            record_audit_entry(
                event_type="b2b.pricing_rule.created",
                action="b2b:pricing_rule.create",
                resource_type="DealerPricingRule",
                resource_id=str(rule.id),
                actor_id=actor.id,
                metadata={
                    "rule_name": rule.name,
                    "rule_type": rule.rule_type,
                    "discount_percentage": str(rule.discount_percentage),
                    "min_quantity": rule.min_quantity,
                    "priority": rule.priority,
                },
            )

        return rule

    @classmethod
    def update_pricing_rule(cls, rule: DealerPricingRule, data: Dict[str, Any], actor: User) -> DealerPricingRule:
        """
        Updates an existing DealerPricingRule with validation and audit logging.
        """
        with transaction.atomic():
            if 'name' in data:
                rule.name = str(data['name']).strip()
            if 'rule_type' in data:
                rule.rule_type = data['rule_type']
            if 'organisation_id' in data:
                rule.organisation_id = data['organisation_id']
            if 'dealer_tier_id' in data:
                rule.dealer_tier_id = data['dealer_tier_id']
            if 'part_listing_id' in data:
                rule.part_listing_id = data['part_listing_id']
            if 'vehicle_listing_id' in data:
                rule.vehicle_listing_id = data['vehicle_listing_id']
            if 'category_id' in data:
                rule.category_id = data['category_id']
            if 'min_quantity' in data:
                rule.min_quantity = data['min_quantity']
            if 'max_quantity' in data:
                rule.max_quantity = data['max_quantity']
            if 'discount_percentage' in data:
                rule.discount_percentage = Decimal(str(data['discount_percentage']))
            if 'fixed_price' in data:
                rule.fixed_price = Decimal(str(data['fixed_price'])) if data['fixed_price'] is not None else None
            if 'currency' in data:
                rule.currency = (data['currency'] or '').strip().upper()
            if 'priority' in data:
                rule.priority = data['priority']
            if 'start_date' in data:
                rule.start_date = data['start_date']
            if 'end_date' in data:
                rule.end_date = data['end_date']
            if 'is_active' in data:
                rule.is_active = bool(data['is_active'])

            rule.updated_by = actor
            rule.full_clean()
            rule.save()

            record_audit_entry(
                event_type="b2b.pricing_rule.updated",
                action="b2b:pricing_rule.update",
                resource_type="DealerPricingRule",
                resource_id=str(rule.id),
                actor_id=actor.id,
                metadata={
                    "rule_name": rule.name,
                    "is_active": rule.is_active,
                    "discount_percentage": str(rule.discount_percentage),
                },
            )

        return rule
