import pytest
from decimal import Decimal
from rest_framework import status
from apps.catalogue.models import PartCategory, Part
from apps.marketplace.models import (
    SparePartListing,
    ListingStatusChoices,
    Order,
    OrderItem,
)
from apps.marketplace.tax import (
    calculate_gst_breakdown,
    validate_gst_classification,
    OFFICIAL_AUTOMOTIVE_HSN_REGISTRY,
)


@pytest.fixture
def brake_category(db):
    return PartCategory.objects.create(
        name="Braking Systems",
        slug="braking-systems",
    )


@pytest.fixture
def filter_category(db):
    return PartCategory.objects.create(
        name="Filters",
        slug="filters",
    )


@pytest.fixture
def catalogue_brake_disc(db, brake_category):
    return Part.objects.create(
        name="Brembo Front Brake Disc (348mm)",
        brand="Brembo",
        mpn="09.C398.13",
        category=brake_category,
    )


# =============================================================================
# 1. TAX ENGINE UNIT TESTS: CALCULATION, DECIMAL PRECISION & ROUNDING
# =============================================================================

class TestGSTTaxEngine:
    def test_calculate_gst_breakdown_precision(self):
        # Base: 1000.00 at 18%
        res = calculate_gst_breakdown(Decimal("1000.00"), Decimal("18.00"))
        assert res["price_before_gst"] == Decimal("1000.00")
        assert res["gst_rate"] == Decimal("18.00")
        assert res["gst_amount"] == Decimal("180.00")
        assert res["total_price"] == Decimal("1180.00")
        assert res["tax_type"] == "INTRA_STATE"
        assert res["cgst_rate"] == Decimal("9.00")
        assert res["cgst_amount"] == Decimal("90.00")
        assert res["sgst_rate"] == Decimal("9.00")
        assert res["sgst_amount"] == Decimal("90.00")
        assert res["cgst_amount"] + res["sgst_amount"] == res["gst_amount"]

    def test_calculate_gst_breakdown_odd_paise_rounding(self):
        # 999.95 at 18% = 179.991 -> rounds to 179.99
        res = calculate_gst_breakdown(Decimal("999.95"), Decimal("18.00"))
        assert res["gst_amount"] == Decimal("179.99")
        assert res["total_price"] == Decimal("1179.94")
        # Split: 179.99 / 2 = 89.995 -> cgst=90.00, sgst=89.99, sum=179.99
        assert res["cgst_amount"] == Decimal("90.00")
        assert res["sgst_amount"] == Decimal("89.99")
        assert res["cgst_amount"] + res["sgst_amount"] == Decimal("179.99")

    def test_place_of_supply_intra_vs_inter_state(self):
        # Intra-state: MH to MH
        intra = calculate_gst_breakdown(
            price=Decimal("500.00"),
            gst_rate=Decimal("28.00"),
            place_of_supply="MH",
            seller_state="MH",
        )
        assert intra["tax_type"] == "INTRA_STATE"
        assert intra["cgst_amount"] == Decimal("70.00")
        assert intra["sgst_amount"] == Decimal("70.00")
        assert intra["igst_amount"] == Decimal("0.00")

        # Inter-state: MH to KA
        inter = calculate_gst_breakdown(
            price=Decimal("500.00"),
            gst_rate=Decimal("28.00"),
            place_of_supply="KA",
            seller_state="MH",
        )
        assert inter["tax_type"] == "INTER_STATE"
        assert inter["cgst_amount"] == Decimal("0.00")
        assert inter["sgst_amount"] == Decimal("0.00")
        assert inter["igst_rate"] == Decimal("28.00")
        assert inter["igst_amount"] == Decimal("140.00")
        assert inter["total_price"] == Decimal("640.00")

    def test_validate_gst_classification_official_slabs(self):
        # HSN 8708 allows 28%, 18%, 12%
        is_val, err, ver = validate_gst_classification("8708", Decimal("28.00"))
        assert is_val is True
        assert err is None
        assert ver is True

        is_val, err, ver = validate_gst_classification("8708", Decimal("12.00"))
        assert is_val is True

        # HSN 8708 disallows arbitrary 15%
        is_val, err, ver = validate_gst_classification("8708", Decimal("15.00"))
        assert is_val is False
        assert "not legally applicable" in err

        # HSN 7007 (safety glass) strictly allows only 28%
        is_val, err, ver = validate_gst_classification("7007", Decimal("18.00"))
        assert is_val is False

        # Unrecognized HSN with standard slab flags verification
        is_val, err, ver = validate_gst_classification("9999", Decimal("18.00"))
        assert is_val is True
        assert ver is False  # Requires tax verification


# =============================================================================
# 2. TAX OPTIONS API ENDPOINT
# =============================================================================

