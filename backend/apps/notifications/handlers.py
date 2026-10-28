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


# ---------------------------------------------------------------------------
# Workflow Resolvers: Orders & Payments
# ---------------------------------------------------------------------------

def _order_created(entry):
    from apps.marketplace.models import Order

    order = (
        Order.objects.select_related('buyer')
        .prefetch_related('items__listing__seller')
        .filter(pk=entry.resource_id)
        .first()
    )
    if order is None:
        return []

    specs = []
    if order.buyer:
        specs.append(
            NotificationSpec(
                recipient=order.buyer,
                title=f"Order Placed: {order.order_number}",
                message=f"Your order {order.order_number} for {order.currency} {order.total_amount} has been placed successfully.",
                link=_tab_link('my_orders'),
            )
        )

    notified_sellers = set()
    for item in order.items.all():
        seller = getattr(getattr(item, 'listing', None), 'seller', None)
        if seller and seller.id != order.buyer_id and seller.id not in notified_sellers:
            notified_sellers.add(seller.id)
            specs.append(
                NotificationSpec(
                    recipient=seller,
                    title=f"New Order Received: {order.order_number}",
                    message=f"You have received a new customer order {order.order_number}.",
                    link=_tab_link('seller_orders'),
                )
            )

    return specs


def _order_payment_verified(entry):
    from apps.marketplace.models import Order

    order = Order.objects.select_related('buyer').filter(pk=entry.resource_id).first()
    if order is None or not order.buyer:
        return []

    return [
        NotificationSpec(
            recipient=order.buyer,
            title=f"Payment Verified: {order.order_number}",
            message=f"Payment of {order.currency} {order.total_amount} for order {order.order_number} was successfully verified.",
            link=_tab_link('my_orders'),
        )
    ]


def _order_payment_verification_failed(entry):
    from apps.marketplace.models import Order

    order = Order.objects.select_related('buyer').filter(pk=entry.resource_id).first()
    if order is None or not order.buyer:
        return []

    error = (entry.metadata or {}).get('error', '')
    msg = f"Payment verification failed for order {order.order_number}."
    if error:
        msg = f"{msg} Reason: {error}"

    return [
        NotificationSpec(
            recipient=order.buyer,
            title=f"Payment Verification Failed: {order.order_number}",
            message=msg,
            link=_tab_link('my_orders'),
        )
    ]


def _order_status_updated(entry):
    from apps.marketplace.models import Order

    order = Order.objects.select_related('buyer').filter(pk=entry.resource_id).first()
    if order is None or not order.buyer:
        return []

    metadata = entry.metadata or {}
    new_status = metadata.get('new_status') or order.status
    notes = metadata.get('notes', '')

    if new_status == 'CONFIRMED':
        title = f"Order Confirmed: {order.order_number}"
        message = f"Your order {order.order_number} has been confirmed by the seller."
    elif new_status == 'SHIPPED':
        title = f"Order Shipped: {order.order_number}"
        message = f"Your order {order.order_number} has been dispatched."
    elif new_status == 'DELIVERED':
        title = f"Order Delivered: {order.order_number}"
        message = f"Your order {order.order_number} has been marked as delivered."
    elif new_status == 'CANCELLED':
        title = f"Order Cancelled: {order.order_number}"
        message = _with_reason(f"Your order {order.order_number} was cancelled.", notes)
    else:
        title = f"Order Update: {order.order_number}"
        message = f"Your order {order.order_number} status is now {new_status}."

    return [
        NotificationSpec(
            recipient=order.buyer,
            title=title,
            message=message,
            link=_tab_link('my_orders'),
        )
    ]


def _order_buyer_cancelled(entry):
    from apps.marketplace.models import Order

    order = (
        Order.objects.select_related('buyer')
        .prefetch_related('items__listing__seller')
        .filter(pk=entry.resource_id)
        .first()
    )
    if order is None:
        return []

    specs = []
    notified_sellers = set()
    for item in order.items.all():
        seller = getattr(getattr(item, 'listing', None), 'seller', None)
        if seller and seller.id != order.buyer_id and seller.id not in notified_sellers:
            notified_sellers.add(seller.id)
            specs.append(
                NotificationSpec(
                    recipient=seller,
                    title=f"Order Cancelled: {order.order_number}",
                    message=f"Order {order.order_number} was cancelled by the buyer.",
                    link=_tab_link('seller_orders'),
                )
            )

    return specs


