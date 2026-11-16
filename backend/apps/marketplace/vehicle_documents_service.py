"""
Vehicle Purchase Documents & Verification Service.

Manages the end-to-end lifecycle of vehicle purchase transaction documents:
- Configurable market and handover requirement specifications (UK, India, Global).
- Secure private media storage with magic-byte content validation.
- Append-only version history (no overwriting of older versions).
- Role-based permissions (dealers submit dealer docs, buyers submit buyer docs).
- Independent review workflow (prevents self-verification, requires rejection reasons).
- Automatic document readiness and readiness-for-handover computation.
- Document expiry tracking and status transitions.
- Append-only audit logs and deduplicated notifications.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, asdict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.identity.models import RoleChoices, User
from apps.marketplace.models import (
    VehicleDocumentCategoryChoices,
    VehicleDocumentOwnerRoleChoices,
    VehicleDocumentReviewEventTypeChoices,
    VehicleDocumentReviewEvent,
    VehicleDocumentStatusChoices,
    VehicleOrder,
    VehicleOrderStatusChoices,
    VehiclePurchaseDocument,
)
from platform_core.audit.writer import record_audit_entry

logger = logging.getLogger(__name__)

# Maximum file size for vehicle documents (10 MB default)
MAX_VEHICLE_DOCUMENT_BYTES = int(getattr(settings, 'VEHICLE_DOCUMENT_MAX_BYTES', 10 * 1024 * 1024))

# Prohibited file extensions
BLOCKED_EXTENSIONS = {
    '.exe', '.bat', '.cmd', '.sh', '.py', '.js', '.php', '.html', '.htm',
    '.svg', '.dll', '.msi', '.vbs', '.ps1', '.jar', '.com', '.scr',
}

# Supported document MIME types and their magic byte signatures
ALLOWED_DOCUMENT_MIMES = {
    'application/pdf': [b'%PDF'],
    'image/jpeg': [b'\xff\xd8\xff'],
    'image/png': [b'\x89PNG\r\n\x1a\n'],
    'image/webp': [b'RIFF'],  # RIFF....WEBP
}

ALLOWED_EXTENSIONS_MAP = {
    'application/pdf': ['.pdf'],
    'image/jpeg': ['.jpg', '.jpeg'],
    'image/png': ['.png'],
    'image/webp': ['.webp'],
}


@dataclass(frozen=True)
class DocumentRequirementSpec:
    category: str
    name: str
    description: str
    owner_role: str
    is_required: bool
    requires_expiry_date: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_market_code_for_order(order: VehicleOrder) -> str:
    """Resolves market code (UK, IN, or GLOBAL) from currency and market timezone."""
    currency = (order.currency or '').upper()
    tz = (order.market_timezone or '').lower()
    if currency == 'GBP' or 'london' in tz or 'uk' in tz:
        return 'UK'
    if currency == 'INR' or 'kolkata' in tz or 'calcutta' in tz or 'india' in tz:
        return 'IN'
    return 'GLOBAL'


def get_document_requirements_for_order(order: VehicleOrder) -> List[DocumentRequirementSpec]:
    """
    Returns configurable document requirement specifications for the given vehicle order
    based on the market jurisdiction and handover preference.
    Does NOT assume every document is mandatory.
    Does NOT require Aadhaar by default.
    """
    market = get_market_code_for_order(order)
    handover = order.handover_type

    requirements: List[DocumentRequirementSpec] = []

    if market == 'UK':
        # UK Market (DVLA / MOT standards)
        requirements.extend([
            DocumentRequirementSpec(
                category=VehicleDocumentCategoryChoices.REGISTRATION_CERTIFICATE,
                name="V5C Logbook / Vehicle Registration",
                description="Official DVLA registration document (V5C) verifying registered keeper and vehicle identity.",
                owner_role=VehicleDocumentOwnerRoleChoices.DEALER,
                is_required=True,
                requires_expiry_date=False,
            ),
            DocumentRequirementSpec(
                category=VehicleDocumentCategoryChoices.ROADWORTHINESS_CERTIFICATE,
                name="MOT Test Certificate",
                description="Statutory proof of current roadworthiness and road safety compliance.",
                owner_role=VehicleDocumentOwnerRoleChoices.DEALER,
                is_required=True,
                requires_expiry_date=True,
            ),
            DocumentRequirementSpec(
                category=VehicleDocumentCategoryChoices.PURCHASE_INVOICE,
                name="Bill of Sale / Commercial Invoice",
                description="Official dealership sales invoice documenting vehicle details, agreed price, and transfer of title.",
                owner_role=VehicleDocumentOwnerRoleChoices.DEALER,
                is_required=True,
                requires_expiry_date=False,
            ),
            DocumentRequirementSpec(
                category=VehicleDocumentCategoryChoices.INSURANCE_CERTIFICATE,
                name="Motor Trade / Driveaway Insurance Cover Note",
                description="Trade insurance cover or certificate confirming vehicle coverage prior to handover.",
                owner_role=VehicleDocumentOwnerRoleChoices.DEALER,
                is_required=False,
                requires_expiry_date=True,
            ),
            DocumentRequirementSpec(
                category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
                name="Buyer Photo ID (Driving Licence / Passport)",
                description="Government-issued photo identification verifying the purchasing party's identity.",
                owner_role=VehicleDocumentOwnerRoleChoices.BUYER,
                is_required=True,
                requires_expiry_date=False,
            ),
            DocumentRequirementSpec(
                category=VehicleDocumentCategoryChoices.BUYER_ADDRESS_PROOF,
                name="Buyer Proof of Address (Utility Bill / Bank Statement)",
                description="Recent proof of address dated within the last 3 months (required for dealer delivery).",
                owner_role=VehicleDocumentOwnerRoleChoices.BUYER,
                is_required=(handover == 'DELIVERY'),
                requires_expiry_date=False,
            ),
        ])
    elif market == 'IN':
        # India Market (Parivahan / RTO standards)
        requirements.extend([
            DocumentRequirementSpec(
                category=VehicleDocumentCategoryChoices.REGISTRATION_CERTIFICATE,
                name="Registration Certificate (RC / Form 23)",
                description="Official RTO vehicle registration certificate/smartcard required for ownership transfer.",
                owner_role=VehicleDocumentOwnerRoleChoices.DEALER,
                is_required=True,
                requires_expiry_date=False,
            ),
            DocumentRequirementSpec(
                category=VehicleDocumentCategoryChoices.INSURANCE_CERTIFICATE,
                name="Motor Insurance Certificate",
                description="Statutory valid third-party or comprehensive motor insurance policy certificate.",
                owner_role=VehicleDocumentOwnerRoleChoices.DEALER,
                is_required=True,
                requires_expiry_date=True,
            ),
            DocumentRequirementSpec(
                category=VehicleDocumentCategoryChoices.ROADWORTHINESS_CERTIFICATE,
                name="Pollution Under Control (PUC) / Fitness Certificate",
                description="Statutory valid emission test (PUC) or commercial fitness certificate.",
                owner_role=VehicleDocumentOwnerRoleChoices.DEALER,
                is_required=True,
                requires_expiry_date=True,
            ),
            DocumentRequirementSpec(
                category=VehicleDocumentCategoryChoices.PROOF_OF_OWNERSHIP,
                name="RTO Transfer Forms (Form 29 / 30 / Delivery Receipt)",
                description="Prescribed RTO notice of ownership transfer and seller authority.",
                owner_role=VehicleDocumentOwnerRoleChoices.DEALER,
                is_required=True,
                requires_expiry_date=False,
            ),
            DocumentRequirementSpec(
                category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
                name="Buyer Identity Proof (PAN / Passport / Voter ID / Driving Licence)",
                description="Government-issued identity verification. Note: Aadhaar is NOT mandatory.",
                owner_role=VehicleDocumentOwnerRoleChoices.BUYER,
                is_required=True,
                requires_expiry_date=False,
            ),
            DocumentRequirementSpec(
                category=VehicleDocumentCategoryChoices.BUYER_ADDRESS_PROOF,
                name="Buyer Address Proof (Electricity / Bank / Passport)",
                description="Valid address proof accepted by RTO for registration transfer.",
                owner_role=VehicleDocumentOwnerRoleChoices.BUYER,
                is_required=False,
                requires_expiry_date=False,
            ),
        ])
    else:
        # Global Baseline
        requirements.extend([
            DocumentRequirementSpec(
                category=VehicleDocumentCategoryChoices.REGISTRATION_CERTIFICATE,
                name="Vehicle Registration Document",
                description="Official jurisdiction vehicle title or registration document.",
                owner_role=VehicleDocumentOwnerRoleChoices.DEALER,
                is_required=True,
                requires_expiry_date=False,
            ),
            DocumentRequirementSpec(
                category=VehicleDocumentCategoryChoices.PURCHASE_INVOICE,
                name="Purchase Invoice / Bill of Sale",
                description="Commercial invoice documenting vehicle particulars and transfer of title.",
                owner_role=VehicleDocumentOwnerRoleChoices.DEALER,
                is_required=True,
                requires_expiry_date=False,
            ),
            DocumentRequirementSpec(
                category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
                name="Buyer Identification Document",
                description="Government-issued identity document for transaction verification.",
                owner_role=VehicleDocumentOwnerRoleChoices.BUYER,
                is_required=True,
                requires_expiry_date=False,
            ),
        ])

    return requirements


def validate_document_file(file_obj: Any) -> Dict[str, Any]:
    """
    Validates uploaded file size, prohibited extensions, and authentic magic-byte MIME signature.
    Returns sanitized filename, detected MIME type, and file size in bytes.
    Raises ValidationError on invalid or malicious files.
    """
    if not file_obj:
        raise ValidationError("No file was uploaded.")

    file_size = getattr(file_obj, 'size', 0)
    if file_size <= 0:
        raise ValidationError("Uploaded file is empty.")

    if file_size > MAX_VEHICLE_DOCUMENT_BYTES:
        max_mb = MAX_VEHICLE_DOCUMENT_BYTES // (1024 * 1024)
        raise ValidationError(f"File size exceeds the maximum permitted limit of {max_mb} MB.")

    raw_name = getattr(file_obj, 'name', 'document')
    safe_name = os.path.basename(raw_name).strip()
    ext = os.path.splitext(safe_name)[1].lower()

    if ext in BLOCKED_EXTENSIONS:
        raise ValidationError(f"File type '{ext}' is strictly prohibited for security reasons.")

    # Inspect magic byte signature from header
    file_obj.seek(0)
    header = file_obj.read(32)
    file_obj.seek(0)

    detected_mime: Optional[str] = None
    for mime, signatures in ALLOWED_DOCUMENT_MIMES.items():
        for sig in signatures:
            if header.startswith(sig):
                detected_mime = mime
                break
        if detected_mime:
            break

    if not detected_mime:
        raise ValidationError(
            f"Invalid file content or unsupported format for '{safe_name}'. "
            "Supported document formats are PDF, JPEG, PNG, and WebP."
        )

    # Cross-check detected MIME matches file extension
    valid_extensions = ALLOWED_EXTENSIONS_MAP.get(detected_mime, [])
    if ext not in valid_extensions:
        raise ValidationError(
            f"File extension '{ext}' does not match detected file format '{detected_mime}'."
        )

    return {
        "original_filename": safe_name,
        "mime_type": detected_mime,
        "file_size": file_size,
    }


def _is_platform_admin(user: Any) -> bool:
    if not user or not user.is_authenticated:
        return False
    return bool(user.is_superuser or user.has_role(RoleChoices.ADMIN))


def _has_permission(user: Any, perm_code: str) -> bool:
    if not user or not user.is_authenticated:
        return False
    if _is_platform_admin(user):
        return True
    if hasattr(user, 'has_permission'):
        return user.has_permission(perm_code)
    return False


def can_user_access_order(user: User, order: VehicleOrder) -> bool:
    """Checks whether user is the buyer, the seller/dealer organisation member, or authorised staff."""
    if not user or not user.is_authenticated:
        return False
    if order.buyer_id == user.id or order.seller_id == user.id:
        return True
    if order.organisation_id and user.organisation_memberships.filter(organisation_id=order.organisation_id).exists():
        return True
    if _has_permission(user, 'marketplace.vehicle_document.review'):
        return True
    return False


def submit_vehicle_order_document(
    order_id: str,
    user: User,
    category: str,
    file_obj: Any,
    document_expiry_date: Optional[date] = None,
    notes: str = "",
) -> VehiclePurchaseDocument:
    """
    Submits a new vehicle purchase document version for a VehicleOrder.
    - Preserves all historical versions (append-only, never overwrites).
    - Enforces dealer vs buyer category permissions.
    - Validates file content using magic bytes.
    - Records append-only review event and audit log.
    - Recalculates document readiness.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication is required to submit vehicle documents.")

    with transaction.atomic():
        try:
            order = (
                VehicleOrder.objects.select_for_update(of=('self',))
                .select_related('listing', 'buyer', 'seller', 'organisation')
                .get(pk=order_id)
            )
        except VehicleOrder.DoesNotExist:
            raise ValidationError(f"Vehicle order '{order_id}' was not found.")

        if order.status == VehicleOrderStatusChoices.CANCELLED:
            raise ValidationError("Cannot upload documents to a cancelled vehicle order.")

        # Determine user role on order
        is_buyer = (order.buyer_id == user.id)
        is_dealer = (order.seller_id == user.id)
        if not is_dealer and order.organisation_id:
            is_dealer = user.organisation_memberships.filter(organisation_id=order.organisation_id).exists()

        if not (is_buyer or is_dealer):
            raise PermissionDenied("You are neither the buyer nor the seller for this vehicle order.")

        # Check valid category
        valid_categories = {c.value: c for c in VehicleDocumentCategoryChoices}
        if category not in valid_categories:
            raise ValidationError(f"Invalid document category '{category}'.")

        # Determine category owner role
        dealer_categories = {
            VehicleDocumentCategoryChoices.REGISTRATION_CERTIFICATE,
            VehicleDocumentCategoryChoices.PROOF_OF_OWNERSHIP,
            VehicleDocumentCategoryChoices.INSURANCE_CERTIFICATE,
            VehicleDocumentCategoryChoices.ROADWORTHINESS_CERTIFICATE,
            VehicleDocumentCategoryChoices.PURCHASE_INVOICE,
            VehicleDocumentCategoryChoices.OTHER_DEALER_DOCUMENT,
        }
        owner_role = (
            VehicleDocumentOwnerRoleChoices.DEALER
            if category in dealer_categories
            else VehicleDocumentOwnerRoleChoices.BUYER
        )

        # Enforce role boundary
        if owner_role == VehicleDocumentOwnerRoleChoices.DEALER and not is_dealer:
            raise PermissionDenied("Only the dealership can upload dealer vehicle compliance documents.")
        if owner_role == VehicleDocumentOwnerRoleChoices.BUYER and not is_buyer:
            raise PermissionDenied("Only the buyer can upload buyer verification documents.")

        # Validate file content
        file_meta = validate_document_file(file_obj)

        # Validate expiry date if provided
        today = timezone.now().date()
        if document_expiry_date:
            if document_expiry_date < today:
                raise ValidationError(f"Document expiry date '{document_expiry_date}' has already passed.")

        # Find existing documents for this order and category under lock
        existing_docs = (
            order.documents.select_for_update(of=('self',))
            .filter(category=category)
            .order_by('-version_number')
        )
        latest_doc = existing_docs.filter(is_latest=True).first()

        new_version = 1
        is_replacement = False
        if latest_doc:
            new_version = latest_doc.version_number + 1
            is_replacement = True

            # Mark previous latest document as no longer latest
            latest_doc.is_latest = False
            prev_status = latest_doc.status
            # If previous document was not rejected, mark it SUPERSEDED
            if latest_doc.status != VehicleDocumentStatusChoices.REJECTED:
                latest_doc.status = VehicleDocumentStatusChoices.SUPERSEDED
            latest_doc.save(update_fields=['is_latest', 'status', 'updated_at'])

            # Record SUPERSEDED review event on the previous document
            VehicleDocumentReviewEvent.objects.create(
                document=latest_doc,
                order=order,
                actor=user,
                event_type=VehicleDocumentReviewEventTypeChoices.SUPERSEDED,
                previous_status=prev_status,
                new_status=latest_doc.status,
                notes=f"Superseded by replacement version {new_version}.",
                metadata={"replacement_version": new_version},
            )

        # Create new document version in private storage
        new_doc = VehiclePurchaseDocument(
            order=order,
            category=category,
            document_owner_role=owner_role,
            version_number=new_version,
            submitted_by=user,
            original_filename=file_meta['original_filename'],
            mime_type=file_meta['mime_type'],
            file_size=file_meta['file_size'],
            document_expiry_date=document_expiry_date,
            status=VehicleDocumentStatusChoices.PENDING_REVIEW,
            is_latest=True,
            rejection_notes=notes.strip(),
        )
        new_doc.file = file_obj
        new_doc.save()

        # Record SUBMITTED / REPLACED event
        event_type = (
            VehicleDocumentReviewEventTypeChoices.REPLACED
            if is_replacement
            else VehicleDocumentReviewEventTypeChoices.SUBMITTED
        )
        VehicleDocumentReviewEvent.objects.create(
            document=new_doc,
            order=order,
            actor=user,
            event_type=event_type,
            previous_status="",
            new_status=VehicleDocumentStatusChoices.PENDING_REVIEW,
            notes=notes.strip() or f"Version {new_version} uploaded.",
            metadata={
                "version": new_version,
                "filename": file_meta['original_filename'],
                "file_size": file_meta['file_size'],
                "mime_type": file_meta['mime_type'],
                "expiry_date": str(document_expiry_date) if document_expiry_date else None,
            },
        )

        # Audit log entry (triggers notifications)
        audit_action = "marketplace.vehicle_document.replacement_submitted" if is_replacement else "marketplace.vehicle_document.submitted"
        record_audit_entry(
            event_type=audit_action,
            action="marketplace:vehicle_document.submit",
            resource_type="VehiclePurchaseDocument",
            resource_id=str(new_doc.id),
            actor_id=user.id,
            metadata={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "category": category,
                "version": new_version,
                "owner_role": owner_role,
                "filename": file_meta['original_filename'],
                "is_replacement": is_replacement,
            },
        )

        logger.info(
            "Vehicle document submitted: Order %s, Category %s, Version %d by %s",
            order.order_number, category, new_version, user.email,
        )

        return new_doc


