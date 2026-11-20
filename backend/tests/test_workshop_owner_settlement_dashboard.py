import uuid
from decimal import Decimal
from datetime import date, timedelta
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationRoleChoices, OrganisationTypeChoices
from apps.garage.models import GarageVehicle
from apps.workshops.models import (
    WorkshopProfile,
    WorkshopBooking,
    WorkshopQuotation,
    QuotationLineItem,
    WorkOrder,
    WorkOrderStatusChoices,
    WorkOrderSettlementStatusChoices,
    WorkOrderPayment,
    WorkOrderPaymentStatusChoices,
    WorkOrderPaymentTypeChoices,
    WorkOrderInvoice,
    WorkOrderInvoiceStatusChoices,
    BookingStatusChoices,
    QuotationStatusChoices,
    DepositStatusChoices,
    LineItemTypeChoices,
    ChangeOrder,
    ChangeOrderStatusChoices,
    ChangeOrderLineItem,
)
from apps.workshops.settlement_service import WorkOrderSettlementService


@pytest.fixture
def owner_user(db):
    user = User.objects.create_user(
        email=f"owner_{uuid.uuid4().hex[:6]}@apexworkshop.com",
        password="Password123!",
        first_name="Oliver",
        last_name="Owner",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def competitor_owner_user(db):
    user = User.objects.create_user(
        email=f"competitor_{uuid.uuid4().hex[:6]}@rivalgarage.com",
        password="Password123!",
        first_name="Rick",
        last_name="Rival",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def buyer_user(db):
    user = User.objects.create_user(
        email=f"buyer_{uuid.uuid4().hex[:6]}@driverxtra.com",
        password="Password123!",
        first_name="Charlie",
        last_name="Customer",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def workshop_org(db, owner_user):
    org = Organisation.objects.create(
        name="Apex Workshop London",
        type=OrganisationTypeChoices.WORKSHOP,
        country="GB",
        jurisdiction="GB-ENG",
        created_by=owner_user,
    )
    org.add_member(owner_user, role=OrganisationRoleChoices.OWNER)
    return org


@pytest.fixture
def workshop_profile(db, workshop_org):
    return WorkshopProfile.objects.create(
        organisation=workshop_org,
        business_name="Apex Workshop London",
        slug=f"apex-uk-{uuid.uuid4().hex[:6]}",
        city="London",
        country="GB",
        currency="GBP",
        bay_capacity=4,
        requires_deposit=True,
        default_deposit_percentage=Decimal('20.00'),
        is_tax_registered=True,
        can_collect_tax=True,
        default_tax_rate_percent=Decimal('20.00'),
        is_accepting_bookings=True,
        is_verified=True,
    )


@pytest.fixture
def competitor_org(db, competitor_owner_user):
    org = Organisation.objects.create(
        name="Rival Garage Manchester",
        type=OrganisationTypeChoices.WORKSHOP,
        country="GB",
        jurisdiction="GB-ENG",
        created_by=competitor_owner_user,
    )
    org.add_member(competitor_owner_user, role=OrganisationRoleChoices.OWNER)
    return org


@pytest.fixture
def competitor_profile(db, competitor_org):
    return WorkshopProfile.objects.create(
        organisation=competitor_org,
        business_name="Rival Garage Manchester",
        slug=f"rival-uk-{uuid.uuid4().hex[:6]}",
        city="Manchester",
        country="GB",
        currency="GBP",
        bay_capacity=2,
        is_accepting_bookings=True,
        is_verified=True,
    )


@pytest.fixture
def vehicle(db, buyer_user):
    return GarageVehicle.objects.create(
        user=buyer_user,
        make="BMW",
        model="3 Series M Sport",
        year=2021,
        registration_plate="GB21 APX",
        vin="WBANV123456789012",
    )


@pytest.fixture
def sample_work_orders(db, workshop_profile, buyer_user, vehicle):
    """
    Creates 3 work orders with different settlement statuses:
    1. WO1: Total £500, Deposit £100 paid, Balance £400 paid -> FULLY_PAID / SETTLED
    2. WO2: Total £300, Deposit £60 paid, Balance £0 paid -> PARTIALLY_PAID
    3. WO3: Total £200, Deposit £0 paid, Balance £0 paid -> UNPAID
    """
    wos = []

    # WO1 - FULLY SETTLED
    b1 = WorkshopBooking.objects.create(
        booking_number=f"WB-{uuid.uuid4().hex[:6].upper()}",
        workshop=workshop_profile,
        buyer=buyer_user,
        vehicle=vehicle,
        preferred_date=date.today(),
        status=BookingStatusChoices.ACCEPTED,
    )
    q1 = WorkshopQuotation.objects.create(
        quotation_number=f"QTN-{uuid.uuid4().hex[:6].upper()}",
        booking=b1,
        subtotal_labour=Decimal('416.67'),
        tax_amount=Decimal('83.33'),
        total_amount=Decimal('500.00'),
        currency='GBP',
        requires_deposit=True,
        deposit_amount=Decimal('100.00'),
        deposit_status=DepositStatusChoices.PAID,
        deposit_transaction_id="pi_dep_wo1",
        status=QuotationStatusChoices.ACCEPTED,
    )
    wo1 = WorkOrder.objects.create(
        work_order_number=f"WO-SETTLE-{uuid.uuid4().hex[:6].upper()}",
        booking=b1,
        quotation=q1,
        workshop=workshop_profile,
        buyer=buyer_user,
        vehicle_make="BMW",
        vehicle_model="3 Series",
        vehicle_year=2021,
        vehicle_registration_plate="GB21 APX",
        vehicle_vin="WBANV123456789012",
        status=WorkOrderStatusChoices.COMPLETED,
        settlement_status=WorkOrderSettlementStatusChoices.FULLY_PAID,
    )
    # Record balance payment
    WorkOrderPayment.objects.create(
        work_order=wo1,
        payment_number=f"WOP-{uuid.uuid4().hex[:6].upper()}",
        payment_type=WorkOrderPaymentTypeChoices.FINAL,
        amount=Decimal('400.00'),
        currency='GBP',
        provider='STRIPE',
        status=WorkOrderPaymentStatusChoices.SUCCESS,
        provider_payment_id="pi_bal_wo1",
        created_by=buyer_user,
    )
    WorkOrderSettlementService.generate_or_update_invoice(wo1)
    wos.append(wo1)

    # WO2 - PARTIALLY PAID
    b2 = WorkshopBooking.objects.create(
        booking_number=f"WB-{uuid.uuid4().hex[:6].upper()}",
        workshop=workshop_profile,
        buyer=buyer_user,
        vehicle=vehicle,
        preferred_date=date.today() + timedelta(days=1),
        status=BookingStatusChoices.ACCEPTED,
    )
    q2 = WorkshopQuotation.objects.create(
        quotation_number=f"QTN-{uuid.uuid4().hex[:6].upper()}",
        booking=b2,
        subtotal_labour=Decimal('250.00'),
        tax_amount=Decimal('50.00'),
        total_amount=Decimal('300.00'),
        currency='GBP',
        requires_deposit=True,
        deposit_amount=Decimal('60.00'),
        deposit_status=DepositStatusChoices.PAID,
        deposit_transaction_id="pi_dep_wo2",
        status=QuotationStatusChoices.ACCEPTED,
    )
    wo2 = WorkOrder.objects.create(
        work_order_number=f"WO-PART-{uuid.uuid4().hex[:6].upper()}",
        booking=b2,
        quotation=q2,
        workshop=workshop_profile,
        buyer=buyer_user,
        vehicle_make="Audi",
        vehicle_model="A4",
        vehicle_year=2020,
        vehicle_registration_plate="AUDI-20",
        vehicle_vin="WAUZZZ12345678901",
        status=WorkOrderStatusChoices.IN_PROGRESS,
        settlement_status=WorkOrderSettlementStatusChoices.PARTIALLY_PAID,
    )
    WorkOrderSettlementService.generate_or_update_invoice(wo2)
    wos.append(wo2)

    # WO3 - UNPAID
    b3 = WorkshopBooking.objects.create(
        booking_number=f"WB-{uuid.uuid4().hex[:6].upper()}",
        workshop=workshop_profile,
        buyer=buyer_user,
        vehicle=vehicle,
        preferred_date=date.today() + timedelta(days=2),
        status=BookingStatusChoices.ACCEPTED,
    )
    q3 = WorkshopQuotation.objects.create(
        quotation_number=f"QTN-{uuid.uuid4().hex[:6].upper()}",
        booking=b3,
        subtotal_labour=Decimal('166.67'),
        tax_amount=Decimal('33.33'),
        total_amount=Decimal('200.00'),
        currency='GBP',
        requires_deposit=False,
        status=QuotationStatusChoices.ACCEPTED,
    )
    wo3 = WorkOrder.objects.create(
        work_order_number=f"WO-UNPAID-{uuid.uuid4().hex[:6].upper()}",
        booking=b3,
        quotation=q3,
        workshop=workshop_profile,
        buyer=buyer_user,
        vehicle_make="Mercedes",
        vehicle_model="C-Class",
        vehicle_year=2019,
        vehicle_registration_plate="MERC-19",
        vehicle_vin="WDD20512345678901",
        status=WorkOrderStatusChoices.AWAITING_PARTS,
        settlement_status=WorkOrderSettlementStatusChoices.UNPAID,
    )
    wos.append(wo3)

    return wos


def test_workshop_owner_can_list_settlements_and_summary_metrics(db, owner_user, workshop_profile, sample_work_orders):
    client = APIClient()
    client.force_authenticate(user=owner_user)

    response = client.get('/api/v1/workshops/manage/settlements/')
    assert response.status_code == status.HTTP_200_OK

    data = response.data
    assert data['status'] == 'success'
    assert 'summary' in data
    assert 'results' in data

    summary = data['summary']
    # Total Value: 500 + 300 + 200 = 1000.00
    assert summary['total_work_order_value'] == '1000.00'
    # Advance Deposits: 100 + 60 = 160.00
    assert summary['advance_deposits_received'] == '160.00'
    # Final Payments: 400.00
    assert summary['final_payments_received'] == '400.00'
    # Total Collected: 160 + 400 = 560.00
    assert summary['total_amount_collected'] == '560.00'
    # Outstanding Customer Balance: 1000 - 560 = 440.00
    assert summary['outstanding_customer_balance'] == '440.00'
    assert summary['currency'] == 'GBP'
    assert summary['total_work_orders'] == 3
    assert summary['fully_paid_count'] == 1
    assert summary['partially_paid_count'] == 1
    assert summary['unpaid_count'] == 1

    assert data['count'] == 3
    assert len(data['results']) == 3


def test_workshop_owner_settlement_status_filtering(db, owner_user, workshop_profile, sample_work_orders):
    client = APIClient()
    client.force_authenticate(user=owner_user)

    # Filter FULLY_PAID
    res_settled = client.get('/api/v1/workshops/manage/settlements/?status=FULLY_PAID')
    assert res_settled.status_code == status.HTTP_200_OK
    assert res_settled.data['count'] == 1
    assert res_settled.data['results'][0]['settlement_status'] == 'FULLY_PAID'
    assert res_settled.data['results'][0]['outstanding'] == '0.00'

    # Filter PARTIALLY_PAID
    res_part = client.get('/api/v1/workshops/manage/settlements/?status=PARTIALLY_PAID')
    assert res_part.status_code == status.HTTP_200_OK
    assert res_part.data['count'] == 1
    assert res_part.data['results'][0]['settlement_status'] == 'PARTIALLY_PAID'
    assert res_part.data['results'][0]['deposit_paid'] == '60.00'
    assert res_part.data['results'][0]['outstanding'] == '240.00'

    # Filter UNPAID
    res_unpaid = client.get('/api/v1/workshops/manage/settlements/?status=UNPAID')
    assert res_unpaid.status_code == status.HTTP_200_OK
    assert res_unpaid.data['count'] == 1
    assert res_unpaid.data['results'][0]['settlement_status'] == 'UNPAID'
    assert res_unpaid.data['results'][0]['total_paid'] == '0.00'


def test_workshop_owner_settlement_search(db, owner_user, workshop_profile, sample_work_orders):
    client = APIClient()
    client.force_authenticate(user=owner_user)

    # Search by registration plate
    res = client.get('/api/v1/workshops/manage/settlements/?q=AUDI-20')
    assert res.status_code == status.HTTP_200_OK
    assert res.data['count'] == 1
    assert res.data['results'][0]['vehicle']['registration_plate'] == 'AUDI-20'

    # Search by customer name
    res2 = client.get('/api/v1/workshops/manage/settlements/?q=Charlie')
    assert res2.status_code == status.HTTP_200_OK
    assert res2.data['count'] == 3


def test_workshop_owner_can_list_invoices(db, owner_user, workshop_profile, sample_work_orders):
    client = APIClient()
    client.force_authenticate(user=owner_user)

    response = client.get('/api/v1/workshops/manage/invoices/')
    assert response.status_code == status.HTTP_200_OK

    data = response.data
    assert data['status'] == 'success'
    # WO1 and WO2 had invoices generated
    assert data['count'] >= 2
    for inv in data['results']:
        assert 'invoice_number' in inv
        assert 'total_amount' in inv
        assert 'status' in inv
        assert 'workshop_name' in inv


def test_workshop_owner_cannot_access_another_workshop_settlements_or_invoices(
    db, competitor_owner_user, competitor_profile, sample_work_orders
):
    """
    Multi-tenant isolation: competitor workshop user must see ZERO of Apex Workshop's settlements or invoices.
    """
    client = APIClient()
    client.force_authenticate(user=competitor_owner_user)

    # Competitor settlements list should return count: 0
    res_settlements = client.get('/api/v1/workshops/manage/settlements/')
    assert res_settlements.status_code == status.HTTP_200_OK
    assert res_settlements.data['count'] == 0
    assert len(res_settlements.data['results']) == 0
    assert res_settlements.data['summary']['total_work_orders'] == 0

    # Competitor invoices list should return count: 0
    res_invoices = client.get('/api/v1/workshops/manage/invoices/')
    assert res_invoices.status_code == status.HTTP_200_OK
    assert res_invoices.data['count'] == 0
    assert len(res_invoices.data['results']) == 0


def test_unauthenticated_user_rejected(db):
    client = APIClient()
    res = client.get('/api/v1/workshops/manage/settlements/')
    assert res.status_code == status.HTTP_401_UNAUTHORIZED

    res2 = client.get('/api/v1/workshops/manage/invoices/')
    assert res2.status_code == status.HTTP_401_UNAUTHORIZED


def test_buyer_user_forbidden(db, buyer_user):
    client = APIClient()
    client.force_authenticate(user=buyer_user)

    res = client.get('/api/v1/workshops/manage/settlements/')
    assert res.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    res2 = client.get('/api/v1/workshops/manage/invoices/')
    assert res2.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


def test_financial_accuracy_change_order_does_not_double_count_tax(
    db, owner_user, workshop_profile, buyer_user, vehicle
):
    """
    When an approved change order is added to a work order:
    1. Authorized total increases by the approved additional amount.
    2. Tax is calculated consistently without double counting.
    """
    b = WorkshopBooking.objects.create(
        booking_number=f"WB-{uuid.uuid4().hex[:6].upper()}",
        workshop=workshop_profile,
        buyer=buyer_user,
        vehicle=vehicle,
        preferred_date=date.today(),
        status=BookingStatusChoices.ACCEPTED,
    )
    q = WorkshopQuotation.objects.create(
        quotation_number=f"QTN-{uuid.uuid4().hex[:6].upper()}",
        booking=b,
        subtotal_labour=Decimal('200.00'),
        tax_amount=Decimal('40.00'),
        total_amount=Decimal('240.00'),
        currency='GBP',
        requires_deposit=True,
        deposit_amount=Decimal('50.00'),
        deposit_status=DepositStatusChoices.PAID,
        status=QuotationStatusChoices.ACCEPTED,
    )
    wo = WorkOrder.objects.create(
        work_order_number=f"WO-CO-{uuid.uuid4().hex[:6].upper()}",
        booking=b,
        quotation=q,
        workshop=workshop_profile,
        buyer=buyer_user,
        vehicle_make="BMW",
        vehicle_model="3 Series",
        vehicle_year=2021,
        vehicle_registration_plate="GB21 APX",
        vehicle_vin="WBANV123456789012",
        status=WorkOrderStatusChoices.IN_PROGRESS,
    )

    # Approved change order of £60
    co = ChangeOrder.objects.create(
        change_order_number=f"CO-{uuid.uuid4().hex[:6].upper()}",
        work_order=wo,
        reason="Additional brake pads replacement",
        subtotal_labour=Decimal('50.00'),
        tax_amount=Decimal('10.00'),
        additional_amount=Decimal('60.00'),
        status=ChangeOrderStatusChoices.APPROVED,
        created_by=owner_user,
    )

    client = APIClient()
    client.force_authenticate(user=owner_user)

    res = client.get(f'/api/v1/workshops/manage/settlements/?q={wo.work_order_number}')
    assert res.status_code == status.HTTP_200_OK
    assert res.data['count'] == 1
    item = res.data['results'][0]

    # Authorized total: 240 + 60 = 300.00
    assert item['total_amount'] == '300.00'
    assert item['approved_change_orders_amount'] == '60.00'
    # Deposit paid: 50.00
    assert item['deposit_paid'] == '50.00'
    # Outstanding: 300 - 50 = 250.00
    assert item['outstanding'] == '250.00'
    assert item['settlement_status'] == 'PARTIALLY_PAID'
