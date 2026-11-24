import logging
from decimal import Decimal
from typing import Dict, Any
from django.db import transaction, models
from django.core.exceptions import (
    ValidationError as DjangoValidationError,
    PermissionDenied as DjangoPermissionDenied,
)
from rest_framework import status, views, generics, permissions
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound

from apps.identity.models import User, RoleChoices
from apps.organisations.models import (
    Organisation,
    OrganisationMembership,
    OrganisationRoleChoices,
)
from apps.marketplace.models import (
    SparePartListing,
    VehicleListing,
    DealerTier,
    DealerOrganisationProfile,
    DealerOrganisationStatusChoices,
    DealerPricingRule,
    DealerPricingRuleTypeChoices,
)
from apps.marketplace.b2b_pricing_service import (
    DealerPricingService,
    DealerEligibilityError,
    MinimumOrderQuantityError,
)
from apps.marketplace.b2b_serializers import (
    DealerTierSerializer,
    DealerOrganisationProfileSerializer,
    DealerPricingRuleSerializer,
    AssignDealerTierSerializer,
    DealerApplicationSubmitSerializer,
    DealerApplicationReviewSerializer,
    B2BQuoteRequestSerializer,
)

logger = logging.getLogger(__name__)


class IsStaffOrPricingAdmin(permissions.BasePermission):
    """Allows access to staff, superusers, or users with administrative/commercial permissions."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return (
            user.is_superuser
            or user.is_staff
            or user.has_role(RoleChoices.ADMIN)
            or user.has_role(RoleChoices.STAFF)
            or user.has_permission('commercial.manage')
        )


class DealerTierListCreateView(views.APIView):
    """
    List dealer tiers or create a new tier.
    GET: Authenticated users can list active tiers.
    POST: Administrative staff can configure new tiers.
    """

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsStaffOrPricingAdmin()]
        return [permissions.IsAuthenticated()]

    def get(self, request):
        tiers = DealerTier.objects.all().order_by('-priority', 'code')
        serializer = DealerTierSerializer(tiers, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = DealerTierSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tier = serializer.save(
            created_by=request.user,
            updated_by=request.user,
        )
        return Response(DealerTierSerializer(tier).data, status=status.HTTP_201_CREATED)


class DealerPricingRuleListCreateView(views.APIView):
    """
    List pricing rules or create a new rule.
    GET: Staff see all rules; dealers see rules applicable to their organisation.
    POST: Staff create pricing rules.
    """

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsStaffOrPricingAdmin()]
        return [permissions.IsAuthenticated()]

    def get(self, request):
        user = request.user
        is_admin = (
            user.is_superuser
            or user.is_staff
            or user.has_role(RoleChoices.ADMIN)
            or user.has_role(RoleChoices.STAFF)
        )

        queryset = DealerPricingRule.objects.all().select_related(
            'organisation', 'dealer_tier', 'part_listing', 'vehicle_listing', 'category'
        )

        if not is_admin:
            # Dealer user: filter to rules matching their organisation or tier
            is_eligible, _, org, profile, tier = DealerPricingService.evaluate_dealer_eligibility(user=user)
            if not is_eligible or not org:
                return Response([], status=status.HTTP_200_OK)

            q_filter = models.Q(organisation=org)
            if tier:
                q_filter |= models.Q(dealer_tier=tier)
            q_filter |= models.Q(organisation__isnull=True, dealer_tier__isnull=True)
            queryset = queryset.filter(q_filter, is_active=True)
        else:
            # Staff filters
            org_id = request.query_params.get('organisation_id')
            tier_id = request.query_params.get('tier_id')
            active_param = request.query_params.get('is_active')
            part_id = request.query_params.get('part_listing_id')

            if org_id:
                queryset = queryset.filter(organisation_id=org_id)
            if tier_id:
                queryset = queryset.filter(dealer_tier_id=tier_id)
            if active_param is not None:
                is_act = active_param.lower() in ('true', '1')
                queryset = queryset.filter(is_active=is_act)
            if part_id:
                queryset = queryset.filter(part_listing_id=part_id)

        serializer = DealerPricingRuleSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = DealerPricingRuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = DealerPricingService.create_pricing_rule(
            data=serializer.validated_data,
            actor=request.user,
        )
        return Response(DealerPricingRuleSerializer(rule).data, status=status.HTTP_201_CREATED)


class DealerPricingRuleDetailView(views.APIView):
    """
    Retrieve, update, or deactivate a pricing rule.
    GET: Authenticated dealers / staff.
    PATCH/DELETE: Administrative staff only.
    """

    def get_permissions(self):
        if self.request.method in ('PATCH', 'DELETE'):
            return [IsStaffOrPricingAdmin()]
        return [permissions.IsAuthenticated()]

    def get_object(self, pk):
        rule = DealerPricingRule.objects.filter(pk=pk).select_related(
            'organisation', 'dealer_tier', 'part_listing', 'vehicle_listing', 'category'
        ).first()
        if not rule:
            raise NotFound("Dealer pricing rule not found.")
        return rule

    def get(self, request, pk):
        rule = self.get_object(pk)
        user = request.user
        is_admin = (
            user.is_superuser
            or user.is_staff
            or user.has_role(RoleChoices.ADMIN)
            or user.has_role(RoleChoices.STAFF)
        )
        if not is_admin:
            is_eligible, _, org, profile, tier = DealerPricingService.evaluate_dealer_eligibility(user=user)
            if not is_eligible or not org:
                raise PermissionDenied("You do not have permission to view this pricing rule.")
            if rule.organisation and rule.organisation_id != org.id:
                raise PermissionDenied("You do not have permission to view another organisation's pricing rule.")
            if rule.dealer_tier and (not tier or rule.dealer_tier_id != tier.id):
                raise PermissionDenied("You do not have permission to view this tier's pricing rule.")
        return Response(DealerPricingRuleSerializer(rule).data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        rule = self.get_object(pk)
        serializer = DealerPricingRuleSerializer(rule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_rule = DealerPricingService.update_pricing_rule(
            rule=rule,
            data=serializer.validated_data,
            actor=request.user,
        )
        return Response(DealerPricingRuleSerializer(updated_rule).data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        rule = self.get_object(pk)
        DealerPricingService.update_pricing_rule(
            rule=rule,
            data={'is_active': False},
            actor=request.user,
        )
        return Response({"status": "success", "message": "Rule successfully deactivated."}, status=status.HTTP_200_OK)


class DealerEligibilityStatusView(views.APIView):
    """
    Returns the requesting user's B2B dealer standing, tier, and discount privileges.
    GET /api/v1/marketplace/b2b/dealer-status/
    Optional ?organisation_id=<uuid>
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org_id = request.query_params.get('organisation_id')
        is_eligible, reason, org, profile, tier = DealerPricingService.evaluate_dealer_eligibility(
            user=request.user,
            organisation_id=org_id,
        )

        return Response({
            "is_eligible": is_eligible,
            "ineligibility_reason": reason,
            "organisation": {
                "id": str(org.id) if org else None,
                "name": org.name if org else None,
                "type": org.type if org else None,
                "country": org.country if org else None,
                "is_active": org.is_active if org else False,
            } if org else None,
            "profile": {
                "is_verified_dealer": profile.is_verified_dealer if profile else False,
                "status": profile.status if profile else None,
                "custom_discount_cap": str(profile.custom_discount_cap) if profile and profile.custom_discount_cap else None,
                "notes": profile.notes if profile else "",
            } if profile else None,
            "tier": {
                "id": str(tier.id) if tier else None,
                "code": tier.code if tier else None,
                "name": tier.name if tier else None,
                "default_discount_percentage": str(tier.default_discount_percentage) if tier else "0.00",
                "priority": tier.priority if tier else 0,
            } if tier else None,
        }, status=status.HTTP_200_OK)


