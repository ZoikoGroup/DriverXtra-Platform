import logging
import uuid
from decimal import Decimal
from typing import Dict, Any, List, Tuple, Optional

from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.identity.models import User
from apps.marketplace.models import (
    Order,
    OrderItem,
    OrderStatusChoices,
    PaymentStatusChoices,
    SparePartListing,
    ProductReview,
    SellerReview,
    ReviewReport,
    ReviewStatusChoices,
    ReviewReportReasonChoices,
    ReviewReportStatusChoices,
    ReviewReportActionChoices,
    ProductReviewHelpfulVote,
)
from platform_core.audit.writer import record_audit_entry, record_denied_audit_entry

logger = logging.getLogger(__name__)


def _is_staff_or_admin(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return bool(
        user.is_superuser
        or user.is_staff
        or getattr(user, 'role', '') in ('STAFF', 'ADMIN')
        or (hasattr(user, 'has_role') and (user.has_role('STAFF') or user.has_role('ADMIN')))
    )


def _is_seller_authorized_for_review(user, review: ProductReview | SellerReview) -> bool:
    """Checks if user is direct seller or organisation admin for the review target."""
    if _is_staff_or_admin(user):
        return True
    if not user or not user.is_authenticated:
        return False

    if review.seller_id == user.id:
        return True

    from apps.organisations.models import OrganisationMembership, OrganisationRoleChoices
    org_id = review.organisation_id
    if org_id:
        return OrganisationMembership.objects.filter(
            user=user,
            organisation_id=org_id,
            is_active=True,
            role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
        ).exists()

    return False


class ReviewEligibilityService:
    """
    Validates buyer purchase eligibility to submit ratings and reviews.
    """

    @classmethod
    def validate_purchase_eligibility(
        cls,
        user: Any,
        order: Order,
        order_item: OrderItem,
    ) -> Tuple[bool, str]:
        """
        Validates whether user is eligible to review the specified OrderItem in Order.
        Rules:
        1. User must be authenticated.
        2. Order must belong to user (order.buyer == user).
        3. OrderItem must belong to Order.
        4. Order must NOT be CANCELLED.
        5. Order must be confirmed/completed or paid.
        6. Item must not have been already reviewed (duplicate prevention).
        """
        if not user or not user.is_authenticated:
            return False, "Authentication required to review purchases."

        if order.buyer_id != user.id and not _is_staff_or_admin(user):
            return False, "You can only review purchases from your own orders."

        if order_item.order_id != order.id:
            return False, f"Item '{order_item.id}' does not belong to order '{order.order_number}'."

        if not order_item.listing_id:
            return False, "This order item is not linked to an active marketplace listing."

        if order.status == OrderStatusChoices.CANCELLED:
            return False, f"Order {order.order_number} is cancelled. Cancelled purchases cannot be reviewed."

        # Verified purchase check: confirmed, processing, completed or paid
        valid_statuses = [
            OrderStatusChoices.CONFIRMED,
            OrderStatusChoices.PROCESSING,
            OrderStatusChoices.COMPLETED,
        ]
        is_paid = order.payment_status in [PaymentStatusChoices.PAID, PaymentStatusChoices.AUTHORIZED]
        if order.status not in valid_statuses and not is_paid:
            return False, "Order must be confirmed or paid before a review can be submitted."

        # Duplicate review prevention
        if hasattr(order_item, 'product_review') or ProductReview.objects.filter(order_item=order_item).exists():
            return False, "You have already reviewed this purchased item."

        return True, "Eligible to review."

    @classmethod
    def get_order_review_eligibility(
        cls,
        order: Order,
        user: Any,
    ) -> Dict[str, Any]:
        """
        Evaluates review eligibility for all items in an order.
        """
        items_data = []
        all_reviewed = True

        for item in order.items.select_related('listing', 'listing__seller').all():
            is_eligible, reason = cls.validate_purchase_eligibility(user, order, item)
            existing_review = getattr(item, 'product_review', None) or ProductReview.objects.filter(order_item=item).first()
            if not existing_review:
                all_reviewed = False

            seller_name = ""
            seller_id = None
            if item.listing and item.listing.seller:
                seller_name = item.listing.seller.full_name or item.listing.seller.email
                seller_id = str(item.listing.seller_id)

            items_data.append({
                "order_item_id": str(item.id),
                "title": item.title,
                "brand": item.brand,
                "listing_id": str(item.listing_id) if item.listing_id else None,
                "seller_id": seller_id,
                "seller_name": seller_name,
                "is_reviewed": existing_review is not None,
                "eligible": is_eligible,
                "reason": reason,
                "review": {
                    "id": str(existing_review.id),
                    "rating": existing_review.rating,
                    "title": existing_review.title,
                    "comment": existing_review.comment,
                    "created_at": existing_review.created_at.isoformat(),
                } if existing_review else None,
            })

        order_eligible = (
            order.status != OrderStatusChoices.CANCELLED
            and (order.buyer_id == user.id or _is_staff_or_admin(user))
            and not all_reviewed
        )

        return {
            "order_id": str(order.id),
            "order_number": order.order_number,
            "eligible": order_eligible,
            "all_reviewed": all_reviewed,
            "items": items_data,
        }


class ReputationService:
    """
    Computes aggregated ratings and reputation metrics for products and sellers.
    """

    @classmethod
    def get_product_rating_summary(cls, listing: SparePartListing) -> Dict[str, Any]:
        """
        Computes average rating, count, and 1-5 star distribution for a product listing.
        Only counts APPROVED reviews.
        """
        reviews_qs = ProductReview.objects.filter(
            listing=listing,
            status=ReviewStatusChoices.APPROVED,
        )

        total_count = reviews_qs.count()
        if total_count == 0:
            return {
                "average_rating": 0.0,
                "review_count": 0,
                "verified_purchases_count": 0,
                "distribution": {
                    "5": 0,
                    "4": 0,
                    "3": 0,
                    "2": 0,
                    "1": 0,
                },
            }

        avg_rating = reviews_qs.aggregate(models.Avg('rating'))['rating__avg'] or 0.0
        verified_count = reviews_qs.filter(is_verified_purchase=True).count()

        # Distribution breakdown
        distribution = {
            "5": reviews_qs.filter(rating=5).count(),
            "4": reviews_qs.filter(rating=4).count(),
            "3": reviews_qs.filter(rating=3).count(),
            "2": reviews_qs.filter(rating=2).count(),
            "1": reviews_qs.filter(rating=1).count(),
        }

        return {
            "average_rating": round(float(avg_rating), 1),
            "review_count": total_count,
            "verified_purchases_count": verified_count,
            "distribution": distribution,
        }

    @classmethod
    def get_seller_reputation_summary(cls, seller: User) -> Dict[str, Any]:
        """
        Calculates seller reputation across both seller ratings and product reviews.
        Computes overall rating, review count, positive percentage, distribution,
        response rate, and verified purchase stats.
        """
        seller_reviews_qs = SellerReview.objects.filter(
            seller=seller,
            status=ReviewStatusChoices.APPROVED,
        )
        product_reviews_qs = ProductReview.objects.filter(
            seller=seller,
            status=ReviewStatusChoices.APPROVED,
        )

        seller_reviews_count = seller_reviews_qs.count()
        product_reviews_count = product_reviews_qs.count()
        total_count = seller_reviews_count + product_reviews_count

        # Detailed ratings breakdown
        seller_avg = seller_reviews_qs.aggregate(models.Avg('rating'))['rating__avg']
        product_avg = product_reviews_qs.aggregate(models.Avg('rating'))['rating__avg']

        if total_count == 0:
            overall_avg = 0.0
            positive_percentage = 100
            response_rate = 100
        else:
            # Combine all approved ratings
            all_ratings = list(seller_reviews_qs.values_list('rating', flat=True)) + list(product_reviews_qs.values_list('rating', flat=True))
            overall_avg = sum(all_ratings) / len(all_ratings) if all_ratings else 0.0
            positive_ratings = sum(1 for r in all_ratings if r >= 4)
            positive_percentage = round((positive_ratings / len(all_ratings)) * 100) if all_ratings else 100

            # Response rate
            replied_count = (
                seller_reviews_qs.exclude(seller_reply='').count()
                + product_reviews_qs.exclude(seller_reply='').count()
            )
            response_rate = round((replied_count / total_count) * 100) if total_count else 100

        # Distribution combining both or seller reviews
        distribution = {
            "5": seller_reviews_qs.filter(rating=5).count() + product_reviews_qs.filter(rating=5).count(),
            "4": seller_reviews_qs.filter(rating=4).count() + product_reviews_qs.filter(rating=4).count(),
            "3": seller_reviews_qs.filter(rating=3).count() + product_reviews_qs.filter(rating=3).count(),
            "2": seller_reviews_qs.filter(rating=2).count() + product_reviews_qs.filter(rating=2).count(),
            "1": seller_reviews_qs.filter(rating=1).count() + product_reviews_qs.filter(rating=1).count(),
        }

        # Sub-scores from seller reviews if present
        comm_avg = seller_reviews_qs.exclude(communication_rating__isnull=True).aggregate(models.Avg('communication_rating'))['communication_rating__avg']
        deliv_avg = seller_reviews_qs.exclude(delivery_rating__isnull=True).aggregate(models.Avg('delivery_rating'))['delivery_rating__avg']
        desc_avg = seller_reviews_qs.exclude(item_description_rating__isnull=True).aggregate(models.Avg('item_description_rating'))['item_description_rating__avg']

        verified_count = (
            seller_reviews_qs.filter(is_verified_purchase=True).count()
            + product_reviews_qs.filter(is_verified_purchase=True).count()
        )

        return {
            "seller_id": str(seller.id),
            "seller_name": seller.full_name or seller.email,
            "average_rating": round(float(overall_avg), 1),
            "seller_rating_avg": round(float(seller_avg), 1) if seller_avg is not None else round(float(overall_avg), 1),
            "product_rating_avg": round(float(product_avg), 1) if product_avg is not None else 0.0,
            "total_reviews_count": total_count,
            "seller_reviews_count": seller_reviews_count,
            "product_reviews_count": product_reviews_count,
            "positive_percentage": positive_percentage,
            "response_rate": response_rate,
            "verified_purchases_count": verified_count,
            "communication_rating_avg": round(float(comm_avg), 1) if comm_avg is not None else None,
            "delivery_rating_avg": round(float(deliv_avg), 1) if deliv_avg is not None else None,
            "item_description_rating_avg": round(float(desc_avg), 1) if desc_avg is not None else None,
            "distribution": distribution,
        }


class ReviewWorkflowService:
    """
    Orchestrates review submission, updates, replies, reports, and administrative moderation.
    """

    @classmethod
    @transaction.atomic
    def create_product_review(
        cls,
        buyer: User,
        order: Order,
        order_item: OrderItem,
        rating: int,
        comment: str,
        title: str = "",
        seller_rating: Optional[int] = None,
        seller_comment: str = "",
        actor: Optional[User] = None,
    ) -> ProductReview:
        """
        Creates a verified product review for an eligible purchase.
        Optionally creates/updates corresponding seller review for the order.
        """
        is_eligible, err_msg = ReviewEligibilityService.validate_purchase_eligibility(buyer, order, order_item)
        if not is_eligible:
            raise DjangoValidationError(err_msg)

        if not (1 <= rating <= 5):
            raise DjangoValidationError("Product rating must be an integer between 1 and 5.")

        if not comment or len(comment.strip()) < 5:
            raise DjangoValidationError("Review comment must be at least 5 characters long.")

        listing = order_item.listing
        seller = listing.seller
        org = listing.organisation

        review = ProductReview.objects.create(
            order=order,
            order_item=order_item,
            listing=listing,
            buyer=buyer,
            seller=seller,
            organisation=org,
            rating=rating,
            title=title.strip(),
            comment=comment.strip(),
            status=ReviewStatusChoices.APPROVED,
            is_verified_purchase=True,
        )

        # If seller rating is provided, record seller review for this order
        if seller_rating is not None:
            if not (1 <= seller_rating <= 5):
                raise DjangoValidationError("Seller rating must be an integer between 1 and 5.")

            SellerReview.objects.update_or_create(
                order=order,
                seller=seller,
                defaults={
                    "buyer": buyer,
                    "organisation": org,
                    "rating": seller_rating,
                    "comment": seller_comment.strip() if seller_comment else "",
                    "status": ReviewStatusChoices.APPROVED,
                    "is_verified_purchase": True,
                },
            )

        record_audit_entry(
            event_type="marketplace.product_review.created",
            action="marketplace:review.create",
            resource_type="ProductReview",
            resource_id=str(review.id),
            actor_id=buyer.id,
            operating_org_id=org.id if org else None,
            metadata={
                "review_id": str(review.id),
                "order_id": str(order.id),
                "order_number": order.order_number,
                "listing_id": str(listing.id),
                "rating": rating,
                "buyer_id": str(buyer.id),
                "seller_id": str(seller.id),
            },
        )

        return review

    @classmethod
    @transaction.atomic
    def update_product_review(
        cls,
        review: ProductReview,
        user: User,
        rating: Optional[int] = None,
        title: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> ProductReview:
        """
        Updates an existing review. Only author or staff/admin can update.
        """
        if review.buyer_id != user.id and not _is_staff_or_admin(user):
            record_denied_audit_entry(
                action="marketplace:review.update_denied",
                resource_type="ProductReview",
                resource_id=str(review.id),
                reason_code="UNAUTHORIZED",
                event_type="marketplace.product_review.update_denied",
                actor_id=user.id,
                metadata={"reason": "Only author or administrator can edit review."},
            )
            raise DjangoValidationError("You are not authorized to edit this review.")

        update_fields = ['updated_at']

        if rating is not None:
            if not (1 <= rating <= 5):
                raise DjangoValidationError("Product rating must be an integer between 1 and 5.")
            review.rating = rating
            update_fields.append('rating')

        if title is not None:
            review.title = title.strip()
            update_fields.append('title')

        if comment is not None:
            if len(comment.strip()) < 5:
                raise DjangoValidationError("Review comment must be at least 5 characters long.")
            review.comment = comment.strip()
            update_fields.append('comment')

        review.save(update_fields=update_fields)

        record_audit_entry(
            event_type="marketplace.product_review.updated",
            action="marketplace:review.update",
            resource_type="ProductReview",
            resource_id=str(review.id),
            actor_id=user.id,
            operating_org_id=review.organisation_id,
            metadata={
                "review_id": str(review.id),
                "rating": review.rating,
                "updated_by": str(user.id),
            },
        )

        return review

    @classmethod
    @transaction.atomic
    def delete_product_review(cls, review: ProductReview, user: User) -> None:
        """
        Deletes a product review. Allowed for review author or staff/admin.
        """
        if review.buyer_id != user.id and not _is_staff_or_admin(user):
            record_denied_audit_entry(
                action="marketplace:review.delete_denied",
                resource_type="ProductReview",
                resource_id=str(review.id),
                reason_code="UNAUTHORIZED",
                event_type="marketplace.product_review.delete_denied",
                actor_id=user.id,
                metadata={"reason": "Only author or administrator can delete review."},
            )
            raise DjangoValidationError("You are not authorized to delete this review.")

        review_id = str(review.id)
        org_id = review.organisation_id
        review.delete()

        record_audit_entry(
            event_type="marketplace.product_review.deleted",
            action="marketplace:review.delete",
            resource_type="ProductReview",
            resource_id=review_id,
            actor_id=user.id,
            operating_org_id=org_id,
            metadata={"review_id": review_id, "deleted_by": str(user.id)},
        )

    @classmethod
    @transaction.atomic
    def add_seller_reply(
        cls,
        review: ProductReview | SellerReview,
        user: User,
        reply: str,
    ) -> ProductReview | SellerReview:
        """
        Allows seller or seller org admin to post a merchant response.
        """
        if not _is_seller_authorized_for_review(user, review):
            record_denied_audit_entry(
                action="marketplace:review.reply_denied",
                resource_type=review.__class__.__name__,
                resource_id=str(review.id),
                reason_code="UNAUTHORIZED",
                event_type="marketplace.review_reply.denied",
                actor_id=user.id,
                metadata={"reason": "User is not authorized seller for this review."},
            )
            raise DjangoValidationError("You are not authorized to reply to this review.")

        if not reply or len(reply.strip()) < 3:
            raise DjangoValidationError("Reply must be at least 3 characters long.")

        review.seller_reply = reply.strip()
        review.seller_reply_at = timezone.now()
        review.seller_replied_by = user
        review.save(update_fields=['seller_reply', 'seller_reply_at', 'seller_replied_by', 'updated_at'])

        record_audit_entry(
            event_type=f"marketplace.{review.__class__.__name__.lower()}.replied",
            action="marketplace:review.reply",
            resource_type=review.__class__.__name__,
            resource_id=str(review.id),
            actor_id=user.id,
            operating_org_id=review.organisation_id,
            metadata={"review_id": str(review.id), "seller_id": str(user.id)},
        )

        return review

    @classmethod
    @transaction.atomic
    def report_review(
        cls,
        user: User,
        review: ProductReview | SellerReview,
        reason: str,
        details: str = "",
    ) -> ReviewReport:
        """
        Allows community members or sellers to report inappropriate reviews.
        """
        if not user or not user.is_authenticated:
            raise DjangoValidationError("Authentication required to report reviews.")

        if review.buyer_id == user.id:
            raise DjangoValidationError("You cannot report your own review.")

        if reason not in ReviewReportReasonChoices.values:
            raise DjangoValidationError(f"Invalid report reason '{reason}'.")

        # Create report record
        is_product = isinstance(review, ProductReview)
        report = ReviewReport.objects.create(
            product_review=review if is_product else None,
            seller_review=review if not is_product else None,
            reporter=user,
            reason=reason,
            details=details.strip(),
            status=ReviewReportStatusChoices.PENDING,
        )

        # Flag the review for moderation
        if review.status == ReviewStatusChoices.APPROVED:
            review.status = ReviewStatusChoices.FLAGGED
            review.save(update_fields=['status', 'updated_at'])

        record_audit_entry(
            event_type="marketplace.review_report.created",
            action="marketplace:review.report",
            resource_type="ReviewReport",
            resource_id=str(report.id),
            actor_id=user.id,
            operating_org_id=review.organisation_id,
            metadata={
                "report_id": str(report.id),
                "review_id": str(review.id),
                "reason": reason,
                "reporter_id": str(user.id),
            },
        )

        return report

    @classmethod
    @transaction.atomic
    def moderate_review(
        cls,
        review: ProductReview | SellerReview,
        admin_user: User,
        action: str,
        admin_notes: str = "",
    ) -> ProductReview | SellerReview:
        """
        Staff/Admin action to moderate a review: APPROVE, FLAG, HIDE, or DELETE.
        """
        if not _is_staff_or_admin(admin_user):
            record_denied_audit_entry(
                action="marketplace:review.moderation_denied",
                resource_type=review.__class__.__name__,
                resource_id=str(review.id),
                reason_code="ROLE_NOT_PERMITTED",
                event_type="marketplace.review_moderation.denied",
                actor_id=admin_user.id,
                metadata={"reason": "Staff or administrator role required for moderation."},
            )
            raise DjangoValidationError("Staff or administrator role required for moderation.")

        action_upper = action.upper()
        review_id = str(review.id)
        org_id = review.organisation_id

        if action_upper == "DELETE":
            review.delete()
            record_audit_entry(
                event_type="marketplace.review.moderated",
                action="marketplace:review.delete_moderation",
                resource_type=review.__class__.__name__,
                resource_id=review_id,
                actor_id=admin_user.id,
                operating_org_id=org_id,
                metadata={"action": "DELETE", "admin_notes": admin_notes},
            )
            return None

        if action_upper == "APPROVE":
            review.status = ReviewStatusChoices.APPROVED
        elif action_upper in ("HIDE", "REJECT"):
            review.status = ReviewStatusChoices.REJECTED
        elif action_upper == "FLAG":
            review.status = ReviewStatusChoices.FLAGGED
        else:
            raise DjangoValidationError(f"Invalid moderation action '{action}'. Use APPROVE, HIDE, FLAG, or DELETE.")

        review.save(update_fields=['status', 'updated_at'])

        record_audit_entry(
            event_type="marketplace.review.moderated",
            action=f"marketplace:review.{action_upper.lower()}",
            resource_type=review.__class__.__name__,
            resource_id=str(review.id),
            actor_id=admin_user.id,
            operating_org_id=org_id,
            metadata={"action": action_upper, "new_status": review.status, "admin_notes": admin_notes},
        )

        return review

    @classmethod
    @transaction.atomic
    def resolve_report(
        cls,
        report: ReviewReport,
        admin_user: User,
        action: str,
        admin_notes: str = "",
    ) -> ReviewReport:
        """
        Resolves a review report: DISMISS, HIDE_REVIEW, or DELETE_REVIEW.
        """
        if not _is_staff_or_admin(admin_user):
            record_denied_audit_entry(
                action="marketplace:review.report_resolve_denied",
                resource_type="ReviewReport",
                resource_id=str(report.id),
                reason_code="ROLE_NOT_PERMITTED",
                event_type="marketplace.review_report.resolve_denied",
                actor_id=admin_user.id,
                metadata={"reason": "Staff or administrator role required to resolve reports."},
            )
            raise DjangoValidationError("Staff or administrator role required to resolve reports.")

        target_review = report.product_review or report.seller_review
        action_upper = action.upper()

        if action_upper == "DISMISS":
            report.status = ReviewReportStatusChoices.DISMISSED
            report.action_taken = ReviewReportActionChoices.DISMISSED
            if target_review and target_review.status == ReviewStatusChoices.FLAGGED:
                target_review.status = ReviewStatusChoices.APPROVED
                target_review.save(update_fields=['status', 'updated_at'])
        elif action_upper == "HIDE_REVIEW":
            report.status = ReviewReportStatusChoices.RESOLVED
            report.action_taken = ReviewReportActionChoices.REVIEW_HIDDEN
            if target_review:
                target_review.status = ReviewStatusChoices.REJECTED
                target_review.save(update_fields=['status', 'updated_at'])
        elif action_upper == "DELETE_REVIEW":
            report.status = ReviewReportStatusChoices.RESOLVED
            report.action_taken = ReviewReportActionChoices.REVIEW_DELETED
            if target_review:
                target_review.delete()
        else:
            raise DjangoValidationError(f"Invalid report resolution action '{action}'. Use DISMISS, HIDE_REVIEW, or DELETE_REVIEW.")

        report.admin_notes = admin_notes.strip()
        report.resolved_by = admin_user
        report.resolved_at = timezone.now()
        report.save(update_fields=['status', 'action_taken', 'admin_notes', 'resolved_by', 'resolved_at', 'updated_at'])

        record_audit_entry(
            event_type="marketplace.review_report.resolved",
            action=f"marketplace:report.{action_upper.lower()}",
            resource_type="ReviewReport",
            resource_id=str(report.id),
            actor_id=admin_user.id,
            metadata={"action": action_upper, "report_id": str(report.id), "admin_notes": admin_notes},
        )

        return report

    @classmethod
    @transaction.atomic
    def vote_helpful(cls, user: User, review: ProductReview) -> Tuple[bool, int]:
        """
        Toggles or registers a helpful vote for a product review.
        Returns (has_voted, total_helpful_votes).
        """
        if not user or not user.is_authenticated:
            raise DjangoValidationError("Authentication required to vote on reviews.")

        existing = ProductReviewHelpfulVote.objects.filter(review=review, user=user).first()
        if existing:
            # Toggle off
            existing.delete()
            review.helpful_votes = max(0, review.helpful_votes - 1)
            review.save(update_fields=['helpful_votes', 'updated_at'])
            return False, review.helpful_votes
        else:
            ProductReviewHelpfulVote.objects.create(review=review, user=user)
            review.helpful_votes += 1
            review.save(update_fields=['helpful_votes', 'updated_at'])
            return True, review.helpful_votes
