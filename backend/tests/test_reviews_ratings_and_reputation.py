import uuid
from decimal import Decimal
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import User, RoleChoices
from apps.catalogue.models import PartCategory
from apps.marketplace.models import (
    Order,
    OrderItem,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
    SparePartListing,
    ListingStatusChoices,
    ProductReview,
    SellerReview,
    ReviewReport,
    ReviewStatusChoices,
    ReviewReportReasonChoices,
    ReviewReportStatusChoices,
    ReviewReportActionChoices,
)
from apps.marketplace.reviews import ReputationService, ReviewWorkflowService


@pytest.fixture
def test_category(db):
    return PartCategory.objects.create(name="Suspension & Steering", slug="suspension-steering")


@pytest.fixture
def other_buyer(db):
    user = User.objects.create_user(
        email='other_buyer@driverxtra.com',
        password='SecurePassword123!',
        first_name='Alice',
        last_name='Buyer',
        phone_number='+447000000088',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.BUYER)
    return user


@pytest.fixture
def other_buyer_client(other_buyer):
    client = APIClient()
    client.force_authenticate(user=other_buyer)
    return client


@pytest.fixture
def completed_order(db, buyer_user, seller_user, test_category):
    listing = SparePartListing.objects.create(
        seller=seller_user,
        category=test_category,
        name="Front Strut Assembly",
        brand="Monroe",
        mpn="MON-778899",
        price=Decimal("120.00"),
        currency="GBP",
        stock_quantity=15,
        status=ListingStatusChoices.APPROVED,
    )

    order = Order.objects.create(
        buyer=buyer_user,
        order_number="ORD-REV-001",
        status=OrderStatusChoices.COMPLETED,
        payment_method=PaymentMethodChoices.ONLINE,
        payment_status=PaymentStatusChoices.PAID,
        currency="GBP",
        subtotal_taxable_amount=Decimal("120.00"),
        total_tax_amount=Decimal("24.00"),
        total_amount=Decimal("144.00"),
        shipping_name="John Buyer",
        shipping_city="London",
    )

    item = OrderItem.objects.create(
        order=order,
        listing=listing,
        item_type="PART",
        title=listing.name,
        brand=listing.brand,
        mpn=listing.mpn,
        unit_price=Decimal("120.00"),
        quantity=1,
        taxable_amount=Decimal("120.00"),
        tax_amount=Decimal("24.00"),
        total_amount=Decimal("144.00"),
    )

    return order, item, listing


@pytest.fixture
def cancelled_order(db, buyer_user, seller_user, test_category):
    listing = SparePartListing.objects.create(
        seller=seller_user,
        category=test_category,
        name="Rear Brake Caliper",
        brand="Brembo",
        mpn="BREM-4455",
        price=Decimal("80.00"),
        currency="GBP",
        stock_quantity=5,
        status=ListingStatusChoices.APPROVED,
    )

    order = Order.objects.create(
        buyer=buyer_user,
        order_number="ORD-REV-CANCELLED",
        status=OrderStatusChoices.CANCELLED,
        payment_method=PaymentMethodChoices.ONLINE,
        payment_status=PaymentStatusChoices.CANCELLED,
        currency="GBP",
        subtotal_taxable_amount=Decimal("80.00"),
        total_tax_amount=Decimal("16.00"),
        total_amount=Decimal("96.00"),
    )

    item = OrderItem.objects.create(
        order=order,
        listing=listing,
        item_type="PART",
        title=listing.name,
        brand=listing.brand,
        mpn=listing.mpn,
        unit_price=Decimal("80.00"),
        quantity=1,
        taxable_amount=Decimal("80.00"),
        tax_amount=Decimal("16.00"),
        total_amount=Decimal("96.00"),
    )

    return order, item, listing


# =============================================================================
# 1. PURCHASE ELIGIBILITY & SUBMISSION TESTS
# =============================================================================

