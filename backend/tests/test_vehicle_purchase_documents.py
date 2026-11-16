import io
from datetime import timedelta
from decimal import Decimal
import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import (
    Permission,
    RoleChoices,
    StaffProfile,
    StaffRole,
    StaffRolePermission,
    User,
)
from apps.organisations.models import (
    Organisation,
    OrganisationMembership,
    OrganisationRoleChoices,
    OrganisationTypeChoices,
)
from apps.catalogue.models import (
    FuelTypeChoices,
    TransmissionChoices,
    VehicleMake,
    VehicleModel,
)
from apps.marketplace.models import (
    ImmutableRecordError,
    ListingStatusChoices,
    VehicleDocumentCategoryChoices,
    VehicleDocumentOwnerRoleChoices,
    VehicleDocumentReviewEventTypeChoices,
    VehicleDocumentReviewEvent,
    VehicleDocumentStatusChoices,
    VehicleListing,
    VehicleListingAvailabilityChoices,
    VehicleOfferStatusChoices,
    VehicleOrder,
    VehicleOrderStatusChoices,
    VehiclePurchaseDocument,
    VehiclePurchaseOffer,
)
from apps.marketplace.vehicle_documents_service import (
    check_expired_vehicle_documents,
    get_document_for_download,
    get_document_requirements_for_order,
    get_vehicle_order_document_readiness,
    submit_vehicle_order_document,
    validate_document_file,
    verify_vehicle_document,
)


@pytest.fixture
def make_bmw(db):
    return VehicleMake.objects.create(name='BMW', country_of_origin='Germany')


@pytest.fixture
def model_m3(db, make_bmw):
    return VehicleModel.objects.create(make=make_bmw, name='M3 Competition', year_start=2023)