def _order_cod_collection_updated(entry):
    from apps.marketplace.models import Order

    order = Order.objects.select_related('buyer').filter(pk=entry.resource_id).first()
    if order is None or not order.buyer:
        return []

    metadata = entry.metadata or {}
    new_cod_status = metadata.get('new_cod_status')
    if new_cod_status != 'COLLECTED':
        return []

    return [
        NotificationSpec(
            recipient=order.buyer,
            title=f"COD Payment Collected: {order.order_number}",
            message=f"Cash payment for order {order.order_number} has been collected and verified.",
            link=_tab_link('my_orders'),
        )
    ]


# ---------------------------------------------------------------------------
# Workflow Resolvers: Shipments & Logistics
# ---------------------------------------------------------------------------

def _shipment_created(entry):
    from apps.marketplace.models import Shipment

    shipment = Shipment.objects.select_related('order__buyer').filter(pk=entry.resource_id).first()
    if shipment is None or not shipment.order or not shipment.order.buyer:
        return []

    metadata = entry.metadata or {}
    carrier = metadata.get('carrier') or shipment.carrier or 'Courier'
    tracking_number = metadata.get('tracking_number') or shipment.tracking_number
    tracking_info = f" (Tracking: {tracking_number})" if tracking_number else ""

    return [
        NotificationSpec(
            recipient=shipment.order.buyer,
            title=f"Shipment Dispatched: {shipment.shipment_number}",
            message=f"Your order {shipment.order.order_number} has been dispatched via {carrier}{tracking_info}.",
            link=_tab_link('my_orders'),
        )
    ]


def _shipment_status_updated(entry):
    from apps.marketplace.models import Shipment

    shipment = Shipment.objects.select_related('order__buyer').filter(pk=entry.resource_id).first()
    if shipment is None or not shipment.order or not shipment.order.buyer:
        return []

    metadata = entry.metadata or {}
    new_status = metadata.get('new_status') or shipment.status
    location = metadata.get('location')

    if new_status == 'DELIVERED':
        title = f"Shipment Delivered: {shipment.shipment_number}"
        message = f"Shipment {shipment.shipment_number} for order {shipment.order.order_number} has been delivered."
    else:
        title = f"Shipment Update: {shipment.shipment_number}"
        loc_str = f" at {location}" if location else ""
        message = f"Shipment {shipment.shipment_number} is now {new_status}{loc_str}."

    return [
        NotificationSpec(
            recipient=shipment.order.buyer,
            title=title,
            message=message,
            link=_tab_link('my_orders'),
        )
    ]


# ---------------------------------------------------------------------------
# Workflow Resolvers: Returns & Refunds
# ---------------------------------------------------------------------------

def _return_created(entry):
    from apps.marketplace.models import ReturnRequest

    req = ReturnRequest.objects.select_related('seller', 'order', 'buyer').filter(pk=entry.resource_id).first()
    if req is None or not req.seller:
        return []

    req_type = req.get_request_type_display() if hasattr(req, 'get_request_type_display') else req.request_type
    reason_label = req.get_reason_display() if hasattr(req, 'get_reason_display') else req.reason
    buyer_name = req.buyer.full_name if req.buyer else "A buyer"

    return [
        NotificationSpec(
            recipient=req.seller,
            title=f"New {req_type} Request: {req.request_number}",
            message=f"{buyer_name} requested a {req_type.lower()} for order {req.order.order_number}. Reason: {reason_label}.",
            link=_tab_link('seller_orders'),
        )
    ]


def _return_decision(entry):
    from apps.marketplace.models import ReturnRequest

    req = ReturnRequest.objects.select_related('buyer', 'order').filter(pk=entry.resource_id).first()
    if req is None or not req.buyer:
        return []

    req_type = req.get_request_type_display().lower() if hasattr(req, 'get_request_type_display') else req.request_type.lower()

    if entry.event_type == 'marketplace.return.approved':
        title = f"{req.get_request_type_display()} Approved: {req.request_number}"
        message = f"Your {req_type} for order {req.order.order_number} has been approved."
    else:
        title = f"{req.get_request_type_display()} Rejected: {req.request_number}"
        message = _with_reason(
            f"Your {req_type} for order {req.order.order_number} was rejected.",
            req.rejection_reason,
        )

    return [
        NotificationSpec(
            recipient=req.buyer,
            title=title,
            message=message,
            link=_tab_link('my_orders'),
        )
    ]