class TestGSTOptionsAPI:
    def test_get_gst_options(self, api_client):
        response = api_client.get('/api/v1/marketplace/tax/gst-options/')
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
        assert data["count"] >= 10
        assert "8708" in [opt["hsn_code"] for opt in data["hsn_options"]]
        assert "8421" in [opt["hsn_code"] for opt in data["hsn_options"]]
        assert data["standard_slabs"] == ["5.00", "12.00", "18.00", "28.00"]


# =============================================================================
# 3. SELLER INVENTORY CREATION & VALIDATION
# =============================================================================

class TestSellerSparePartGST:
    def test_seller_create_part_with_verified_gst(self, seller_auth_client, filter_category):
        payload = {
            "name": "Bosch Fuel Filter",
            "brand": "Bosch",
            "mpn": "F026402005",
            "category": str(filter_category.id),
            "price": "450.00",
            "currency": "INR",
            "stock_quantity": 10,
            "condition": "NEW",
            "hsn_code": "8421",
            "gst_rate": "18.00",
        }
        res = seller_auth_client.post('/api/v1/marketplace/parts/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data["hsn_code"] == "8421"
        assert data["gst_rate"] == "18.00"
        assert data["is_tax_verified"] is True
        assert data["price_before_gst"] == "450.00"
        # 450 * 0.18 = 81.00
        assert data["gst_amount"] == 81.0 or data["gst_amount"] == Decimal("81.00")
        assert data["total_price"] == 531.0 or data["total_price"] == Decimal("531.00")
        assert data["tax_breakdown"]["tax_type"] == "INTRA_STATE"
        assert Decimal(str(data["tax_breakdown"]["cgst_amount"])) == Decimal("40.50")
        assert Decimal(str(data["tax_breakdown"]["sgst_amount"])) == Decimal("40.50")

    def test_seller_create_part_rejects_arbitrary_rate(self, seller_auth_client, filter_category):
        payload = {
            "name": "Generic Fuel Filter",
            "brand": "Generic",
            "mpn": "GEN-FIL-01",
            "category": str(filter_category.id),
            "price": "300.00",
            "stock_quantity": 5,
            "condition": "NEW",
            "hsn_code": "8421",
            "gst_rate": "14.50",  # Arbitrary rate not in schedule
        }
        res = seller_auth_client.post('/api/v1/marketplace/parts/', payload, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        json_data = res.json()
        assert "gst_rate" in str(json_data)
        if "details" in json_data and isinstance(json_data["details"], dict):
            assert "gst_rate" in json_data["details"]

    def test_seller_create_part_defaults_hsn_and_gst_from_category(self, seller_auth_client, brake_category):
        # Creation without HSN/rate auto-assigns authoritative category default
        payload = {
            "name": "Brembo Brake Pads Set",
            "brand": "Brembo",
            "mpn": "P85075",
            "category": str(brake_category.id),
            "price": "1200.00",
            "currency": "INR",
            "stock_quantity": 8,
            "condition": "NEW",
        }
        res = seller_auth_client.post('/api/v1/marketplace/parts/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data["hsn_code"] == "8708"
        assert Decimal(str(data["gst_rate"])) == Decimal("28.00")
        assert Decimal(str(data["gst_amount"])) == Decimal("336.00")
        assert Decimal(str(data["total_price"])) == Decimal("1536.00")


# =============================================================================
# 4. BUYER PUBLIC BROWSE & PRICE TRANSPARENCY
# =============================================================================

class TestBuyerBrowseGSTTransparency:
    def test_public_browse_part_returns_gst_breakdown(self, api_client, seller_user, brake_category):
        listing = SparePartListing.objects.create(
            seller=seller_user,
            name="Ferodo Premier Brake Rotor",
            brand="Ferodo",
            mpn="DDF1223",
            category=brake_category,
            price=Decimal("2500.00"),
            currency="INR",
            hsn_code="8708",
            gst_rate=Decimal("28.00"),
            is_tax_verified=True,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
            stock_quantity=5,
        )

        res = api_client.get(f'/api/v1/marketplace/browse/parts/{listing.id}/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["hsn_code"] == "8708"
        assert data["gst_rate"] == "28.00"
        assert data["price_before_gst"] == "2500.00"
        # 2500 * 0.28 = 700.00
        assert Decimal(str(data["gst_amount"])) == Decimal("700.00")
        assert Decimal(str(data["total_price"])) == Decimal("3200.00")
        assert "tax_breakdown" in data
        assert Decimal(str(data["tax_breakdown"]["cgst_amount"])) == Decimal("350.00")
        assert Decimal(str(data["tax_breakdown"]["sgst_amount"])) == Decimal("350.00")


# =============================================================================
# 5. CHECKOUT INTEGRITY & SERVER-SIDE RECALCULATION
# =============================================================================

class TestCheckoutAndOrderIntegrity:
    def test_checkout_recalculates_gst_server_side_and_creates_snapshot(
        self, buyer_auth_client, seller_user, brake_category, filter_category
    ):
        # Listing 1: Brake Rotor (28% GST)
        l1 = SparePartListing.objects.create(
            seller=seller_user,
            name="Rotinger Drilled Brake Rotor Pair",
            brand="Rotinger",
            mpn="RT-2041",
            category=brake_category,
            price=Decimal("4000.00"),
            currency="INR",
            hsn_code="8708",
            gst_rate=Decimal("28.00"),
            status=ListingStatusChoices.APPROVED,
            is_active=True,
            stock_quantity=4,
        )

        # Listing 2: Oil Filter (18% GST)
        l2 = SparePartListing.objects.create(
            seller=seller_user,
            name="Mann-Filter Oil Filter",
            brand="Mann",
            mpn="HU-7010-Z",
            category=filter_category,
            price=Decimal("500.00"),
            currency="INR",
            hsn_code="8421",
            gst_rate=Decimal("18.00"),
            status=ListingStatusChoices.APPROVED,
            is_active=True,
            stock_quantity=10,
        )

        # Buyer attempts to check out, attempting to pass tampered client amounts
        payload = {
            "items": [
                {"listing_id": str(l1.id), "quantity": 1},
                {"listing_id": str(l2.id), "quantity": 2},
            ],
            "place_of_supply": "KA",
            "currency": "INR",
            # Tampered fields that MUST BE IGNORED by backend:
            "gst_rate": "5.00",
            "total_amount": "100.00",
        }

        res = buyer_auth_client.post('/api/v1/marketplace/orders/checkout/', payload, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data["status"] == "success"
        order_data = data["order"]

        # Expected calculations strictly verified on server:
        # l1: 4000.00 * 1 = 4000.00 taxable, 28% GST = 1120.00, line total = 5120.00
        # l2: 500.00 * 2 = 1000.00 taxable, 18% GST = 180.00, line total = 1180.00
        # Subtotal taxable: 4000 + 1000 = 5000.00
        # Total tax: 1120 + 180 = 1300.00
        # Total amount: 5000 + 1300 = 6300.00
        assert Decimal(order_data["subtotal_taxable_amount"]) == Decimal("5000.00")
        assert Decimal(order_data["total_tax_amount"]) == Decimal("1300.00")
        assert Decimal(order_data["total_amount"]) == Decimal("6300.00")

        # Verify database Order and OrderItem records
        order = Order.objects.get(id=order_data["id"])
        assert order.items.count() == 2
        assert order.total_amount == Decimal("6300.00")

        # Verify stock was deducted under row lock
        l1.refresh_from_db()
        l2.refresh_from_db()
        assert l1.stock_quantity == 3
        assert l2.stock_quantity == 8

    def test_order_historical_tax_snapshot_preserved_on_listing_modification(
        self, buyer_auth_client, seller_auth_client, seller_user, brake_category
    ):
        listing = SparePartListing.objects.create(
            seller=seller_user,
            name="Tarox F2000 Brake Disc",
            brand="Tarox",
            mpn="TX-F2000",
            category=brake_category,
            price=Decimal("1000.00"),
            currency="INR",
            hsn_code="8708",
            gst_rate=Decimal("28.00"),
            status=ListingStatusChoices.APPROVED,
            is_active=True,
            stock_quantity=5,
        )

        # Place order
        res = buyer_auth_client.post('/api/v1/marketplace/orders/checkout/', {
            "items": [{"listing_id": str(listing.id), "quantity": 1}],
            "currency": "INR",
        }, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        order_id = res.json()["order"]["id"]

        order_item = OrderItem.objects.get(order_id=order_id)
        assert order_item.unit_price == Decimal("1000.00")
        assert order_item.gst_rate == Decimal("28.00")
        assert order_item.tax_amount == Decimal("280.00")
        assert order_item.total_amount == Decimal("1280.00")

        # Seller changes listing price and HSN later
        listing.price = Decimal("2000.00")
        listing.hsn_code = "8708"
        listing.gst_rate = Decimal("18.00")  # e.g. concessional update
        listing.save()

        # The historical order snapshot MUST REMAIN UNCHANGED
        order_item.refresh_from_db()
        assert order_item.unit_price == Decimal("1000.00")
        assert order_item.gst_rate == Decimal("28.00")
        assert order_item.tax_amount == Decimal("280.00")
        assert order_item.total_amount == Decimal("1280.00")