@pytest.fixture
def seller_user(db):
    user = User.objects.create_user(
        email='dealer_principal@bavarian.co.uk',
        password='SecurePassword123!',
        first_name='David',
        last_name='Dealer',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def dealer_org(db, seller_user):
    org = Organisation.objects.create(
        name="Bavarian Motors London",
        slug="bavarian-motors-london",
        type=OrganisationTypeChoices.DEALER_GROUP,
    )
    OrganisationMembership.objects.create(
        user=seller_user,
        organisation=org,
        role=OrganisationRoleChoices.OWNER,
        is_active=True,
    )
    return org


@pytest.fixture
def dealer_colleague(db, dealer_org):
    colleague = User.objects.create_user(
        email='dealer_admin@bavarian.co.uk',
        password='SecurePassword123!',
        first_name='Derek',
        last_name='Admin',
        is_email_verified=True,
    )
    colleague.add_role(RoleChoices.SELLER)
    OrganisationMembership.objects.create(
        user=colleague,
        organisation=dealer_org,
        role=OrganisationRoleChoices.ADMIN,
        is_active=True,
    )
    return colleague


@pytest.fixture
def buyer_user(db):
    user = User.objects.create_user(
        email='buyer_john@gmail.com',
        password='SecurePassword123!',
        first_name='John',
        last_name='Buyer',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def unrelated_user(db):
    user = User.objects.create_user(
        email='unrelated@gmail.com',
        password='SecurePassword123!',
        first_name='Eve',
        last_name='Unrelated',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def staff_reviewer(db):
    user = User.objects.create_user(
        email='review_officer@driverxtra.com',
        password='SecurePassword123!',
        first_name='Rachel',
        last_name='Reviewer',
        is_email_verified=True,
        is_staff=True,
    )
    user.add_role(RoleChoices.ADMIN)
    return user


@pytest.fixture
def vehicle_order(db, buyer_user, seller_user, dealer_org, make_bmw, model_m3):
    listing = VehicleListing.objects.create(
        seller=seller_user,
        organisation=dealer_org,
        title='2023 BMW M3 Competition',
        make=make_bmw,
        model=model_m3,
        year=2023,
        price=75000.00,
        currency='GBP',
        mileage=6000,
        fuel_type=FuelTypeChoices.PETROL,
        transmission=TransmissionChoices.AUTOMATIC,
        status=ListingStatusChoices.APPROVED,
        availability_status=VehicleListingAvailabilityChoices.RESERVED,
        is_active=True,
        location_city='London',
        location_postcode='W1K 7AA',
    )
    now = timezone.now()
    offer = VehiclePurchaseOffer.objects.create(
        listing=listing,
        buyer=buyer_user,
        seller=seller_user,
        organisation=dealer_org,
        status=VehicleOfferStatusChoices.ACCEPTED,
        agreed_price=Decimal('74000.00'),
        currency='GBP',
        expires_at=now + timedelta(days=2),
        accepted_at=now,
    )
    order = VehicleOrder.objects.create(
        order_number='ORD-TEST-DOCS-001',
        listing=listing,
        accepted_offer=offer,
        buyer=buyer_user,
        seller=seller_user,
        organisation=dealer_org,
        status=VehicleOrderStatusChoices.PAYMENT_CONFIRMED,
        agreed_price=Decimal('74000.00'),
        currency='GBP',
        handover_type='COLLECTION',
        payment_deadline=now + timedelta(days=5),
        market_timezone='Europe/London',
        payment_confirmed_at=now,
        confirmed_by=seller_user,
    )
    return order


def make_dummy_pdf(content: bytes = b"%PDF-1.4 dummy vehicle registration document content") -> SimpleUploadedFile:
    return SimpleUploadedFile("v5c_registration.pdf", content, content_type="application/pdf")


def make_dummy_png(content: bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR dummy") -> SimpleUploadedFile:
    return SimpleUploadedFile("buyer_licence.png", content, content_type="image/png")


# ==============================================================================
# 1. Buyer & Dealer Upload Scopes and Ownership Boundaries
# ==============================================================================

@pytest.mark.django_db
def test_buyer_uploads_only_to_their_own_order(vehicle_order, buyer_user, unrelated_user):
    """Buyer can upload buyer documents to their own order, but unrelated users are denied."""
    pdf = make_dummy_pdf()
    doc = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=buyer_user,
        category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
        file_obj=pdf,
    )
    assert doc.id is not None
    assert doc.document_owner_role == VehicleDocumentOwnerRoleChoices.BUYER
    assert doc.status == VehicleDocumentStatusChoices.PENDING_REVIEW

    # Unrelated user cannot upload to this order
    pdf2 = make_dummy_pdf()
    with pytest.raises(PermissionDenied) as exc:
        submit_vehicle_order_document(
            order_id=str(vehicle_order.id),
            user=unrelated_user,
            category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
            file_obj=pdf2,
        )
    assert "neither the buyer nor the seller" in str(exc.value)


@pytest.mark.django_db
def test_dealer_uploads_to_their_organisation_orders(vehicle_order, seller_user, dealer_colleague, unrelated_user):
    """Dealer principal and organisation members can upload dealer documents; unrelated users cannot."""
    pdf = make_dummy_pdf()
    doc = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=seller_user,
        category=VehicleDocumentCategoryChoices.REGISTRATION_CERTIFICATE,
        file_obj=pdf,
    )
    assert doc.id is not None
    assert doc.document_owner_role == VehicleDocumentOwnerRoleChoices.DEALER

    # Colleague in same organisation can also upload dealer documents
    mot_pdf = make_dummy_pdf()
    doc2 = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=dealer_colleague,
        category=VehicleDocumentCategoryChoices.ROADWORTHINESS_CERTIFICATE,
        file_obj=mot_pdf,
        document_expiry_date=timezone.now().date() + timedelta(days=180),
    )
    assert doc2.id is not None
    assert doc2.version_number == 1

    # Dealer cannot upload buyer documents
    buyer_doc = make_dummy_pdf()
    with pytest.raises(PermissionDenied):
        submit_vehicle_order_document(
            order_id=str(vehicle_order.id),
            user=seller_user,
            category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
            file_obj=buyer_doc,
        )


# ==============================================================================
# 2. File Validation: MIME, Magic Bytes, Prohibited Extensions, and Size Limits
# ==============================================================================

@pytest.mark.django_db
def test_invalid_file_type_is_rejected():
    """An executable or malicious file disguised with a .pdf extension is rejected by magic bytes."""
    fake_pdf = SimpleUploadedFile("malicious.pdf", b"MZ\x90\x00\x03\x00\x00\x00DOS_EXE_HEADER", content_type="application/pdf")
    with pytest.raises(ValidationError) as exc:
        validate_document_file(fake_pdf)
    assert "Invalid file content or unsupported format" in str(exc.value)

    # Disallowed extension is rejected
    sh_file = SimpleUploadedFile("script.sh", b"#!/bin/bash\necho bad", content_type="text/x-sh")
    with pytest.raises(ValidationError) as exc2:
        validate_document_file(sh_file)
    assert "strictly prohibited" in str(exc2.value)


@pytest.mark.django_db
def test_oversized_file_is_rejected():
    """Files exceeding 10 MB are rejected."""
    oversized = SimpleUploadedFile("huge.pdf", b"%PDF" + b"0" * (11 * 1024 * 1024), content_type="application/pdf")
    with pytest.raises(ValidationError) as exc:
        validate_document_file(oversized)
    assert "exceeds the maximum permitted limit" in str(exc.value)


# ==============================================================================
# 3. Private Storage & Access-Controlled Download
# ==============================================================================

@pytest.mark.django_db
def test_private_storage_prevents_public_url(vehicle_order, seller_user):
    """Calling .url on private document file raises ValueError."""
    pdf = make_dummy_pdf()
    doc = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=seller_user,
        category=VehicleDocumentCategoryChoices.PURCHASE_INVOICE,
        file_obj=pdf,
    )
    with pytest.raises(ValueError) as exc:
        _ = doc.file.url
    assert "Private vehicle document storage does not provide public URLs" in str(exc.value)


