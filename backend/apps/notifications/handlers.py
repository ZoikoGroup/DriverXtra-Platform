"""Map successful AuditLog business events to in-app notifications.

Recipients are always resolved from the audited resource row (resource_type + resource_id),
never from free-form audit metadata. Events without a reliable recipient are not mapped.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction

from platform_core.audit.models import AuditLog
from apps.notifications.services import create_notification

logger = logging.getLogger(__name__)

# A seller reply is only notified if the enquiry's replied_at was stamped in the same request
# that produced the audit entry (the view saves the reply, then writes the audit row).
REPLY_FRESHNESS_WINDOW = timedelta(minutes=2)


@dataclass
class NotificationSpec:
    recipient: object
    title: str
    message: str
    link: str


def _tab_link(tab: str) -> str:
    return f"/platform?tab={tab}"


def _with_reason(message: str, reason: str) -> str:
    reason = (reason or '').strip()
    return f"{message} Reason: {reason}" if reason else message


# ---------------------------------------------------------------------------
# Resolvers: (audit_entry) -> list[NotificationSpec]
# ---------------------------------------------------------------------------

def _seller_application_decision(entry):
    from apps.onboarding.models import SellerApplication, SellerApplicationStatusChoices

    application = SellerApplication.objects.select_related('user').filter(pk=entry.resource_id).first()
    if application is None:
        return []

    if entry.event_type == 'seller.application.approved':
        if application.status != SellerApplicationStatusChoices.APPROVED:
            return []
        title = "Seller application approved"
        message = f"Your application for '{application.business_name}' has been approved. Seller features are now available on your account."
    else:
        if application.status != SellerApplicationStatusChoices.REJECTED:
            return []
        title = "Seller application rejected"
        message = _with_reason(
            f"Your application for '{application.business_name}' was not approved.",
            application.rejection_reason,
        )
    return [NotificationSpec(application.user, title, message, _tab_link('seller_onboarding'))]


_LISTING_DECISIONS = {
    'listing.approved': ('APPROVED', "Listing approved", "is now live on the marketplace."),
    'listing.rejected': ('REJECTED', "Listing rejected", "was rejected by the review team."),
    'listing.changes_requested': ('CHANGES_REQUESTED', "Changes requested on listing", "needs changes before it can be approved."),
}


def _listing_decision(entry):
    from apps.marketplace.models import VehicleListing, SparePartListing

    if entry.resource_type == 'VehicleListing':
        listing = VehicleListing.objects.select_related('seller').filter(pk=entry.resource_id).first()
        name = listing.title if listing else ''
    elif entry.resource_type == 'SparePartListing':
        listing = SparePartListing.objects.select_related('seller').filter(pk=entry.resource_id).first()
        name = listing.name if listing else ''
    else:
        return []
    if listing is None:
        return []

    expected_status, title, outcome = _LISTING_DECISIONS[entry.event_type]
    if listing.status != expected_status:
        return []
    message = f"Your listing '{name}' {outcome}"
    if expected_status != 'APPROVED':
        message = _with_reason(message, listing.rejection_reason)
    return [NotificationSpec(listing.seller, f"{title}: {name}", message, _tab_link('seller_inventory'))]


_CATALOGUE_APPLICATION_DECISIONS = {
    'catalogue.application.approved': ('APPROVED', "Catalogue application approved", "has been approved and added to the catalogue."),
    'catalogue.application.rejected': ('REJECTED', "Catalogue application rejected", "was rejected."),
    'catalogue.application.changes_requested': ('CHANGES_REQUESTED', "Changes requested on catalogue application", "needs changes."),
}


def _catalogue_application_decision(entry):
    from apps.catalogue.models import VehicleCatalogueApplication

    application = VehicleCatalogueApplication.objects.select_related('seller').filter(pk=entry.resource_id).first()
    if application is None:
        return []
    expected_status, title, outcome = _CATALOGUE_APPLICATION_DECISIONS[entry.event_type]
    if application.status != expected_status:
        return []
    vehicle = f"{application.make_name} {application.model_name}".strip()
    message = f"Your catalogue application for '{vehicle}' {outcome}"
    if expected_status != 'APPROVED':
        message = _with_reason(message, application.rejection_reason)
    return [NotificationSpec(application.seller, title, message, _tab_link('catalogue'))]


_PHOTO_PROPOSAL_DECISIONS = {
    'catalogue.photo_proposal.approved': ('APPROVED', "Catalogue photo approved", "has been approved and is now the catalogue image."),
    'catalogue.photo_proposal.rejected': ('REJECTED', "Catalogue photo rejected", "was rejected."),
}


def _photo_proposal_decision(entry):
    from apps.catalogue.models import CataloguePhotoProposal

    proposal = (
        CataloguePhotoProposal.objects.select_related('seller', 'model', 'model__make')
        .filter(pk=entry.resource_id)
        .first()
    )
    if proposal is None:
        return []
    expected_status, title, outcome = _PHOTO_PROPOSAL_DECISIONS[entry.event_type]
    if proposal.status != expected_status:
        return []
    message = f"Your photo proposal for '{proposal.model}' {outcome}"
    if expected_status != 'APPROVED':
        message = _with_reason(message, proposal.rejection_reason)
    return [NotificationSpec(proposal.seller, title, message, _tab_link('catalogue'))]


def _vehicle_enquiry_created(entry):
    from apps.marketplace.models import VehicleEnquiry

    enquiry = (
        VehicleEnquiry.objects.select_related('seller', 'buyer', 'listing')
        .filter(pk=entry.resource_id)
        .first()
    )
    if enquiry is None or enquiry.seller_id == enquiry.buyer_id:
        return []
    message = f"{enquiry.buyer.full_name} sent an enquiry about '{enquiry.listing.title}'."
    return [NotificationSpec(enquiry.seller, "New vehicle enquiry", message, _tab_link('seller_inventory'))]


def _vehicle_enquiry_updated(entry):
    from apps.marketplace.models import VehicleEnquiry
    from apps.notifications.models import Notification

    # The audit metadata only signals that a reply exists; the reply itself is confirmed from the model.
    if not (entry.metadata or {}).get('has_reply'):
        return []
    enquiry = (
        VehicleEnquiry.objects.select_related('seller', 'buyer', 'listing')
        .filter(pk=entry.resource_id)
        .first()
    )
    if enquiry is None or not (enquiry.seller_reply or '').strip() or enquiry.replied_at is None:
        return []
    # Status/notes-only updates keep the earlier replied_at; only a reply saved in this request is fresh.
    if entry.created_at and enquiry.replied_at < entry.created_at - REPLY_FRESHNESS_WINDOW:
        return []
    already_notified = Notification.objects.filter(
        recipient=enquiry.buyer,
        event_type=entry.event_type,
        resource_id=str(enquiry.id),
        created_at__gte=enquiry.replied_at,
    ).exists()
    if already_notified:
        return []
    message = f"The seller replied to your enquiry about '{enquiry.listing.title}'."
    return [NotificationSpec(enquiry.buyer, "Seller replied to your enquiry", message, _tab_link('my_enquiries'))]


def _org_member_added(entry):
    from apps.organisations.models import OrganisationMembership

    membership = (
        OrganisationMembership.objects.select_related('user', 'organisation')
        .filter(pk=entry.resource_id, is_active=True)
        .first()
    )
    if membership is None or membership.user_id == entry.actor_id:
        return []
    message = f"You were added to '{membership.organisation.name}' as {membership.get_role_display()}."
    return [NotificationSpec(membership.user, "Added to an organisation", message, _tab_link('organisations'))]


EVENT_RESOLVERS = {
    'seller.application.approved': _seller_application_decision,
    'seller.application.rejected': _seller_application_decision,
    'listing.approved': _listing_decision,
    'listing.rejected': _listing_decision,
    'listing.changes_requested': _listing_decision,
    'catalogue.application.approved': _catalogue_application_decision,
    'catalogue.application.rejected': _catalogue_application_decision,
    'catalogue.application.changes_requested': _catalogue_application_decision,
    'catalogue.photo_proposal.approved': _photo_proposal_decision,
    'catalogue.photo_proposal.rejected': _photo_proposal_decision,
    'marketplace.vehicle_enquiry.created': _vehicle_enquiry_created,
    'marketplace.vehicle_enquiry.updated': _vehicle_enquiry_updated,
    'org.member.added': _org_member_added,
}


def process_audit_entry(entry) -> list:
    """Create notifications for one audit entry. Safe to call repeatedly for the same entry."""
    if entry.status != AuditLog.STATUS_ALLOWED:
        return []
    resolver = EVENT_RESOLVERS.get(entry.event_type)
    if resolver is None:
        return []

    created = []
    for spec in resolver(entry):
        notification = create_notification(
            recipient=spec.recipient,
            audit_entry=entry,
            title=spec.title,
            message=spec.message,
            link=spec.link,
        )
        if notification is not None:
            created.append(notification)
    return created


def handle_audit_log_saved(sender, instance, created, raw=False, **kwargs):
    """post_save receiver for AuditLog. Never raises into the business operation."""
    if not created or raw:
        return
    if instance.event_type not in EVENT_RESOLVERS or instance.status != AuditLog.STATUS_ALLOWED:
        return
    try:
        # Savepoint: a failure here rolls back only the notification work, not the caller's transaction.
        with transaction.atomic():
            process_audit_entry(instance)
    except Exception:
        logger.exception(
            "Failed to create notifications for audit entry %s (%s)",
            instance.id,
            instance.event_type,
        )
