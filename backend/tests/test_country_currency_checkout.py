import pytest
from decimal import Decimal
from django.conf import settings
from rest_framework import status
from rest_framework.test import APIClient
from apps.identity.models import User, RoleChoices
from apps.catalogue.models import PartCategory
from apps.marketplace.models import (
    SparePartListing,
    ListingStatusChoices,
    Order,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
)


@pytest.fixture
def test_category(db):
    return PartCategory.objects.create(name="Braking Systems", slug="braking-systems-country-test")


@pytest.fixture
def seller_user(db):
    user = User.objects.create_user(
        email="seller_currency_test@driverxtra.com",
        password="SecurePassword123!",
        first_name="Ravi",
        last_name="Seller",
        phone_number="+919876543210",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def buyer_user(db):
    user = User.objects.create_user(
        email="buyer_currency_test@driverxtra.com",
        password="SecurePassword123!",
        first_name="Anita",
        last_name="Buyer",
        phone_number="+919123456789",
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def buyer_client(buyer_user):
    client = APIClient()
    client.force_authenticate(user=buyer_user)
    return client


@pytest.fixture
def inr_part(db, seller_user, test_category):
    return SparePartListing.objects.create(
        seller=seller_user,
        name="Front Disc Brake Pad Set (India)",
        brand="Brembo",
        mpn="BR-PAD-INR",
        category=test_category,
        price=Decimal("4000.00"),
        currency="INR",
        hsn_code="8708",
        gst_rate=Decimal("18.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        stock_quantity=10,
    )


@pytest.fixture
def gbp_part(db, seller_user, test_category):
    return SparePartListing.objects.create(
        seller=seller_user,
        name="Front Disc Brake Pad Set (UK)",
        brand="Ferodo",
        mpn="FRP-PAD-GBP",
        category=test_category,
        price=Decimal("50.00"),
        currency="GBP",
        hsn_code="8708",
        gst_rate=Decimal("0.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        stock_quantity=10,
    )


@pytest.fixture
def multi_currency_part(db, seller_user, test_category):
    return SparePartListing.objects.create(
        seller=seller_user,
        name="Multi-Currency Clutch Kit",
        brand="Sachs",
        mpn="MC-CLUTCH-01",
        category=test_category,
        price=Decimal("100.00"),
        currency="GBP",
        country_prices={"IN": "9500.00", "GB": "100.00"},
        hsn_code="8708",
        gst_rate=Decimal("18.00"),
        status=ListingStatusChoices.APPROVED,
        is_active=True,
        stock_quantity=10,
    )


@pytest.mark.django_db
class TestCountryAndCurrencyCheckoutFlow:
    """
    Regression test suite for destination country-specific checkout pricing,
    authoritative server-side calculations, exchange rate conversion,
    and payment gateway routing (Razorpay for INR, Stripe for GBP).
    """

    def test_1_india_checkout_with_inr_product(self, buyer_client, inr_part):
        """Scenario 1: India checkout with an INR-priced product produces INR total and Razorpay session."""
        calc_payload = {
            "items": [{"listing_id": str(inr_part.id), "quantity": 1}],
            "shipping_country": "India",
            "place_of_supply": "MH",
            "currency": "INR",
        }
        res_calc = buyer_client.post("/api/v1/marketplace/orders/calculate/", calc_payload, format="json")
        assert res_calc.status_code == status.HTTP_200_OK
        data_calc = res_calc.data
        assert data_calc["currency"] == "INR"
        assert Decimal(data_calc["subtotal_taxable_amount"]) == Decimal("4000.00")
        assert Decimal(data_calc["total_amount"]) == Decimal("4720.00")
        assert Decimal(data_calc["total_tax_amount"]) == Decimal("720.00")

        checkout_payload = {
            "items": [{"listing_id": str(inr_part.id), "quantity": 1}],
            "shipping_name": "Anita Buyer",
            "shipping_phone": "+919123456789",
            "shipping_address_line1": "101, Marine Drive",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400020",
            "shipping_country": "India",
            "currency": "INR",
            "payment_method": "ONLINE",
            "expected_total_amount": "4720.00",
            "idempotency_key": "india-inr-checkout-test-1",
        }
        res_order = buyer_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        assert res_order.status_code == status.HTTP_201_CREATED
        order_data = res_order.data["order"]
        assert order_data["currency"] == "INR"
        assert Decimal(str(order_data["total_amount"])) == Decimal("4720.00")
        assert res_order.data["payment_session"]["provider"] == "RAZORPAY"
        assert res_order.data["payment_session"]["currency"] == "INR"
        assert res_order.data["payment_session"]["amount_minor"] == 472000  # minor units: paise

    def test_2_uk_checkout_with_gbp_product(self, buyer_client, gbp_part):
        """Scenario 2: UK checkout with a GBP-priced product produces GBP total and Stripe session."""
        calc_payload = {
            "items": [{"listing_id": str(gbp_part.id), "quantity": 2}],
            "shipping_country": "United Kingdom",
            "place_of_supply": "London",
            "currency": "GBP",
        }
        res_calc = buyer_client.post("/api/v1/marketplace/orders/calculate/", calc_payload, format="json")
        assert res_calc.status_code == status.HTTP_200_OK
        data_calc = res_calc.data
        assert data_calc["currency"] == "GBP"
        assert Decimal(data_calc["subtotal_taxable_amount"]) == Decimal("100.00")
        # UK VAT is 0.00 in current settings
        assert Decimal(data_calc["total_tax_amount"]) == Decimal("0.00")
        assert Decimal(data_calc["total_amount"]) == Decimal("100.00")

        checkout_payload = {
            "items": [{"listing_id": str(gbp_part.id), "quantity": 2}],
            "shipping_name": "Oliver Twist",
            "shipping_phone": "+447000123456",
            "shipping_address_line1": "10 Downing Street",
            "shipping_city": "London",
            "shipping_state": "London",
            "shipping_postal_code": "SW1A 2AA",
            "shipping_country": "United Kingdom",
            "currency": "GBP",
            "payment_method": "ONLINE",
            "expected_total_amount": "100.00",
            "idempotency_key": "uk-gbp-checkout-test-2",
        }
        res_order = buyer_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        assert res_order.status_code == status.HTTP_201_CREATED
        order_data = res_order.data["order"]
        assert order_data["currency"] == "GBP"
        assert Decimal(str(order_data["total_amount"])) == Decimal("100.00")
        assert res_order.data["payment_session"]["provider"] == "STRIPE"
        assert res_order.data["payment_session"]["currency"] == "GBP"
        assert res_order.data["payment_session"]["amount_minor"] == 10000  # minor units: pence

    def test_3_switching_from_uk_to_india_while_cart_open(self, buyer_client, gbp_part):
        """
        Scenario 3: A GBP item initially previewed for UK is switched to India.
        Server authoritative converts GBP 50.00 to INR using the configured exchange rate (105.00),
        producing INR 5250.00 unit price, adding statutory GST, and yielding INR total.
        """
        # Step A: Preview for UK
        uk_payload = {
            "items": [{"listing_id": str(gbp_part.id), "quantity": 1}],
            "shipping_country": "United Kingdom",
            "place_of_supply": "London",
            "currency": "GBP",
        }
        res_uk = buyer_client.post("/api/v1/marketplace/orders/calculate/", uk_payload, format="json")
        assert res_uk.status_code == status.HTTP_200_OK
        assert res_uk.data["currency"] == "GBP"
        assert Decimal(res_uk.data["total_amount"]) == Decimal("50.00")

        # Step B: Buyer switches destination country to India
        india_payload = {
            "items": [{"listing_id": str(gbp_part.id), "quantity": 1}],
            "shipping_country": "India",
            "place_of_supply": "DL",
            "currency": "INR",
        }
        res_india = buyer_client.post("/api/v1/marketplace/orders/calculate/", india_payload, format="json")
        assert res_india.status_code == status.HTTP_200_OK
        assert res_india.data["currency"] == "INR"
        # 50.00 GBP * 105.00 = 5250.00 INR taxable amount
        assert Decimal(res_india.data["subtotal_taxable_amount"]) == Decimal("5250.00")
        # GST rate on gbp_part is 0.00 (from fixture), total should be 5250.00 INR
        assert Decimal(res_india.data["total_amount"]) == Decimal("5250.00")

    def test_4_switching_from_india_to_uk_while_cart_open(self, buyer_client, inr_part):
        """
        Scenario 4: An INR item initially previewed for India is switched to UK.
        Server authoritative converts INR 4000.00 to GBP using configured exchange rate (0.0095),
        producing GBP 38.00 unit price and total.
        """
        # Step A: Preview for India
        in_payload = {
            "items": [{"listing_id": str(inr_part.id), "quantity": 1}],
            "shipping_country": "India",
            "place_of_supply": "MH",
            "currency": "INR",
        }
        res_in = buyer_client.post("/api/v1/marketplace/orders/calculate/", in_payload, format="json")
        assert res_in.status_code == status.HTTP_200_OK
        assert res_in.data["currency"] == "INR"

        # Step B: Buyer switches destination country to UK
        uk_payload = {
            "items": [{"listing_id": str(inr_part.id), "quantity": 1}],
            "shipping_country": "United Kingdom",
            "place_of_supply": "London",
            "currency": "GBP",
        }
        res_uk = buyer_client.post("/api/v1/marketplace/orders/calculate/", uk_payload, format="json")
        assert res_uk.status_code == status.HTTP_200_OK
        assert res_uk.data["currency"] == "GBP"
        # 4000.00 INR * 0.0095 = 38.00 GBP
        assert Decimal(res_uk.data["subtotal_taxable_amount"]) == Decimal("38.00")
        assert Decimal(res_uk.data["total_amount"]) == Decimal("38.00")

    def test_5_product_missing_valid_destination_price_unconfigured_conversion(
        self, buyer_client, gbp_part, monkeypatch
    ):
        """
        Scenario 5: If conversion is not configured and a product has no destination-currency price,
        the backend returns a clear error explaining which product needs a valid price.
        """
        monkeypatch.setattr(settings, "CURRENCY_EXCHANGE_RATES", {})

        calc_payload = {
            "items": [{"listing_id": str(gbp_part.id), "quantity": 1}],
            "shipping_country": "India",
            "place_of_supply": "MH",
            "currency": "INR",
        }
        res = buyer_client.post("/api/v1/marketplace/orders/calculate/", calc_payload, format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "lacks a valid price for INR and currency conversion from GBP to INR is not configured" in res.data["error"]
        assert gbp_part.name in res.data["error"]

    def test_6_no_silent_currency_relabeling_or_1_to_1_conversion(self, buyer_client, gbp_part):
        """
        Scenario 6: Verify that converting 50 GBP to INR does NOT silently label 50 as 50 INR (1:1 conversion).
        It must mathematically apply the configured Decimal rate (50 * 105 = 5250 INR).
        """
        calc_payload = {
            "items": [{"listing_id": str(gbp_part.id), "quantity": 1}],
            "shipping_country": "India",
            "place_of_supply": "MH",
            "currency": "INR",
        }
        res = buyer_client.post("/api/v1/marketplace/orders/calculate/", calc_payload, format="json")
        assert res.status_code == status.HTTP_200_OK
        # Must NOT be 50.00 INR!
        assert Decimal(res.data["subtotal_taxable_amount"]) != Decimal("50.00")
        assert Decimal(res.data["subtotal_taxable_amount"]) == Decimal("5250.00")

    def test_7_country_prices_override_takes_precedence_over_exchange_rate(
        self, buyer_client, multi_currency_part
    ):
        """
        Scenario: If a listing specifies explicit country_prices, that price takes precedence
        over generic exchange-rate conversion.
        """
        calc_payload = {
            "items": [{"listing_id": str(multi_currency_part.id), "quantity": 1}],
            "shipping_country": "India",
            "place_of_supply": "MH",
            "currency": "INR",
        }
        res = buyer_client.post("/api/v1/marketplace/orders/calculate/", calc_payload, format="json")
        assert res.status_code == status.HTTP_200_OK
        # Multi-currency part has country_prices={"IN": "9500.00"}
        # Generic rate (100 * 105) would have been 10500.00; explicit country price is 9500.00
        assert Decimal(res.data["subtotal_taxable_amount"]) == Decimal("9500.00")

    def test_8_authoritative_server_side_validation_rejects_client_tampered_total(
        self, buyer_client, inr_part
    ):
        """
        Scenario 7/8: Server validates authoritative prices. Never trusts frontend totals.
        Tampered total returns 409 Conflict.
        """
        checkout_payload = {
            "items": [{"listing_id": str(inr_part.id), "quantity": 1}],
            "shipping_name": "Anita Buyer",
            "shipping_phone": "+919123456789",
            "shipping_address_line1": "101, Marine Drive",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400020",
            "shipping_country": "India",
            "currency": "INR",
            "payment_method": "ONLINE",
            "expected_total_amount": "1.00",  # Fraudulent client-supplied amount
            "idempotency_key": "tampered-total-test",
        }
        res = buyer_client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        assert res.status_code == status.HTTP_409_CONFLICT
        assert "The order total has changed from" in res.data["error"]
        assert Decimal(res.data["updated_total_amount"]) == Decimal("4720.00")


# =============================================================================
# ENG-03: EXPLICIT DELIVERY COUNTRY REQUIRED (no implicit India/UK fallback)
# =============================================================================

@pytest.mark.django_db
class TestEng03DeliveryCountryRequired:
    CHECKOUT_URL = "/api/v1/marketplace/orders/checkout/"
    CALCULATE_URL = "/api/v1/marketplace/orders/calculate/"

    @staticmethod
    def _payload(listing, *, currency, country, payment_method="ONLINE"):
        payload = {
            "items": [{"listing_id": str(listing.id), "quantity": 1}],
            "payment_method": payment_method,
            "shipping_name": "Country Test Buyer",
            "shipping_phone": "+44 7911 123456",
            "shipping_address_line1": "1 Test Street",
            "shipping_city": "London",
            "shipping_postal_code": "NW1 6XE",
        }
        if currency is not None:
            payload["currency"] = currency
        if country is not None:
            payload["shipping_country"] = country
        return payload

    @pytest.mark.parametrize("url", [CHECKOUT_URL, CALCULATE_URL], ids=["checkout", "preview"])
    @pytest.mark.parametrize("country", [None, "", "   "], ids=["omitted", "empty", "whitespace"])
    @pytest.mark.parametrize("currency", ["INR", "GBP", None], ids=["INR", "GBP", "no-currency"])
    def test_missing_country_rejected_without_side_effects(self, buyer_client, inr_part, gbp_part,
                                                           url, country, currency):
        from apps.marketplace.models import PaymentTransaction

        listing = gbp_part if currency == "GBP" else inr_part
        res = buyer_client.post(url, self._payload(listing, currency=currency, country=country), format="json")

        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.content
        body = res.json()
        assert body["code"] == "DELIVERY_COUNTRY_REQUIRED"
        assert body["error"] == "A delivery country is required."
        assert "shipping_country" in body["field_errors"]
        assert Order.objects.count() == 0
        assert PaymentTransaction.objects.count() == 0
        inr_part.refresh_from_db()
        gbp_part.refresh_from_db()
        assert (inr_part.stock_quantity, gbp_part.stock_quantity) == (10, 10)

    def test_missing_country_rejected_for_cash_on_delivery(self, buyer_client, gbp_part):
        res = buyer_client.post(self.CHECKOUT_URL,
                                self._payload(gbp_part, currency="GBP", country=None, payment_method="COD"),
                                format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert res.json()["code"] == "DELIVERY_COUNTRY_REQUIRED"
        assert Order.objects.count() == 0
        gbp_part.refresh_from_db()
        assert gbp_part.stock_quantity == 10

    @pytest.mark.parametrize("payment_method", ["ONLINE", "COD"])
    def test_explicit_india_checkout_unchanged(self, buyer_client, inr_part, payment_method):
        payload = self._payload(inr_part, currency="INR", country="India", payment_method=payment_method)
        payload.update({"shipping_city": "Mumbai", "shipping_state": "MH", "shipping_postal_code": "400020",
                        "shipping_phone": "+919123456789", "place_of_supply": "MH"})
        res = buyer_client.post(self.CHECKOUT_URL, payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED, res.content
        order = res.json()["order"]
        assert (order["currency"], order["payment_method"]) == ("INR", payment_method)
        if payment_method == "ONLINE":
            assert res.json()["payment_session"]["provider"] == "RAZORPAY"

    @pytest.mark.parametrize("payment_method", ["ONLINE", "COD"])
    def test_explicit_uk_checkout_unchanged(self, buyer_client, gbp_part, payment_method):
        payload = self._payload(gbp_part, currency="GBP", country="United Kingdom", payment_method=payment_method)
        res = buyer_client.post(self.CHECKOUT_URL, payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED, res.content
        order = res.json()["order"]
        assert (order["currency"], order["payment_method"]) == ("GBP", payment_method)
        if payment_method == "ONLINE":
            assert res.json()["payment_session"]["provider"] == "STRIPE"
