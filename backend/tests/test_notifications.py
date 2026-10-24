import smtplib
from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    VehicleCatalogueApplication,
    CataloguePhotoProposal,
    CatalogueApplicationStatusChoices,
    FuelTypeChoices,
    TransmissionChoices,
)
from apps.marketplace.models import VehicleListing, ListingStatusChoices, VehicleEnquiry
from apps.notifications.handlers import handle_audit_log_saved, process_audit_entry
from apps.notifications.models import Notification, EmailStatusChoices
from apps.onboarding.models import SellerApplication, SellerApplicationStatusChoices, BusinessTypeChoices
from platform_core.audit.models import AuditLog
from platform_core.audit.writer import record_audit_entry, record_denied_audit_entry

NOTIFICATIONS_URL = "/api/v1/notifications/"
UNREAD_COUNT_URL = "/api/v1/notifications/unread-count/"
READ_ALL_URL = "/api/v1/notifications/read-all/"


def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def make_bmw(db):
    return VehicleMake.objects.create(name='BMW', country_of_origin='Germany')


@pytest.fixture
def model_m3(db, make_bmw):
    return VehicleModel.objects.create(make=make_bmw, name='M3', year_start=2021)


def _vehicle(seller, make, model, status_value, title='2022 BMW M3 Competition'):
    return VehicleListing.objects.create(
        seller=seller,
        title=title,
        make=make,
        model=model,
        year=2022,
        price=64950.00,
        mileage=12500,
        fuel_type=FuelTypeChoices.PETROL,
        transmission=TransmissionChoices.AUTOMATIC,
        status=status_value,
        is_active=True,
    )


@pytest.fixture
def pending_vehicle(db, seller_user, make_bmw, model_m3):
    return _vehicle(seller_user, make_bmw, model_m3, ListingStatusChoices.PENDING_APPROVAL)


@pytest.fixture
def approved_vehicle(db, seller_user, make_bmw, model_m3):
    return _vehicle(seller_user, make_bmw, model_m3, ListingStatusChoices.APPROVED)


@pytest.fixture
def pending_seller_application(db, buyer_user):
    return SellerApplication.objects.create(
        user=buyer_user,
        business_name='Northern Parts Ltd',
        business_type=BusinessTypeChoices.PARTS_MERCHANT,
        contact_email='hello@northernparts.test',
        contact_phone='+44 161 000 0000',
        status=SellerApplicationStatusChoices.PENDING,
        submitted_at=timezone.now(),
    )


@pytest.fixture
def seller_notification(db, seller_user, pending_vehicle, admin_auth_client):
    response = admin_auth_client.post(
        f"/api/v1/marketplace/admin/vehicles/{pending_vehicle.id}/review/",
        {"action": "APPROVE"},
        format='json',
    )
    assert response.status_code == status.HTTP_200_OK
    return Notification.objects.get(recipient=seller_user)


@pytest.fixture
def email_enabled(settings):
    settings.NOTIFICATIONS_EMAIL_ENABLED = True
    settings.NOTIFICATIONS_EMAIL_MAX_ATTEMPTS = 3
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    return settings


def _submit_enquiry(buyer, listing):
    response = auth_client(buyer).post(
        f"/api/v1/marketplace/vehicles/{listing.id}/enquire/",
        {"message": "Is this vehicle still available for viewing?"},
        format='json',
    )
    assert response.status_code == status.HTTP_201_CREATED
    return VehicleEnquiry.objects.get(buyer=buyer, listing=listing)


def _seller_patch_enquiry(seller, enquiry, payload):
    response = auth_client(seller).patch(
        f"/api/v1/marketplace/seller/enquiries/{enquiry.id}/", payload, format='json'
    )
    assert response.status_code == status.HTTP_200_OK
    return response