@pytest.mark.django_db
def test_access_controlled_download(vehicle_order, buyer_user, seller_user, unrelated_user):
    """Authorised buyer and seller can download; anonymous or unrelated users are denied."""
    pdf = make_dummy_pdf()
    doc = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=seller_user,
        category=VehicleDocumentCategoryChoices.REGISTRATION_CERTIFICATE,
        file_obj=pdf,
    )

    # Buyer can download dealer compliance doc for their order
    retrieved_doc, stream = get_document_for_download(str(doc.id), buyer_user)
    assert retrieved_doc.id == doc.id
    assert stream.read().startswith(b"%PDF")
    stream.close()

    # Seller can download
    _, stream2 = get_document_for_download(str(doc.id), seller_user)
    assert stream2.read().startswith(b"%PDF")
    stream2.close()

    # Unrelated user is denied
    with pytest.raises(PermissionDenied):
        get_document_for_download(str(doc.id), unrelated_user)


# ==============================================================================
# 4. Review Workflow, Self-Verification Prevention, and Rejection Reasons
# ==============================================================================

@pytest.mark.django_db
def test_reviewers_cannot_verify_own_submissions(vehicle_order, buyer_user, seller_user):
    """Users are strictly forbidden from approving or rejecting documents they submitted."""
    pdf = make_dummy_png()
    doc = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=buyer_user,
        category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
        file_obj=pdf,
    )

    # Buyer attempts to approve their own document -> Denied
    with pytest.raises(PermissionDenied) as exc:
        verify_vehicle_document(
            document_id=str(doc.id),
            reviewer=buyer_user,
            approved=True,
        )
    assert "cannot verify or reject a document that you submitted yourself" in str(exc.value)


@pytest.mark.django_db
def test_rejection_requires_reason_and_records_history(vehicle_order, buyer_user, seller_user):
    """Rejection requires a documented reason and preserves append-only review events."""
    png = make_dummy_png()
    doc = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=buyer_user,
        category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
        file_obj=png,
    )

    # Reject without reason -> ValidationError
    with pytest.raises(ValidationError) as exc:
        verify_vehicle_document(
            document_id=str(doc.id),
            reviewer=seller_user,
            approved=False,
            rejection_reason="",
        )
    assert "clear rejection reason must be documented" in str(exc.value)

    # Reject with valid reason
    rejected_doc = verify_vehicle_document(
        document_id=str(doc.id),
        reviewer=seller_user,
        approved=False,
        rejection_reason="Driving licence scan is blurry and expiration date unreadable.",
    )
    assert rejected_doc.status == VehicleDocumentStatusChoices.REJECTED
    assert rejected_doc.rejection_reason == "Driving licence scan is blurry and expiration date unreadable."
    assert rejected_doc.verified_by == seller_user

    events = rejected_doc.review_events.all()
    assert events.count() == 2  # SUBMITTED, REJECTED
    assert events.filter(event_type=VehicleDocumentReviewEventTypeChoices.REJECTED).exists()