def verify_vehicle_document(
    document_id: str,
    reviewer: User,
    approved: bool,
    rejection_reason: str = "",
    notes: str = "",
) -> VehiclePurchaseDocument:
    """
    Reviews a pending vehicle purchase document:
    - Approves (VERIFIED) or Rejects (REJECTED).
    - Prevents users from verifying their own submissions.
    - Prevents duplicate or conflicting review actions.
    - Enforces non-empty rejection reason on rejection.
    - Recalculates document readiness: transitions order to READY_FOR_HANDOVER
      if all required documents are verified and payment conditions are confirmed.
    - Records immutable review events and audit trail.
    """
    if not reviewer or not reviewer.is_authenticated:
        raise PermissionDenied("Authentication is required to verify vehicle documents.")

    with transaction.atomic():
        try:
            document = (
                VehiclePurchaseDocument.objects.select_for_update(of=('self',))
                .select_related('order', 'order__listing', 'order__buyer', 'order__seller', 'order__organisation')
                .get(pk=document_id)
            )
        except VehiclePurchaseDocument.DoesNotExist:
            raise ValidationError(f"Vehicle document '{document_id}' was not found.")

        order = (
            VehicleOrder.objects.select_for_update(of=('self',))
            .get(pk=document.order_id)
        )

        if order.status == VehicleOrderStatusChoices.CANCELLED:
            raise ValidationError("Cannot verify documents for a cancelled vehicle order.")

        # Ensure document is in reviewable state
        if document.status != VehicleDocumentStatusChoices.PENDING_REVIEW:
            raise ValidationError(
                f"Document is in '{document.status}' status and cannot be reviewed. "
                "Only documents in PENDING_REVIEW can be verified or rejected."
            )

        if not document.is_latest:
            raise ValidationError("Cannot review an older, superseded document version.")

        # Self-verification check: strictly forbidden
        if document.submitted_by_id == reviewer.id:
            raise PermissionDenied("You cannot verify or reject a document that you submitted yourself.")

        # Role permission checks
        is_order_seller = (order.seller_id == reviewer.id)
        if not is_order_seller and order.organisation_id:
            is_order_seller = reviewer.organisation_memberships.filter(organisation_id=order.organisation_id).exists()

        is_authorised_staff = _has_permission(reviewer, 'marketplace.vehicle_document.review')

        if document.document_owner_role == VehicleDocumentOwnerRoleChoices.BUYER:
            # Buyer documents can be reviewed by the associated dealer or authorised staff
            if not (is_order_seller or is_authorised_staff):
                raise PermissionDenied("You do not have permission to review buyer documents for this order.")
        else:
            # Dealer documents: reviewed by authorised staff / platform review officer
            if not is_authorised_staff:
                raise PermissionDenied(
                    "Dealer vehicle compliance documents must be verified by an authorised platform review officer."
                )

        now = timezone.now()
        prev_status = document.status

        if approved:
            # Check expiry date
            if document.document_expiry_date and document.document_expiry_date < now.date():
                raise ValidationError("Cannot approve an expired document.")

            document.status = VehicleDocumentStatusChoices.VERIFIED
            document.verified_by = reviewer
            document.verified_at = now
            document.rejection_reason = ""
            document.save(update_fields=['status', 'verified_by', 'verified_at', 'rejection_reason', 'updated_at'])

            # Record VERIFIED review event
            VehicleDocumentReviewEvent.objects.create(
                document=document,
                order=order,
                actor=reviewer,
                event_type=VehicleDocumentReviewEventTypeChoices.VERIFIED,
                previous_status=prev_status,
                new_status=VehicleDocumentStatusChoices.VERIFIED,
                notes=notes.strip() or "Document approved.",
                metadata={"verified_by": reviewer.email, "verified_at": now.isoformat()},
            )

            # Audit log
            record_audit_entry(
                event_type="marketplace.vehicle_document.approved",
                action="marketplace:vehicle_document.approve",
                resource_type="VehiclePurchaseDocument",
                resource_id=str(document.id),
                actor_id=reviewer.id,
                metadata={
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                    "category": document.category,
                    "version": document.version_number,
                    "submitted_by_id": str(document.submitted_by_id),
                },
            )

            # Check if all required documents are now verified
            readiness = get_vehicle_order_document_readiness(order)
            if readiness['all_required_verified']:
                record_audit_entry(
                    event_type="marketplace.vehicle_document.all_verified",
                    action="marketplace:vehicle_document.all_verified",
                    resource_type="VehicleOrder",
                    resource_id=str(order.id),
                    actor_id=reviewer.id,
                    metadata={"order_number": order.order_number},
                )

                # If payment is already confirmed, transition to READY_FOR_HANDOVER
                has_payment_confirmed = (
                    order.status == VehicleOrderStatusChoices.PAYMENT_CONFIRMED
                    or order.payment_confirmed_at is not None
                )
                if has_payment_confirmed and order.status in (
                    VehicleOrderStatusChoices.PAYMENT_CONFIRMED,
                    VehicleOrderStatusChoices.DOCUMENTS_PENDING,
                ):
                    order.status = VehicleOrderStatusChoices.READY_FOR_HANDOVER
                    order.save(update_fields=['status', 'updated_at'])

                    record_audit_entry(
                        event_type="marketplace.vehicle_order.ready_for_handover",
                        action="marketplace:vehicle_order.ready_for_handover",
                        resource_type="VehicleOrder",
                        resource_id=str(order.id),
                        actor_id=reviewer.id,
                        metadata={"order_number": order.order_number},
                    )

            logger.info("Vehicle document %s approved by %s", document.id, reviewer.email)

        else:
            # Rejection requires non-empty reason
            reason_clean = rejection_reason.strip()
            if not reason_clean:
                raise ValidationError("A clear rejection reason must be documented when rejecting a document.")

            document.status = VehicleDocumentStatusChoices.REJECTED
            document.verified_by = reviewer
            document.verified_at = now
            document.rejection_reason = reason_clean
            document.save(update_fields=['status', 'verified_by', 'verified_at', 'rejection_reason', 'updated_at'])

            # Record REJECTED review event
            VehicleDocumentReviewEvent.objects.create(
                document=document,
                order=order,
                actor=reviewer,
                event_type=VehicleDocumentReviewEventTypeChoices.REJECTED,
                previous_status=prev_status,
                new_status=VehicleDocumentStatusChoices.REJECTED,
                notes=reason_clean,
                metadata={"rejected_by": reviewer.email, "reason": reason_clean},
            )

            # If order was marked READY_FOR_HANDOVER, revert back to DOCUMENTS_PENDING
            if order.status == VehicleOrderStatusChoices.READY_FOR_HANDOVER:
                order.status = VehicleOrderStatusChoices.DOCUMENTS_PENDING
                order.save(update_fields=['status', 'updated_at'])

            # Audit log
            record_audit_entry(
                event_type="marketplace.vehicle_document.rejected",
                action="marketplace:vehicle_document.reject",
                resource_type="VehiclePurchaseDocument",
                resource_id=str(document.id),
                actor_id=reviewer.id,
                metadata={
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                    "category": document.category,
                    "version": document.version_number,
                    "reason": reason_clean,
                    "submitted_by_id": str(document.submitted_by_id),
                },
            )

            logger.info("Vehicle document %s rejected by %s: %s", document.id, reviewer.email, reason_clean)

        return document