@pytest.mark.django_db
def test_buyer_review_eligibility_endpoint(buyer_auth_client, completed_order):
    order, item, listing = completed_order
    url = f"/api/v1/marketplace/buyer/orders/{order.id}/review-eligibility/"
    response = buyer_auth_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    data = response.data
    assert data["order_number"] == order.order_number
    assert data["eligible"] is True
    assert len(data["items"]) == 1
    assert data["items"][0]["order_item_id"] == str(item.id)
    assert data["items"][0]["eligible"] is True
    assert data["items"][0]["is_reviewed"] is False


@pytest.mark.django_db
def test_successful_product_review_submission(buyer_auth_client, completed_order, seller_user):
    order, item, listing = completed_order
    url = f"/api/v1/marketplace/buyer/orders/{order.order_number}/reviews/"
    payload = {
        "order_item_id": str(item.id),
        "rating": 5,
        "title": "Excellent fitment and ride quality",
        "comment": "Installed these struts over the weekend. Perfect fit and original ride quality restored.",
        "seller_rating": 5,
        "seller_comment": "Fast dispatch and great packaging.",
    }
    response = buyer_auth_client.post(url, data=payload, format='json')
    assert response.status_code == status.HTTP_201_CREATED
    data = response.data
    assert data["rating"] == 5
    assert data["title"] == "Excellent fitment and ride quality"
    assert data["is_verified_purchase"] is True
    assert data["order_item_id"] == str(item.id)
    assert data["listing_id"] == str(listing.id)

    # Check database persistence
    assert ProductReview.objects.filter(order_item=item).count() == 1
    assert SellerReview.objects.filter(order=order, seller=seller_user).count() == 1


@pytest.mark.django_db
def test_duplicate_review_submission_blocked(buyer_auth_client, completed_order):
    order, item, listing = completed_order
    url = f"/api/v1/marketplace/buyer/orders/{order.id}/reviews/"
    payload = {
        "order_item_id": str(item.id),
        "rating": 4,
        "comment": "Good quality product that fits as expected.",
    }
    # First submission succeeds
    r1 = buyer_auth_client.post(url, data=payload, format='json')
    assert r1.status_code == status.HTTP_201_CREATED

    # Second submission for the same purchase fails with 400
    r2 = buyer_auth_client.post(url, data=payload, format='json')
    assert r2.status_code == status.HTTP_400_BAD_REQUEST
    assert "already reviewed" in r2.data["error"].lower()