# ---------------------------------------------------------------------------
# Event → notification mapping
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_seller_application_approval_notifies_applicant(admin_auth_client, buyer_user, pending_seller_application):
    response = admin_auth_client.post(
        f"/api/v1/admin/seller-applications/{pending_seller_application.id}/review/",
        {"action": "APPROVE"},
        format='json',
    )
    assert response.status_code == status.HTTP_200_OK

    notification = Notification.objects.get(recipient=buyer_user)
    assert notification.event_type == 'seller.application.approved'
    assert 'Northern Parts Ltd' in notification.message
    assert notification.link == '/platform?tab=seller_onboarding'
    assert notification.resource_type == 'SellerApplication'
    assert notification.resource_id == str(pending_seller_application.id)
    assert notification.is_read is False
    assert notification.email_status == EmailStatusChoices.NOT_REQUIRED


@pytest.mark.django_db
def test_seller_application_rejection_notifies_applicant_with_reason(admin_auth_client, buyer_user, pending_seller_application):
    response = admin_auth_client.post(
        f"/api/v1/admin/seller-applications/{pending_seller_application.id}/review/",
        {"action": "REJECT", "reason": "Company registration number could not be verified."},
        format='json',
    )
    assert response.status_code == status.HTTP_200_OK

    notification = Notification.objects.get(recipient=buyer_user)
    assert notification.event_type == 'seller.application.rejected'
    assert 'Company registration number could not be verified.' in notification.message
    # Only the applicant is notified, never the reviewer.
    assert Notification.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "action,reason,event_type",
    [
        ("APPROVE", "", "listing.approved"),
        ("REJECT", "Photos do not match the vehicle.", "listing.rejected"),
        ("REQUEST_CHANGES", "Please add the service history.", "listing.changes_requested"),
    ],
)
def test_vehicle_listing_review_notifies_listing_seller(
    admin_auth_client, seller_user, admin_user, pending_vehicle, action, reason, event_type
):
    payload = {"action": action}
    if reason:
        payload["rejection_reason"] = reason
    response = admin_auth_client.post(
        f"/api/v1/marketplace/admin/vehicles/{pending_vehicle.id}/review/", payload, format='json'
    )
    assert response.status_code == status.HTTP_200_OK

    notifications = Notification.objects.all()
    assert notifications.count() == 1
    notification = notifications.get()
    assert notification.recipient == seller_user
    assert notification.event_type == event_type
    assert pending_vehicle.title in notification.title
    assert notification.link == '/platform?tab=seller_inventory'
    if reason:
        assert reason in notification.message
    assert not Notification.objects.filter(recipient=admin_user).exists()


@pytest.mark.django_db
def test_catalogue_application_rejection_notifies_submitting_seller(admin_auth_client, seller_user):
    application = VehicleCatalogueApplication.objects.create(
        seller=seller_user,
        make_name='Rivian',
        model_name='R1S',
        year_start=2023,
    )
    response = admin_auth_client.post(
        f"/api/v1/catalogue/applications/{application.id}/review/",
        {"action": "REJECT", "rejection_reason": "Duplicate of an existing model."},
        format='json',
    )
    assert response.status_code == status.HTTP_200_OK

    notification = Notification.objects.get(recipient=seller_user)
    assert notification.event_type == 'catalogue.application.rejected'
    assert 'Rivian R1S' in notification.message
    assert 'Duplicate of an existing model.' in notification.message
    assert notification.link == '/platform?tab=catalogue'


@pytest.mark.django_db
def test_catalogue_photo_proposal_rejection_notifies_submitting_seller(admin_auth_client, seller_user, model_m3):
    proposal = CataloguePhotoProposal.objects.create(
        model=model_m3,
        seller=seller_user,
        proposed_image_url='https://example.test/m3.jpg',
    )
    response = admin_auth_client.post(
        f"/api/v1/catalogue/photo-proposals/{proposal.id}/review/",
        {"action": "REJECT", "rejection_reason": "Image resolution too low."},
        format='json',
    )
    assert response.status_code == status.HTTP_200_OK

    notification = Notification.objects.get(recipient=seller_user)
    assert notification.event_type == 'catalogue.photo_proposal.rejected'
    assert 'Image resolution too low.' in notification.message


