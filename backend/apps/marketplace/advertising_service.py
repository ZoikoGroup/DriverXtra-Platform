"""
Core business logic, state machine, and payment orchestration for Sponsored Listings and Advertising Campaigns.

Phase 7.2:
- Enforces strict role-based access and dealership boundaries.
- Prevents unapproved or inactive inventory from receiving sponsored placement.
- Integrates with Stripe (UK) and Razorpay (India) via PaymentService.
- Manages whole-day pro-rata refund calculations and immutable audit records.
- Implements session-based de-duplication for impression and click tracking.
"""

import datetime
import hashlib
import logging
import uuid
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple

from django.conf import settings
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction, models
from django.db.models import F
from django.utils import timezone

from apps.identity.models import User
from apps.organisations.models import Organisation, OrganisationMembership, OrganisationRoleChoices
from apps.marketplace.models import (
    AdvertisingCampaign,
    SponsoredListing,
    CampaignPayment,
    CampaignRefundOperation,
    CampaignRefundStatusChoices,
    CampaignImpression,
    CampaignClick,
    CampaignDailyMetric,
    CampaignStatusChoices,
    CampaignPaymentStatusChoices,
    CampaignTypeChoices,
    VehicleListing,
    SparePartListing,
    ListingStatusChoices,
    PaymentTransaction,
)
from apps.marketplace.advertising_pricing import (
    calculate_campaign_pricing,
    calculate_pro_rata_refund,
    normalize_advertising_country,
    is_live_advertising_payment_authorized,
    is_live_advertising_charge_authorized,
    is_live_advertising_refund_authorized,
)
from apps.notifications.services import create_notification
from platform_core.audit.writer import record_audit_entry

logger = logging.getLogger(__name__)


class AdvertisingOrderAdapter:
    """Adapter class presenting an AdvertisingCampaign as an Order-compatible object for payment providers."""
    def __init__(self, campaign: AdvertisingCampaign):
        self.id = campaign.id
        self.order_number = f"AD-{campaign.id.hex[:12].upper()}"
        self.currency = campaign.currency
        self.total_amount = Decimal(campaign.total_budget_minor) / Decimal(100)
        self.buyer = campaign.seller
        first_name = getattr(campaign.seller, 'first_name', '') or ''
        last_name = getattr(campaign.seller, 'last_name', '') or ''
        full_name = f"{first_name} {last_name}".strip()
        self.shipping_name = full_name or getattr(campaign.seller, 'email', 'Ad Sponsor')
        self.payment_method = 'ONLINE'
        self.payment_status = 'PENDING'
        self.created_at = campaign.created_at
        self.status = 'PENDING'