def get_vehicle_order_document_readiness(order: VehicleOrder) -> Dict[str, Any]:
    """
    Calculates detailed document readiness for a VehicleOrder:
    - Evaluates required categories vs latest submitted document statuses.
    - Tracks pending reviews, verified documents, rejected documents, and expired documents.
    - Determines if the order is ready for handover.
    """
    requirements = get_document_requirements_for_order(order)
    today = timezone.now().date()

    # Pre-fetch latest documents for this order
    latest_docs = {
        doc.category: doc
        for doc in order.documents.filter(is_latest=True).select_related('submitted_by', 'verified_by')
    }

    # Count historical superseded versions per category
    historical_counts: Dict[str, int] = {}
    for d in order.documents.filter(is_latest=False).values('category'):
        cat = d['category']
        historical_counts[cat] = historical_counts.get(cat, 0) + 1

    req_details: List[Dict[str, Any]] = []
    total_required = 0
    verified_required_count = 0
    pending_count = 0
    rejected_count = 0
    expired_count = 0

    for req in requirements:
        if req.is_required:
            total_required += 1

        latest = latest_docs.get(req.category)
        if latest is None:
            current_status = VehicleDocumentStatusChoices.REQUIRED if req.is_required else "OPTIONAL"
            doc_data = None
        else:
            # Check expiry runtime flag
            if latest.status == VehicleDocumentStatusChoices.VERIFIED and latest.document_expiry_date and latest.document_expiry_date < today:
                current_status = VehicleDocumentStatusChoices.EXPIRED
                expired_count += 1
            else:
                current_status = latest.status

            if current_status == VehicleDocumentStatusChoices.PENDING_REVIEW:
                pending_count += 1
            elif current_status == VehicleDocumentStatusChoices.VERIFIED and req.is_required:
                verified_required_count += 1
            elif current_status == VehicleDocumentStatusChoices.REJECTED:
                rejected_count += 1

            doc_data = {
                "id": str(latest.id),
                "version_number": latest.version_number,
                "original_filename": latest.original_filename,
                "file_size": latest.file_size,
                "mime_type": latest.mime_type,
                "document_expiry_date": str(latest.document_expiry_date) if latest.document_expiry_date else None,
                "submitted_by_name": latest.submitted_by.full_name or latest.submitted_by.email,
                "submitted_at": latest.created_at.isoformat(),
                "verified_by_name": latest.verified_by.full_name if latest.verified_by else None,
                "verified_at": latest.verified_at.isoformat() if latest.verified_at else None,
                "rejection_reason": latest.rejection_reason,
            }

        req_details.append({
            "category": req.category,
            "name": req.name,
            "label": req.name,
            "description": req.description,
            "notes": req.description,
            "owner_role": req.owner_role,
            "is_required": req.is_required,
            "required": req.is_required,
            "requires_expiry_date": req.requires_expiry_date,
            "status": current_status,
            "current_status": current_status,
            "previous_versions_count": historical_counts.get(req.category, 0),
            "latest_document": doc_data,
        })

    all_required_verified = (total_required > 0 and verified_required_count == total_required and pending_count == 0 and rejected_count == 0)

    # Handover readiness requires payment confirmed AND all documents verified
    has_payment_confirmed = (
        order.status in (VehicleOrderStatusChoices.PAYMENT_CONFIRMED, VehicleOrderStatusChoices.READY_FOR_HANDOVER)
        or order.payment_confirmed_at is not None
    )
    can_handover = all_required_verified and has_payment_confirmed and order.status != VehicleOrderStatusChoices.CANCELLED

    return {
        "market": get_market_code_for_order(order),
        "total_required": total_required,
        "required_count": total_required,
        "verified_required_count": verified_required_count,
        "verified_count": verified_required_count,
        "pending_count": pending_count,
        "rejected_count": rejected_count,
        "expired_count": expired_count,
        "all_required_verified": all_required_verified,
        "all_verified": all_required_verified,
        "has_payment_confirmed": has_payment_confirmed,
        "can_transition_to_handover": can_handover,
        "requirements": req_details,
        "by_category": {
            req["category"]: req for req in req_details
        },
    }