@pytest.mark.django_db
def test_rejected_documents_can_be_replaced_and_versions_preserved(vehicle_order, buyer_user, seller_user):
    """Rejected documents can be superseded by a new version; history remains accessible."""
    png_v1 = make_dummy_png()
    doc_v1 = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=buyer_user,
        category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
        file_obj=png_v1,
    )
    verify_vehicle_document(
        document_id=str(doc_v1.id),
        reviewer=seller_user,
        approved=False,
        rejection_reason="Blurry photo.",
    )

    # Buyer uploads clear replacement v2
    png_v2 = make_dummy_png(b"\x89PNG\r\n\x1a\nclear_photo_version_2")
    doc_v2 = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=buyer_user,
        category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
        file_obj=png_v2,
        notes="High-resolution scan attached as requested.",
    )

    assert doc_v2.version_number == 2
    assert doc_v2.is_latest is True
    assert doc_v2.status == VehicleDocumentStatusChoices.PENDING_REVIEW

    # v1 is preserved as non-latest
    doc_v1.refresh_from_db()
    assert doc_v1.version_number == 1
    assert doc_v1.is_latest is False
    assert doc_v1.status == VehicleDocumentStatusChoices.REJECTED

    # Dealer approves v2
    verified_v2 = verify_vehicle_document(
        document_id=str(doc_v2.id),
        reviewer=seller_user,
        approved=True,
    )
    assert verified_v2.status == VehicleDocumentStatusChoices.VERIFIED


# ==============================================================================
# 5. Duplicate Verification Prevention
# ==============================================================================

@pytest.mark.django_db
def test_duplicate_verification_prevented(vehicle_order, buyer_user, seller_user):
    """Once a document is VERIFIED or REJECTED, subsequent verification attempts fail."""
    png = make_dummy_png()
    doc = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=buyer_user,
        category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
        file_obj=png,
    )
    verify_vehicle_document(
        document_id=str(doc.id),
        reviewer=seller_user,
        approved=True,
    )

    # Attempt second verification
    with pytest.raises(ValidationError) as exc:
        verify_vehicle_document(
            document_id=str(doc.id),
            reviewer=seller_user,
            approved=True,
        )
    assert "Only documents in PENDING_REVIEW can be verified" in str(exc.value)


# ==============================================================================
# 6. Expiry Tracking and Status Adjustment
# ==============================================================================

@pytest.mark.django_db
def test_expired_documents_are_not_treated_as_verified(vehicle_order, seller_user, staff_reviewer):
    """Documents whose expiry date has passed transition to EXPIRED and block readiness."""
    yesterday = timezone.now().date() - timedelta(days=1)
    tomorrow = timezone.now().date() + timedelta(days=30)

    # Cannot submit with already expired date
    pdf_expired = make_dummy_pdf()
    with pytest.raises(ValidationError) as exc:
        submit_vehicle_order_document(
            order_id=str(vehicle_order.id),
            user=seller_user,
            category=VehicleDocumentCategoryChoices.ROADWORTHINESS_CERTIFICATE,
            file_obj=pdf_expired,
            document_expiry_date=yesterday,
        )
    assert "has already passed" in str(exc.value)

    # Upload valid document expiring tomorrow
    pdf_valid = make_dummy_pdf()
    doc = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=seller_user,
        category=VehicleDocumentCategoryChoices.ROADWORTHINESS_CERTIFICATE,
        file_obj=pdf_valid,
        document_expiry_date=tomorrow,
    )
    verify_vehicle_document(
        document_id=str(doc.id),
        reviewer=staff_reviewer,
        approved=True,
    )
    doc.refresh_from_db()
    assert doc.status == VehicleDocumentStatusChoices.VERIFIED

    # Simulate passing of time
    VehiclePurchaseDocument.objects.filter(id=doc.id).update(document_expiry_date=yesterday)

    # Run check_expired_vehicle_documents
    expired_count = check_expired_vehicle_documents()
    assert expired_count == 1

    doc.refresh_from_db()
    assert doc.status == VehicleDocumentStatusChoices.EXPIRED


# ==============================================================================
# 7. Document Readiness and Ready-for-Handover Independence
# ==============================================================================