@pytest.mark.django_db
def test_catalogue_decision_skipped_when_resource_status_does_not_match(seller_user):
    # An audit row claiming approval for an application that is still pending must not notify.
    application = VehicleCatalogueApplication.objects.create(
        seller=seller_user, make_name='Rivian', model_name='R1T', year_start=2023,
        status=CatalogueApplicationStatusChoices.PENDING,
    )
    record_audit_entry(
        event_type='catalogue.application.approved',
        action='catalogue:application.approve',
        resource_type='VehicleCatalogueApplication',
        resource_id=str(application.id),
    )
    assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_vehicle_enquiry_creation_notifies_seller(buyer_user, seller_user, approved_vehicle):
    enquiry = _submit_enquiry(buyer_user, approved_vehicle)

    notification = Notification.objects.get()
    assert notification.recipient == seller_user
    assert notification.event_type == 'marketplace.vehicle_enquiry.created'
    assert notification.resource_id == str(enquiry.id)
    assert approved_vehicle.title in notification.message
    assert notification.link == '/platform?tab=seller_inventory'


@pytest.mark.django_db
def test_seller_reply_notifies_buyer_once_per_reply(buyer_user, seller_user, approved_vehicle):
    enquiry = _submit_enquiry(buyer_user, approved_vehicle)

    _seller_patch_enquiry(seller_user, enquiry, {"seller_reply": "Yes, available this weekend."})
    buyer_notifications = Notification.objects.filter(recipient=buyer_user)
    assert buyer_notifications.count() == 1
    reply_notification = buyer_notifications.get()
    assert reply_notification.event_type == 'marketplace.vehicle_enquiry.updated'
    assert reply_notification.link == '/platform?tab=my_enquiries'

    # Status-only and notes-only updates keep the existing reply and must not re-notify the buyer.
    _seller_patch_enquiry(seller_user, enquiry, {"status": "CLOSED"})
    _seller_patch_enquiry(seller_user, enquiry, {"seller_notes": "Called the buyer."})
    assert Notification.objects.filter(recipient=buyer_user).count() == 1

    # A genuinely new reply is notified again.
    _seller_patch_enquiry(seller_user, enquiry, {"seller_reply": "Update: price reduced by £500."})
    assert Notification.objects.filter(recipient=buyer_user).count() == 2


@pytest.mark.django_db
def test_enquiry_update_without_reply_does_not_notify_buyer(buyer_user, seller_user, approved_vehicle):
    enquiry = _submit_enquiry(buyer_user, approved_vehicle)
    _seller_patch_enquiry(seller_user, enquiry, {"status": "RESPONDED", "seller_notes": "Internal only"})
    assert not Notification.objects.filter(recipient=buyer_user).exists()


@pytest.mark.django_db
def test_stale_reply_is_not_renotified_from_metadata(buyer_user, seller_user, approved_vehicle):
    enquiry = _submit_enquiry(buyer_user, approved_vehicle)
    VehicleEnquiry.objects.filter(pk=enquiry.pk).update(
        seller_reply='Old reply', replied_at=timezone.now() - timedelta(days=3)
    )
    # Metadata says a reply exists, but the reply was not saved in this operation.
    record_audit_entry(
        event_type='marketplace.vehicle_enquiry.updated',
        action='marketplace:enquiry.update',
        resource_type='VehicleEnquiry',
        resource_id=str(enquiry.id),
        actor_id=seller_user.id,
        metadata={"has_reply": True},
    )
    assert not Notification.objects.filter(recipient=buyer_user).exists()


@pytest.mark.django_db
def test_org_member_added_notifies_new_member(seller_user, buyer_user, test_organisation):
    response = auth_client(seller_user).post(
        f"/api/v1/organisations/{test_organisation.id}/members/",
        {"email": buyer_user.email, "role": "MEMBER"},
        format='json',
    )
    assert response.status_code == status.HTTP_201_CREATED

    notification = Notification.objects.get()
    assert notification.recipient == buyer_user
    assert notification.event_type == 'org.member.added'
    assert test_organisation.name in notification.message
    assert notification.link == '/platform?tab=organisations'