@pytest.mark.django_db
def test_invalid_rating_values_rejected(buyer_auth_client, completed_order):
    order, item, listing = completed_order
    url = f"/api/v1/marketplace/buyer/orders/{order.id}/reviews/"

    # Rating 0 (less than 1)
    r_zero = buyer_auth_client.post(url, data={"order_item_id": str(item.id), "rating": 0, "comment": "Valid comment here"}, format='json')
    assert r_zero.status_code == status.HTTP_400_BAD_REQUEST

    # Rating 6 (greater than 5)
    r_six = buyer_auth_client.post(url, data={"order_item_id": str(item.id), "rating": 6, "comment": "Valid comment here"}, format='json')
    assert r_six.status_code == status.HTTP_400_BAD_REQUEST

    # Short comment
    r_short = buyer_auth_client.post(url, data={"order_item_id": str(item.id), "rating": 4, "comment": "bad"}, format='json')
    assert r_short.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_cancelled_order_review_rejected(buyer_auth_client, cancelled_order):
    order, item, listing = cancelled_order
    url = f"/api/v1/marketplace/buyer/orders/{order.id}/reviews/"
    payload = {
        "order_item_id": str(item.id),
        "rating": 1,
        "comment": "Order was cancelled but trying to submit review.",
    }
    response = buyer_auth_client.post(url, data=payload, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "cancelled" in response.data["error"].lower()


@pytest.mark.django_db
def test_unauthorized_buyer_cannot_review_others_order(other_buyer_client, completed_order):
    order, item, listing = completed_order
    url = f"/api/v1/marketplace/buyer/orders/{order.id}/reviews/"
    payload = {
        "order_item_id": str(item.id),
        "rating": 5,
        "comment": "Attempting to review someone else's order.",
    }
    response = other_buyer_client.post(url, data=payload, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_unauthenticated_user_cannot_submit_review(api_client, completed_order):
    order, item, listing = completed_order
    url = f"/api/v1/marketplace/buyer/orders/{order.id}/reviews/"
    payload = {
        "order_item_id": str(item.id),
        "rating": 5,
        "comment": "Unauthenticated submission.",
    }
    response = api_client.post(url, data=payload, format='json')
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =============================================================================
# 2. RATING & REPUTATION CALCULATION TESTS
# =============================================================================

@pytest.mark.django_db
def test_product_rating_calculation_and_breakdown(completed_order, other_buyer, buyer_user, seller_user, test_category):
    order1, item1, listing = completed_order

    # Review 1: 5 stars
    ProductReview.objects.create(
        order=order1,
        order_item=item1,
        listing=listing,
        buyer=buyer_user,
        seller=seller_user,
        rating=5,
        title="Superb",
        comment="5 star quality",
        status=ReviewStatusChoices.APPROVED,
    )

    # Create Order 2 and Item 2 for other_buyer
    order2 = Order.objects.create(
        buyer=other_buyer,
        order_number="ORD-REV-002",
        status=OrderStatusChoices.COMPLETED,
        currency="GBP",
        subtotal_taxable_amount=Decimal("120.00"),
        total_tax_amount=Decimal("24.00"),
        total_amount=Decimal("144.00"),
    )
    item2 = OrderItem.objects.create(
        order=order2,
        listing=listing,
        item_type="PART",
        title=listing.name,
        unit_price=Decimal("120.00"),
        quantity=1,
        taxable_amount=Decimal("120.00"),
        tax_amount=Decimal("24.00"),
        total_amount=Decimal("144.00"),
    )

    # Review 2: 3 stars
    ProductReview.objects.create(
        order=order2,
        order_item=item2,
        listing=listing,
        buyer=other_buyer,
        seller=seller_user,
        rating=3,
        title="Average",
        comment="Average quality",
        status=ReviewStatusChoices.APPROVED,
    )

    summary = ReputationService.get_product_rating_summary(listing)
    assert summary["review_count"] == 2
    assert summary["average_rating"] == 4.0  # (5 + 3) / 2 = 4.0
    assert summary["distribution"]["5"] == 1
    assert summary["distribution"]["3"] == 1
    assert summary["distribution"]["1"] == 0


@pytest.mark.django_db
def test_seller_reputation_calculation(completed_order, buyer_user, seller_user):
    order, item, listing = completed_order

    # SellerReview 1: 5 stars with reply
    SellerReview.objects.create(
        order=order,
        buyer=buyer_user,
        seller=seller_user,
        rating=5,
        communication_rating=5,
        delivery_rating=4,
        comment="Seller was very communicative.",
        seller_reply="Thank you so much!",
        status=ReviewStatusChoices.APPROVED,
    )

    reputation = ReputationService.get_seller_reputation_summary(seller_user)
    assert reputation["seller_name"] == seller_user.full_name
    assert reputation["average_rating"] == 5.0
    assert reputation["positive_percentage"] == 100
    assert reputation["response_rate"] == 100
    assert reputation["seller_reviews_count"] == 1


# =============================================================================
# 3. REVIEW UPDATE, DELETE & SELLER REPLY TESTS
# =============================================================================

@pytest.mark.django_db
def test_buyer_can_update_own_review(buyer_auth_client, completed_order, buyer_user, seller_user):
    order, item, listing = completed_order
    review = ProductReview.objects.create(
        order=order,
        order_item=item,
        listing=listing,
        buyer=buyer_user,
        seller=seller_user,
        rating=3,
        title="Okay",
        comment="Decent item after all.",
        status=ReviewStatusChoices.APPROVED,
    )

    url = f"/api/v1/marketplace/reviews/{review.id}/"
    update_payload = {
        "rating": 5,
        "title": "Updated: Outstanding item!",
        "comment": "After testing further, the performance is flawless.",
    }
    response = buyer_auth_client.patch(url, data=update_payload, format='json')
    assert response.status_code == status.HTTP_200_OK
    assert response.data["rating"] == 5
    assert response.data["title"] == "Updated: Outstanding item!"

    review.refresh_from_db()
    assert review.rating == 5


@pytest.mark.django_db
def test_other_user_cannot_update_or_delete_review(other_buyer_client, completed_order, buyer_user, seller_user):
    order, item, listing = completed_order
    review = ProductReview.objects.create(
        order=order,
        order_item=item,
        listing=listing,
        buyer=buyer_user,
        seller=seller_user,
        rating=4,
        comment="Good part.",
        status=ReviewStatusChoices.APPROVED,
    )

    url = f"/api/v1/marketplace/reviews/{review.id}/"
    # Attempt update
    r_patch = other_buyer_client.patch(url, data={"rating": 1}, format='json')
    assert r_patch.status_code == status.HTTP_400_BAD_REQUEST

    # Attempt delete
    r_del = other_buyer_client.delete(url)
    assert r_del.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_seller_can_reply_to_review(seller_auth_client, completed_order, buyer_user, seller_user):
    order, item, listing = completed_order
    review = ProductReview.objects.create(
        order=order,
        order_item=item,
        listing=listing,
        buyer=buyer_user,
        seller=seller_user,
        rating=5,
        comment="Great service!",
        status=ReviewStatusChoices.APPROVED,
    )

    url = f"/api/v1/marketplace/reviews/{review.id}/reply/"
    reply_payload = {"reply": "Thank you for choosing DriverXtra! We appreciate your business."}
    response = seller_auth_client.post(url, data=reply_payload, format='json')
    assert response.status_code == status.HTTP_200_OK
    assert response.data["has_seller_reply"] is True
    assert "We appreciate your business" in response.data["seller_reply"]


@pytest.mark.django_db
def test_non_seller_cannot_reply_to_review(buyer_auth_client, completed_order, buyer_user, seller_user):
    order, item, listing = completed_order
    review = ProductReview.objects.create(
        order=order,
        order_item=item,
        listing=listing,
        buyer=buyer_user,
        seller=seller_user,
        rating=5,
        comment="Great item.",
        status=ReviewStatusChoices.APPROVED,
    )

    url = f"/api/v1/marketplace/reviews/{review.id}/reply/"
    response = buyer_auth_client.post(url, data={"reply": "Unauthorized reply attempt."}, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN


# =============================================================================
# 4. REPORTING & MODERATION TESTS
# =============================================================================

@pytest.mark.django_db
def test_user_can_report_abusive_review(other_buyer_client, completed_order, buyer_user, seller_user):
    order, item, listing = completed_order
    review = ProductReview.objects.create(
        order=order,
        order_item=item,
        listing=listing,
        buyer=buyer_user,
        seller=seller_user,
        rating=1,
        comment="Spam promotional link www.scam.com buy now!",
        status=ReviewStatusChoices.APPROVED,
    )

    url = f"/api/v1/marketplace/reviews/{review.id}/report/"
    report_payload = {
        "reason": "SPAM",
        "details": "Contains spam advertisement and external URL.",
    }
    response = other_buyer_client.post(url, data=report_payload, format='json')
    assert response.status_code == status.HTTP_201_CREATED
    assert "report_id" in response.data

    review.refresh_from_db()
    assert review.status == ReviewStatusChoices.FLAGGED
    assert ReviewReport.objects.filter(product_review=review).count() == 1


@pytest.mark.django_db
def test_admin_review_moderation(admin_auth_client, completed_order, buyer_user, seller_user):
    order, item, listing = completed_order
    review = ProductReview.objects.create(
        order=order,
        order_item=item,
        listing=listing,
        buyer=buyer_user,
        seller=seller_user,
        rating=1,
        comment="Abusive language used here.",
        status=ReviewStatusChoices.FLAGGED,
    )

    url = f"/api/v1/marketplace/admin/reviews/{review.id}/moderate/"
    mod_payload = {
        "action": "HIDE",
        "admin_notes": "Hidden due to policy violation.",
    }
    response = admin_auth_client.post(url, data=mod_payload, format='json')
    assert response.status_code == status.HTTP_200_OK

    review.refresh_from_db()
    assert review.status == ReviewStatusChoices.REJECTED


@pytest.mark.django_db
def test_admin_resolve_review_report(admin_auth_client, completed_order, buyer_user, seller_user, other_buyer):
    order, item, listing = completed_order
    review = ProductReview.objects.create(
        order=order,
        order_item=item,
        listing=listing,
        buyer=buyer_user,
        seller=seller_user,
        rating=1,
        comment="Offensive review content.",
        status=ReviewStatusChoices.FLAGGED,
    )
    report = ReviewReport.objects.create(
        product_review=review,
        reporter=other_buyer,
        reason=ReviewReportReasonChoices.OFFENSIVE,
        status=ReviewReportStatusChoices.PENDING,
    )

    url = f"/api/v1/marketplace/admin/review-reports/{report.id}/resolve/"
    resolve_payload = {
        "action": "HIDE_REVIEW",
        "admin_notes": "Review violates community guidelines and has been hidden.",
    }
    response = admin_auth_client.post(url, data=resolve_payload, format='json')
    assert response.status_code == status.HTTP_200_OK

    report.refresh_from_db()
    assert report.status == ReviewReportStatusChoices.RESOLVED
    assert report.action_taken == ReviewReportActionChoices.REVIEW_HIDDEN

    review.refresh_from_db()
    assert review.status == ReviewStatusChoices.REJECTED


# =============================================================================
# 5. PUBLIC LISTING REVIEWS & HELPFUL VOTES
# =============================================================================

@pytest.mark.django_db
def test_public_part_reviews_view(api_client, completed_order, buyer_user, seller_user):
    order, item, listing = completed_order
    ProductReview.objects.create(
        order=order,
        order_item=item,
        listing=listing,
        buyer=buyer_user,
        seller=seller_user,
        rating=5,
        title="Top tier",
        comment="5 stars, smooth transaction.",
        status=ReviewStatusChoices.APPROVED,
    )

    url = f"/api/v1/marketplace/browse/parts/{listing.id}/reviews/"
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert "summary" in response.data
    assert response.data["summary"]["average_rating"] == 5.0
    assert response.data["summary"]["review_count"] == 1
    assert len(response.data["results"]) == 1


@pytest.mark.django_db
def test_toggle_helpful_vote(other_buyer_client, completed_order, buyer_user, seller_user):
    order, item, listing = completed_order
    review = ProductReview.objects.create(
        order=order,
        order_item=item,
        listing=listing,
        buyer=buyer_user,
        seller=seller_user,
        rating=5,
        comment="Very informative review.",
        status=ReviewStatusChoices.APPROVED,
    )

    url = f"/api/v1/marketplace/reviews/{review.id}/helpful/"
    # Vote helpful
    r1 = other_buyer_client.post(url)
    assert r1.status_code == status.HTTP_200_OK
    assert r1.data["has_voted"] is True
    assert r1.data["helpful_votes"] == 1

    # Toggle off
    r2 = other_buyer_client.post(url)
    assert r2.status_code == status.HTTP_200_OK
    assert r2.data["has_voted"] is False
    assert r2.data["helpful_votes"] == 0