@pytest.mark.django_db
def test_document_readiness_and_ready_for_handover_transition(
    vehicle_order, buyer_user, seller_user, staff_reviewer
):
    """Order is only marked READY_FOR_HANDOVER when all required docs are verified AND payment confirmed."""
    readiness_initial = get_vehicle_order_document_readiness(vehicle_order)
    assert readiness_initial['all_required_verified'] is False
    assert readiness_initial['can_transition_to_handover'] is False

    # Upload and verify all required documents for UK collection
    # 1. Dealer V5C
    v5c = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=seller_user,
        category=VehicleDocumentCategoryChoices.REGISTRATION_CERTIFICATE,
        file_obj=make_dummy_pdf(),
    )
    verify_vehicle_document(str(v5c.id), staff_reviewer, approved=True)

    # 2. Dealer MOT
    mot = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=seller_user,
        category=VehicleDocumentCategoryChoices.ROADWORTHINESS_CERTIFICATE,
        file_obj=make_dummy_pdf(),
        document_expiry_date=timezone.now().date() + timedelta(days=200),
    )
    verify_vehicle_document(str(mot.id), staff_reviewer, approved=True)

    # 3. Dealer Invoice
    inv = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=seller_user,
        category=VehicleDocumentCategoryChoices.PURCHASE_INVOICE,
        file_obj=make_dummy_pdf(),
    )
    verify_vehicle_document(str(inv.id), staff_reviewer, approved=True)

    # 4. Buyer ID
    buyer_id = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=buyer_user,
        category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
        file_obj=make_dummy_png(),
    )
    verify_vehicle_document(str(buyer_id.id), seller_user, approved=True)

    # All required documents are now verified
    readiness_final = get_vehicle_order_document_readiness(vehicle_order)
    assert readiness_final['all_required_verified'] is True
    assert readiness_final['can_transition_to_handover'] is True

    # Order automatically transitioned to READY_FOR_HANDOVER since payment was already confirmed
    vehicle_order.refresh_from_db()
    assert vehicle_order.status == VehicleOrderStatusChoices.READY_FOR_HANDOVER


# ==============================================================================
# 8. REST API Endpoints Verification
# ==============================================================================