@pytest.mark.django_db
def test_unsupported_events_do_not_create_notifications(seller_user, approved_vehicle):
    record_audit_entry(
        event_type='auth.login.success',
        action='auth:login',
        resource_type='User',
        resource_id=str(seller_user.id),
        actor_id=seller_user.id,
    )
    record_audit_entry(
        event_type='inventory.stock.adjusted',
        action='marketplace:stock.adjust',
        resource_type='SparePartListing',
        resource_id=str(approved_vehicle.id),
    )
    assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_denied_audit_entries_do_not_create_notifications(approved_vehicle):
    record_denied_audit_entry(
        action='listing:approve',
        event_type='listing.approved',
        resource_type='VehicleListing',
        resource_id=str(approved_vehicle.id),
        reason_code='PERMISSION_DENIED',
    )
    assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_missing_resource_is_skipped_without_error():
    import uuid
    record_audit_entry(
        event_type='listing.approved',
        action='listing:approve',
        resource_type='VehicleListing',
        resource_id=str(uuid.uuid4()),
    )
    assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_same_audit_entry_processed_twice_creates_one_notification(seller_notification, seller_user):
    entry = AuditLog.objects.get(id=seller_notification.source_audit_id)

    assert process_audit_entry(entry) == []
    handle_audit_log_saved(sender=AuditLog, instance=entry, created=True)

    assert Notification.objects.filter(recipient=seller_user).count() == 1


@pytest.mark.django_db
def test_handler_failure_does_not_break_business_operation(admin_auth_client, seller_user, pending_vehicle):
    with mock.patch('apps.notifications.handlers.create_notification', side_effect=RuntimeError('boom')):
        response = admin_auth_client.post(
            f"/api/v1/marketplace/admin/vehicles/{pending_vehicle.id}/review/",
            {"action": "APPROVE"},
            format='json',
        )
    assert response.status_code == status.HTTP_200_OK
    pending_vehicle.refresh_from_db()
    assert pending_vehicle.status == ListingStatusChoices.APPROVED
    assert Notification.objects.count() == 0


# ---------------------------------------------------------------------------
# API: authentication, isolation, unread filtering, read state
# ---------------------------------------------------------------------------

@pytest.mark.django_db
@pytest.mark.parametrize(
    "method,url",
    [
        ("get", NOTIFICATIONS_URL),
        ("get", UNREAD_COUNT_URL),
        ("post", READ_ALL_URL),
        ("post", "/api/v1/notifications/00000000-0000-0000-0000-000000000000/read/"),
    ],
)
def test_notification_endpoints_require_authentication(api_client, method, url):
    response = getattr(api_client, method)(url)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_list_returns_only_current_users_notifications(seller_notification, seller_user, buyer_user):
    seller_response = auth_client(seller_user).get(NOTIFICATIONS_URL)
    assert seller_response.status_code == status.HTTP_200_OK
    assert seller_response.data['count'] == 1
    item = seller_response.data['results'][0]
    assert item['id'] == str(seller_notification.id)
    assert item['is_read'] is False
    assert 'email_status' not in item and 'email_error' not in item

    buyer_response = auth_client(buyer_user).get(NOTIFICATIONS_URL)
    assert buyer_response.data['count'] == 0


@pytest.mark.django_db
def test_list_is_newest_first(seller_user, make_bmw, model_m3, admin_auth_client):
    first = _vehicle(seller_user, make_bmw, model_m3, ListingStatusChoices.PENDING_APPROVAL, title='First listing')
    second = _vehicle(seller_user, make_bmw, model_m3, ListingStatusChoices.PENDING_APPROVAL, title='Second listing')
    for listing in (first, second):
        admin_auth_client.post(
            f"/api/v1/marketplace/admin/vehicles/{listing.id}/review/", {"action": "APPROVE"}, format='json'
        )
    Notification.objects.filter(title__contains='First listing').update(created_at=timezone.now() - timedelta(minutes=5))

    results = auth_client(seller_user).get(NOTIFICATIONS_URL).data['results']
    assert [r['title'] for r in results] == ['Listing approved: Second listing', 'Listing approved: First listing']