class AdvertisingCampaignService:
    """Central orchestration service for advertising campaigns and sponsored listings."""

    @classmethod
    def create_campaign(
        cls,
        seller: User,
        data: Optional[Dict[str, Any]] = None,
        title: Optional[str] = None,
        campaign_type: str = CampaignTypeChoices.VEHICLES,
        currency: Optional[str] = None,
        target_country: Optional[str] = None,
        package_code: Optional[str] = None,
        duration_days: Optional[int] = None,
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
        organisation: Optional[Any] = None,
        organisation_id: Optional[str | uuid.UUID] = None,
        description: str = "",
        listing_ids: Optional[List[Any]] = None,
        **kwargs,
    ) -> AdvertisingCampaign:
        """
        Creates a new advertising campaign in DRAFT state.
        Validates ownership, dates, budgets, and initial sponsored listings.
        Supports both dictionary data and explicit keyword arguments.
        """
        if data is None:
            data = {}

        # 1. Title & Campaign Type
        final_title = title if title is not None else data.get('title', '')
        final_title = str(final_title).strip()
        if not final_title:
            raise ValidationError({"title": "Campaign title is required."})

        final_camp_type = campaign_type if campaign_type is not None else data.get('campaign_type', CampaignTypeChoices.VEHICLES)
        if final_camp_type not in CampaignTypeChoices.values:
            raise ValidationError({"campaign_type": f"Invalid campaign type '{final_camp_type}'."})

        # 2. Validate Organisation & Permissions
        org_val = organisation if organisation is not None else (
            organisation_id if organisation_id is not None else data.get('organisation', data.get('organisation_id'))
        )
        org_obj = None
        if org_val:
            if isinstance(org_val, Organisation):
                org_obj = org_val
            else:
                org_obj = Organisation.objects.filter(id=org_val).first()
                if not org_obj:
                    raise ValidationError({"organisation": "Specified dealership organisation not found."})

        if org_obj:
            if not (seller.is_staff or (hasattr(seller, 'has_role') and seller.has_role('ADMIN'))):
                membership = OrganisationMembership.objects.filter(
                    organisation=org_obj,
                    user=seller,
                    is_active=True,
                ).first()
                if not membership or membership.role not in (OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN):
                    raise PermissionDenied("Only organisation OWNER or ADMIN may create campaigns for this dealership.")

        # 3. Validate Dates & Duration
        final_start_date = start_date or data.get('start_date')
        if not final_start_date:
            final_start_date = timezone.localdate()

        final_package_code = package_code or data.get('package_code')
        final_duration_days = duration_days or data.get('duration_days')
        final_end_date = end_date or data.get('end_date')

        if not final_end_date:
            days = 7
            if final_package_code in ('7_DAYS', 'AD_PKG_7D'):
                days = 7
            elif final_package_code in ('14_DAYS', 'AD_PKG_14D'):
                days = 14
            elif final_package_code in ('30_DAYS', 'AD_PKG_30D'):
                days = 30
            elif final_duration_days:
                days = int(final_duration_days)
            final_end_date = final_start_date + datetime.timedelta(days=days - 1)

        today = timezone.localdate()
        if final_start_date < today:
            raise ValidationError({"start_date": "Campaign start_date cannot be in the past."})
        if final_end_date < final_start_date:
            raise ValidationError({"end_date": "Campaign end_date cannot be earlier than start_date."})

        # 4. Currency & Pricing Calculation
        final_currency = currency or data.get('currency')
        if not final_currency:
            final_currency = 'INR' if (org_obj and org_obj.country == 'IN') else 'GBP'
        final_currency = str(final_currency).strip().upper()

        country_code = target_country or data.get('target_country')
        if not country_code:
            country_code = org_obj.country if org_obj else ('IN' if final_currency == 'INR' else 'GB')

        pricing = calculate_campaign_pricing(
            start_date=final_start_date,
            end_date=final_end_date,
            currency=final_currency,
            package_code=final_package_code,
            country_code=country_code,
            duration_days=final_duration_days,
        )

        final_description = description if description is not None else data.get('description', '')

        # 5. Atomic Campaign & Sponsored Listings Creation
        with transaction.atomic():
            campaign = AdvertisingCampaign.objects.create(
                title=final_title,
                description=str(final_description).strip(),
                seller=seller,
                organisation=org_obj,
                campaign_type=final_camp_type,
                status=CampaignStatusChoices.DRAFT,
                start_date=final_start_date,
                end_date=final_end_date,
                currency=pricing['currency'],
                total_budget_minor=pricing.get('total_budget_minor') or pricing.get('total_amount_minor', 0),
                daily_rate_minor=pricing['daily_rate_minor'],
                package_code=pricing['package_code'],
                payment_status=CampaignPaymentStatusChoices.UNPAID,
            )

            # Attach initial listings if supplied
            listings_to_attach = listing_ids or data.get('listing_ids', [])
            if listings_to_attach:
                cls.attach_listings(campaign=campaign, listing_ids=listings_to_attach, user=seller)

        record_audit_entry(
            event_type="advertising.campaign.created",
            action="advertising:create",
            resource_type="AdvertisingCampaign",
            resource_id=str(campaign.id),
            actor_id=seller.id,
            operating_org_id=campaign.organisation_id,
            metadata={
                "title": campaign.title,
                "campaign_type": campaign.campaign_type,
                "total_budget_minor": campaign.total_budget_minor,
                "duration_days": campaign.duration_days,
            },
        )
        return campaign

    @classmethod
    def attach_listings(
        cls,
        campaign: AdvertisingCampaign,
        arg2: Any = None,
        arg3: Any = None,
        listing_ids: Optional[List[Any]] = None,
        seller: Optional[User] = None,
        user: Optional[User] = None,
        **kwargs,
    ) -> List[SponsoredListing]:
        """
        Attaches approved, active listings to a campaign.
        Enforces ownership and ensures listing type matches campaign type.
        Supports both positional and keyword calling conventions:
        (campaign, listing_ids, user) or (campaign, seller, listing_ids).
        """
        if campaign.status not in (CampaignStatusChoices.DRAFT, CampaignStatusChoices.PENDING_APPROVAL):
            raise ValidationError("Listings can only be modified while campaign is in DRAFT or PENDING_APPROVAL.")

        # Resolve target listings and acting user
        if isinstance(arg2, (list, tuple, set)):
            target_ids = list(arg2)
            acting_user = arg3 or user or seller or campaign.seller
        elif hasattr(arg2, 'id') and not isinstance(arg2, (str, uuid.UUID)):
            acting_user = arg2
            target_ids = list(arg3 or listing_ids or [])
        else:
            target_ids = list(listing_ids or (arg2 if isinstance(arg2, (list, tuple)) else []))
            acting_user = user or seller or arg3 or campaign.seller

        created_entries = []
        with transaction.atomic():
            for lid in target_ids:
                if campaign.campaign_type == CampaignTypeChoices.VEHICLES:
                    v_listing = VehicleListing.objects.filter(id=lid).first()
                    if not v_listing:
                        raise ValidationError(f"Vehicle listing {lid} not found.")
                    if v_listing.status != ListingStatusChoices.APPROVED or not v_listing.is_active:
                        raise ValidationError(f"Vehicle '{v_listing.title}' cannot be sponsored because it is not APPROVED or active.")
                    # Ownership validation
                    if campaign.organisation_id:
                        if v_listing.organisation_id != campaign.organisation_id:
                            raise PermissionDenied(f"Vehicle {lid} does not belong to dealership {campaign.organisation.name}.")
                    elif v_listing.seller_id != acting_user.id and not (acting_user.is_staff or (hasattr(acting_user, 'has_role') and acting_user.has_role('ADMIN'))):
                        raise PermissionDenied(f"You do not own vehicle listing {lid}.")

                    entry, _ = SponsoredListing.objects.get_or_create(
                        campaign=campaign,
                        vehicle_listing=v_listing,
                        defaults={'is_active': True},
                    )
                    created_entries.append(entry)

                elif campaign.campaign_type == CampaignTypeChoices.SPARE_PARTS:
                    p_listing = SparePartListing.objects.filter(id=lid).first()
                    if not p_listing:
                        raise ValidationError(f"Spare part listing {lid} not found.")
                    if p_listing.status != ListingStatusChoices.APPROVED or not p_listing.is_active:
                        raise ValidationError(f"Part '{p_listing.name}' cannot be sponsored because it is not APPROVED or active.")
                    # Ownership validation
                    if campaign.organisation_id:
                        if p_listing.organisation_id != campaign.organisation_id:
                            raise PermissionDenied(f"Part {lid} does not belong to dealership {campaign.organisation.name}.")
                    elif p_listing.seller_id != acting_user.id and not (acting_user.is_staff or (hasattr(acting_user, 'has_role') and acting_user.has_role('ADMIN'))):
                        raise PermissionDenied(f"You do not own spare part listing {lid}.")

                    entry, _ = SponsoredListing.objects.get_or_create(
                        campaign=campaign,
                        part_listing=p_listing,
                        defaults={'is_active': True},
                    )
                    created_entries.append(entry)

        return created_entries

    @classmethod
    def submit_campaign(cls, campaign: AdvertisingCampaign, seller: User) -> AdvertisingCampaign:
        """Transitions a DRAFT campaign to PENDING_APPROVAL."""
        if campaign.status != CampaignStatusChoices.DRAFT:
            raise ValidationError(f"Only DRAFT campaigns may be submitted. Current status: '{campaign.status}'.")

        # Must have at least one sponsored item
        if not campaign.sponsored_listings.filter(is_active=True).exists():
            raise ValidationError("A campaign must contain at least one sponsored listing before submission.")

        # Re-verify that all attached items remain approved and active
        for item in campaign.sponsored_listings.filter(is_active=True):
            if not item.is_eligible_for_serving and not (
                item.target_listing and item.target_listing.status == ListingStatusChoices.APPROVED and item.target_listing.is_active
            ):
                raise ValidationError(f"Item '{item}' is no longer approved or active. Please update your selection.")

        campaign.status = CampaignStatusChoices.PENDING_APPROVAL
        campaign.save(update_fields=['status', 'updated_at'])

        audit_entry = record_audit_entry(
            event_type="advertising.campaign.submitted",
            action="advertising:submit",
            resource_type="AdvertisingCampaign",
            resource_id=str(campaign.id),
            actor_id=seller.id,
            operating_org_id=campaign.organisation_id,
        )

        if campaign.seller:
            create_notification(
                recipient=campaign.seller,
                audit_entry=audit_entry,
                title="Advertising Campaign Submitted",
                message=f"Campaign '{campaign.title}' has been submitted for staff review.",
                resource_type="AdvertisingCampaign",
                resource_id=str(campaign.id),
            )

        return campaign

    @classmethod
    def approve_campaign(
        cls,
        campaign: AdvertisingCampaign,
        staff_user: User,
        review_notes: str = "",
        approval_notes: Optional[str] = None,
        **kwargs,
    ) -> AdvertisingCampaign:
        """
        Staff approves a campaign in PENDING_APPROVAL.
        Transitions to APPROVED (or PAYMENT_PENDING).
        """
        if campaign.status != CampaignStatusChoices.PENDING_APPROVAL:
            raise ValidationError(f"Campaign in state '{campaign.status}' cannot be approved.")

        # Anti-self-approval rule
        if campaign.seller_id == staff_user.id and not staff_user.is_superuser:
            raise PermissionDenied("Self-approval violation: Staff cannot approve or reject their own advertising campaign.")

        notes = approval_notes if approval_notes is not None else review_notes
        campaign.status = CampaignStatusChoices.APPROVED
        campaign.approved_by = staff_user
        campaign.approved_at = timezone.now()
        campaign.review_notes = notes
        campaign.rejection_reason = ""
        campaign.save(update_fields=['status', 'approved_by', 'approved_at', 'review_notes', 'rejection_reason', 'updated_at'])

        audit_entry = record_audit_entry(
            event_type="advertising.campaign.approved",
            action="advertising:approve",
            resource_type="AdvertisingCampaign",
            resource_id=str(campaign.id),
            actor_id=staff_user.id,
            operating_org_id=campaign.organisation_id,
            metadata={"approved_by": staff_user.email},
        )

        if campaign.seller:
            create_notification(
                recipient=campaign.seller,
                audit_entry=audit_entry,
                title="Advertising Campaign Approved!",
                message=f"Your campaign '{campaign.title}' has been approved. Please complete payment to activate.",
                resource_type="AdvertisingCampaign",
                resource_id=str(campaign.id),
            )

        return campaign

    @classmethod
    def reject_campaign(
        cls,
        campaign: AdvertisingCampaign,
        staff_user: User,
        rejection_reason: str = "",
        reason: Optional[str] = None,
        **kwargs,
    ) -> AdvertisingCampaign:
        """Staff rejects a campaign with a mandatory reason."""
        if campaign.status not in (CampaignStatusChoices.PENDING_APPROVAL, CampaignStatusChoices.APPROVED):
            raise ValidationError(f"Campaign in state '{campaign.status}' cannot be rejected.")

        # Anti-self-approval rule
        if campaign.seller_id == staff_user.id and not staff_user.is_superuser:
            raise PermissionDenied("Self-approval violation: Staff cannot approve or reject their own advertising campaign.")

        clean_reason = str(rejection_reason or reason or '').strip()
        if not clean_reason:
            raise ValidationError({"rejection_reason": "A detailed rejection reason is mandatory."})

        campaign.status = CampaignStatusChoices.REJECTED
        campaign.rejection_reason = clean_reason
        campaign.approved_by = staff_user
        campaign.approved_at = timezone.now()
        campaign.save(update_fields=['status', 'rejection_reason', 'approved_by', 'approved_at', 'updated_at'])

        # If already paid prior to review, initiate full 100% refund
        if campaign.payment_status == CampaignPaymentStatusChoices.PAID:
            cls.refund_campaign(campaign, refund_minor=campaign.total_budget_minor, reason=f"Staff Rejection: {clean_reason}")

        audit_entry = record_audit_entry(
            event_type="advertising.campaign.rejected",
            action="advertising:reject",
            resource_type="AdvertisingCampaign",
            resource_id=str(campaign.id),
            actor_id=staff_user.id,
            operating_org_id=campaign.organisation_id,
            metadata={"rejection_reason": clean_reason},
        )

        if campaign.seller:
            create_notification(
                recipient=campaign.seller,
                audit_entry=audit_entry,
                title="Advertising Campaign Rejected",
                message=f"Your campaign '{campaign.title}' was rejected: {clean_reason}",
                resource_type="AdvertisingCampaign",
                resource_id=str(campaign.id),
            )

        return campaign

    @classmethod
    def create_payment_session(
        cls,
        campaign: AdvertisingCampaign,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates an authoritative payment session/order via Stripe or Razorpay provider.
        Campaign must be in APPROVED or PAYMENT_PENDING state.
        """
        if campaign.status not in (CampaignStatusChoices.APPROVED, CampaignStatusChoices.PAYMENT_PENDING):
            raise ValidationError(
                f"Campaign must be APPROVED before payment can be initiated. Current status: '{campaign.status}'."
            )

        if campaign.payment_status == CampaignPaymentStatusChoices.PAID:
            raise ValidationError("Campaign has already been paid for.")

        from apps.marketplace.payments.stripe_provider import StripePaymentProvider
        from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider

        order_adapter = AdvertisingOrderAdapter(campaign)

        if campaign.currency.upper() == 'INR':
            provider = RazorpayPaymentProvider()
        elif campaign.currency.upper() == 'GBP':
            provider = StripePaymentProvider()
        else:
            raise ValidationError(f"Unsupported currency for advertising payment: '{campaign.currency}'.")

        is_live = not getattr(provider, 'test_mode', True)
        if is_live and not is_live_advertising_charge_authorized():
            raise ValidationError("Live commercial advertising payments are disabled pending formal tax and compliance signoff.")

        session_data = provider.create_payment_session(order_adapter, return_url=return_url, cancel_url=cancel_url)

        campaign.status = CampaignStatusChoices.PAYMENT_PENDING
        campaign.payment_status = CampaignPaymentStatusChoices.PENDING
        campaign.save(update_fields=['status', 'payment_status', 'updated_at'])

        return {
            "campaign_id": str(campaign.id),
            "provider": session_data.get('provider', 'UNKNOWN'),
            "currency": campaign.currency,
            "amount_minor": campaign.total_budget_minor,
            "session_data": session_data,
        }

    @classmethod
    def record_successful_payment(
        cls,
        campaign_id: str | uuid.UUID,
        provider: str,
        gateway_reference: str,
        gateway_payment_id: str,
        amount_minor: int,
        currency: str,
        raw_response: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        is_live: bool = False,
    ) -> CampaignPayment:
        """
        Records a verified payment from Stripe or Razorpay webhook.
        Transitions campaign to SCHEDULED (if start_date > today) or ACTIVE (if start_date <= today),
        provided live commercial advertising payments are authorized.
        """
        with transaction.atomic():
            campaign = AdvertisingCampaign.objects.select_for_update().filter(id=campaign_id).first()
            if not campaign:
                raise ValidationError(f"Campaign {campaign_id} not found.")

            # Idempotency check: if payment with this gateway_payment_id already exists and is PAID, return early
            existing_payment = CampaignPayment.objects.filter(
                gateway_payment_id=gateway_payment_id,
                payment_status=CampaignPaymentStatusChoices.PAID,
            ).first()
            if existing_payment:
                logger.info("Payment %s for campaign %s already recorded. Skipping duplicate.", gateway_payment_id, campaign_id)
                return existing_payment

            # Validate currency and amount
            if currency.strip().upper() != campaign.currency.strip().upper():
                raise ValidationError(f"Payment currency mismatch: expected '{campaign.currency}', received '{currency}'.")

            if amount_minor < campaign.total_budget_minor:
                raise ValidationError(
                    f"Underpayment detected: expected {campaign.total_budget_minor} minor units, received {amount_minor}."
                )

            # Create CampaignPayment record
            payment = CampaignPayment.objects.create(
                campaign=campaign,
                provider=provider.strip().upper(),
                gateway_reference=gateway_reference,
                gateway_payment_id=gateway_payment_id,
                amount_minor=amount_minor,
                currency=currency.strip().upper(),
                payment_status=CampaignPaymentStatusChoices.PAID,
                idempotency_key=idempotency_key or str(uuid.uuid4()),
                paid_at=timezone.now(),
                raw_response=raw_response or {},
            )

            campaign.payment_status = CampaignPaymentStatusChoices.PAID
            campaign.payment_reference = gateway_payment_id

            # Determine activation state
            today = timezone.localdate()
            activation_held = is_live and not is_live_advertising_charge_authorized()
            if activation_held:
                logger.warning(
                    "Payment recorded for campaign %s, but activation withheld because LIVE_ADVERTISING_CHARGES_ENABLED is False.",
                    campaign.id,
                )
                # Keep campaign status non-active (e.g. PAYMENT_PENDING) until formal compliance signoff
            else:
                if campaign.status in (CampaignStatusChoices.APPROVED, CampaignStatusChoices.PAYMENT_PENDING):
                    if campaign.start_date <= today <= campaign.end_date:
                        campaign.status = CampaignStatusChoices.ACTIVE
                    elif campaign.start_date > today:
                        campaign.status = CampaignStatusChoices.SCHEDULED
                elif campaign.status == CampaignStatusChoices.DRAFT:
                    campaign.status = CampaignStatusChoices.PAYMENT_PENDING

            campaign.save(update_fields=['payment_status', 'payment_reference', 'status', 'updated_at'])

        audit_entry = record_audit_entry(
            event_type="advertising.payment.confirmed" if not activation_held else "advertising.payment.confirmed_activation_held",
            action="advertising:payment",
            resource_type="AdvertisingCampaign",
            resource_id=str(campaign.id),
            actor_id=getattr(campaign.seller, 'id', None),
            operating_org_id=campaign.organisation_id,
            metadata={
                "gateway_payment_id": gateway_payment_id,
                "amount_minor": amount_minor,
                "currency": currency,
                "new_status": campaign.status,
                "is_live": is_live,
                "activation_held": activation_held,
            },
        )

        if campaign.seller:
            create_notification(
                recipient=campaign.seller,
                audit_entry=audit_entry,
                title="Advertising Payment Confirmed",
                message=f"Payment of {currency} {amount_minor / 100:.2f} confirmed for campaign '{campaign.title}'. Status: {campaign.get_status_display()}.",
                resource_type="AdvertisingCampaign",
                resource_id=str(campaign.id),
            )

        return payment

    @classmethod
    def pause_campaign(
        cls,
        campaign: AdvertisingCampaign,
        user: Optional[User] = None,
        actor: Optional[User] = None,
        **kwargs,
    ) -> AdvertisingCampaign:
        """Pauses an active campaign."""
        if campaign.status != CampaignStatusChoices.ACTIVE:
            raise ValidationError(f"Only ACTIVE campaigns can be paused. Current status: '{campaign.status}'.")

        acting_user = actor or user or campaign.seller

        campaign.status = CampaignStatusChoices.PAUSED
        campaign.paused_at = timezone.now()
        campaign.save(update_fields=['status', 'paused_at', 'updated_at'])

        record_audit_entry(
            event_type="advertising.campaign.paused",
            action="advertising:pause",
            resource_type="AdvertisingCampaign",
            resource_id=str(campaign.id),
            actor_id=acting_user.id if acting_user else None,
            operating_org_id=campaign.organisation_id,
        )
        return campaign

    @classmethod
    def resume_campaign(
        cls,
        campaign: AdvertisingCampaign,
        user: Optional[User] = None,
        actor: Optional[User] = None,
        **kwargs,
    ) -> AdvertisingCampaign:
        """Resumes a paused campaign."""
        if campaign.status != CampaignStatusChoices.PAUSED:
            raise ValidationError(f"Only PAUSED campaigns can be resumed. Current status: '{campaign.status}'.")

        acting_user = actor or user or campaign.seller

        today = timezone.localdate()
        if today > campaign.end_date:
            campaign.status = CampaignStatusChoices.COMPLETED
            campaign.completed_at = timezone.now()
        elif campaign.start_date <= today <= campaign.end_date:
            campaign.status = CampaignStatusChoices.ACTIVE
        else:
            campaign.status = CampaignStatusChoices.SCHEDULED

        campaign.save(update_fields=['status', 'completed_at', 'updated_at'])

        record_audit_entry(
            event_type="advertising.campaign.resumed",
            action="advertising:resume",
            resource_type="AdvertisingCampaign",
            resource_id=str(campaign.id),
            actor_id=acting_user.id if acting_user else None,
            operating_org_id=campaign.organisation_id,
            metadata={"new_status": campaign.status},
        )
        return campaign

    @classmethod
    def cancel_campaign(
        cls,
        campaign: AdvertisingCampaign,
        user: Optional[User] = None,
        actor: Optional[User] = None,
        reason: str = "",
        **kwargs,
    ) -> Tuple[AdvertisingCampaign, int]:
        """
        Cancels a campaign and calculates pro-rata refund in integer minor units.
        Returns (campaign, refund_minor).
        """
        if campaign.status in (CampaignStatusChoices.COMPLETED, CampaignStatusChoices.CANCELLED, CampaignStatusChoices.REJECTED):
            raise ValidationError(f"Campaign in state '{campaign.status}' cannot be cancelled.")

        acting_user = actor or user or campaign.seller
        refund_minor = 0
        today = timezone.localdate()

        with transaction.atomic():
            campaign.status = CampaignStatusChoices.CANCELLED
            campaign.cancelled_at = timezone.now()

            # If paid, calculate pro-rata refund
            if campaign.payment_status == CampaignPaymentStatusChoices.PAID:
                refund_minor = calculate_pro_rata_refund(
                    campaign_total_minor=campaign.total_budget_minor,
                    start_date=campaign.start_date,
                    end_date=campaign.end_date,
                    cancellation_date=today,
                )
                if refund_minor > 0:
                    cls.refund_campaign(campaign, refund_minor=refund_minor, reason=reason or "Early Seller Cancellation")
                    campaign.payment_status = (
                        CampaignPaymentStatusChoices.REFUNDED
                        if refund_minor >= campaign.total_budget_minor
                        else CampaignPaymentStatusChoices.PARTIALLY_REFUNDED
                    )

            campaign.save(update_fields=['status', 'cancelled_at', 'payment_status', 'updated_at'])

        audit_entry = record_audit_entry(
            event_type="advertising.campaign.cancelled",
            action="advertising:cancel",
            resource_type="AdvertisingCampaign",
            resource_id=str(campaign.id),
            actor_id=acting_user.id if acting_user else None,
            operating_org_id=campaign.organisation_id,
            metadata={"refund_minor": refund_minor, "reason": reason},
        )

        if campaign.seller:
            create_notification(
                recipient=campaign.seller,
                audit_entry=audit_entry,
                title="Advertising Campaign Cancelled",
                message=f"Campaign '{campaign.title}' has been cancelled. Refund due: {campaign.currency} {refund_minor / 100:.2f}.",
                resource_type="AdvertisingCampaign",
                resource_id=str(campaign.id),
            )

        return campaign, refund_minor

    @classmethod
    def generate_refund_gateway_key(cls, payment_id: str | uuid.UUID, operation_id: str) -> str:
        """
        Derives a deterministic, collision-resistant gateway idempotency key from the complete
        stable operation_id and payment_id.

        Guarantees:
        - Retrying the same operation produces the exact same key.
        - Distinct operation IDs (even those sharing prefixes like 'ref_' or 'wh_') produce distinct keys.
        - Fits within gateway receipt/key constraints (Razorpay 40-character maximum and Stripe headers).
        """
        clean_op = str(operation_id).strip()
        pid_hex = (payment_id.hex if isinstance(payment_id, uuid.UUID) else str(payment_id).replace('-', ''))[:12]
        op_hash = hashlib.sha256(clean_op.encode('utf-8')).hexdigest()[:16]
        return f"ADV-REF-{pid_hex.upper()}-{op_hash.upper()}"

    @classmethod
    def refund_campaign(
        cls,
        campaign: AdvertisingCampaign,
        refund_minor: int,
        reason: str = "",
        operation_id: Optional[str] = None,
    ) -> Optional[CampaignPayment]:
        """
        Executes a gateway refund against the campaign payment and updates the financial ledger.

        Enforces:
        - Valid positive refund amount not exceeding remaining payment balance.
        - Campaign payment ownership verification.
        - Operation-level idempotency to prevent duplicate gateway refund calls.
        - Support for multiple partial refunds of the exact same amount.
        - Strict safety gate: blocks live refunds if LIVE_ADVERTISING_PAYMENTS_ENABLED is False.
        - Real/mock gateway dispatch via StripePaymentProvider or RazorpayPaymentProvider.
        - Atomic status and ledger update on success or error capture on failure.
        """
        if refund_minor <= 0:
            return None

        op_id = (operation_id or f"ref_{uuid.uuid4().hex[:16]}").strip()

        with transaction.atomic():
            payment = (
                campaign.payments.select_for_update()
                .filter(payment_status__in=[
                    CampaignPaymentStatusChoices.PAID,
                    CampaignPaymentStatusChoices.PARTIALLY_REFUNDED,
                ])
                .first()
            )
            if not payment:
                fully_refunded = campaign.payments.filter(payment_status=CampaignPaymentStatusChoices.REFUNDED).first()
                if fully_refunded:
                    logger.info("Campaign %s payment %s is already fully refunded.", campaign.id, fully_refunded.id)
                    return fully_refunded
                logger.warning("No eligible PAID or PARTIALLY_REFUNDED CampaignPayment found for campaign %s to issue refund.", campaign.id)
                return None

            if payment.campaign_id != campaign.id:
                raise ValidationError("Payment does not belong to the target advertising campaign.")

            # Check if this specific operation has already succeeded (idempotency)
            existing_op = CampaignRefundOperation.objects.select_for_update().filter(operation_id=op_id).first()
            if existing_op and existing_op.status == CampaignRefundStatusChoices.SUCCEEDED:
                logger.info(
                    "Refund operation %s of %d minor units already succeeded for payment %s. Skipping duplicate dispatch.",
                    op_id,
                    existing_op.amount_minor,
                    payment.id,
                )
                return payment

            # Calculate cumulative refunded amount so far across succeeded operations
            current_refunded = sum(
                op.amount_minor for op in payment.refund_operations.filter(status=CampaignRefundStatusChoices.SUCCEEDED)
            )
            # Fallback for existing legacy records
            if payment.refund_amount_minor > current_refunded and not payment.refund_operations.exists():
                current_refunded = payment.refund_amount_minor

            remaining_refundable = payment.amount_minor - current_refunded
            if refund_minor > remaining_refundable:
                raise ValidationError(
                    f"Requested refund amount ({refund_minor}) exceeds remaining refundable amount "
                    f"({remaining_refundable}) for payment {payment.id}."
                )

            # Persist pending operation
            if existing_op:
                ref_op = existing_op
                ref_op.status = CampaignRefundStatusChoices.PENDING
                ref_op.amount_minor = refund_minor
                ref_op.reason = reason
                ref_op.save(update_fields=['status', 'amount_minor', 'reason', 'updated_at'])
            else:
                ref_op = CampaignRefundOperation.objects.create(
                    payment=payment,
                    campaign=campaign,
                    operation_id=op_id,
                    amount_minor=refund_minor,
                    status=CampaignRefundStatusChoices.PENDING,
                    reason=reason,
                )

        # Determine gateway provider
        provider_name = (payment.provider or '').upper()
        if not provider_name:
            provider_name = 'STRIPE' if payment.currency == 'GBP' else 'RAZORPAY'

        provider = None
        if provider_name == 'STRIPE':
            from apps.marketplace.payments.stripe_provider import StripePaymentProvider
            provider = StripePaymentProvider()
        elif provider_name == 'RAZORPAY':
            from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider
            provider = RazorpayPaymentProvider()

        # Enforce live advertising refund safety gate
        is_live = provider is not None and not getattr(provider, 'test_mode', True)
        if is_live and not is_live_advertising_refund_authorized():
            ref_op.status = CampaignRefundStatusChoices.FAILED
            ref_op.raw_response = {"error": "Live advertising refunds are disabled pending formal compliance signoff."}
            ref_op.save(update_fields=['status', 'raw_response', 'updated_at'])
            raise ValidationError("Live gateway advertising refunds are disabled pending formal compliance signoff.")

        payment_ref = (payment.gateway_payment_id or payment.gateway_reference or '').strip()
        refund_num = cls.generate_refund_gateway_key(payment.id, ref_op.operation_id)
        amount_decimal = Decimal(refund_minor) / Decimal(100)
        notes = {
            "campaign_id": str(campaign.id),
            "payment_id": str(payment.id),
            "operation_id": ref_op.operation_id,
            "reason": (reason or "Advertising refund")[:255],
        }

        gateway_refund_id = ""
        extra_data = {}

        if provider and payment_ref:
            try:
                success, ref_id_or_err, extra = provider.issue_refund(
                    payment_reference=payment_ref,
                    amount=amount_decimal,
                    currency=payment.currency,
                    reason=reason or "Advertising refund",
                    refund_number=refund_num,
                    notes=notes,
                )
            except Exception as exc:
                logger.exception("Unexpected error during gateway issue_refund for campaign payment %s: %s", payment.id, exc)
                success = False
                ref_id_or_err = f"Gateway communication exception: {str(exc)}"
                extra = {"error": str(exc), "exception_type": exc.__class__.__name__}

            if not success:
                logger.error("Gateway refund dispatch failed for campaign %s: %s", campaign.id, ref_id_or_err)
                ref_op.status = CampaignRefundStatusChoices.FAILED
                ref_op.raw_response = extra
                ref_op.save(update_fields=['status', 'raw_response', 'updated_at'])

                raw = dict(payment.raw_response or {})
                raw["refund_dispatch_error"] = str(ref_id_or_err)
                raw["refund_dispatch_error_extra"] = extra
                payment.raw_response = raw
                payment.save(update_fields=['raw_response', 'updated_at'])
                raise ValidationError(f"Payment gateway refund dispatch failed: {ref_id_or_err}")

            gateway_refund_id = str(ref_id_or_err)
            extra_data = extra
        else:
            gateway_refund_id = f"sim_rfnd_{uuid.uuid4().hex[:12]}"
            extra_data = {"simulated": True, "provider": provider_name}

        with transaction.atomic():
            ref_op = CampaignRefundOperation.objects.select_for_update().get(id=ref_op.id)
            ref_op.status = CampaignRefundStatusChoices.SUCCEEDED
            ref_op.gateway_refund_id = gateway_refund_id
            ref_op.raw_response = extra_data
            ref_op.save(update_fields=['status', 'gateway_refund_id', 'raw_response', 'updated_at'])

            payment = CampaignPayment.objects.select_for_update().get(id=payment.id)
            total_refunded = sum(
                op.amount_minor for op in payment.refund_operations.filter(status=CampaignRefundStatusChoices.SUCCEEDED)
            )
            payment.refund_amount_minor = total_refunded
            payment.refund_reason = reason
            payment.refunded_at = timezone.now()
            payment.payment_status = (
                CampaignPaymentStatusChoices.REFUNDED
                if total_refunded >= payment.amount_minor
                else CampaignPaymentStatusChoices.PARTIALLY_REFUNDED
            )
            raw = dict(payment.raw_response or {})
            raw["gateway_refund_id"] = gateway_refund_id
            raw["latest_gateway_refund_id"] = gateway_refund_id
            raw["latest_refund_operation_id"] = ref_op.operation_id
            payment.raw_response = raw
            payment.save(update_fields=[
                'refund_amount_minor',
                'refund_reason',
                'refunded_at',
                'payment_status',
                'raw_response',
                'updated_at',
            ])

        return payment

    @classmethod
    def reconcile_refund_from_webhook(
        cls,
        campaign: Optional[AdvertisingCampaign],
        payment: Optional[CampaignPayment],
        gateway_refund_id: str,
        refund_amount_minor: int,
        cumulative_amount_refunded_minor: Optional[int] = None,
        raw_payload: Optional[Dict[str, Any]] = None,
        operation_id_hint: Optional[str] = None,
        event_id: str = "",
        reason: str = "Gateway refund reconciled via webhook",
    ) -> Optional[CampaignRefundOperation]:
        """
        Passively reconciles a gateway refund event without dispatching outbound refund API calls.

        Guarantees:
        - NEVER calls provider.issue_refund() or dispatches a new refund to the gateway.
        - Matches existing CampaignRefundOperation by gateway_refund_id, operation_id_hint,
          or pending operation with matching amount.
        - Correctly handles Stripe cumulative amount_refunded without double-counting.
        - Creates a passive CampaignRefundOperation record for external/dashboard refunds.
        - Atomically recalculates cumulative refunded amounts and updates payment/campaign status.
        """
        if not payment and campaign:
            payment = (
                campaign.payments.filter(
                    payment_status__in=[
                        CampaignPaymentStatusChoices.PAID,
                        CampaignPaymentStatusChoices.PARTIALLY_REFUNDED,
                        CampaignPaymentStatusChoices.REFUNDED,
                    ]
                )
                .order_by('-created_at')
                .first()
            )

        if not payment:
            logger.warning(
                "Cannot passively reconcile refund for campaign %s: no eligible CampaignPayment found.",
                getattr(campaign, 'id', None),
            )
            return None

        clean_rfnd_id = str(gateway_refund_id or '').strip()
        clean_op_hint = str(operation_id_hint or '').strip()
        raw_payload = raw_payload or {}

        with transaction.atomic():
            payment = CampaignPayment.objects.select_for_update().get(id=payment.id)
            target_campaign = payment.campaign

            # 1. Match existing operation
            matched_op = None
            if clean_rfnd_id:
                matched_op = payment.refund_operations.select_for_update().filter(gateway_refund_id=clean_rfnd_id).first()
            if not matched_op and clean_op_hint:
                matched_op = payment.refund_operations.select_for_update().filter(operation_id=clean_op_hint).first()
            if not matched_op and refund_amount_minor > 0:
                matched_op = payment.refund_operations.select_for_update().filter(
                    status=CampaignRefundStatusChoices.PENDING,
                    amount_minor=refund_amount_minor,
                ).first()

            if matched_op:
                if matched_op.status == CampaignRefundStatusChoices.SUCCEEDED:
                    logger.info("Refund operation %s already succeeded and recorded.", matched_op.operation_id)
                    return matched_op

                matched_op.status = CampaignRefundStatusChoices.SUCCEEDED
                if clean_rfnd_id and not matched_op.gateway_refund_id:
                    matched_op.gateway_refund_id = clean_rfnd_id
                matched_op.raw_response = raw_payload
                matched_op.save(update_fields=['status', 'gateway_refund_id', 'raw_response', 'updated_at'])
            else:
                # 2. Determine incremental refund amount if out-of-band / external refund
                succeeded_sum = sum(
                    op.amount_minor for op in payment.refund_operations.filter(status=CampaignRefundStatusChoices.SUCCEEDED)
                )
                effective_amount = refund_amount_minor
                if cumulative_amount_refunded_minor is not None and cumulative_amount_refunded_minor > 0:
                    incremental = cumulative_amount_refunded_minor - succeeded_sum
                    if incremental <= 0:
                        logger.info(
                            "Cumulative amount %d minor is already accounted for by existing succeeded operations (%d minor).",
                            cumulative_amount_refunded_minor,
                            succeeded_sum,
                        )
                        return None
                    effective_amount = incremental

                if effective_amount <= 0:
                    return None

                # Derive stable operation_id for external refund
                ext_op_id = f"wh_ext_{clean_rfnd_id}" if clean_rfnd_id else f"wh_ext_{event_id or uuid.uuid4().hex[:12]}"
                existing_ext = CampaignRefundOperation.objects.filter(operation_id=ext_op_id).first()
                if existing_ext:
                    return existing_ext

                matched_op = CampaignRefundOperation.objects.create(
                    payment=payment,
                    campaign=target_campaign,
                    operation_id=ext_op_id,
                    amount_minor=effective_amount,
                    status=CampaignRefundStatusChoices.SUCCEEDED,
                    gateway_refund_id=clean_rfnd_id,
                    reason=reason,
                    raw_response=raw_payload,
                )

            # 3. Recalculate ledger on CampaignPayment
            total_refunded = sum(
                op.amount_minor for op in payment.refund_operations.filter(status=CampaignRefundStatusChoices.SUCCEEDED)
            )
            payment.refund_amount_minor = min(total_refunded, payment.amount_minor)
            payment.refunded_at = timezone.now()
            payment.payment_status = (
                CampaignPaymentStatusChoices.REFUNDED
                if total_refunded >= payment.amount_minor
                else CampaignPaymentStatusChoices.PARTIALLY_REFUNDED
            )
            raw = dict(payment.raw_response or {})
            if clean_rfnd_id:
                raw["latest_gateway_refund_id"] = clean_rfnd_id
            if matched_op:
                raw["latest_refund_operation_id"] = matched_op.operation_id
            payment.raw_response = raw
            payment.save(update_fields=['refund_amount_minor', 'refunded_at', 'payment_status', 'raw_response', 'updated_at'])

            # 4. Synchronize campaign payment_status and status
            target_campaign.payment_status = payment.payment_status
            if payment.payment_status == CampaignPaymentStatusChoices.REFUNDED:
                if target_campaign.status != CampaignStatusChoices.COMPLETED:
                    target_campaign.status = CampaignStatusChoices.CANCELLED
                    target_campaign.cancelled_at = timezone.now()
                    target_campaign.save(update_fields=['payment_status', 'status', 'cancelled_at', 'updated_at'])
                else:
                    target_campaign.save(update_fields=['payment_status', 'updated_at'])
            else:
                target_campaign.save(update_fields=['payment_status', 'updated_at'])

            record_audit_entry(
                event_type="advertising.refund.webhook_reconciled",
                action="advertising:refund.webhook_reconciled",
                resource_type="AdvertisingCampaign",
                resource_id=str(target_campaign.id),
                actor_id=None,
                operating_org_id=target_campaign.organisation_id,
                metadata={
                    "gateway_refund_id": clean_rfnd_id,
                    "operation_id": matched_op.operation_id if matched_op else None,
                    "amount_minor": matched_op.amount_minor if matched_op else 0,
                    "total_refunded_minor": total_refunded,
                    "payment_status": payment.payment_status,
                },
            )

        return matched_op

    # =========================================================================
    # SCHEDULED TASKS & BACKGROUND EXPIRATION
    # =========================================================================

    @classmethod
    def activate_scheduled_campaigns(cls) -> int:
        """Finds SCHEDULED campaigns whose start_date has arrived and activates them."""
        today = timezone.localdate()
        scheduled_qs = AdvertisingCampaign.objects.filter(
            status=CampaignStatusChoices.SCHEDULED,
            payment_status=CampaignPaymentStatusChoices.PAID,
            start_date__lte=today,
            end_date__gte=today,
        )
        activated_count = scheduled_qs.update(
            status=CampaignStatusChoices.ACTIVE,
            updated_at=timezone.now(),
        )
        if activated_count > 0:
            logger.info("Activated %d scheduled advertising campaigns.", activated_count)
        return activated_count

    @classmethod
    def complete_expired_campaigns(cls) -> int:
        """Finds ACTIVE or PAUSED campaigns whose end_date has passed and marks them COMPLETED."""
        today = timezone.localdate()
        expired_qs = AdvertisingCampaign.objects.filter(
            status__in=[CampaignStatusChoices.ACTIVE, CampaignStatusChoices.PAUSED],
            end_date__lt=today,
        )
        completed_count = expired_qs.update(
            status=CampaignStatusChoices.COMPLETED,
            completed_at=timezone.now(),
            updated_at=timezone.now(),
        )
        if completed_count > 0:
            logger.info("Completed %d expired advertising campaigns.", completed_count)
        return completed_count

    @classmethod
    def recover_held_paid_campaigns(cls) -> int:
        """
        Recovers advertising campaigns whose payment was captured/recorded as PAID
        but activation was held in PAYMENT_PENDING during a payment gate shutdown
        or live compliance freeze.

        Safety Rules:
        - When a campaign is live (associated with a live payment/provider), it is ONLY
          recovered if is_live_advertising_charge_authorized() is True.
        - Transitions eligible campaigns based on current date:
          * start_date <= today <= end_date -> ACTIVE
          * start_date > today -> SCHEDULED
          * today > end_date -> COMPLETED (expired campaigns are never activated)
        - Ineligible campaigns are NEVER overwritten (CANCELLED, REJECTED, REFUNDED,
          PARTIALLY_REFUNDED, or non-PAID campaigns remain untouched).
        - Idempotent and safe for repeated execution without duplicate audit logs or duplicate activations.
        """
        today = timezone.localdate()
        is_charge_authorized = is_live_advertising_charge_authorized()

        candidate_ids = list(
            AdvertisingCampaign.objects.filter(
                status=CampaignStatusChoices.PAYMENT_PENDING,
                payment_status=CampaignPaymentStatusChoices.PAID,
            )
            .exclude(
                payments__payment_status__in=[
                    CampaignPaymentStatusChoices.REFUNDED,
                    CampaignPaymentStatusChoices.PARTIALLY_REFUNDED,
                ]
            )
            .exclude(payments__refund_amount_minor__gt=0)
            .values_list('id', flat=True)
            .distinct()
        )

        recovered_count = 0

        for c_id in candidate_ids:
            with transaction.atomic():
                campaign = (
                    AdvertisingCampaign.objects.select_for_update()
                    .filter(
                        id=c_id,
                        status=CampaignStatusChoices.PAYMENT_PENDING,
                        payment_status=CampaignPaymentStatusChoices.PAID,
                    )
                    .first()
                )
                if not campaign:
                    continue

                # Defensive check: ensure no refunds recorded on payments
                has_refund = campaign.payments.filter(
                    models.Q(payment_status__in=[
                        CampaignPaymentStatusChoices.REFUNDED,
                        CampaignPaymentStatusChoices.PARTIALLY_REFUNDED,
                    ]) | models.Q(refund_amount_minor__gt=0)
                ).exists()
                if has_refund:
                    logger.info("Campaign %s has refunds; skipping recovery.", campaign.id)
                    continue

                # Inspect live mode on payments and providers
                is_live = False
                for p in campaign.payments.all():
                    raw = p.raw_response or {}
                    if isinstance(raw, dict):
                        if raw.get('livemode') is True or raw.get('data', {}).get('object', {}).get('livemode') is True:
                            is_live = True
                            break
                    prov = (p.provider or '').upper()
                    if prov == 'STRIPE':
                        from apps.marketplace.payments.stripe_provider import StripePaymentProvider
                        if not getattr(StripePaymentProvider(), 'test_mode', True):
                            is_live = True
                            break
                    elif prov == 'RAZORPAY':
                        from apps.marketplace.payments.razorpay_provider import RazorpayPaymentProvider
                        if not getattr(RazorpayPaymentProvider(), 'test_mode', True):
                            is_live = True
                            break

                if is_live and not is_charge_authorized:
                    logger.info("Live campaign %s recovery held: live advertising charges disabled.", campaign.id)
                    continue

                old_status = campaign.status
                if campaign.start_date <= today <= campaign.end_date:
                    target_status = CampaignStatusChoices.ACTIVE
                elif campaign.start_date > today:
                    target_status = CampaignStatusChoices.SCHEDULED
                else:
                    target_status = CampaignStatusChoices.COMPLETED

                campaign.status = target_status
                update_fields = ['status', 'updated_at']
                if target_status == CampaignStatusChoices.COMPLETED:
                    campaign.completed_at = timezone.now()
                    update_fields.append('completed_at')

                campaign.save(update_fields=update_fields)

                record_audit_entry(
                    event_type="advertising.campaign.recovered",
                    action="advertising:campaign.recovered",
                    resource_type="AdvertisingCampaign",
                    resource_id=str(campaign.id),
                    actor_id=None,
                    operating_org_id=campaign.organisation_id,
                    metadata={
                        "previous_status": old_status,
                        "new_status": target_status,
                        "start_date": str(campaign.start_date),
                        "end_date": str(campaign.end_date),
                        "is_live": is_live,
                    },
                )
                recovered_count += 1

        if recovered_count > 0:
            logger.info("Successfully recovered %d held paid advertising campaigns.", recovered_count)
        return recovered_count

    # =========================================================================
    # IMPRESSION & CLICK TRACKING WITH DE-DUPLICATION
    # =========================================================================

    @classmethod
    def record_impression(
        cls,
        sponsored_listing_id: str | uuid.UUID,
        session_id: str,
        ip_address: Optional[str] = None,
        referrer: str = "",
        user_agent: str = "",
        user: Optional[User] = None,
        **kwargs,
    ) -> Tuple[Optional[CampaignImpression], bool]:
        """
        Records a valid, de-duplicated impression event.
        De-duplicates based on sha256(session_id + sponsored_listing_id + date).
        Returns (impression, created).
        """
        today = timezone.localdate()
        clean_session = str(session_id or '').strip()
        if not clean_session:
            clean_session = str(uuid.uuid4())

        hash_input = f"{clean_session}:{sponsored_listing_id}:{today}"
        session_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

        # Check de-duplication in DB
        existing = CampaignImpression.objects.filter(
            session_hash=session_hash,
            sponsored_listing_id=sponsored_listing_id,
            date=today,
        ).first()
        if existing:
            return existing, False

        sponsored_listing = SponsoredListing.objects.filter(id=sponsored_listing_id, is_active=True).first()
        if not sponsored_listing or not sponsored_listing.campaign.is_currently_promoted:
            return None, False

        with transaction.atomic():
            impression = CampaignImpression.objects.create(
                campaign=sponsored_listing.campaign,
                sponsored_listing=sponsored_listing,
                session_hash=session_hash,
                date=today,
            )
            # Atomically increment counters
            SponsoredListing.objects.filter(id=sponsored_listing.id).update(impressions_count=F('impressions_count') + 1)
            AdvertisingCampaign.objects.filter(id=sponsored_listing.campaign_id).update(impressions_count=F('impressions_count') + 1)

            # Update daily metric aggregate
            metric, _ = CampaignDailyMetric.objects.get_or_create(
                campaign=sponsored_listing.campaign,
                date=today,
            )
            CampaignDailyMetric.objects.filter(id=metric.id).update(impressions=F('impressions') + 1)

        return impression, True

    @classmethod
    def record_click(
        cls,
        sponsored_listing_id: str | uuid.UUID,
        session_id: str,
        ip_address: Optional[str] = None,
        destination_url: str = "",
        user: Optional[User] = None,
        **kwargs,
    ) -> Tuple[Optional[CampaignClick], bool]:
        """
        Records a valid, de-duplicated click event.
        De-duplicates based on sha256(session_id + sponsored_listing_id + date + hour).
        Returns (click, created).
        """
        now = timezone.now()
        today = now.date()
        hour = now.hour
        clean_session = str(session_id or '').strip()
        if not clean_session:
            clean_session = str(uuid.uuid4())

        hash_input = f"{clean_session}:{sponsored_listing_id}:{today}:{hour}"
        session_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

        existing = CampaignClick.objects.filter(
            session_hash=session_hash,
            sponsored_listing_id=sponsored_listing_id,
            date=today,
        ).first()
        if existing:
            return existing, False

        sponsored_listing = SponsoredListing.objects.filter(id=sponsored_listing_id, is_active=True).first()
        if not sponsored_listing or not sponsored_listing.campaign.is_currently_promoted:
            return None, False

        with transaction.atomic():
            click = CampaignClick.objects.create(
                campaign=sponsored_listing.campaign,
                sponsored_listing=sponsored_listing,
                session_hash=session_hash,
                date=today,
            )
            # Atomically increment counters
            SponsoredListing.objects.filter(id=sponsored_listing.id).update(clicks_count=F('clicks_count') + 1)
            AdvertisingCampaign.objects.filter(id=sponsored_listing.campaign_id).update(clicks_count=F('clicks_count') + 1)

            # Update daily metric aggregate
            metric, _ = CampaignDailyMetric.objects.get_or_create(
                campaign=sponsored_listing.campaign,
                date=today,
            )
            CampaignDailyMetric.objects.filter(id=metric.id).update(clicks=F('clicks') + 1)

        return click, True

    # =========================================================================
    # SPONSORED INVENTORY FEED (PUBLIC BROWSE INTEGRATION)
    # =========================================================================

    @classmethod
    def get_sponsored_feed(
        cls,
        listing_type: Optional[str] = None,
        campaign_type: Optional[str] = None,
        target_country: Optional[str] = None,
        country: Optional[str] = None,
        limit: int = 2,
        make_name: Optional[str] = None,
        category_name: Optional[str] = None,
        **kwargs,
    ) -> List[SponsoredListing]:
        """
        Fetches up to `limit` active sponsored items for search result placement.
        Strictly guarantees:
        - Campaign is ACTIVE and PAID.
        - Start and end dates are valid (start_date <= today <= end_date).
        - Underlying inventory is APPROVED and is_active=True.
        - Prevents duplicate items.
        Returns a list of eligible SponsoredListing instances.
        """
        today = timezone.localdate()
        eff_type = (campaign_type or listing_type or CampaignTypeChoices.VEHICLES).strip().upper()

        active_campaigns = AdvertisingCampaign.objects.filter(
            status=CampaignStatusChoices.ACTIVE,
            payment_status=CampaignPaymentStatusChoices.PAID,
            start_date__lte=today,
            end_date__gte=today,
            campaign_type=eff_type,
        )

        entries = (
            SponsoredListing.objects.filter(
                campaign__in=active_campaigns,
                is_active=True,
            )
            .select_related(
                'campaign',
                'vehicle_listing',
                'vehicle_listing__make',
                'vehicle_listing__model',
                'part_listing',
                'part_listing__category',
            )
            .order_by('?')[:limit * 3]
        )

        valid_entries = []
        seen_listing_ids = set()

        for entry in entries:
            if len(valid_entries) >= limit:
                break

            if eff_type == CampaignTypeChoices.VEHICLES:
                v = entry.vehicle_listing
                if not v or v.status != ListingStatusChoices.APPROVED or not v.is_active:
                    continue
                if make_name and v.make and v.make.name.lower() != make_name.lower():
                    continue
                if v.id in seen_listing_ids:
                    continue
                seen_listing_ids.add(v.id)
                valid_entries.append(entry)

            elif eff_type == CampaignTypeChoices.SPARE_PARTS:
                p = entry.part_listing
                if not p or p.status != ListingStatusChoices.APPROVED or not p.is_active:
                    continue
                if category_name and p.category and p.category.name.lower() != category_name.lower():
                    continue
                if p.id in seen_listing_ids:
                    continue
                seen_listing_ids.add(p.id)
                valid_entries.append(entry)

        return valid_entries


generate_campaign_refund_gateway_key = AdvertisingCampaignService.generate_refund_gateway_key
