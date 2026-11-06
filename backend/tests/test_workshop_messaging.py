import uuid
from datetime import date, timedelta
from decimal import Decimal
import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken
from channels.testing import WebsocketCommunicator

from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationMembership, OrganisationRoleChoices, OrganisationTypeChoices
from apps.garage.models import GarageVehicle
from apps.notifications.models import Notification
from apps.workshops.models import (
    WorkshopProfile,
    WorkshopBooking,
    WorkshopConversation,
    WorkshopMessage,
    BookingStatusChoices,
    SenderTypeChoices,
)
from apps.workshops.consumers import WorkshopChatConsumer
from apps.workshops.messaging_service import (
    get_or_create_conversation_for_booking,
    create_message,
    mark_messages_as_read,
)


@pytest.fixture
def workshop_owner(db):
    user = User.objects.create_user(
        email='apex_owner@apexmotors.co.uk',
        password='SecurePassword123!',
        first_name='Apex',
        last_name='Workshop Owner',
        phone_number='+447111000111',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def workshop_staff(db):
    user = User.objects.create_user(
        email='apex_mechanic@apexmotors.co.uk',
        password='SecurePassword123!',
        first_name='Apex',
        last_name='Senior Mechanic',
        phone_number='+447111000222',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def buyer(db):
    user = User.objects.create_user(
        email='customer_john@driverxtra.co.uk',
        password='SecurePassword123!',
        first_name='John',
        last_name='Customer',
        phone_number='+447222000111',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def other_buyer(db):
    user = User.objects.create_user(
        email='unrelated_buyer@driverxtra.co.uk',
        password='SecurePassword123!',
        first_name='Unrelated',
        last_name='Buyer',
        phone_number='+447222000222',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def other_workshop_staff(db):
    user = User.objects.create_user(
        email='other_workshop@rivalmotors.co.uk',
        password='SecurePassword123!',
        first_name='Rival',
        last_name='Staff',
        phone_number='+447111000333',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def organisation(db, workshop_owner):
    org = Organisation.objects.create(
        name='Apex Auto Services Ltd',
        slug='apex-auto-services-messaging',
        type=OrganisationTypeChoices.WORKSHOP,
        created_by=workshop_owner,
    )
    OrganisationMembership.objects.create(
        organisation=org,
        user=workshop_owner,
        role=OrganisationRoleChoices.OWNER,
        is_active=True,
    )
    return org


@pytest.fixture
def workshop_profile(db, organisation):
    return WorkshopProfile.objects.create(
        organisation=organisation,
        business_name='Apex Auto Services Ltd',
        slug='apex-auto-services-msg',
        contact_email='service@apexmotors.co.uk',
        contact_phone='+442079460991',
        address_line1='Unit 4, Industrial Estate',
        city='London',
        postal_code='SW1A 1AA',
        country='GB',
        is_verified=True,
        bay_capacity=4,
    )


@pytest.fixture
def vehicle(db, buyer):
    return GarageVehicle.objects.create(
        user=buyer,
        make='BMW',
        model='3 Series 320d',
        year=2021,
        registration_plate='AB21 CDE',
        vin='WBA3A5C55CF123456',
        current_odometer=30000,
        odometer_unit='mi',
    )


@pytest.fixture
def booking(db, workshop_profile, buyer, vehicle):
    return WorkshopBooking.objects.create(
        booking_number=f"BK-{uuid.uuid4().hex[:8].upper()}",
        workshop=workshop_profile,
        buyer=buyer,
        vehicle=vehicle,
        vehicle_make='BMW',
        vehicle_model='3 Series 320d',
        vehicle_year=2021,
        vehicle_registration_plate='AB21 CDE',
        preferred_date=date.today() + timedelta(days=2),
        preferred_time_slot='MORNING',
        status=BookingStatusChoices.CONFIRMED,
    )


@pytest.fixture
def buyer_client(buyer):
    client = APIClient()
    client.force_authenticate(user=buyer)
    return client


@pytest.fixture
def workshop_client(workshop_owner, organisation):
    client = APIClient()
    client.force_authenticate(user=workshop_owner)
    return client


@pytest.fixture
def other_buyer_client(other_buyer):
    client = APIClient()
    client.force_authenticate(user=other_buyer)
    return client


# ---------------------------------------------------------------------------
# REST API TESTS
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_buyer_initializes_conversation(buyer_client, booking, buyer):
    """Buyer accesses their booking conversation; a new conversation thread is created."""
    url = f"/api/v1/workshops/bookings/{booking.id}/conversation/"
    response = buyer_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data['booking_number'] == booking.booking_number
    assert data['buyer_id'] == str(buyer.id)
    assert data['unread_count'] == 0

    # Idempotent: repeated access returns the same conversation
    response_again = buyer_client.get(url)
    assert response_again.status_code == status.HTTP_200_OK
    assert response_again.json()['id'] == data['id']


@pytest.mark.django_db
def test_conversation_by_booking_number(buyer_client, booking):
    """Conversation can be retrieved by human-readable booking_number identifier."""
    url = f"/api/v1/workshops/bookings/{booking.booking_number}/conversation/"
    response = buyer_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()['booking_number'] == booking.booking_number


@pytest.mark.django_db
def test_unauthorized_buyer_rejected(other_buyer_client, booking):
    """An unrelated buyer cannot access someone else's booking conversation."""
    url = f"/api/v1/workshops/bookings/{booking.id}/conversation/"
    response = other_buyer_client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_workshop_staff_can_access_conversation(workshop_client, booking, workshop_owner):
    """Authorized workshop staff can access booking conversations for their workshop."""
    url = f"/api/v1/workshops/bookings/{booking.id}/conversation/"
    response = workshop_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()['workshop_id'] == str(booking.workshop_id)


@pytest.mark.django_db
def test_list_conversations(buyer_client, workshop_client, other_buyer_client, booking, buyer):
    """User conversation listing filters strictly by user participation."""
    # Initialize conversation
    conv = get_or_create_conversation_for_booking(booking, buyer)

    # Buyer sees conversation
    res_buyer = buyer_client.get("/api/v1/workshops/conversations/")
    assert res_buyer.status_code == status.HTTP_200_OK
    ids_buyer = [c['id'] for c in res_buyer.json()]
    assert str(conv.id) in ids_buyer

    # Workshop sees conversation
    res_workshop = workshop_client.get("/api/v1/workshops/conversations/")
    assert res_workshop.status_code == status.HTTP_200_OK
    ids_workshop = [c['id'] for c in res_workshop.json()]
    assert str(conv.id) in ids_workshop

    # Other buyer does not see conversation
    res_other = other_buyer_client.get("/api/v1/workshops/conversations/")
    assert res_other.status_code == status.HTTP_200_OK
    ids_other = [c['id'] for c in res_other.json()]
    assert str(conv.id) not in ids_other


@pytest.mark.django_db
def test_exchange_messages_and_read_receipts(buyer_client, workshop_client, booking, buyer, workshop_owner):
    """Buyers and workshops can exchange messages, track unread counts, and mark read."""
    conv = get_or_create_conversation_for_booking(booking, buyer)
    messages_url = f"/api/v1/workshops/conversations/{conv.id}/messages/"

    # 1. Buyer posts message
    post_res = buyer_client.post(messages_url, {'content': 'Hello, is my car ready?'})
    assert post_res.status_code == status.HTTP_201_CREATED
    msg1_data = post_res.json()
    assert msg1_data['sender_type'] == 'BUYER'
    assert msg1_data['content'] == 'Hello, is my car ready?'
    assert msg1_data['is_read'] is False

    # 2. Workshop sees 1 unread message
    res_conv_workshop = workshop_client.get(f"/api/v1/workshops/bookings/{booking.id}/conversation/")
    assert res_conv_workshop.json()['unread_count'] == 1

    # 3. Buyer sees 0 unread messages (own message doesn't count as unread for self)
    res_conv_buyer = buyer_client.get(f"/api/v1/workshops/bookings/{booking.id}/conversation/")
    assert res_conv_buyer.json()['unread_count'] == 0

    # 4. Workshop replies
    reply_res = workshop_client.post(messages_url, {'content': 'Almost done! Brake pads replaced.'})
    assert reply_res.status_code == status.HTTP_201_CREATED
    assert reply_res.json()['sender_type'] == 'WORKSHOP'

    # 5. Workshop marks buyer message as read
    read_url = f"/api/v1/workshops/conversations/{conv.id}/read/"
    read_res = workshop_client.post(read_url)
    assert read_res.status_code == status.HTTP_200_OK
    assert read_res.json()['marked_read'] >= 1

    # 6. Check messages list
    list_res = buyer_client.get(messages_url)
    assert list_res.status_code == status.HTTP_200_OK
    messages = list_res.json()
    assert len(messages) == 2
    assert messages[0]['content'] == 'Hello, is my car ready?'
    assert messages[0]['is_read'] is True
    assert messages[1]['content'] == 'Almost done! Brake pads replaced.'


@pytest.mark.django_db
def test_message_validation_rejects_empty(buyer_client, booking, buyer):
    """Empty message without attachment is rejected with 400 Bad Request."""
    conv = get_or_create_conversation_for_booking(booking, buyer)
    messages_url = f"/api/v1/workshops/conversations/{conv.id}/messages/"
    res = buyer_client.post(messages_url, {'content': '   '})
    assert res.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_message_notification_delivery(booking, buyer, workshop_owner):
    """Sending a message creates an in-app notification for the counterparty."""
    conv = get_or_create_conversation_for_booking(booking, buyer)

    # Buyer sends message -> Workshop owner notified
    create_message(conv, buyer, "When should I arrive?")
    notifs_owner = Notification.objects.filter(recipient=workshop_owner, event_type="workshop.message.received")
    assert notifs_owner.exists()
    assert "When should I arrive?" in notifs_owner.first().message

    # Workshop owner replies -> Buyer notified
    create_message(conv, workshop_owner, "You can collect at 4 PM.")
    notifs_buyer = Notification.objects.filter(recipient=buyer, event_type="workshop.message.received")
    assert notifs_buyer.exists()
    assert "4 PM" in notifs_buyer.first().message


# ---------------------------------------------------------------------------
# WEBSOCKET CHANNELS CONSUMER TESTS
# ---------------------------------------------------------------------------

from asgiref.sync import async_to_sync

@pytest.mark.django_db(transaction=True)
def test_websocket_authorization_and_message_delivery(booking, buyer, other_buyer):
    """Tests WebSocket handshake authentication, access control, and real-time message handling."""
    async def _run_test():
        conv = await get_or_create_conv_async(booking, buyer)

        # 1. Unauthenticated connection rejected
        communicator_anon = WebsocketCommunicator(
            WorkshopChatConsumer.as_asgi(),
            f"/ws/workshops/conversations/{conv.id}/",
        )
        communicator_anon.scope["url_route"] = {"kwargs": {"conversation_id": str(conv.id)}}
        connected, code = await communicator_anon.connect()
        assert not connected
        assert code in (4401, 4403, 1000)

        # 2. Unauthorized buyer connection rejected
        communicator_unauth = WebsocketCommunicator(
            WorkshopChatConsumer.as_asgi(),
            f"/ws/workshops/conversations/{conv.id}/",
        )
        communicator_unauth.scope["user"] = other_buyer
        communicator_unauth.scope["url_route"] = {"kwargs": {"conversation_id": str(conv.id)}}
        connected, code = await communicator_unauth.connect()
        assert not connected
        assert code == 4403

        # 3. Authorized buyer connects successfully
        communicator_buyer = WebsocketCommunicator(
            WorkshopChatConsumer.as_asgi(),
            f"/ws/workshops/conversations/{conv.id}/",
        )
        communicator_buyer.scope["user"] = buyer
        communicator_buyer.scope["url_route"] = {"kwargs": {"conversation_id": str(conv.id)}}
        connected, _ = await communicator_buyer.connect()
        assert connected

        # 4. Buyer sends real-time message
        await communicator_buyer.send_json_to({
            "action": "send_message",
            "content": "Live WebSocket test message",
        })

        # 5. Receives broadcast message
        response = await communicator_buyer.receive_json_from()
        assert response["type"] == "chat_message"
        assert response["message"]["content"] == "Live WebSocket test message"
        assert response["message"]["sender_type"] == "BUYER"

        # 6. Disconnect
        await communicator_buyer.disconnect()

    async_to_sync(_run_test)()


from channels.db import database_sync_to_async

@database_sync_to_async
def get_or_create_conv_async(booking, buyer):
    return get_or_create_conversation_for_booking(booking, buyer)