@pytest.mark.django_db
def test_unread_filter_and_count(seller_notification, seller_user, make_bmw, model_m3, admin_auth_client):
    other = _vehicle(seller_user, make_bmw, model_m3, ListingStatusChoices.PENDING_APPROVAL, title='Another listing')
    admin_auth_client.post(f"/api/v1/marketplace/admin/vehicles/{other.id}/review/", {"action": "APPROVE"}, format='json')
    client = auth_client(seller_user)
    assert client.get(UNREAD_COUNT_URL).data['unread_count'] == 2

    client.post(f"{NOTIFICATIONS_URL}{seller_notification.id}/read/")

    assert client.get(UNREAD_COUNT_URL).data['unread_count'] == 1
    unread = client.get(NOTIFICATIONS_URL, {"unread": "true"}).data
    assert unread['count'] == 1
    assert unread['results'][0]['id'] != str(seller_notification.id)
    assert client.get(NOTIFICATIONS_URL, {"unread": "false"}).data['count'] == 2


@pytest.mark.django_db
def test_invalid_unread_filter_returns_400(seller_user):
    response = auth_client(seller_user).get(NOTIFICATIONS_URL, {"unread": "maybe"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data['status'] == 'error'


@pytest.mark.django_db
def test_mark_one_read_sets_read_at_and_is_idempotent(seller_notification, seller_user):
    client = auth_client(seller_user)
    url = f"{NOTIFICATIONS_URL}{seller_notification.id}/read/"

    response = client.post(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['notification']['is_read'] is True
    seller_notification.refresh_from_db()
    first_read_at = seller_notification.read_at
    assert first_read_at is not None

    assert client.post(url).status_code == status.HTTP_200_OK
    seller_notification.refresh_from_db()
    assert seller_notification.read_at == first_read_at


@pytest.mark.django_db
def test_user_cannot_mark_another_users_notification_read(seller_notification, buyer_user):
    response = auth_client(buyer_user).post(f"{NOTIFICATIONS_URL}{seller_notification.id}/read/")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    seller_notification.refresh_from_db()
    assert seller_notification.is_read is False


@pytest.mark.django_db
def test_mark_all_read_only_affects_current_user(seller_notification, seller_user, buyer_user, approved_vehicle):
    _submit_enquiry(buyer_user, approved_vehicle)  # second seller notification
    enquiry = VehicleEnquiry.objects.get()
    _seller_patch_enquiry(seller_user, enquiry, {"seller_reply": "Yes it is."})  # buyer notification

    response = auth_client(seller_user).post(READ_ALL_URL)
    assert response.status_code == status.HTTP_200_OK
    assert response.data['updated_count'] == 2

    assert not Notification.objects.filter(recipient=seller_user, is_read=False).exists()
    assert Notification.objects.filter(recipient=seller_user, read_at__isnull=True).count() == 0
    assert Notification.objects.filter(recipient=buyer_user, is_read=False).count() == 1


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_email_disabled_by_default(settings, seller_notification):
    assert settings.NOTIFICATIONS_EMAIL_ENABLED is False
    assert seller_notification.email_status == EmailStatusChoices.NOT_REQUIRED
    assert seller_notification.email_attempts == 0
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_email_is_sent_only_after_transaction_commit(
    email_enabled, admin_auth_client, seller_user, pending_vehicle, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        response = admin_auth_client.post(
            f"/api/v1/marketplace/admin/vehicles/{pending_vehicle.id}/review/", {"action": "APPROVE"}, format='json'
        )
        assert response.status_code == status.HTTP_200_OK
        notification = Notification.objects.get(recipient=seller_user)
        assert notification.email_status == EmailStatusChoices.PENDING
        assert len(mail.outbox) == 0

    assert len(callbacks) == 1
    callbacks[0]()

    notification.refresh_from_db()
    assert notification.email_status == EmailStatusChoices.SENT
    assert notification.email_attempts == 1
    assert notification.emailed_at is not None
    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.to == [seller_user.email]
    assert sent.subject == f"DriverXtra: {notification.title}"
    assert 'http://localhost:3000/platform?tab=seller_inventory' in sent.body


@pytest.mark.django_db
def test_email_failure_is_recorded_and_business_operation_succeeds(
    email_enabled, admin_auth_client, seller_user, pending_vehicle, django_capture_on_commit_callbacks
):
    with mock.patch(
        'apps.notifications.services.send_mail',
        side_effect=smtplib.SMTPAuthenticationError(535, b'Authentication failed'),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = admin_auth_client.post(
                f"/api/v1/marketplace/admin/vehicles/{pending_vehicle.id}/review/", {"action": "APPROVE"}, format='json'
            )

    assert response.status_code == status.HTTP_200_OK
    pending_vehicle.refresh_from_db()
    assert pending_vehicle.status == ListingStatusChoices.APPROVED

    notification = Notification.objects.get(recipient=seller_user)
    assert notification.email_status == EmailStatusChoices.FAILED
    assert notification.email_attempts == 1
    assert notification.email_error.startswith('SMTPAuthenticationError')
    assert notification.emailed_at is None


@pytest.mark.django_db
def test_retry_command_resends_failed_email(email_enabled, seller_notification):
    Notification.objects.filter(pk=seller_notification.pk).update(
        email_status=EmailStatusChoices.FAILED, email_attempts=1, email_error='SMTPServerDisconnected: x'
    )
    out = StringIO()
    call_command('retry_notification_emails', stdout=out)

    seller_notification.refresh_from_db()
    assert seller_notification.email_status == EmailStatusChoices.SENT
    assert seller_notification.email_attempts == 2
    assert seller_notification.email_error == ''
    assert len(mail.outbox) == 1
    assert '1 sent' in out.getvalue()


@pytest.mark.django_db
def test_retry_command_respects_attempt_limit(email_enabled, seller_notification):
    Notification.objects.filter(pk=seller_notification.pk).update(
        email_status=EmailStatusChoices.FAILED, email_attempts=1
    )
    with mock.patch('apps.notifications.services.send_mail', side_effect=smtplib.SMTPServerDisconnected('down')):
        for _ in range(5):
            call_command('retry_notification_emails', stdout=StringIO())

    seller_notification.refresh_from_db()
    assert seller_notification.email_status == EmailStatusChoices.FAILED
    assert seller_notification.email_attempts == 3  # NOTIFICATIONS_EMAIL_MAX_ATTEMPTS in the fixture


@pytest.mark.django_db
def test_retry_command_skips_recent_pending_and_sent(email_enabled, seller_notification):
    Notification.objects.filter(pk=seller_notification.pk).update(email_status=EmailStatusChoices.PENDING)
    call_command('retry_notification_emails', stdout=StringIO())
    seller_notification.refresh_from_db()
    assert seller_notification.email_status == EmailStatusChoices.PENDING  # too recent: post-commit send may still run

    call_command('retry_notification_emails', '--min-age-seconds=0', stdout=StringIO())
    seller_notification.refresh_from_db()
    assert seller_notification.email_status == EmailStatusChoices.SENT

    call_command('retry_notification_emails', '--min-age-seconds=0', stdout=StringIO())
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_retry_command_does_nothing_when_email_disabled(settings, seller_notification):
    Notification.objects.filter(pk=seller_notification.pk).update(email_status=EmailStatusChoices.FAILED)
    out = StringIO()
    call_command('retry_notification_emails', stdout=out)
    assert 'NOTIFICATIONS_EMAIL_ENABLED is False' in out.getvalue()
    assert len(mail.outbox) == 0