def check_expired_vehicle_documents() -> int:
    """
    Periodic task/check to identify documents that have passed their expiry date:
    - Transitions VERIFIED documents past expiry to EXPIRED.
    - Records an immutable review event.
    - Reverts order from READY_FOR_HANDOVER to DOCUMENTS_PENDING if compliance is compromised.
    - Returns count of expired documents updated.
    """
    today = timezone.now().date()
    expired_docs = VehiclePurchaseDocument.objects.filter(
        status=VehicleDocumentStatusChoices.VERIFIED,
        is_latest=True,
        document_expiry_date__lt=today,
    ).select_related('order')

    count = 0
    for doc in expired_docs:
        with transaction.atomic():
            doc_locked = VehiclePurchaseDocument.objects.select_for_update().get(pk=doc.id)
            if doc_locked.status != VehicleDocumentStatusChoices.VERIFIED:
                continue

            doc_locked.status = VehicleDocumentStatusChoices.EXPIRED
            doc_locked.save(update_fields=['status', 'updated_at'])

            VehicleDocumentReviewEvent.objects.create(
                document=doc_locked,
                order=doc_locked.order,
                actor=None,
                event_type=VehicleDocumentReviewEventTypeChoices.EXPIRED,
                previous_status=VehicleDocumentStatusChoices.VERIFIED,
                new_status=VehicleDocumentStatusChoices.EXPIRED,
                notes=f"Document expired on {doc_locked.document_expiry_date}.",
                metadata={"expiry_date": str(doc_locked.document_expiry_date)},
            )

            record_audit_entry(
                event_type="marketplace.vehicle_document.expired",
                action="marketplace:vehicle_document.expire",
                resource_type="VehiclePurchaseDocument",
                resource_id=str(doc_locked.id),
                actor_id=None,
                metadata={
                    "order_id": str(doc_locked.order_id),
                    "category": doc_locked.category,
                    "expiry_date": str(doc_locked.document_expiry_date),
                },
            )

            # If order was ready for handover, revert to DOCUMENTS_PENDING
            order = doc_locked.order
            if order.status == VehicleOrderStatusChoices.READY_FOR_HANDOVER:
                order.status = VehicleOrderStatusChoices.DOCUMENTS_PENDING
                order.save(update_fields=['status', 'updated_at'])

            count += 1

    return count


def get_document_for_download(document_id: str, user: User) -> Tuple[VehiclePurchaseDocument, Any]:
    """
    Secure access-controlled document retrieval for authenticated download:
    - Verifies user is the buyer, dealer organisation member, or authorised review staff.
    - Prevents public unauthenticated access.
    - Opens and returns (document, file_stream).
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication is required to download vehicle purchase documents.")

    try:
        document = VehiclePurchaseDocument.objects.select_related(
            'order', 'order__buyer', 'order__seller', 'order__organisation'
        ).get(pk=document_id)
    except VehiclePurchaseDocument.DoesNotExist:
        raise ValidationError("Document does not exist.")

    order = document.order
    if not can_user_access_order(user, order):
        raise PermissionDenied("You do not have permission to access documents for this vehicle order.")

    try:
        file_stream = document.file.open('rb')
    except Exception as exc:
        logger.error("Failed to open private document %s (%s): %s", document.id, document.file.name, exc)
        raise ValidationError("Document file could not be read from storage.")

    return document, file_stream