class DealerOrganisationTierAssignView(views.APIView):
    """
    Assigns or updates the dealer tier and status for an organisation.
    POST /api/v1/marketplace/b2b/organisations/<id>/tier/
    Administrative staff only.
    """
    permission_classes = [IsStaffOrPricingAdmin]

    def post(self, request, pk):
        org = Organisation.objects.filter(pk=pk).first()
        if not org:
            return Response({"error": f"Organisation '{pk}' not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AssignDealerTierSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        profile = DealerPricingService.assign_dealer_tier(
            organisation=org,
            tier_code=data['tier_code'],
            actor=request.user,
            notes=data.get('notes', ''),
            status=data.get('status', 'ACTIVE'),
            is_verified=data.get('is_verified', True),
            custom_discount_cap=data.get('custom_discount_cap'),
        )

        return Response(DealerOrganisationProfileSerializer(profile).data, status=status.HTTP_200_OK)


class B2BPriceQuoteView(views.APIView):
    """
    Calculates verified B2B dealer price quotes for a list of items and quantities.
    POST /api/v1/marketplace/b2b/quote/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = B2BQuoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        items_input = data['items']
        org_id = data.get('organisation_id')
        currency = data.get('currency')
        shipping_country = data.get('shipping_country')

        # Check eligibility
        is_eligible, reason, org, profile, tier = DealerPricingService.evaluate_dealer_eligibility(
            user=request.user,
            organisation_id=org_id,
        )

        calculated_items = []
        retail_subtotal = Decimal('0.00')
        dealer_subtotal = Decimal('0.00')
        total_discount_savings = Decimal('0.00')
        moq_errors = []

        for item_data in items_input:
            listing_id = item_data['listing_id']
            qty = item_data['quantity']

            listing = SparePartListing.objects.filter(id=listing_id, is_active=True).first()
            if not listing:
                listing = VehicleListing.objects.filter(id=listing_id, is_active=True).first()

            if not listing:
                return Response(
                    {"error": f"Listing '{listing_id}' not found or inactive."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            pricing = DealerPricingService.calculate_item_price(
                listing=listing,
                quantity=qty,
                user=request.user,
                organisation_id=org_id,
                destination_currency=currency,
                destination_country=shipping_country,
            )

            line_retail_subtotal = pricing['retail_unit_price'] * qty
            line_dealer_subtotal = pricing['dealer_unit_price'] * qty
            retail_subtotal += line_retail_subtotal
            dealer_subtotal += line_dealer_subtotal
            total_discount_savings += pricing['total_discount_amount']

            if not pricing['moq_satisfied']:
                moq_errors.append(
                    f"Item '{getattr(listing, 'name', getattr(listing, 'title', ''))}' requires a minimum quantity of {pricing['minimum_order_quantity']} (requested: {qty})."
                )

            calculated_items.append({
                "listing_id": str(listing.id),
                "title": getattr(listing, 'name', getattr(listing, 'title', '')),
                "quantity": qty,
                "retail_unit_price": str(pricing['retail_unit_price']),
                "dealer_unit_price": str(pricing['dealer_unit_price']),
                "discount_amount_per_unit": str(pricing['discount_amount_per_unit']),
                "total_discount_amount": str(pricing['total_discount_amount']),
                "discount_percentage": str(pricing['discount_percentage']),
                "is_dealer_pricing_applied": pricing['is_dealer_pricing_applied'],
                "applied_tier": pricing['applied_tier'],
                "applied_rule_id": pricing['applied_rule_id'],
                "applied_rule_name": pricing['applied_rule_name'],
                "precedence_level": pricing['precedence_level'],
                "minimum_order_quantity": pricing['minimum_order_quantity'],
                "moq_satisfied": pricing['moq_satisfied'],
                "currency": pricing['currency'],
            })

        return Response({
            "is_dealer_eligible": is_eligible,
            "ineligibility_reason": reason,
            "applied_tier": tier.code if tier else None,
            "applied_tier_name": tier.name if tier else None,
            "organisation_id": str(org.id) if org else None,
            "organisation_name": org.name if org else None,
            "retail_subtotal": str(retail_subtotal),
            "dealer_subtotal": str(dealer_subtotal),
            "total_discount_savings": str(total_discount_savings),
            "currency": calculated_items[0]["currency"] if calculated_items else (currency or "GBP"),
            "items": calculated_items,
            "has_moq_violations": len(moq_errors) > 0,
            "moq_errors": moq_errors,
        }, status=status.HTTP_200_OK)


class ListingVolumeDiscountsView(views.APIView):
    """
    Returns configured quantity breaks and volume discount rate cards for a listing.
    GET /api/v1/marketplace/b2b/listings/<id>/volume-discounts/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        listing = SparePartListing.objects.filter(pk=pk).first()
        if not listing:
            listing = VehicleListing.objects.filter(pk=pk).first()
        if not listing:
            return Response({"error": "Listing not found."}, status=status.HTTP_404_NOT_FOUND)

        org_id = request.query_params.get('organisation_id')
        currency = request.query_params.get('currency')
        country = request.query_params.get('country')

        schedule = DealerPricingService.get_listing_volume_discount_schedule(
            listing=listing,
            user=request.user if request.user and request.user.is_authenticated else None,
            organisation_id=org_id,
            destination_currency=currency,
            destination_country=country,
        )

        return Response({
            "listing_id": str(listing.id),
            "title": getattr(listing, 'name', getattr(listing, 'title', '')),
            "volume_discount_schedule": schedule,
        }, status=status.HTTP_200_OK)


class DealerApplicationSubmitView(views.APIView):
    """
    Submit or list dealer verification applications.
    POST: Organisation OWNER or ADMIN submits dealer verification request.
    GET: Current user's organisation applications (or staff view).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        is_admin = (
            user.is_superuser
            or user.is_staff
            or user.has_role(RoleChoices.ADMIN)
            or user.has_role(RoleChoices.STAFF)
        )
        if is_admin:
            status_param = request.query_params.get('status')
            queryset = DealerOrganisationProfile.objects.all().select_related('organisation', 'tier', 'verified_by')
            if status_param and status_param.upper() != 'ALL':
                queryset = queryset.filter(status=status_param.upper())
            serializer = DealerOrganisationProfileSerializer(queryset, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # Non-staff: return applications for organisations the user belongs to
        user_org_ids = user.organisation_memberships.filter(
            is_active=True,
            role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN, OrganisationRoleChoices.MEMBER],
        ).values_list('organisation_id', flat=True)

        profiles = DealerOrganisationProfile.objects.filter(
            organisation_id__in=user_org_ids
        ).select_related('organisation', 'tier', 'verified_by')
        serializer = DealerOrganisationProfileSerializer(profiles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = DealerApplicationSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        org_id = data.get('organisation_id')
        target_org = None
        if org_id:
            target_org = Organisation.objects.filter(pk=org_id, is_active=True).first()
            if not target_org:
                return Response(
                    {"error": f"Organisation '{org_id}' not found or inactive."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            # Resolve primary organisation of user
            membership = request.user.organisation_memberships.filter(
                is_active=True,
                role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
            ).select_related('organisation').first()
            if membership:
                target_org = membership.organisation

        if not target_org:
            return Response(
                {"error": "No eligible active organisation specified or found for this account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile = DealerPricingService.request_dealer_verification(
                organisation=target_org,
                applicant=request.user,
                business_data=data,
            )
        except DjangoValidationError as exc:
            msg = exc.message_dict if hasattr(exc, 'message_dict') else (exc.messages[0] if hasattr(exc, 'messages') else str(exc))
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except (PermissionDenied, DjangoPermissionDenied) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        return Response(
            DealerOrganisationProfileSerializer(profile).data,
            status=status.HTTP_201_CREATED,
        )


class DealerApplicationMeView(views.APIView):
    """
    Returns the current user's organisation's dealer verification status and application detail.
    GET /api/v1/marketplace/b2b/applications/me/
    Optional ?organisation_id=<uuid>
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org_id = request.query_params.get('organisation_id')
        user = request.user
        target_org = None

        if org_id:
            target_org = Organisation.objects.filter(pk=org_id).first()
            if not target_org:
                return Response({"error": "Organisation not found."}, status=status.HTTP_404_NOT_FOUND)
            if not (user.is_superuser or user.is_staff or target_org.is_member(user)):
                raise PermissionDenied("You do not have access to view this organisation's application.")
        else:
            membership = user.organisation_memberships.filter(is_active=True).select_related('organisation').first()
            if membership:
                target_org = membership.organisation

        if not target_org:
            return Response({
                "has_application": False,
                "application": None,
                "message": "No organisation associated with your account.",
            }, status=status.HTTP_200_OK)

        profile = getattr(target_org, 'dealer_profile', None)
        if not profile:
            profile = DealerOrganisationProfile.objects.filter(organisation=target_org).select_related('tier', 'verified_by').first()

        if not profile:
            return Response({
                "has_application": False,
                "organisation_id": str(target_org.id),
                "organisation_name": target_org.name,
                "application": None,
            }, status=status.HTTP_200_OK)

        return Response({
            "has_application": True,
            "organisation_id": str(target_org.id),
            "organisation_name": target_org.name,
            "application": DealerOrganisationProfileSerializer(profile).data,
        }, status=status.HTTP_200_OK)


class AdminDealerApplicationListView(views.APIView):
    """
    Platform admin list of dealer verification applications.
    GET /api/v1/marketplace/b2b/admin/applications/
    Filters: ?status=PENDING, ?search=
    """
    permission_classes = [IsStaffOrPricingAdmin]

    def get(self, request):
        status_param = request.query_params.get('status', 'PENDING')
        search_query = request.query_params.get('search', '').strip()

        queryset = DealerOrganisationProfile.objects.all().select_related(
            'organisation', 'tier', 'verified_by'
        ).order_by('-updated_at')

        if status_param and status_param.upper() != 'ALL':
            queryset = queryset.filter(status=status_param.upper())

        if search_query:
            queryset = queryset.filter(
                models.Q(organisation__name__icontains=search_query) |
                models.Q(organisation__slug__icontains=search_query)
            )

        serializer = DealerOrganisationProfileSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminDealerApplicationDetailView(views.APIView):
    """
    Platform admin view of specific dealer application.
    GET /api/v1/marketplace/b2b/admin/applications/<uuid:pk>/
    """
    permission_classes = [IsStaffOrPricingAdmin]

    def get(self, request, pk):
        profile = DealerOrganisationProfile.objects.filter(pk=pk).select_related(
            'organisation', 'tier', 'verified_by'
        ).first()
        if not profile:
            # Also support querying by organisation_id
            profile = DealerOrganisationProfile.objects.filter(organisation_id=pk).select_related(
                'organisation', 'tier', 'verified_by'
            ).first()

        if not profile:
            raise NotFound("Dealer application profile not found.")

        return Response(DealerOrganisationProfileSerializer(profile).data, status=status.HTTP_200_OK)


class AdminDealerApplicationReviewView(views.APIView):
    """
    Platform admin endpoint to approve or reject a dealer application.
    POST /api/v1/marketplace/b2b/admin/applications/<uuid:pk>/review/
    """
    permission_classes = [IsStaffOrPricingAdmin]

    def post(self, request, pk):
        profile = DealerOrganisationProfile.objects.filter(pk=pk).select_related(
            'organisation', 'tier'
        ).first()
        if not profile:
            profile = DealerOrganisationProfile.objects.filter(organisation_id=pk).select_related(
                'organisation', 'tier'
            ).first()

        if not profile:
            raise NotFound("Dealer application profile not found.")

        serializer = DealerApplicationReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            reviewed_profile = DealerPricingService.review_dealer_application(
                profile=profile,
                reviewer=request.user,
                action=data['action'],
                rejection_reason=data.get('rejection_reason', ''),
                tier_code=data.get('tier_code', 'STANDARD'),
                admin_notes=data.get('admin_notes', ''),
                custom_discount_cap=data.get('custom_discount_cap'),
            )
        except DjangoValidationError as exc:
            msg = exc.message_dict if hasattr(exc, 'message_dict') else (exc.messages[0] if hasattr(exc, 'messages') else str(exc))
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except (PermissionDenied, DjangoPermissionDenied) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        return Response(
            DealerOrganisationProfileSerializer(reviewed_profile).data,
            status=status.HTTP_200_OK,
        )
