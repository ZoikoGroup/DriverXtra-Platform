from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationRoleChoices, OrganisationTypeChoices
from apps.garage.models import GarageVehicle
from apps.workshops.models import (
    WorkshopProfile,
    WorkshopBooking,
    WorkshopQuotation,
    WorkOrder,
    WorkOrderStatusChoices,
    WorkOrderPartUsage,
)
from apps.catalogue.models import PartCategory
from apps.marketplace.models import (
    SparePartListing,
    ListingStatusChoices,
    StockMovement,
    StockMovementReasonChoices,
)
from apps.workshops.services import WorkOrderService


@pytest.fixture
def owner_user(db):
    user = User.objects.create_user(
        email='workshop.owner@apexmotors.co.uk',
        password='Password123!',
        first_name='Oliver',
        last_name='Owner',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.WORKSHOP)
    return user


@pytest.fixture
def buyer_user(db):
    user = User.objects.create_user(
        email='customer@driverxtra.co.uk',
        password='Password123!',
        first_name='Charlie',
        last_name='Customer',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def workshop_org(db, owner_user):
    org = Organisation.objects.create(
        name="Apex Motors Workshop",
        type=OrganisationTypeChoices.WORKSHOP,
        created_by=owner_user,
    )
    org.add_member(owner_user, role=OrganisationRoleChoices.OWNER)
    return org


@pytest.fixture
def workshop_profile(db, workshop_org):
    return WorkshopProfile.objects.create(
        organisation=workshop_org,
        business_name="Apex Motors",
        slug="apex-motors-stock",
        city="London",
        bay_capacity=3,
        is_tax_registered=True,
        can_collect_tax=True,
        default_tax_rate_percent=Decimal('20.00'),
        is_accepting_bookings=True,
        is_verified=True,
    )


@pytest.fixture
def garage_vehicle(db, buyer_user):
    return GarageVehicle.objects.create(
        user=buyer_user,
        make="Audi",
        model="A4 S-Line",
        year=2021,
        registration_plate="GF21 XTR",
        vin="WAUZZZF41MA000123",
        current_odometer=28000,
        odometer_unit="mi",
    )


@pytest.fixture
def work_order(db, workshop_profile, buyer_user, garage_vehicle, owner_user):
    booking = WorkshopBooking.objects.create(
        workshop=workshop_profile,
        buyer=buyer_user,
        vehicle=garage_vehicle,
        vehicle_make=garage_vehicle.make,
        vehicle_model=garage_vehicle.model,
        vehicle_year=garage_vehicle.year,
        vehicle_registration_plate=garage_vehicle.registration_plate,
        vehicle_vin=garage_vehicle.vin,
        current_odometer=garage_vehicle.current_odometer,
        odometer_unit=garage_vehicle.odometer_unit,
        preferred_date=date.today() + timedelta(days=2),
        status="CONFIRMED",
    )
    quotation = WorkshopQuotation.objects.create(
        booking=booking,
        status="ACCEPTED",
        subtotal_labour=Decimal('100.00'),
        subtotal_parts=Decimal('60.00'),
        subtotal_other=Decimal('0.00'),
        tax_rate_percent=Decimal('20.00'),
        tax_amount=Decimal('32.00'),
        total_amount=Decimal('192.00'),
        currency='GBP',
        created_by=owner_user,
    )
    return WorkOrder.objects.create(
        workshop=workshop_profile,
        booking=booking,
        quotation=quotation,
        buyer=buyer_user,
        vehicle=garage_vehicle,
        vehicle_make=garage_vehicle.make,
        vehicle_model=garage_vehicle.model,
        vehicle_year=garage_vehicle.year,
        vehicle_registration_plate=garage_vehicle.registration_plate,
        vehicle_vin=garage_vehicle.vin,
        current_odometer=28000,
        odometer_unit="mi",
        status=WorkOrderStatusChoices.ASSIGNED,
    )


@pytest.fixture
def brake_category(db):
    cat, _ = PartCategory.objects.get_or_create(slug="brakes-test", defaults={"name": "Brakes"})
    return cat


@pytest.fixture
def brake_pad_listing(db, workshop_org, owner_user, brake_category):
    return SparePartListing.objects.create(
        organisation=workshop_org,
        seller=owner_user,
        category=brake_category,
        name="Brembo Front Brake Pad Set",
        brand="Brembo",
        mpn="BRK-PAD-001",
        price=Decimal('55.00'),
        currency='GBP',
        stock_quantity=5,
        status=ListingStatusChoices.APPROVED,
    )


@pytest.mark.django_db
def test_record_part_usage_decrements_inventory_stock(work_order, brake_pad_listing, owner_user):
    """Recording part usage linked to a spare part listing atomically decrements inventory."""
    initial_stock = brake_pad_listing.stock_quantity
    assert initial_stock == 5

    usage = WorkOrderService.record_part_usage(
        work_order=work_order,
        part_name="Brembo Front Brake Pads",
        quantity=Decimal('2.00'),
        unit_cost=Decimal('55.00'),
        part_number="BRK-PAD-001",
        inventory_item=brake_pad_listing,
        actor=owner_user,
    )

    assert usage.is_stock_deducted is True
    assert usage.inventory_item_id == brake_pad_listing.id

    brake_pad_listing.refresh_from_db()
    assert brake_pad_listing.stock_quantity == 3

    # Check StockMovement audit ledger entry
    movement = StockMovement.objects.filter(listing=brake_pad_listing).latest('created_at')
    assert movement.delta == -2
    assert movement.resulting_quantity == 3
    assert movement.reason == StockMovementReasonChoices.WORK_ORDER
    assert movement.actor == owner_user


@pytest.mark.django_db
def test_record_part_usage_fails_when_insufficient_stock(work_order, brake_pad_listing, owner_user):
    """Recording part usage with quantity exceeding available stock raises validation error."""
    assert brake_pad_listing.stock_quantity == 5

    with pytest.raises(DjangoValidationError) as exc_info:
        WorkOrderService.record_part_usage(
            work_order=work_order,
            part_name="Brembo Front Brake Pads",
            quantity=Decimal('10.00'),
            unit_cost=Decimal('55.00'),
            inventory_item=brake_pad_listing,
            actor=owner_user,
        )

    assert "Insufficient inventory stock" in str(exc_info.value)
    brake_pad_listing.refresh_from_db()
    assert brake_pad_listing.stock_quantity == 5


@pytest.mark.django_db
def test_delete_part_usage_restores_inventory_stock(work_order, brake_pad_listing, owner_user):
    """Deleting a part usage reverses the stock deduction and creates restock movement."""
    usage = WorkOrderService.record_part_usage(
        work_order=work_order,
        part_name="Brembo Front Brake Pads",
        quantity=Decimal('2.00'),
        unit_cost=Decimal('55.00'),
        inventory_item=brake_pad_listing,
        actor=owner_user,
    )

    brake_pad_listing.refresh_from_db()
    assert brake_pad_listing.stock_quantity == 3

    # Now delete part usage
    WorkOrderService.delete_part_usage(part_usage=usage, actor=owner_user)

    brake_pad_listing.refresh_from_db()
    assert brake_pad_listing.stock_quantity == 5

    movement = StockMovement.objects.filter(listing=brake_pad_listing).latest('created_at')
    assert movement.delta == 2
    assert movement.resulting_quantity == 5
    assert movement.reason == StockMovementReasonChoices.WORK_ORDER_RESTOCK


@pytest.mark.django_db
def test_work_order_cancellation_restores_all_consumed_parts(work_order, brake_pad_listing, owner_user):
    """Cancelling a work order automatically restocks all consumed inventory parts."""
    WorkOrderService.record_part_usage(
        work_order=work_order,
        part_name="Brembo Front Brake Pads",
        quantity=Decimal('3.00'),
        unit_cost=Decimal('55.00'),
        inventory_item=brake_pad_listing,
        actor=owner_user,
    )

    brake_pad_listing.refresh_from_db()
    assert brake_pad_listing.stock_quantity == 2

    # Cancel work order
    WorkOrderService.update_status(
        work_order=work_order,
        new_status=WorkOrderStatusChoices.CANCELLED,
        actor=owner_user,
        cancellation_reason="Customer postponed repair.",
    )

    brake_pad_listing.refresh_from_db()
    assert brake_pad_listing.stock_quantity == 5

    # Check that parts_used now has is_stock_deducted=False
    for part in work_order.parts_used.all():
        assert part.is_stock_deducted is False

    restock_movement = StockMovement.objects.filter(
        listing=brake_pad_listing,
        reason=StockMovementReasonChoices.WORK_ORDER_RESTOCK,
    ).latest('created_at')
    assert restock_movement.delta == 3
    assert restock_movement.resulting_quantity == 5