def _return_completed(entry):
    from apps.marketplace.models import ReturnRequest

    req = ReturnRequest.objects.select_related('buyer', 'order').filter(pk=entry.resource_id).first()
    if req is None or not req.buyer:
        return []

    return [
        NotificationSpec(
            recipient=req.buyer,
            title=f"Return Completed: {req.request_number}",
            message=f"Your return for order {req.order.order_number} has been completed and restocked.",
            link=_tab_link('my_orders'),
        )
    ]


def _refund_processed(entry):
    from apps.marketplace.models import Refund

    refund = Refund.objects.select_related('order__buyer').filter(pk=entry.resource_id).first()
    if refund is None or not refund.order or not refund.order.buyer:
        return []

    return [
        NotificationSpec(
            recipient=refund.order.buyer,
            title=f"Refund Processed: {refund.refund_number}",
            message=f"A refund of {refund.currency} {refund.amount} for order {refund.order.order_number} has been processed via {refund.refund_method}.",
            link=_tab_link('my_orders'),
        )
    ]


# ---------------------------------------------------------------------------
# Workflow Resolvers: Disputes
# ---------------------------------------------------------------------------

def _dispute_created(entry):
    from apps.marketplace.models import Dispute

    dispute = Dispute.objects.select_related('seller', 'order', 'buyer').filter(pk=entry.resource_id).first()
    if dispute is None or not dispute.seller:
        return []

    category = dispute.get_category_display() if hasattr(dispute, 'get_category_display') else dispute.category

    return [
        NotificationSpec(
            recipient=dispute.seller,
            title=f"Dispute Opened: {dispute.dispute_number}",
            message=f"A dispute was opened for order {dispute.order.order_number} ({category}).",
            link=_tab_link('seller_orders'),
        )
    ]


def _dispute_status_updated(entry):
    from apps.marketplace.models import Dispute

    dispute = Dispute.objects.select_related('buyer', 'seller', 'order').filter(pk=entry.resource_id).first()
    if dispute is None:
        return []

    metadata = entry.metadata or {}
    new_status = metadata.get('new_status') or dispute.status
    resolution = metadata.get('resolution') or dispute.resolution
    notes = metadata.get('resolution_notes') or dispute.resolution_notes

    msg = f"Dispute {dispute.dispute_number} for order {dispute.order.order_number} status is now {new_status}."
    if resolution:
        msg = f"{msg} Decision: {resolution}."
    if notes:
        msg = f"{msg} Note: {notes}"

    specs = []
    if dispute.buyer and dispute.buyer_id != entry.actor_id:
        specs.append(
            NotificationSpec(
                recipient=dispute.buyer,
                title=f"Dispute Updated: {dispute.dispute_number}",
                message=msg,
                link=_tab_link('my_orders'),
            )
        )

    if dispute.seller and dispute.seller_id != entry.actor_id:
        specs.append(
            NotificationSpec(
                recipient=dispute.seller,
                title=f"Dispute Updated: {dispute.dispute_number}",
                message=msg,
                link=_tab_link('seller_orders'),
            )
        )

    return specs


def _dispute_message_added(entry):
    from apps.marketplace.models import Dispute

    dispute = Dispute.objects.select_related('buyer', 'seller', 'order').filter(pk=entry.resource_id).first()
    if dispute is None:
        return []

    specs = []
    if dispute.seller and entry.actor_id != dispute.seller_id:
        specs.append(
            NotificationSpec(
                recipient=dispute.seller,
                title=f"New Message on Dispute {dispute.dispute_number}",
                message=f"A new message was posted on dispute {dispute.dispute_number} for order {dispute.order.order_number}.",
                link=_tab_link('seller_orders'),
            )
        )

    if dispute.buyer and entry.actor_id != dispute.buyer_id:
        specs.append(
            NotificationSpec(
                recipient=dispute.buyer,
                title=f"New Message on Dispute {dispute.dispute_number}",
                message=f"A new message was posted on dispute {dispute.dispute_number} for order {dispute.order.order_number}.",
                link=_tab_link('my_orders'),
            )
        )

    return specs