@pytest.mark.django_db
def test_vehicle_document_api_endpoints(vehicle_order, buyer_user, seller_user, unrelated_user):
    """Tests document list, upload, verify, and streaming download endpoints."""
    client = APIClient()

    # Anonymous access is rejected
    res = client.get(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED

    # Buyer lists documents
    client.force_authenticate(user=buyer_user)
    res = client.get(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/")
    assert res.status_code == status.HTTP_200_OK
    assert "readiness" in res.data
    assert "documents" in res.data

    # Buyer uploads document
    png = make_dummy_png()
    upload_res = client.post(
        f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/upload/",
        {
            "category": VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
            "file": png,
            "notes": "Driver license upload via API",
        },
        format="multipart",
    )
    assert upload_res.status_code == status.HTTP_201_CREATED
    doc_id = upload_res.data["id"]

    # Dealer verifies document via API
    client.force_authenticate(user=seller_user)
    verify_res = client.post(
        f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/{doc_id}/verify/",
        {"action": "APPROVE", "notes": "Approved via dealer dashboard"},
        format="json",
    )
    assert verify_res.status_code == status.HTTP_200_OK
    assert verify_res.data["status"] == VehicleDocumentStatusChoices.VERIFIED

    # Download document
    download_res = client.get(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/{doc_id}/download/")
    assert download_res.status_code == status.HTTP_200_OK
    assert download_res["Content-Type"] == "image/png"
    assert "attachment; filename=" in download_res["Content-Disposition"]

    # Unrelated user cannot download
    client.force_authenticate(user=unrelated_user)
    unauth_download = client.get(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/{doc_id}/download/")
    assert unauth_download.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_anonymous_cannot_access_any_document_endpoints(vehicle_order, buyer_user):
    """Anonymous unauthenticated requests to list, upload, verify, or download are rejected with 401."""
    client = APIClient()

    # Pre-upload a document as buyer
    doc = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=buyer_user,
        category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
        file_obj=make_dummy_png(),
    )

    # 1. Anonymous list
    res_list = client.get(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/")
    assert res_list.status_code == status.HTTP_401_UNAUTHORIZED

    # 2. Anonymous upload
    res_upload = client.post(
        f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/upload/",
        {"category": VehicleDocumentCategoryChoices.BUYER_ID_PROOF, "file": make_dummy_png()},
        format="multipart",
    )
    assert res_upload.status_code == status.HTTP_401_UNAUTHORIZED

    # 3. Anonymous verify
    res_verify = client.post(
        f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/{doc.id}/verify/",
        {"action": "APPROVE"},
        format="json",
    )
    assert res_verify.status_code == status.HTTP_401_UNAUTHORIZED

    # 4. Anonymous download
    res_download = client.get(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/{doc.id}/download/")
    assert res_download.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_cross_buyer_and_cross_dealer_isolation(vehicle_order, buyer_user, seller_user, dealer_org):
    """
    Buyer A cannot access Buyer B's documents.
    Dealer A cannot access Dealer B's documents.
    """
    client = APIClient()

    # Create Buyer B (different buyer)
    buyer_b = User.objects.create_user(
        email="buyer_b@example.com",
        password="SecurePassword123!",
        first_name="Buyer",
        last_name="Beta",
        is_email_verified=True,
    )
    buyer_b.add_role(RoleChoices.BUYER)

    # Create Dealer B (different seller & dealership organisation)
    dealer_b = User.objects.create_user(
        email="dealer_b@motors.co.uk",
        password="SecurePassword123!",
        first_name="Dealer",
        last_name="Beta",
        is_email_verified=True,
    )
    dealer_b.add_role(RoleChoices.SELLER)
    org_b = Organisation.objects.create(
        name="Apex Motors Manchester",
        slug="apex-motors-manchester",
        type=OrganisationTypeChoices.DEALER_GROUP,
    )
    OrganisationMembership.objects.create(
        user=dealer_b,
        organisation=org_b,
        role=OrganisationRoleChoices.OWNER,
        is_active=True,
    )

    # Upload document to vehicle_order (which belongs to buyer_user and dealer_org)
    doc = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=buyer_user,
        category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
        file_obj=make_dummy_png(),
    )

    # --- Buyer B attempts on Order A ---
    client.force_authenticate(user=buyer_b)
    # 1. Buyer B cannot list documents
    res = client.get(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/")
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # 2. Buyer B cannot upload documents
    res = client.post(
        f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/upload/",
        {"category": VehicleDocumentCategoryChoices.BUYER_ID_PROOF, "file": make_dummy_png()},
        format="multipart",
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # 3. Buyer B cannot download documents
    res = client.get(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/{doc.id}/download/")
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # --- Dealer B attempts on Order A ---
    client.force_authenticate(user=dealer_b)
    # 1. Dealer B cannot list documents
    res = client.get(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/")
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # 2. Dealer B cannot upload documents
    res = client.post(
        f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/upload/",
        {"category": VehicleDocumentCategoryChoices.REGISTRATION_CERTIFICATE, "file": make_dummy_pdf()},
        format="multipart",
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # 3. Dealer B cannot verify documents
    res = client.post(
        f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/{doc.id}/verify/",
        {"action": "APPROVE"},
        format="json",
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # 4. Dealer B cannot download documents
    res = client.get(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/{doc.id}/download/")
    assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_ordinary_staff_without_explicit_review_permission_cannot_access(vehicle_order, buyer_user):
    """
    Ordinary staff without explicit 'marketplace.vehicle_document.review' permission
    cannot list, download, or verify private vehicle documents.
    """
    client = APIClient()

    # Pre-upload a document
    doc = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=buyer_user,
        category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
        file_obj=make_dummy_png(),
    )

    # Create an ordinary staff member with a non-review role (e.g. SUPPORT_AGENT)
    support_staff = User.objects.create_user(
        email="support_clerk@driverxtra.com",
        password="SecurePassword123!",
        first_name="Sam",
        last_name="Support",
        is_email_verified=True,
        is_staff=True,
    )
    support_staff.add_role(RoleChoices.STAFF)
    support_role, _ = StaffRole.objects.get_or_create(
        code="SUPPORT_AGENT",
        defaults={"name": "Support Agent", "description": "General customer support"},
    )
    StaffProfile.objects.create(user=support_staff, staff_role=support_role)

    client.force_authenticate(user=support_staff)

    # 1. Ordinary staff cannot list private documents
    res_list = client.get(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/")
    assert res_list.status_code == status.HTTP_403_FORBIDDEN

    # 2. Ordinary staff cannot download private document
    res_dl = client.get(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/{doc.id}/download/")
    assert res_dl.status_code == status.HTTP_403_FORBIDDEN

    # 3. Ordinary staff cannot verify document
    res_v = client.post(
        f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/{doc.id}/verify/",
        {"action": "APPROVE"},
        format="json",
    )
    assert res_v.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_authorised_reviewer_can_access_and_verify(vehicle_order, buyer_user):
    """Authorised staff with explicit 'marketplace.vehicle_document.review' permission can list, download, and verify."""
    client = APIClient()

    doc = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=buyer_user,
        category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
        file_obj=make_dummy_png(),
    )

    # Create staff reviewer with explicit permission
    review_perm, _ = Permission.objects.get_or_create(
        code="marketplace.vehicle_document.review",
        defaults={"name": "Review Vehicle Documents"},
    )
    officer_role, _ = StaffRole.objects.get_or_create(
        code="VERIFICATION_OFFICER",
        defaults={"name": "Verification Officer", "description": "Authorised to review vehicle docs"},
    )
    StaffRolePermission.objects.get_or_create(staff_role=officer_role, permission=review_perm)

    officer = User.objects.create_user(
        email="compliance_officer@driverxtra.com",
        password="SecurePassword123!",
        first_name="Carol",
        last_name="Compliance",
        is_email_verified=True,
        is_staff=True,
    )
    officer.add_role(RoleChoices.STAFF)
    StaffProfile.objects.create(user=officer, staff_role=officer_role)

    client.force_authenticate(user=officer)

    # 1. Can list
    res_list = client.get(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/")
    assert res_list.status_code == status.HTTP_200_OK

    # 2. Can download
    res_dl = client.get(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/{doc.id}/download/")
    assert res_dl.status_code == status.HTTP_200_OK

    # 3. Can verify
    res_v = client.post(
        f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/{doc.id}/verify/",
        {"action": "APPROVE", "notes": "Approved by authorised compliance officer"},
        format="json",
    )
    assert res_v.status_code == status.HTTP_200_OK
    assert res_v.data["status"] == VehicleDocumentStatusChoices.VERIFIED


@pytest.mark.django_db
def test_document_listing_does_not_expose_storage_paths_or_public_urls(vehicle_order, buyer_user):
    """Listing response never exposes storage paths or direct public URLs."""
    client = APIClient()

    submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=buyer_user,
        category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
        file_obj=make_dummy_png(),
    )

    client.force_authenticate(user=buyer_user)
    res = client.get(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/")
    assert res.status_code == status.HTTP_200_OK

    docs = res.data["documents"]
    assert len(docs) >= 1
    for doc in docs:
        # 'file' field must NOT be exposed
        assert "file" not in doc
        # download_url must use API endpoint, not filesystem or cloud bucket URL
        dl_url = doc["download_url"]
        assert dl_url.startswith(f"/api/v1/marketplace/vehicle-orders/{vehicle_order.id}/documents/")
        assert dl_url.endswith("/download/")
        assert "private_media" not in dl_url
        assert "http://" not in dl_url and "https://" not in dl_url
        assert "\\" not in dl_url


@pytest.mark.django_db
def test_superseded_version_cannot_satisfy_readiness(vehicle_order, buyer_user, seller_user):
    """When a document is superseded by a new version, the superseded version no longer satisfies readiness."""
    # Step 1: Upload and approve v1
    v1 = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=buyer_user,
        category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
        file_obj=make_dummy_png(),
    )
    verify_vehicle_document(document_id=str(v1.id), reviewer=seller_user, approved=True)

    v1.refresh_from_db()
    assert v1.status == VehicleDocumentStatusChoices.VERIFIED
    assert v1.is_latest is True

    # Step 2: Buyer uploads v2 replacement
    v2 = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=buyer_user,
        category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
        file_obj=make_dummy_png(),
    )

    v1.refresh_from_db()
    v2.refresh_from_db()
    assert v1.is_latest is False
    assert v1.status == VehicleDocumentStatusChoices.SUPERSEDED
    assert v2.is_latest is True
    assert v2.status == VehicleDocumentStatusChoices.PENDING_REVIEW

    # Document readiness must reflect that BUYER_ID_PROOF is PENDING, NOT satisfied
    readiness = get_vehicle_order_document_readiness(vehicle_order)
    cat_req = next(r for r in readiness["requirements"] if r["category"] == VehicleDocumentCategoryChoices.BUYER_ID_PROOF)
    assert cat_req["status"] == VehicleDocumentStatusChoices.PENDING_REVIEW
    assert cat_req["latest_document"]["version_number"] == 2
    assert cat_req["previous_versions_count"] == 1
    assert readiness["all_required_verified"] is False


@pytest.mark.django_db
def test_handover_readiness_strict_dual_condition(vehicle_order, buyer_user, seller_user, staff_reviewer):
    """
    Order transitions to READY_FOR_HANDOVER strictly when:
    1. Payment is confirmed AND
    2. All required documents are verified.
    Neither alone is sufficient.
    """
    # Case 1: Payment NOT confirmed, but all documents verified
    vehicle_order.status = VehicleOrderStatusChoices.PAYMENT_PENDING
    vehicle_order.payment_confirmed_at = None
    vehicle_order.save()

    reqs = get_document_requirements_for_order(vehicle_order)
    for req in reqs:
        uploader = seller_user if req.owner_role == VehicleDocumentOwnerRoleChoices.DEALER else buyer_user
        f = make_dummy_pdf() if req.owner_role == VehicleDocumentOwnerRoleChoices.DEALER else make_dummy_png()
        exp = timezone.now().date() + timedelta(days=365) if req.requires_expiry_date else None
        d = submit_vehicle_order_document(
            order_id=str(vehicle_order.id),
            user=uploader,
            category=req.category,
            file_obj=f,
            document_expiry_date=exp,
        )
        verify_vehicle_document(document_id=str(d.id), reviewer=staff_reviewer, approved=True)

    vehicle_order.refresh_from_db()
    # Documents are 100% verified, but payment is unconfirmed -> NOT ready for handover
    assert vehicle_order.status == VehicleOrderStatusChoices.PAYMENT_PENDING

    # Case 2: Payment is confirmed now -> transitions immediately to READY_FOR_HANDOVER
    vehicle_order.status = VehicleOrderStatusChoices.PAYMENT_CONFIRMED
    vehicle_order.payment_confirmed_at = timezone.now()
    vehicle_order.save()

    readiness = get_vehicle_order_document_readiness(vehicle_order)
    assert readiness["all_required_verified"] is True
    assert readiness["has_payment_confirmed"] is True
    assert readiness["can_transition_to_handover"] is True

    # Case 3: Re-verify an upload to trigger sync
    # If a document now expires, order status must revert from READY_FOR_HANDOVER to DOCUMENTS_PENDING
    vehicle_order.status = VehicleOrderStatusChoices.READY_FOR_HANDOVER
    vehicle_order.save()

    # Expire MOT document
    mot_doc = vehicle_order.documents.filter(category=VehicleDocumentCategoryChoices.ROADWORTHINESS_CERTIFICATE).first()
    mot_doc.document_expiry_date = timezone.now().date() - timedelta(days=1)
    mot_doc.save()

    expired_count = check_expired_vehicle_documents()
    assert expired_count >= 1

    vehicle_order.refresh_from_db()
    assert vehicle_order.status == VehicleOrderStatusChoices.DOCUMENTS_PENDING


@pytest.mark.django_db
def test_concurrent_upload_duplicate_version_prevented_by_constraint(vehicle_order, seller_user):
    """Database UniqueConstraint prevents duplicate (order, category, version_number)."""
    pdf = make_dummy_pdf()
    doc1 = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=seller_user,
        category=VehicleDocumentCategoryChoices.REGISTRATION_CERTIFICATE,
        file_obj=pdf,
    )
    assert doc1.version_number == 1

    # Attempting to directly insert another document with version_number 1 for the same order and category
    with pytest.raises(IntegrityError):
        VehiclePurchaseDocument.objects.create(
            order=vehicle_order,
            category=VehicleDocumentCategoryChoices.REGISTRATION_CERTIFICATE,
            document_owner_role=VehicleDocumentOwnerRoleChoices.DEALER,
            version_number=1,  # Duplicate!
            submitted_by=seller_user,
            file=doc1.file,
            original_filename="duplicate_v5c.pdf",
            mime_type="application/pdf",
            file_size=1024,
            status=VehicleDocumentStatusChoices.PENDING_REVIEW,
        )


@pytest.mark.django_db
def test_review_events_are_immutable(vehicle_order, buyer_user, seller_user):
    """VehicleDocumentReviewEvent records cannot be updated or deleted."""
    doc = submit_vehicle_order_document(
        order_id=str(vehicle_order.id),
        user=buyer_user,
        category=VehicleDocumentCategoryChoices.BUYER_ID_PROOF,
        file_obj=make_dummy_png(),
    )
    event = VehicleDocumentReviewEvent.objects.filter(document=doc).first()
    assert event is not None

    # Mutating an event must raise ImmutableRecordError
    event.notes = "Tampered notes"
    with pytest.raises(ImmutableRecordError):
        event.save()

    # Deleting an event must raise ImmutableRecordError
    with pytest.raises(ImmutableRecordError):
        event.delete()