# ---------------------------------------------------------------------------
# Workflow Resolvers: Reviews & Moderation
# ---------------------------------------------------------------------------

def _product_review_created(entry):
    from apps.marketplace.models import ProductReview

    review = ProductReview.objects.select_related('seller', 'listing', 'buyer').filter(pk=entry.resource_id).first()
    if review is None or not review.seller:
        return []

    buyer_name = review.buyer.full_name if review.buyer else "A verified buyer"
    part_name = review.listing.name if review.listing else "a product"

    return [
        NotificationSpec(
            recipient=review.seller,
            title=f"New Review: {part_name}",
            message=f"{buyer_name} left a {review.rating}-star review for '{part_name}'.",
            link=_tab_link('seller_orders'),
        )
    ]


def _review_replied(entry):
    from apps.marketplace.models import ProductReview, SellerReview

    if entry.resource_type == 'ProductReview' or entry.event_type == 'marketplace.productreview.replied':
        review = ProductReview.objects.select_related('buyer', 'listing').filter(pk=entry.resource_id).first()
        item_name = f"your review for '{review.listing.name}'" if review and review.listing else "your review"
    else:
        review = SellerReview.objects.select_related('buyer', 'seller').filter(pk=entry.resource_id).first()
        item_name = "your seller review"

    if review is None or not review.buyer:
        return []

    reply_preview = (review.seller_reply or '')[:120]
    return [
        NotificationSpec(
            recipient=review.buyer,
            title="Seller Replied to Your Review",
            message=f"The seller responded to {item_name}: \"{reply_preview}\"",
            link=_tab_link('my_orders'),
        )
    ]


def _review_moderated(entry):
    from apps.marketplace.models import ProductReview, SellerReview

    metadata = entry.metadata or {}
    action = metadata.get('action', '').upper()
    if action not in ('HIDE', 'REJECT'):
        return []

    if entry.resource_type == 'ProductReview':
        review = ProductReview.objects.select_related('buyer', 'listing').filter(pk=entry.resource_id).first()
        item_name = f"'{review.listing.name}'" if review and review.listing else "a product"
    else:
        review = SellerReview.objects.select_related('buyer', 'seller').filter(pk=entry.resource_id).first()
        item_name = "a seller"

    if review is None or not review.buyer:
        return []

    return [
        NotificationSpec(
            recipient=review.buyer,
            title="Review Moderation Notice",
            message=f"Your review for {item_name} was removed from public display by moderators.",
            link=_tab_link('my_orders'),
        )
    ]


EVENT_RESOLVERS = {
    # Phase 1 & 2
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

    # Orders & Payments
    'marketplace.order.created': _order_created,
    'marketplace.order.payment_verified': _order_payment_verified,
    'marketplace.order.payment_verification_failed': _order_payment_verification_failed,
    'marketplace.order.status_updated': _order_status_updated,
    'marketplace.order.buyer_cancelled': _order_buyer_cancelled,
    'marketplace.order.cod_collection_updated': _order_cod_collection_updated,

    # Shipments & Logistics
    'marketplace.shipment.created': _shipment_created,
    'marketplace.shipment.status_updated': _shipment_status_updated,

    # Returns & Refunds
    'marketplace.return.created': _return_created,
    'marketplace.return.approved': _return_decision,
    'marketplace.return.rejected': _return_decision,
    'marketplace.return.completed': _return_completed,
    'marketplace.refund.processed': _refund_processed,

    # Disputes
    'marketplace.dispute.created': _dispute_created,
    'marketplace.dispute.status_updated': _dispute_status_updated,
    'marketplace.dispute.message_added': _dispute_message_added,

    # Reviews & Moderation
    'marketplace.product_review.created': _product_review_created,
    'marketplace.productreview.replied': _review_replied,
    'marketplace.sellerreview.replied': _review_replied,
    'marketplace.review.moderated': _review_moderated,
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
