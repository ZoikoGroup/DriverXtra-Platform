import os
import uuid
from django.conf import settings
from django.core.files.storage import default_storage
from rest_framework import generics, permissions, status, views
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.exceptions import (
    PermissionDenied,
    ValidationError as DRFValidationError,
    NotAuthenticated,
    NotFound,
)
from django.http import Http404
from django.db import models, transaction
from django.db.models import (
    Q, F, Count, Case, When, Value, IntegerField, TextField, Exists, OuterRef,
)
from django.db.models.functions import Cast
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.pagination import PageNumberPagination
from common.permissions import IsPlatformStaff, HasPermission
from platform_core.audit.writer import record_audit_entry, record_denied_audit_entry
from apps.catalogue.models import Part, PartCompatibility, FitmentTypeChoices
from apps.garage.models import GarageVehicle
from apps.marketplace.fitment import (
    get_conflicting_variants,
    batch_evaluate_listings_fitment,
    evaluate_listing_single_variant,
)
from apps.marketplace.models import (
    VehicleListing,
    SparePartListing,
    ListingStatusChoices,
    StockMovementReasonChoices,
    PartConditionChoices,
    BuyerFavouriteVehicle,
    BuyerFavouritePart,
    VehicleEnquiry,
    VehicleEnquiryStatusChoices,
    Order,
    OrderItem,
    OrderStatusChoices,
    PaymentMethodChoices,
    PaymentStatusChoices,
    CODCollectionStatusChoices,
    PaymentTransaction,
    PaymentWebhookEvent,
    Shipment,
    ShipmentItem,
    TrackingEvent,
    CarrierChoices,
    ShipmentStatusChoices,
)
from apps.organisations.models import OrganisationMembership, OrganisationRoleChoices
from apps.marketplace.serializers import (
    VehicleListingSellerSerializer,
    SparePartListingSellerSerializer,
    VehicleListingPublicSerializer,
    SparePartListingPublicSerializer,
    CataloguePartOfferSerializer,
    PriceChangeSerializer,
    AdminPartListingReviewSerializer,
    ListingReviewSerializer,
    StockMovementSerializer,
    StockAdjustmentSerializer,
    BuyerFavouriteVehicleSerializer,
    BuyerFavouritePartSerializer,
    VehicleEnquiryCreateSerializer,
    VehicleEnquirySellerSerializer,
    VehicleEnquiryBuyerSerializer,
    VehicleEnquiryStatusUpdateSerializer,
    OrderSerializer,
    SellerOrderSerializer,
    CheckoutPayloadSerializer,
    PaymentVerifyPayloadSerializer,
    CODCollectionUpdateSerializer,
    ShipmentSerializer,
    ShipmentCreatePayloadSerializer,
    ShipmentStatusUpdatePayloadSerializer,
    TrackingEventCreatePayloadSerializer,
    TrackingEventSerializer,
)
from apps.marketplace.services import adjust_stock, change_price
from apps.marketplace.payments import PaymentService
from apps.marketplace.logistics import ShipmentService, get_available_carriers_for_country



class IsSellerOrStaff(permissions.BasePermission):
    """Permits access to authenticated users with SELLER, WORKSHOP, STAFF, or ADMIN roles."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return (
            user.is_staff
            or user.is_superuser
            or user.has_role('SELLER')
            or user.has_role('WORKSHOP')
            or user.has_role('ADMIN')
            or user.has_role('STAFF')
        )


class IsBuyer(permissions.BasePermission):
    """Allows access to authenticated users holding the BUYER role (or platform admins)."""
    message = "You must have a Buyer account to access favourite vehicles."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return (
            user.is_superuser
            or user.has_role('ADMIN')
            or user.has_role('MARKETPLACE_ADMIN')
            or user.has_role('BUYER')
        )



# =====================================================================
# 1. Buyer Browse & Search APIs (Approved, Active Inventory Only)
# =====================================================================

class MarketplaceVehicleListView(generics.ListAPIView):
    """Public / Buyer endpoint to search and browse approved vehicles for sale.

    GET /api/v1/marketplace/browse/vehicles/
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = VehicleListingPublicSerializer

    def get_queryset(self):
        queryset = VehicleListing.objects.filter(
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        ).select_related('make', 'model', 'variant', 'seller', 'organisation')

        params = self.request.query_params

        make = params.get('make') or params.get('make_id')
        if make:
            queryset = queryset.filter(Q(make__name__iexact=make) | Q(make_id=make))

        model = params.get('model') or params.get('model_id')
        if model:
            queryset = queryset.filter(Q(model__name__iexact=model) | Q(model_id=model))

        year = params.get('year')
        if year:
            queryset = queryset.filter(year=year)
        year_min = params.get('year_min')
        if year_min:
            queryset = queryset.filter(year__gte=year_min)
        year_max = params.get('year_max')
        if year_max:
            queryset = queryset.filter(year__lte=year_max)

        fuel_type = params.get('fuel_type')
        if fuel_type:
            queryset = queryset.filter(fuel_type__iexact=fuel_type)

        transmission = params.get('transmission')
        if transmission:
            queryset = queryset.filter(transmission__iexact=transmission)

        price_min = params.get('price_min')
        if price_min:
            queryset = queryset.filter(price__gte=price_min)
        price_max = params.get('price_max')
        if price_max:
            queryset = queryset.filter(price__lte=price_max)

        location = params.get('location')
        if location:
            queryset = queryset.filter(
                Q(location_city__icontains=location) | Q(location_postcode__icontains=location)
            )

        search = params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(make__name__icontains=search)
                | Q(model__name__icontains=search)
                | Q(description__icontains=search)
            )

        return queryset


class MarketplaceVehicleDetailView(generics.RetrieveAPIView):
    """Public / Buyer endpoint to view full details of an approved vehicle for sale.

    GET /api/v1/marketplace/browse/vehicles/<id>/
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = VehicleListingPublicSerializer
    lookup_field = 'id'

    def get_queryset(self):
        return VehicleListing.objects.filter(
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        ).select_related('make', 'model', 'variant', 'seller', 'organisation')


class MarketplacePartPagination(PageNumberPagination):
    """Custom pagination for spare parts browse supporting page_size up to 50."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50

    def get_page_size(self, request):
        if self.page_size_query_param:
            val = request.query_params.get(self.page_size_query_param)
            if val is not None:
                try:
                    val_int = int(val)
                except (ValueError, TypeError):
                    raise DRFValidationError({"page_size": "Page size must be a positive integer."})
                if val_int < 1:
                    raise DRFValidationError({"page_size": "Page size must be a positive integer."})
                if val_int > self.max_page_size:
                    return self.max_page_size
                return val_int
        return self.page_size


class MarketplacePartListView(generics.ListAPIView):
    """Public / Buyer endpoint to search and browse approved spare parts for sale.

    GET /api/v1/marketplace/browse/parts/
    Optional ?fits_vehicle=<garage_vehicle_id> annotates results with fitment evaluation.
    Optional ?fits_only=true filters to only verified/conditional fitments.
    Optional ?sort=newest|price_asc|price_desc|relevance (default: newest).
    Optional ?condition=NEW,USED,REFURBISHED.
    Optional ?in_stock=true|false.
    Optional ?include_facets=true.
    Optional ?page=<int>&page_size=<int>.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = SparePartListingPublicSerializer
    pagination_class = MarketplacePartPagination

    def get_queryset(self):
        queryset = SparePartListing.objects.filter(
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        ).select_related('category', 'seller', 'organisation', 'catalogue_part').prefetch_related('compatible_variants')

        params = self.request.query_params

        # 1. Category filter
        category = params.get('category') or params.get('category_id')
        category_slug = params.get('category_slug')
        if category:
            queryset = queryset.filter(Q(category_id=category) | Q(category__parent_id=category))
        elif category_slug:
            queryset = queryset.filter(
                Q(category__slug=category_slug) | Q(category__parent__slug=category_slug)
            )

        # 2. Brand filter
        brand = params.get('brand')
        if brand:
            queryset = queryset.filter(brand__iexact=brand)

        # 3. MPN filter
        mpn = params.get('mpn')
        if mpn:
            queryset = queryset.filter(mpn__icontains=mpn)

        # 4. Price filters
        price_min = params.get('price_min')
        if price_min:
            queryset = queryset.filter(price__gte=price_min)
        price_max = params.get('price_max')
        if price_max:
            queryset = queryset.filter(price__lte=price_max)

        # 5. Variant ID filter
        variant_id = params.get('variant_id') or params.get('vehicle_variant_id')
        if variant_id:
            queryset = queryset.filter(compatible_variants__id=variant_id)

        # 6. Condition filter (Part D: accepts comma-separated multiple, validates choices)
        condition_param = params.get('condition')
        if condition_param:
            valid_conditions = set(PartConditionChoices.values)
            raw_conds = [c.strip().upper() for c in condition_param.split(',') if c.strip()]
            if not raw_conds or any(c not in valid_conditions for c in raw_conds):
                valid_str = ', '.join(sorted(valid_conditions))
                raise DRFValidationError({"condition": f"Invalid condition choice. Must be one of: {valid_str}."})
            queryset = queryset.filter(condition__in=raw_conds)

        # 7. In-Stock filter (Part D: true/false boolean string, true filters stock_quantity > 0)
        in_stock_param = params.get('in_stock')
        if in_stock_param is not None:
            val = in_stock_param.strip().lower()
            if val in ('true', '1'):
                queryset = queryset.filter(stock_quantity__gt=0)
            elif val in ('false', '0'):
                pass
            else:
                raise DRFValidationError({"in_stock": "Invalid in_stock value. Must be 'true' or 'false'."})

        # 8. Sort parameter validation
        sort = params.get('sort', 'newest')
        if sort not in ('newest', 'price_asc', 'price_desc', 'relevance'):
            raise DRFValidationError({"sort": f"Invalid sort option '{sort}'. Must be one of: newest, price_asc, price_desc, relevance."})

        # 9. fits_vehicle and fits_only handling
        fits_vehicle = params.get('fits_vehicle')
        fits_only_param = params.get('fits_only')
        fits_only = False
        if fits_only_param is not None:
            val = fits_only_param.strip().lower()
            if val in ('true', '1'):
                fits_only = True
                if not fits_vehicle:
                    raise DRFValidationError({"fits_only": "fits_only filter requires fits_vehicle parameter."})
            elif val in ('false', '0'):
                fits_only = False
            else:
                raise DRFValidationError({"fits_only": "Invalid fits_only value. Must be 'true' or 'false'."})

        target_variant = None
        no_variant = False
        if fits_vehicle:
            user = self.request.user
            if not (user and user.is_authenticated):
                raise NotAuthenticated("Authentication credentials were not provided.")
            try:
                v_uuid = uuid.UUID(str(fits_vehicle))
            except (ValueError, AttributeError, TypeError):
                raise DRFValidationError({"fits_vehicle": "Invalid vehicle UUID format."})

            garage_vehicle = GarageVehicle.objects.filter(
                id=v_uuid,
                user=user,
                is_archived=False,
            ).select_related('vehicle_variant').first()
            if not garage_vehicle:
                raise NotFound("Garage vehicle not found.")

            if garage_vehicle.vehicle_variant:
                target_variant = garage_vehicle.vehicle_variant
            else:
                no_variant = True

            self._cached_fits_vehicle = fits_vehicle
            self._cached_target_variant = target_variant
            self._cached_no_variant = no_variant

            if fits_only:
                if no_variant or target_variant is None:
                    queryset = queryset.none()
                else:
                    compat_match = PartCompatibility.objects.filter(
                        part_id=OuterRef('catalogue_part_id'),
                        vehicle_variant_id=target_variant.id,
                        fitment_type__in=[FitmentTypeChoices.CONFIRMED_FIT, FitmentTypeChoices.CONDITIONAL_FIT],
                    )
                    any_compat = PartCompatibility.objects.filter(
                        part_id=OuterRef('catalogue_part_id'),
                        vehicle_variant_id=target_variant.id,
                    )
                    fits_predicate = Q(catalogue_part__isnull=False) & (
                        Q(Exists(compat_match)) |
                        (Q(catalogue_part__is_universal=True) & ~Q(Exists(any_compat)))
                    )
                    queryset = queryset.filter(fits_predicate)

        # 10. Search & Relevance
        search = params.get('search', '').strip()
        queryset = queryset.annotate(oem_text=Cast('oem_numbers', output_field=TextField()))

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(brand__icontains=search)
                | Q(mpn__icontains=search)
                | Q(description__icontains=search)
                | Q(oem_text__icontains=search)
            )

        if sort == 'relevance':
            if search:
                # Portable relevance ranking weights:
                # 1. Exact MPN match: 100 points
                # 2. Exact OEM cross reference match: 90 points
                # 3. MPN prefix match (starts with search query): 60 points
                # 4. Brand exact match: 40 points
                # 5. Name contains: 25 points
                # 6. Brand contains: 15 points
                # 7. Description contains: 5 points
                relevance_score = Case(
                    When(mpn__iexact=search, then=Value(100)),
                    When(oem_text__icontains=search, then=Value(90)),
                    When(mpn__istartswith=search, then=Value(60)),
                    When(brand__iexact=search, then=Value(40)),
                    When(name__icontains=search, then=Value(25)),
                    When(brand__icontains=search, then=Value(15)),
                    When(description__icontains=search, then=Value(5)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
                queryset = queryset.annotate(relevance_score=relevance_score).order_by('-relevance_score', '-created_at', 'id')
            else:
                queryset = queryset.order_by('-created_at', 'id')
        elif sort == 'price_asc':
            queryset = queryset.order_by('price', '-created_at', 'id')
        elif sort == 'price_desc':
            queryset = queryset.order_by('-price', '-created_at', 'id')
        else:  # newest
            queryset = queryset.order_by('-created_at', 'id')

        return queryset.distinct()

    def _compute_facets(self, queryset):
        base_qs = queryset.order_by()
        brands = list(
            base_qs.values('brand')
            .annotate(count=Count('id', distinct=True))
            .order_by('-count', 'brand')
        )
        categories = [
            {
                'id': str(c['category__id']),
                'name': c['category__name'],
                'slug': c['category__slug'],
                'count': c['count'],
            }
            for c in base_qs.values('category__id', 'category__name', 'category__slug')
            .annotate(count=Count('id', distinct=True))
            .order_by('-count', 'category__name')
            if c['category__id'] is not None
        ]
        conditions = list(
            base_qs.values('condition')
            .annotate(count=Count('id', distinct=True))
            .order_by('-count', 'condition')
        )
        return {
            'brands': brands,
            'categories': categories,
            'conditions': conditions,
        }

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Compute facets over full filtered queryset before pagination if requested
        facets_data = None
        include_facets = request.query_params.get('include_facets', '').strip().lower()
        if include_facets in ('true', '1'):
            facets_data = self._compute_facets(queryset)

        page = self.paginate_queryset(queryset)
        listings_to_evaluate = page if page is not None else list(queryset)

        fits_vehicle = getattr(self, '_cached_fits_vehicle', None)
        target_variant = getattr(self, '_cached_target_variant', None)
        no_variant = getattr(self, '_cached_no_variant', False)

        if fits_vehicle and target_variant and listings_to_evaluate:
            eval_map = batch_evaluate_listings_fitment(listings_to_evaluate, target_variant)
            for listing in listings_to_evaluate:
                listing._annotated_fitment = eval_map.get(listing.id)

        serializer_context = self.get_serializer_context()
        if fits_vehicle:
            serializer_context['fits_vehicle'] = True
            serializer_context['fits_vehicle_variant'] = target_variant
            serializer_context['fits_vehicle_no_variant'] = no_variant

        if page is not None:
            serializer = self.get_serializer(page, many=True, context=serializer_context)
            response = self.get_paginated_response(serializer.data)
            if facets_data is not None:
                response.data['facets'] = facets_data
            return response

        serializer = self.get_serializer(queryset, many=True, context=serializer_context)
        response_data = {'results': serializer.data}
        if facets_data is not None:
            response_data['facets'] = facets_data
        return Response(response_data)


class MarketplacePartDetailView(generics.RetrieveAPIView):
    """Public / Buyer endpoint to view full details of an approved spare part for sale.

    GET /api/v1/marketplace/browse/parts/<id>/
    Optional ?fits_vehicle=<garage_vehicle_id> annotates response with fitment evaluation.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = SparePartListingPublicSerializer
    lookup_field = 'id'

    def get_queryset(self):
        return SparePartListing.objects.filter(
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        ).select_related('category', 'seller', 'organisation', 'catalogue_part').prefetch_related('compatible_variants')

    def retrieve(self, request, *args, **kwargs):
        fits_vehicle = request.query_params.get('fits_vehicle')
        target_variant = None
        no_variant = False

        if fits_vehicle:
            if not (request.user and request.user.is_authenticated):
                raise NotAuthenticated("Authentication credentials were not provided.")
            try:
                v_uuid = uuid.UUID(str(fits_vehicle))
            except (ValueError, AttributeError, TypeError):
                raise DRFValidationError({"fits_vehicle": "Invalid vehicle UUID format."})

            garage_vehicle = GarageVehicle.objects.filter(
                id=v_uuid,
                user=request.user,
                is_archived=False,
            ).select_related('vehicle_variant').first()
            if not garage_vehicle:
                raise NotFound("Garage vehicle not found.")

            if garage_vehicle.vehicle_variant:
                target_variant = garage_vehicle.vehicle_variant
            else:
                no_variant = True

        instance = self.get_object()
        serializer_context = self.get_serializer_context()
        if fits_vehicle:
            serializer_context['fits_vehicle'] = True
            serializer_context['fits_vehicle_variant'] = target_variant
            serializer_context['fits_vehicle_no_variant'] = no_variant

        serializer = self.get_serializer(instance, context=serializer_context)
        return Response(serializer.data)


class CataloguePartOffersView(generics.ListAPIView):
    """Public endpoint to list approved marketplace offers for a specific canonical catalogue part.

    GET /api/v1/marketplace/browse/parts/catalogue/<catalogue_part_id>/offers/
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = CataloguePartOfferSerializer

    def get_queryset(self):
        catalogue_part_id = self.kwargs.get('catalogue_part_id')
        part = Part.objects.filter(id=catalogue_part_id, is_active=True).first()
        if not part:
            raise Http404("Catalogue part not found or inactive.")

        return SparePartListing.objects.filter(
            catalogue_part=part,
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        ).select_related('seller', 'organisation').order_by('price', '-created_at')


# =====================================================================
# 2. Seller Inventory Management APIs (Add, List, Edit, Resubmit)
# =====================================================================

class SellerVehicleListCreateView(generics.ListCreateAPIView):
    """Seller endpoint to view own submitted vehicles or submit a new vehicle for approval.

    GET /api/v1/marketplace/vehicles/
    POST /api/v1/marketplace/vehicles/
    """
    permission_classes = [IsSellerOrStaff]
    serializer_class = VehicleListingSellerSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = VehicleListing.objects.filter(is_active=True).select_related(
            'make', 'model', 'variant', 'seller', 'organisation'
        )
        if not (user.is_staff or user.has_role('ADMIN')):
            # Restrict to listings owned by user or their active organisation
            queryset = queryset.filter(
                Q(seller=user) | Q(organisation__memberships__user=user, organisation__memberships__is_active=True)
            ).distinct()

        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param.upper())

        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        org = serializer.validated_data.get('organisation')
        if org:
            if not (user.is_staff or user.has_role('ADMIN')):
                member_role = org.get_member_role(user)
                if member_role not in ('OWNER', 'ADMIN'):
                    raise PermissionDenied("Only organisation OWNER or ADMIN may create listings for this organisation.")

        # Default to PENDING_APPROVAL unless explicitly requested as DRAFT
        initial_status = ListingStatusChoices.PENDING_APPROVAL
        if self.request.data.get('status') == ListingStatusChoices.DRAFT:
            initial_status = ListingStatusChoices.DRAFT

        serializer.save(
            seller=user,
            status=initial_status,
            submitted_at=timezone.now(),
        )


class SellerVehicleDetailUpdateView(generics.RetrieveUpdateAPIView):
    """Seller endpoint to retrieve or update their vehicle submission.

    GET /api/v1/marketplace/vehicles/<id>/
    PATCH /api/v1/marketplace/vehicles/<id>/
    """
    permission_classes = [IsSellerOrStaff]
    serializer_class = VehicleListingSellerSerializer
    lookup_field = 'id'
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        queryset = VehicleListing.objects.filter(is_active=True).select_related(
            'make', 'model', 'variant', 'seller', 'organisation'
        )
        if not (user.is_staff or user.has_role('ADMIN')):
            queryset = queryset.filter(
                Q(seller=user) | Q(organisation__memberships__user=user, organisation__memberships__is_active=True)
            ).distinct()
        return queryset

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method in ('PATCH', 'PUT'):
            user = request.user
            if not (user.is_staff or user.has_role('ADMIN')):
                if obj.organisation:
                    member_role = obj.organisation.get_member_role(user)
                    if member_role not in ('OWNER', 'ADMIN'):
                        raise PermissionDenied("Only organisation OWNER or ADMIN may edit listings for this organisation.")
                elif obj.seller != user:
                    raise PermissionDenied("You can only edit your own listings.")

    def perform_update(self, serializer):
        instance = serializer.instance
        update_data = {}
        req_status = self.request.data.get('status')
        if req_status == ListingStatusChoices.PENDING_APPROVAL and instance.status in (
            ListingStatusChoices.DRAFT,
            ListingStatusChoices.REJECTED,
            ListingStatusChoices.CHANGES_REQUESTED,
        ):
            update_data['status'] = ListingStatusChoices.PENDING_APPROVAL
            update_data['submitted_at'] = timezone.now()
            update_data['rejection_reason'] = ""
        elif instance.status in (ListingStatusChoices.REJECTED, ListingStatusChoices.CHANGES_REQUESTED):
            update_data['status'] = ListingStatusChoices.PENDING_APPROVAL
            update_data['submitted_at'] = timezone.now()
            update_data['rejection_reason'] = ""
        elif instance.status == ListingStatusChoices.APPROVED:
            material_fields = {
                'price', 'description', 'make', 'make_id', 'model', 'model_id',
                'variant', 'variant_id', 'images', 'primary_image_url', 'vin', 'mileage'
            }
            has_material_change = False
            for field in material_fields:
                if field in serializer.validated_data:
                    current_val = getattr(instance, field, None)
                    new_val = serializer.validated_data[field]
                    if current_val != new_val:
                        has_material_change = True
                        break
                elif field in self.request.data:
                    has_material_change = True
                    break

            if has_material_change:
                update_data['status'] = ListingStatusChoices.PENDING_APPROVAL
                update_data['submitted_at'] = timezone.now()
                update_data['rejection_reason'] = ""

        serializer.save(**update_data)


class SellerVehicleResubmitView(views.APIView):
    """Seller endpoint to submit or resubmit a draft/rejected vehicle submission for review.

    POST /api/v1/marketplace/vehicles/<id>/resubmit/
    POST /api/v1/marketplace/vehicles/<id>/submit/
    """
    permission_classes = [IsSellerOrStaff]

    def post(self, request, id):
        user = request.user
        listing = VehicleListing.objects.filter(id=id, is_active=True).first()
        if not listing:
            return Response({"error": "Vehicle listing not found."}, status=status.HTTP_404_NOT_FOUND)

        is_admin = user.is_staff or user.has_role('ADMIN')
        is_seller = listing.seller == user
        is_org_admin = False
        if listing.organisation:
            is_org_admin = listing.organisation.get_member_role(user) in ('OWNER', 'ADMIN')

        if not (is_admin or is_seller or is_org_admin):
            raise PermissionDenied("You are not authorized to submit this vehicle. Only the listing seller or organisation OWNER/ADMIN may resubmit.")

        if listing.status == ListingStatusChoices.APPROVED:
            return Response(
                {"error": "This listing is already approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if listing.status == ListingStatusChoices.PENDING_APPROVAL:
            return Response(
                {"error": "This listing is already pending approval."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        was_draft = listing.status == ListingStatusChoices.DRAFT
        listing.status = ListingStatusChoices.PENDING_APPROVAL
        listing.submitted_at = timezone.now()
        listing.rejection_reason = ""
        listing.save()

        serializer = VehicleListingSellerSerializer(listing, context={'request': request})
        action_msg = "Vehicle listing submitted for approval." if was_draft else "Vehicle listing resubmitted for approval."
        return Response(
            {
                "status": "success",
                "message": action_msg,
                "listing": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class SellerPartListCreateView(generics.ListCreateAPIView):
    """Seller endpoint to view own submitted spare parts or submit a new spare part for approval.

    GET /api/v1/marketplace/parts/
    POST /api/v1/marketplace/parts/
    """
    permission_classes = [IsSellerOrStaff]
    serializer_class = SparePartListingSellerSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = SparePartListing.objects.filter(is_active=True).select_related(
            'category', 'seller', 'organisation'
        ).prefetch_related('compatible_variants')
        if not (user.is_staff or user.has_role('ADMIN')):
            queryset = queryset.filter(
                Q(seller=user) | Q(organisation__memberships__user=user, organisation__memberships__is_active=True)
            ).distinct()

        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param.upper())

        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        org = serializer.validated_data.get('organisation')
        if org:
            if not (user.is_staff or user.has_role('ADMIN')):
                member_role = org.get_member_role(user)
                if member_role not in ('OWNER', 'ADMIN'):
                    raise PermissionDenied("Only organisation OWNER or ADMIN may create listings for this organisation.")

        initial_status = ListingStatusChoices.PENDING_APPROVAL
        if self.request.data.get('status') == ListingStatusChoices.DRAFT:
            initial_status = ListingStatusChoices.DRAFT

        # Submission gate: non-draft creation cannot enter PENDING_APPROVAL with CONFLICT
        if initial_status != ListingStatusChoices.DRAFT:
            cat_part = serializer.validated_data.get('catalogue_part')
            variants = serializer.validated_data.get('compatible_variants', [])
            conflicts = get_conflicting_variants(cat_part, variants)
            if conflicts:
                corr_id = getattr(self.request, 'correlation_id', '')
                record_denied_audit_entry(
                    action="listing:submit",
                    resource_type="SparePartListing",
                    resource_id="",
                    reason_code="FITMENT_CONFLICT",
                    correlation_id=corr_id,
                    actor_id=user.id,
                    metadata={
                        "conflicting_variant_ids": [c["variant_id"] for c in conflicts],
                    },
                )
                raise DRFValidationError({
                    "compatible_variants": "Listing contains compatible variants that conflict with catalogue records (DOES_NOT_FIT).",
                    "conflicts": conflicts,
                })

        requested_stock = serializer.validated_data.get('stock_quantity', 1)

        with transaction.atomic():
            instance = serializer.save(
                seller=user,
                status=initial_status,
                stock_quantity=0,
                submitted_at=timezone.now(),
            )
            if requested_stock > 0:
                adjust_stock(
                    listing=instance,
                    delta=requested_stock,
                    reason=StockMovementReasonChoices.INITIAL,
                    actor=user,
                    note="Initial stock on listing creation",
                )


class SellerPartDetailUpdateView(generics.RetrieveUpdateAPIView):
    """Seller endpoint to retrieve or update their spare part submission.

    GET /api/v1/marketplace/parts/<id>/
    PATCH /api/v1/marketplace/parts/<id>/
    """
    permission_classes = [IsSellerOrStaff]
    serializer_class = SparePartListingSellerSerializer
    lookup_field = 'id'
    http_method_names = ['get', 'patch', 'head', 'options']

    def patch(self, request, *args, **kwargs):
        if 'stock_quantity' in request.data:
            raise DRFValidationError({
                "stock_quantity": "Direct modification of stock_quantity via update is disabled. Use POST /api/v1/marketplace/parts/<id>/stock/ to adjust stock."
            })
        return super().patch(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        queryset = SparePartListing.objects.filter(is_active=True).select_related(
            'category', 'seller', 'organisation'
        ).prefetch_related('compatible_variants')
        if not (user.is_staff or user.has_role('ADMIN')):
            queryset = queryset.filter(
                Q(seller=user) | Q(organisation__memberships__user=user, organisation__memberships__is_active=True)
            ).distinct()
        return queryset

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method in ('PATCH', 'PUT'):
            user = request.user
            if not (user.is_staff or user.has_role('ADMIN')):
                if obj.organisation:
                    member_role = obj.organisation.get_member_role(user)
                    if member_role not in ('OWNER', 'ADMIN'):
                        raise PermissionDenied("Only organisation OWNER or ADMIN may edit listings for this organisation.")
                elif obj.seller != user:
                    raise PermissionDenied("You can only edit your own listings.")

    def perform_update(self, serializer):
        instance = serializer.instance
        update_data = {}
        req_status = self.request.data.get('status')
        if req_status == ListingStatusChoices.PENDING_APPROVAL and instance.status in (
            ListingStatusChoices.DRAFT,
            ListingStatusChoices.REJECTED,
            ListingStatusChoices.CHANGES_REQUESTED,
        ):
            update_data['status'] = ListingStatusChoices.PENDING_APPROVAL
            update_data['submitted_at'] = timezone.now()
            update_data['rejection_reason'] = ""
        elif instance.status in (ListingStatusChoices.REJECTED, ListingStatusChoices.CHANGES_REQUESTED):
            update_data['status'] = ListingStatusChoices.PENDING_APPROVAL
            update_data['submitted_at'] = timezone.now()
            update_data['rejection_reason'] = ""
        elif instance.status == ListingStatusChoices.APPROVED:
            material_fields = {
                'price', 'compare_at_price', 'catalogue_part', 'description', 'name', 'brand', 'mpn', 'oem_numbers',
                'category', 'category_id', 'images', 'primary_image_url',
                'condition', 'compatible_variants'
            }
            has_material_change = False
            for field in material_fields:
                if field in serializer.validated_data:
                    current_val = getattr(instance, field, None)
                    new_val = serializer.validated_data[field]
                    if current_val != new_val:
                        has_material_change = True
                        break
                elif field in self.request.data:
                    has_material_change = True
                    break

            if has_material_change:
                update_data['status'] = ListingStatusChoices.PENDING_APPROVAL
                update_data['submitted_at'] = timezone.now()
                update_data['rejection_reason'] = ""

        # Gate on updates moving to PENDING_APPROVAL
        if update_data.get('status') == ListingStatusChoices.PENDING_APPROVAL:
            target_cat_part = serializer.validated_data.get('catalogue_part', instance.catalogue_part)
            target_variants = serializer.validated_data.get(
                'compatible_variants',
                list(instance.compatible_variants.all())
            )
            conflicts = get_conflicting_variants(target_cat_part, target_variants)
            if conflicts:
                corr_id = getattr(self.request, 'correlation_id', '')
                record_denied_audit_entry(
                    action="listing:submit",
                    resource_type="SparePartListing",
                    resource_id=str(instance.id),
                    reason_code="FITMENT_CONFLICT",
                    correlation_id=corr_id,
                    actor_id=self.request.user.id,
                    metadata={
                        "listing_id": str(instance.id),
                        "conflicting_variant_ids": [c["variant_id"] for c in conflicts],
                    },
                )
                raise DRFValidationError({
                    "compatible_variants": "Listing contains compatible variants that conflict with catalogue records (DOES_NOT_FIT).",
                    "conflicts": conflicts,
                })

        serializer.save(**update_data)


class SellerPartResubmitView(views.APIView):
    """Seller endpoint to submit or resubmit a draft/rejected spare part submission.

    POST /api/v1/marketplace/parts/<id>/resubmit/
    POST /api/v1/marketplace/parts/<id>/submit/
    """
    permission_classes = [IsSellerOrStaff]

    def post(self, request, id):
        user = request.user
        listing = SparePartListing.objects.filter(id=id, is_active=True).first()
        if not listing:
            return Response({"error": "Part listing not found."}, status=status.HTTP_404_NOT_FOUND)

        is_admin = user.is_staff or user.has_role('ADMIN')
        is_seller = listing.seller == user
        is_org_admin = False
        if listing.organisation:
            is_org_admin = listing.organisation.get_member_role(user) in ('OWNER', 'ADMIN')

        if not (is_admin or is_seller or is_org_admin):
            raise PermissionDenied("You are not authorized to resubmit this spare part. Only the listing seller or organisation OWNER/ADMIN may resubmit.")

        if listing.status == ListingStatusChoices.APPROVED:
            return Response(
                {"error": "This listing is already approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if listing.status == ListingStatusChoices.PENDING_APPROVAL:
            return Response(
                {"error": "This listing is already pending approval."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Submission gate: cannot enter PENDING_APPROVAL with CONFLICT
        conflicts = get_conflicting_variants(listing.catalogue_part, listing.compatible_variants.all())
        if conflicts:
            corr_id = getattr(request, 'correlation_id', '')
            record_denied_audit_entry(
                action="listing:submit",
                resource_type="SparePartListing",
                resource_id=str(listing.id),
                reason_code="FITMENT_CONFLICT",
                correlation_id=corr_id,
                actor_id=user.id,
                metadata={
                    "listing_id": str(listing.id),
                    "conflicting_variant_ids": [c["variant_id"] for c in conflicts],
                },
            )
            return Response(
                {
                    "status": "error",
                    "code": 400,
                    "message": "Listing cannot be submitted because it contains compatible variants that conflict with canonical catalogue records (DOES_NOT_FIT).",
                    "details": {
                        "compatible_variants": "Listing contains compatible variants that conflict with catalogue records.",
                        "conflicts": conflicts,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        was_draft = listing.status == ListingStatusChoices.DRAFT
        listing.status = ListingStatusChoices.PENDING_APPROVAL
        listing.submitted_at = timezone.now()
        listing.rejection_reason = ""
        listing.save()

        serializer = SparePartListingSellerSerializer(listing, context={'request': request})
        action_msg = "Spare part listing submitted for approval." if was_draft else "Spare part listing resubmitted for approval."
        return Response(
            {
                "status": "success",
                "message": action_msg,
                "listing": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class PartStockAdjustmentView(views.APIView):
    """Seller endpoint to record manual stock adjustments on a spare part listing.

    POST /api/v1/marketplace/parts/<id>/stock/
    Payload: { delta: int, reason: 'ADJUSTMENT' | 'CORRECTION', note?: str }
    """
    permission_classes = [IsSellerOrStaff]

    def post(self, request, id):
        user = request.user
        listing = SparePartListing.objects.filter(id=id, is_active=True).first()
        if not listing:
            return Response({"error": "Part listing not found."}, status=status.HTTP_404_NOT_FOUND)

        is_admin = user.is_staff or user.has_role('ADMIN')
        is_seller = listing.seller == user
        is_org_admin = False
        if listing.organisation:
            is_org_admin = listing.organisation.get_member_role(user) in ('OWNER', 'ADMIN')

        if not (is_admin or is_seller or is_org_admin):
            if listing.organisation:
                raise PermissionDenied("Only organisation OWNER or ADMIN may adjust stock for this organisation.")
            raise PermissionDenied("You can only adjust stock for your own listings.")

        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        delta = serializer.validated_data['delta']
        reason = serializer.validated_data['reason']
        note = serializer.validated_data.get('note', '')

        try:
            movement = adjust_stock(
                listing=listing,
                delta=delta,
                reason=reason,
                actor=user,
                note=note,
            )
        except DjangoValidationError as exc:
            msg = exc.messages[0] if hasattr(exc, 'messages') and exc.messages else str(exc)
            raise DRFValidationError({"stock_quantity": msg})

        return Response(
            {
                "status": "success",
                "message": "Stock adjusted successfully.",
                "movement": StockMovementSerializer(movement).data,
                "listing": SparePartListingSellerSerializer(listing, context={'request': request}).data,
            },
            status=status.HTTP_200_OK,
        )


class PartStockHistoryView(views.APIView):
    """Seller endpoint to view stock movement audit history for a spare part listing.

    GET /api/v1/marketplace/parts/<id>/stock-history/
    """
    permission_classes = [IsSellerOrStaff]

    def get(self, request, id):
        user = request.user
        listing = SparePartListing.objects.filter(id=id, is_active=True).first()
        if not listing:
            return Response({"error": "Part listing not found."}, status=status.HTTP_404_NOT_FOUND)

        is_admin = user.is_staff or user.has_role('ADMIN')
        is_seller = listing.seller == user
        is_org_admin = False
        if listing.organisation:
            is_org_admin = listing.organisation.get_member_role(user) in ('OWNER', 'ADMIN')

        if not (is_admin or is_seller or is_org_admin):
            if listing.organisation:
                raise PermissionDenied("Only organisation OWNER or ADMIN may view stock history for this organisation.")
            raise PermissionDenied("You can only view stock history for your own listings.")

        movements = listing.stock_movements.all().select_related('actor').order_by('-created_at')
        serializer = StockMovementSerializer(movements, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PartPriceHistoryView(views.APIView):
    """Seller endpoint to view price modification audit history for a spare part listing.

    GET /api/v1/marketplace/parts/<id>/price-history/
    """
    permission_classes = [IsSellerOrStaff]

    def get(self, request, id):
        user = request.user
        listing = SparePartListing.objects.filter(id=id, is_active=True).first()
        if not listing:
            return Response({"error": "Part listing not found."}, status=status.HTTP_404_NOT_FOUND)

        is_admin = user.is_staff or user.has_role('ADMIN')
        is_seller = listing.seller == user
        is_org_admin = False
        if listing.organisation:
            is_org_admin = listing.organisation.get_member_role(user) in ('OWNER', 'ADMIN')

        if not (is_admin or is_seller or is_org_admin):
            if listing.organisation:
                raise PermissionDenied("Only organisation OWNER or ADMIN may view price history for this organisation.")
            raise PermissionDenied("You can only view price history for your own listings.")

        price_changes = listing.price_changes.all().select_related('actor').order_by('-created_at')
        serializer = PriceChangeSerializer(price_changes, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class LowStockPartListView(generics.ListAPIView):
    """Seller endpoint to view spare part inventory at or below low stock threshold.

    GET /api/v1/marketplace/parts/low-stock/
    """
    permission_classes = [IsSellerOrStaff]
    serializer_class = SparePartListingSellerSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = SparePartListing.objects.filter(
            is_active=True,
            stock_quantity__lte=F('low_stock_threshold'),
        ).select_related('category', 'seller', 'organisation').prefetch_related('compatible_variants')

        if not (user.is_staff or user.has_role('ADMIN')):
            queryset = queryset.filter(
                Q(seller=user) | Q(organisation__memberships__user=user, organisation__memberships__is_active=True)
            ).distinct()

        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param.upper())

        return queryset


# =====================================================================
# 3. Admin Moderation & Approval Queues
# =====================================================================

class AdminVehicleListingListView(generics.ListAPIView):
    """Admin endpoint to inspect all submitted vehicle listings in the review queue.

    GET /api/v1/marketplace/admin/vehicles/?status=PENDING_APPROVAL
    """
    permission_classes = [IsPlatformStaff, HasPermission('listing.review')]
    serializer_class = VehicleListingSellerSerializer

    def get_queryset(self):
        queryset = VehicleListing.objects.all().select_related(
            'make', 'model', 'variant', 'seller', 'organisation', 'reviewed_by'
        )
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param.upper())
        return queryset


class AdminVehicleListingDetailView(generics.RetrieveAPIView):
    """Admin endpoint to inspect full details of any vehicle listing in the review queue.

    GET /api/v1/marketplace/admin/vehicles/<id>/
    """
    permission_classes = [IsPlatformStaff, HasPermission('listing.review')]
    serializer_class = VehicleListingSellerSerializer
    lookup_field = 'id'
    queryset = VehicleListing.objects.all().select_related(
        'make', 'model', 'variant', 'seller', 'organisation', 'reviewed_by'
    )


class AdminVehicleListingReviewView(views.APIView):
    """Admin endpoint to approve, reject, or request changes on a vehicle listing.

    POST /api/v1/marketplace/admin/vehicles/<id>/review/
    """
    permission_classes = [IsPlatformStaff, HasPermission('listing.review')]

    def post(self, request, id):
        listing = VehicleListing.objects.filter(id=id).first()
        if not listing:
            return Response({"error": "Vehicle listing not found."}, status=status.HTTP_404_NOT_FOUND)

        # Self-approval protection: Admins cannot approve their own inventory submissions
        if listing.seller == request.user and not request.user.is_superuser:
            return Response(
                {"error": "Self-approval violation: You cannot review or approve your own vehicle listing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ListingReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data['action']
        rejection_reason = serializer.validated_data.get('rejection_reason', '')
        admin_notes = serializer.validated_data.get('admin_notes', '')

        if action == 'APPROVE':
            listing.status = ListingStatusChoices.APPROVED
            listing.rejection_reason = ""
        elif action == 'REJECT':
            listing.status = ListingStatusChoices.REJECTED
            listing.rejection_reason = rejection_reason
        elif action == 'REQUEST_CHANGES':
            listing.status = ListingStatusChoices.CHANGES_REQUESTED
            listing.rejection_reason = rejection_reason

        listing.reviewed_by = request.user
        listing.reviewed_at = timezone.now()
        if admin_notes:
            listing.admin_notes = admin_notes
        listing.save()

        corr_id = getattr(request, 'correlation_id', '')
        event_type_map = {
            'APPROVE': 'listing.approved',
            'REJECT': 'listing.rejected',
            'REQUEST_CHANGES': 'listing.changes_requested',
        }
        action_map = {
            'APPROVE': 'listing:approve',
            'REJECT': 'listing:reject',
            'REQUEST_CHANGES': 'listing:request_changes',
        }
        record_audit_entry(
            event_type=event_type_map.get(action, 'listing.reviewed'),
            action=action_map.get(action, 'listing:review'),
            resource_type='VehicleListing',
            resource_id=str(listing.id),
            actor_id=request.user.id,
            correlation_id=corr_id,
            metadata={
                'title': listing.title,
                'seller_id': str(listing.seller_id),
                'action': action,
                'reason': rejection_reason,
            },
        )

        detail_serializer = VehicleListingSellerSerializer(listing, context={'request': request})
        return Response(
            {
                "status": "success",
                "message": f"Vehicle listing {action.lower()}d successfully.",
                "listing": detail_serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class AdminPartListingListView(generics.ListAPIView):
    """Admin endpoint to inspect all submitted spare part listings in the review queue.

    GET /api/v1/marketplace/admin/parts/?status=PENDING_APPROVAL
    """
    permission_classes = [IsPlatformStaff, HasPermission('listing.review')]
    serializer_class = AdminPartListingReviewSerializer

    def get_queryset(self):
        queryset = SparePartListing.objects.all().select_related(
            'category', 'seller', 'organisation', 'reviewed_by', 'catalogue_part'
        ).prefetch_related('compatible_variants')
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param.upper())
        return queryset


class AdminPartListingDetailView(generics.RetrieveAPIView):
    """Admin endpoint to inspect full details of any spare part listing in the review queue.

    GET /api/v1/marketplace/admin/parts/<id>/
    """
    permission_classes = [IsPlatformStaff, HasPermission('listing.review')]
    serializer_class = AdminPartListingReviewSerializer
    lookup_field = 'id'
    queryset = SparePartListing.objects.all().select_related(
        'category', 'seller', 'organisation', 'reviewed_by', 'catalogue_part'
    ).prefetch_related('compatible_variants')


class AdminPartListingReviewView(views.APIView):
    """Admin endpoint to approve, reject, or request changes on a spare part listing.

    POST /api/v1/marketplace/admin/parts/<id>/review/
    """
    permission_classes = [IsPlatformStaff, HasPermission('listing.review')]

    def post(self, request, id):
        listing = SparePartListing.objects.filter(id=id).first()
        if not listing:
            return Response({"error": "Spare part listing not found."}, status=status.HTTP_404_NOT_FOUND)

        # Self-approval protection
        if listing.seller == request.user and not request.user.is_superuser:
            return Response(
                {"error": "Self-approval violation: You cannot review or approve your own spare part listing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ListingReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data['action']
        rejection_reason = serializer.validated_data.get('rejection_reason', '')
        admin_notes = serializer.validated_data.get('admin_notes', '')

        if action == 'APPROVE':
            conflicts = get_conflicting_variants(listing.catalogue_part, listing.compatible_variants.all())
            if conflicts:
                return Response(
                    {
                        "status": "error",
                        "code": 400,
                        "message": "Cannot approve listing with conflicting fitment records.",
                        "details": {
                            "compatible_variants": "Listing contains compatible variants that conflict with catalogue records (DOES_NOT_FIT).",
                            "conflicts": conflicts,
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            listing.status = ListingStatusChoices.APPROVED
            listing.rejection_reason = ""
        elif action == 'REJECT':
            listing.status = ListingStatusChoices.REJECTED
            listing.rejection_reason = rejection_reason
        elif action == 'REQUEST_CHANGES':
            listing.status = ListingStatusChoices.CHANGES_REQUESTED
            listing.rejection_reason = rejection_reason

        listing.reviewed_by = request.user
        listing.reviewed_at = timezone.now()
        if admin_notes:
            listing.admin_notes = admin_notes
        listing.save()

        corr_id = getattr(request, 'correlation_id', '')
        event_type_map = {
            'APPROVE': 'listing.approved',
            'REJECT': 'listing.rejected',
            'REQUEST_CHANGES': 'listing.changes_requested',
        }
        action_map = {
            'APPROVE': 'listing:approve',
            'REJECT': 'listing:reject',
            'REQUEST_CHANGES': 'listing:request_changes',
        }
        record_audit_entry(
            event_type=event_type_map.get(action, 'listing.reviewed'),
            action=action_map.get(action, 'listing:review'),
            resource_type='SparePartListing',
            resource_id=str(listing.id),
            actor_id=request.user.id,
            correlation_id=corr_id,
            metadata={
                'title': listing.name,
                'seller_id': str(listing.seller_id),
                'action': action,
                'reason': rejection_reason,
            },
        )

        detail_serializer = AdminPartListingReviewSerializer(listing, context={'request': request})
        return Response(
            {
                "status": "success",
                "message": f"Spare part listing {action.lower()}d successfully.",
                "listing": detail_serializer.data,
            },
            status=status.HTTP_200_OK,
        )


# =====================================================================
# 4. Buyer Favourites APIs
# =====================================================================

class BuyerFavouriteVehicleListCreateView(generics.ListCreateAPIView):
    """List or add approved vehicles to the authenticated buyer's favourites list.

    GET /api/v1/marketplace/favourites/
    POST /api/v1/marketplace/favourites/
    """
    permission_classes = [permissions.IsAuthenticated, IsBuyer]
    serializer_class = BuyerFavouriteVehicleSerializer

    def get_queryset(self):
        # Strict user isolation: Buyer only views their own favourites
        # select_related prevents N+1 queries when loading nested vehicle details
        return BuyerFavouriteVehicle.objects.filter(
            user=self.request.user,
        ).select_related(
            'vehicle',
            'vehicle__make',
            'vehicle__model',
            'vehicle__variant',
            'vehicle__seller',
            'vehicle__organisation',
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vehicle = serializer.validated_data['vehicle']

        # Determine ownership strictly from authenticated user, never from client input.
        # Idempotent addition: prevents duplicate database records upon repeated requests.
        favourite, created = BuyerFavouriteVehicle.objects.get_or_create(
            user=request.user,
            vehicle=vehicle,
        )
        out_serializer = self.get_serializer(favourite)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(out_serializer.data, status=status_code)


class BuyerFavouriteVehicleDetailView(views.APIView):
    """Retrieve or remove a vehicle from the authenticated buyer's favourites.

    GET /api/v1/marketplace/favourites/<id>/
    DELETE /api/v1/marketplace/favourites/<id>/
    Supports looking up either by favourite record ID or by vehicle ID.
    """
    permission_classes = [permissions.IsAuthenticated, IsBuyer]

    def get(self, request, id):
        fav = BuyerFavouriteVehicle.objects.filter(user=request.user).filter(
            Q(id=id) | Q(vehicle_id=id)
        ).select_related(
            'vehicle',
            'vehicle__make',
            'vehicle__model',
            'vehicle__variant',
            'vehicle__seller',
            'vehicle__organisation',
        ).first()

        if not fav:
            raise Http404("Favourite vehicle not found.")

        serializer = BuyerFavouriteVehicleSerializer(fav, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, id):
        fav = BuyerFavouriteVehicle.objects.filter(user=request.user).filter(
            Q(id=id) | Q(vehicle_id=id)
        ).first()

        if fav:
            fav.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        # Object-level isolation check:
        # If this favourite exists but belongs to another buyer, return 404 (prevent access/deletion)
        other_fav = BuyerFavouriteVehicle.objects.filter(
            Q(id=id) | Q(vehicle_id=id)
        ).exclude(user=request.user).first()

        if other_fav:
            return Response(
                {"detail": "Favourite vehicle not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Safe repeated removal: if already removed, return 204 No Content
        return Response(status=status.HTTP_204_NO_CONTENT)


class BuyerFavouritePartListCreateView(generics.ListCreateAPIView):
    """List or add approved spare parts to the authenticated buyer's favourites list.

    GET /api/v1/marketplace/favourites/parts/
    POST /api/v1/marketplace/favourites/parts/
    """
    permission_classes = [permissions.IsAuthenticated, IsBuyer]
    serializer_class = BuyerFavouritePartSerializer

    def get_queryset(self):
        # Strict user isolation: Buyer only views their own favourites
        # select_related prevents N+1 queries when loading nested spare part details
        return BuyerFavouritePart.objects.filter(
            user=self.request.user,
        ).select_related(
            'part',
            'part__category',
            'part__seller',
            'part__organisation',
        ).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        part = serializer.validated_data['part']

        # Determine ownership strictly from authenticated user, never from client input.
        # Idempotent addition: prevents duplicate database records upon repeated requests.
        favourite, created = BuyerFavouritePart.objects.get_or_create(
            user=request.user,
            part=part,
        )
        out_serializer = self.get_serializer(favourite)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(out_serializer.data, status=status_code)


class BuyerFavouritePartDetailView(views.APIView):
    """Retrieve or remove a spare part from the authenticated buyer's favourites.

    GET /api/v1/marketplace/favourites/parts/<id>/
    DELETE /api/v1/marketplace/favourites/parts/<id>/
    Supports looking up either by favourite record ID or by part ID.
    """
    permission_classes = [permissions.IsAuthenticated, IsBuyer]

    def get(self, request, id):
        fav = BuyerFavouritePart.objects.filter(user=request.user).filter(
            Q(id=id) | Q(part_id=id)
        ).select_related(
            'part',
            'part__category',
            'part__seller',
            'part__organisation',
        ).first()

        if not fav:
            raise Http404("Favourite part not found.")

        serializer = BuyerFavouritePartSerializer(fav, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, id):
        fav = BuyerFavouritePart.objects.filter(user=request.user).filter(
            Q(id=id) | Q(part_id=id)
        ).first()

        if fav:
            fav.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        # Object-level isolation check:
        # If this favourite exists but belongs to another buyer, return 404 (prevent access/deletion)
        other_fav = BuyerFavouritePart.objects.filter(
            Q(id=id) | Q(part_id=id)
        ).exclude(user=request.user).first()

        if other_fav:
            return Response(
                {"detail": "Favourite part not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Safe repeated removal: if already removed, return 204 No Content
        return Response(status=status.HTTP_204_NO_CONTENT)


class MarketplaceImageUploadView(views.APIView):
    """Secure endpoint for uploading listing and catalogue photos from a seller's computer.

    POST /api/v1/marketplace/upload-image/
    DELETE /api/v1/marketplace/upload-image/
    """
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsSellerOrStaff]

    def post(self, request, *args, **kwargs):
        # 1. Gather files from multipart request
        files = request.FILES.getlist('files')
        if not files:
            files = request.FILES.getlist('file')

        if not files:
            raise DRFValidationError({"file": "No image file provided. Please attach an image under 'file' or 'files'."})

        # 2. Check listing ownership & photo limit if listing_id is supplied
        listing_type = request.data.get('listing_type', '').lower().strip()
        listing_id = request.data.get('listing_id', '').strip()

        if listing_id:
            user = request.user
            is_admin = user.is_staff or user.is_superuser or user.has_role('ADMIN') or user.has_role('MARKETPLACE_ADMIN')

            if listing_type == 'vehicle':
                listing = VehicleListing.objects.filter(id=listing_id, is_active=True).first()
                if not listing:
                    raise NotFound("Vehicle listing not found.")
                is_owner = listing.seller_id == user.id
                is_org_admin = False
                if listing.organisation_id:
                    is_org_admin = listing.organisation.get_member_role(user) in ('OWNER', 'ADMIN')
                if not (is_admin or is_owner or is_org_admin):
                    raise PermissionDenied("You do not have permission to upload photos for this listing.")
                existing_count = len(listing.images or [])
                if existing_count + len(files) > 10:
                    raise DRFValidationError({"file": f"Listing already has {existing_count} photos. Adding {len(files)} would exceed the maximum limit of 10 photos."})
            elif listing_type == 'part':
                listing = SparePartListing.objects.filter(id=listing_id, is_active=True).first()
                if not listing:
                    raise NotFound("Spare part listing not found.")
                is_owner = listing.seller_id == user.id
                is_org_admin = False
                if listing.organisation_id:
                    is_org_admin = listing.organisation.get_member_role(user) in ('OWNER', 'ADMIN')
                if not (is_admin or is_owner or is_org_admin):
                    raise PermissionDenied("You do not have permission to upload photos for this listing.")
                existing_count = len(listing.images or [])
                if existing_count + len(files) > 10:
                    raise DRFValidationError({"file": f"Listing already has {existing_count} photos. Adding {len(files)} would exceed the maximum limit of 10 photos."})
        else:
            if len(files) > 10:
                raise DRFValidationError({"file": f"Cannot upload more than 10 images at once. Provided: {len(files)}."})

        # 3. Validate each file (size, extension, and binary magic bytes)
        max_size = getattr(settings, 'MAX_UPLOAD_SIZE_BYTES', 5 * 1024 * 1024)
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
        validated_files = []

        for f in files:
            if f.size > max_size:
                raise DRFValidationError({"file": f"File '{f.name}' exceeds the maximum allowed size of {max_size // (1024 * 1024)}MB."})

            ext = os.path.splitext(f.name)[1].lower()
            if ext not in allowed_extensions:
                raise DRFValidationError({"file": f"File '{f.name}' has an unsupported extension '{ext}'. Allowed formats are JPEG, PNG, and WebP."})

            # Inspect magic bytes to prevent spoofed/malicious file uploads
            pos = f.tell() if hasattr(f, 'tell') else 0
            header = f.read(32)
            if hasattr(f, 'seek'):
                f.seek(pos)

            is_jpeg = header.startswith(b'\xff\xd8\xff')
            is_png = header.startswith(b'\x89PNG\r\n\x1a\n')
            is_webp = len(header) >= 12 and header.startswith(b'RIFF') and header[8:12] == b'WEBP'

            if not (is_jpeg or is_png or is_webp):
                raise DRFValidationError({"file": f"File '{f.name}' contains invalid or corrupted image data. Allowed types are genuine JPEG, PNG, and WebP images."})

            canonical_ext = '.jpg' if is_jpeg else ('.png' if is_png else '.webp')
            validated_files.append((f, canonical_ext))

        # 4. Save validated files to default storage under safe unique names
        category = listing_type if listing_type in ('vehicle', 'part', 'catalogue') else 'marketplace'
        year_month = timezone.now().strftime("%Y/%m")
        uploaded_results = []

        for f, canonical_ext in validated_files:
            unique_id = uuid.uuid4().hex
            storage_path = f"uploads/{category}s/{year_month}/{unique_id}{canonical_ext}"
            saved_name = default_storage.save(storage_path, f)
            storage_url = default_storage.url(saved_name)
            absolute_url = request.build_absolute_uri(storage_url)

            uploaded_results.append({
                "id": unique_id,
                "url": storage_url,
                "absolute_url": absolute_url,
                "relative_url": storage_url,
                "filename": f.name,
                "size": f.size,
                "content_type": f"image/{canonical_ext.lstrip('.')}",
            })

        # 5. Build structured response
        if len(uploaded_results) == 1:
            first = uploaded_results[0]
            response_data = {
                "status": "success",
                "id": first["id"],
                "url": first["url"],
                "absolute_url": first["absolute_url"],
                "relative_url": first["relative_url"],
                "filename": first["filename"],
                "size": first["size"],
                "content_type": first["content_type"],
                "images": uploaded_results,
            }
        else:
            response_data = {
                "status": "success",
                "count": len(uploaded_results),
                "images": uploaded_results,
            }

        return Response(response_data, status=status.HTTP_201_CREATED)

    def delete(self, request, *args, **kwargs):
        url = request.data.get('url') or request.query_params.get('url', '')
        if not url:
            return Response({"error": "Missing 'url' parameter for deletion."}, status=status.HTTP_400_BAD_REQUEST)

        # Security check: forbid directory traversal
        if ".." in url:
            return Response({"error": "Invalid file path."}, status=status.HTTP_400_BAD_REQUEST)

        clean_path = url
        if "/media/" in clean_path:
            clean_path = clean_path.split("/media/", 1)[1]
        elif clean_path.startswith("/"):
            clean_path = clean_path.lstrip("/")

        if not clean_path.startswith("uploads/"):
            return Response({"error": "Only uploaded marketplace images may be deleted."}, status=status.HTTP_400_BAD_REQUEST)

        if default_storage.exists(clean_path):
            default_storage.delete(clean_path)

        return Response({"status": "success", "message": "Image deleted successfully."}, status=status.HTTP_200_OK)


class GSTOptionsView(views.APIView):
    """Public / Seller endpoint returning official automotive HSN classifications and valid GST rates."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from apps.marketplace.tax import get_all_hsn_options
        options = get_all_hsn_options()
        return Response({
            "status": "success",
            "count": len(options),
            "hsn_options": options,
            "standard_slabs": ["5.00", "12.00", "18.00", "28.00"],
        }, status=status.HTTP_200_OK)


class OrderCheckoutView(views.APIView):
    """Recalculates GST strictly on the backend and creates an immutable purchase order.

    POST /api/v1/marketplace/orders/checkout/
    Payload: {
        items: [{ listing_id: UUID, quantity: int }],
        place_of_supply?: str (e.g. "MH", "KA", "DL"),
        currency?: str (default "INR"),
        preview_only?: bool (if true, calculates and returns breakdown without persisting order)
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        import re
        from apps.marketplace.serializers import CheckoutPayloadSerializer, OrderSerializer
        from apps.marketplace.models import Order, OrderItem, OrderStatusChoices
        from apps.marketplace.tax import calculate_gst_breakdown, quantize_currency
        from decimal import Decimal
        from django.db import IntegrityError

        serializer = CheckoutPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        items_data = data['items']
        place_of_supply = data.get('place_of_supply', '').strip()
        currency = data.get('currency', 'INR').strip().upper()
        preview_only = bool(request.data.get('preview_only', False)) or ('calculate' in request.path)

        if not items_data:
            return Response({"error": "At least one item is required for checkout."}, status=status.HTTP_400_BAD_REQUEST)

        buyer = request.user

        # 1. Idempotency Guard (early replay check)
        idempotency_key = (
            request.headers.get('Idempotency-Key')
            or request.headers.get('X-Idempotency-Key')
            or data.get('idempotency_key', '')
        ).strip()

        if not preview_only and idempotency_key:
            existing_order = Order.objects.filter(buyer=buyer, idempotency_key=idempotency_key).first()
            if existing_order:
                payment_session = None
                if existing_order.payment_method == PaymentMethodChoices.ONLINE and existing_order.payment_status != PaymentStatusChoices.PAID:
                    payment_session = PaymentService.create_payment_session(existing_order)
                return Response(
                    {
                        "status": "success",
                        "message": "Order already processed (idempotent replay).",
                        "replayed": True,
                        "order": OrderSerializer(existing_order).data,
                        "payment_session": payment_session,
                    },
                    status=status.HTTP_200_OK,
                )

        # 2. Consolidate requested quantities across duplicate listing items
        consolidated_items = {}
        for item in items_data:
            lid = item['listing_id']
            qty = item['quantity']
            if qty <= 0:
                return Response(
                    {"error": f"Quantity must be at least 1."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            consolidated_items[lid] = consolidated_items.get(lid, 0) + qty

        # Early check: ensure all requested items exist as SparePartListing (returns 404 if missing or vehicle)
        for listing_id in consolidated_items.keys():
            if not SparePartListing.objects.filter(id=listing_id, is_active=True).exists():
                return Response(
                    {"error": f"Spare part listing with ID {listing_id} not found or inactive."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        from apps.marketplace.pricing import (
            PriceCalculationError,
            normalize_destination_country,
            get_required_currency_for_country,
            resolve_authoritative_unit_price,
            calculate_item_tax_breakdown,
        )

        # Shipping & Contact fields
        shipping_name = data.get('shipping_name', '').strip()
        shipping_phone = data.get('shipping_phone', '').strip()
        shipping_address_line1 = data.get('shipping_address_line1', '').strip()
        shipping_address_line2 = data.get('shipping_address_line2', '').strip()
        shipping_city = data.get('shipping_city', '').strip()
        shipping_state = data.get('shipping_state', '').strip() or place_of_supply
        shipping_postal_code = data.get('shipping_postal_code', '').strip()
        shipping_country_input = data.get('shipping_country', '').strip() or request.data.get('shipping_country', '').strip()
        payment_method = data.get('payment_method', PaymentMethodChoices.ONLINE)

        # Destination Country & Required Currency Resolution
        explicit_currency = (data.get('currency', '') or request.data.get('currency', '')).strip().upper()
        if not shipping_country_input:
            shipping_country_raw = 'United Kingdom' if explicit_currency == 'GBP' else 'India'
        else:
            shipping_country_raw = shipping_country_input

        try:
            country_code, canonical_country = normalize_destination_country(shipping_country_raw)
        except PriceCalculationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        shipping_country = canonical_country
        required_currency = get_required_currency_for_country(country_code)

        if explicit_currency and explicit_currency != required_currency:
            if country_code == 'GB':
                return Response(
                    {"error": f"{explicit_currency} currency cannot be used for delivery to the United Kingdom. UK orders must use GBP."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            else:
                return Response(
                    {"error": f"{explicit_currency} currency cannot be used for delivery to India. India orders must use INR."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        currency = required_currency

        try:
            with transaction.atomic():
                calculated_items = []
                subtotal_taxable = Decimal('0.00')
                cgst_total = Decimal('0.00')
                sgst_total = Decimal('0.00')
                igst_total = Decimal('0.00')
                tax_total = Decimal('0.00')
                grand_total = Decimal('0.00')

                seller_state = ""
                effective_place_of_supply = shipping_state or place_of_supply or ('UK' if country_code == 'GB' else 'MH')

                for listing_id, qty in consolidated_items.items():
                    if preview_only:
                        listing = SparePartListing.objects.filter(id=listing_id, is_active=True).first()
                    else:
                        listing = SparePartListing.objects.select_for_update().filter(id=listing_id, is_active=True).first()

                    if not listing:
                        return Response(
                            {"error": f"Spare part listing with ID {listing_id} not found or inactive."},
                            status=status.HTTP_404_NOT_FOUND,
                        )

                    if listing.status != ListingStatusChoices.APPROVED:
                        return Response(
                            {"error": f"Part '{listing.name}' ({listing.mpn}) is not available for purchase (status: {listing.status})."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    if listing.stock_quantity < qty:
                        return Response(
                            {
                                "error": f"Insufficient stock for '{listing.name}'. Available: {listing.stock_quantity}, requested: {qty}."
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    # Authoritative server-side pricing and cross-currency conversion
                    try:
                        unit_price, orig_currency, is_converted = resolve_authoritative_unit_price(
                            listing=listing,
                            destination_currency=currency,
                            destination_country=shipping_country,
                        )
                    except PriceCalculationError as e:
                        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

                    if listing.organisation and listing.organisation.jurisdiction:
                        seller_state = listing.organisation.jurisdiction

                    tax_calc = calculate_item_tax_breakdown(
                        unit_price=unit_price,
                        quantity=qty,
                        listing=listing,
                        country_code=country_code,
                        place_of_supply=place_of_supply,
                        seller_state=seller_state,
                        shipping_state=shipping_state,
                        shipping_city=shipping_city,
                    )

                    line_taxable = tax_calc["taxable_amount"]
                    line_gst = tax_calc["tax_amount"]
                    line_cgst = tax_calc["cgst_amount"]
                    line_sgst = tax_calc["sgst_amount"]
                    line_igst = tax_calc["igst_amount"]
                    line_total = tax_calc["total_amount"]
                    effective_place_of_supply = tax_calc["effective_place_of_supply"]
                    gst_rate = tax_calc["gst_rate"]

                    subtotal_taxable += line_taxable
                    cgst_total += line_cgst
                    sgst_total += line_sgst
                    igst_total += line_igst
                    tax_total += line_gst
                    grand_total += line_total

                    calculated_items.append({
                        "listing": listing,
                        "item_type": "PART",
                        "title": listing.name,
                        "brand": listing.brand,
                        "mpn": listing.mpn,
                        "hsn_code": listing.hsn_code,
                        "gst_rate": gst_rate,
                        "is_tax_verified": listing.is_tax_verified,
                        "unit_price": unit_price,
                        "quantity": qty,
                        "taxable_amount": line_taxable,
                        "cgst_amount": line_cgst,
                        "sgst_amount": line_sgst,
                        "igst_amount": line_igst,
                        "tax_amount": line_gst,
                        "total_amount": line_total,
                    })

                available_payment_methods = PaymentService.get_available_payment_methods(
                    country=shipping_country,
                    currency=currency,
                    amount=grand_total,
                )

                if preview_only:
                    return Response({
                        "status": "success",
                        "preview": True,
                        "currency": currency,
                        "country": country_code,
                        "place_of_supply": effective_place_of_supply,
                        "seller_state": seller_state,
                        "subtotal_taxable_amount": str(subtotal_taxable),
                        "cgst_amount": str(cgst_total),
                        "sgst_amount": str(sgst_total),
                        "igst_amount": str(igst_total),
                        "total_tax_amount": str(tax_total),
                        "total_amount": str(grand_total),
                        "available_payment_methods": available_payment_methods,
                        "items": [
                            {
                                "listing_id": str(ci["listing"].id),
                                "title": ci["title"],
                                "brand": ci["brand"],
                                "mpn": ci["mpn"],
                                "hsn_code": ci["hsn_code"],
                                "gst_rate": str(ci["gst_rate"]),
                                "unit_price": str(ci["unit_price"]),
                                "quantity": ci["quantity"],
                                "taxable_amount": str(ci["taxable_amount"]),
                                "cgst_amount": str(ci["cgst_amount"]),
                                "sgst_amount": str(ci["sgst_amount"]),
                                "igst_amount": str(ci["igst_amount"]),
                                "tax_amount": str(ci["tax_amount"]),
                                "total_amount": str(ci["total_amount"]),
                            }
                            for ci in calculated_items
                        ],
                    }, status=status.HTTP_200_OK)

                # 4. Shipping & Contact Validation (required when placing orders)
                shipping_errors = {}
                if not shipping_name:
                    shipping_errors['shipping_name'] = 'Full name is required for delivery.'
                if not shipping_phone:
                    shipping_errors['shipping_phone'] = 'Contact phone number is required.'
                elif len(re.sub(r'[^0-9+]', '', shipping_phone)) < 7:
                    shipping_errors['shipping_phone'] = 'A valid phone number is required.'
                if not shipping_address_line1:
                    shipping_errors['shipping_address_line1'] = 'Shipping address line 1 is required.'
                if not shipping_city:
                    shipping_errors['shipping_city'] = 'City is required.'
                if not shipping_postal_code:
                    shipping_errors['shipping_postal_code'] = 'Postal / PIN code is required.'

                if shipping_errors:
                    return Response(
                        {
                            "status": "error",
                            "error": "Missing or invalid required shipping and contact details.",
                            "field_errors": shipping_errors,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # COD Eligibility Check
                if payment_method == PaymentMethodChoices.COD:
                    is_eligible, reason = PaymentService.check_cod_eligibility(
                        country=shipping_country,
                        currency=currency,
                        amount=grand_total,
                    )
                    if not is_eligible:
                        return Response(
                            {"error": f"Cash on Delivery is not available: {reason}"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                # 5. Authoritative Price / Tax Change Guard
                expected_total = data.get('expected_total_amount')
                if expected_total is not None:
                    if quantize_currency(Decimal(str(expected_total))) != quantize_currency(grand_total):
                        return Response(
                            {
                                "status": "price_changed",
                                "code": "PRICE_CHANGED",
                                "error": f"The order total has changed from {expected_total} to {grand_total} due to updated listing prices or tax rates. Please review and confirm the updated total before proceeding.",
                                "reviewed_total_amount": str(expected_total),
                                "updated_total_amount": str(grand_total),
                                "subtotal_taxable_amount": str(subtotal_taxable),
                                "total_tax_amount": str(tax_total),
                                "currency": currency,
                            },
                            status=status.HTTP_409_CONFLICT,
                        )

                # 6. Order Creation with PENDING_CONFIRMATION status
                order_number = f"DX-ORD-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
                cod_status = (
                    CODCollectionStatusChoices.PENDING
                    if payment_method == PaymentMethodChoices.COD
                    else CODCollectionStatusChoices.NOT_APPLICABLE
                )
                order = Order.objects.create(
                    buyer=buyer,
                    order_number=order_number,
                    idempotency_key=idempotency_key or None,
                    status=OrderStatusChoices.PENDING_CONFIRMATION,
                    payment_method=payment_method,
                    payment_status=PaymentStatusChoices.PENDING,
                    cod_collection_status=cod_status,
                    currency=currency,
                    place_of_supply=effective_place_of_supply,
                    seller_state=seller_state,
                    shipping_name=shipping_name,
                    shipping_phone=shipping_phone,
                    shipping_address_line1=shipping_address_line1,
                    shipping_address_line2=shipping_address_line2,
                    shipping_city=shipping_city,
                    shipping_state=shipping_state,
                    shipping_postal_code=shipping_postal_code,
                    shipping_country=shipping_country,
                    subtotal_taxable_amount=subtotal_taxable,
                    cgst_amount=cgst_total,
                    sgst_amount=sgst_total,
                    igst_amount=igst_total,
                    total_tax_amount=tax_total,
                    total_amount=grand_total,
                )

                for ci in calculated_items:
                    OrderItem.objects.create(
                        order=order,
                        listing=ci["listing"],
                        item_type=ci["item_type"],
                        title=ci["title"],
                        brand=ci["brand"],
                        mpn=ci["mpn"],
                        hsn_code=ci["hsn_code"],
                        gst_rate=ci["gst_rate"],
                        is_tax_verified=ci["is_tax_verified"],
                        unit_price=ci["unit_price"],
                        quantity=ci["quantity"],
                        taxable_amount=ci["taxable_amount"],
                        cgst_amount=ci["cgst_amount"],
                        sgst_amount=ci["sgst_amount"],
                        igst_amount=ci["igst_amount"],
                        tax_amount=ci["tax_amount"],
                        total_amount=ci["total_amount"],
                    )
                    adjust_stock(
                        listing=ci["listing"],
                        delta=-ci["quantity"],
                        reason=StockMovementReasonChoices.SALE,
                        actor=buyer,
                        note=f"Customer order {order_number}",
                    )

                payment_session = PaymentService.create_payment_session(order)

                return Response(
                    {
                        "status": "success",
                        "message": (
                            "Order created successfully. Awaiting payment/confirmation."
                            if payment_method == PaymentMethodChoices.ONLINE
                            else "Order created successfully with Cash on Delivery."
                        ),
                        "order": OrderSerializer(order).data,
                        "payment_session": payment_session,
                    },
                    status=status.HTTP_201_CREATED,
                )
        except IntegrityError:
            if idempotency_key:
                existing_order = Order.objects.filter(buyer=buyer, idempotency_key=idempotency_key).first()
                if existing_order:
                    payment_session = None
                    if existing_order.payment_method == PaymentMethodChoices.ONLINE and existing_order.payment_status != PaymentStatusChoices.PAID:
                        payment_session = PaymentService.create_payment_session(existing_order)
                    return Response(
                        {
                            "status": "success",
                            "message": "Order already processed (idempotent replay).",
                            "replayed": True,
                            "order": OrderSerializer(existing_order).data,
                            "payment_session": payment_session,
                        },
                        status=status.HTTP_200_OK,
                    )
            raise


class BuyerOrderListView(generics.ListAPIView):
    """Lists past orders placed by the authenticated buyer."""
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        from apps.marketplace.serializers import OrderSerializer
        return OrderSerializer

    def get_queryset(self):
        from apps.marketplace.models import Order
        return Order.objects.filter(buyer=self.request.user).prefetch_related('items__listing__seller').order_by('-created_at')


class BuyerOrderDetailView(views.APIView):
    """Retrieves detail of an order by UUID or order_number for the authenticated buyer."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, identifier):
        import uuid
        from apps.marketplace.models import Order
        from apps.marketplace.serializers import OrderSerializer

        is_uuid = False
        try:
            uuid.UUID(str(identifier))
            is_uuid = True
        except (ValueError, AttributeError):
            is_uuid = False

        if is_uuid:
            order = Order.objects.filter(id=identifier, buyer=request.user).prefetch_related('items__listing__seller').first()
        else:
            order = Order.objects.filter(order_number=identifier, buyer=request.user).prefetch_related('items__listing__seller').first()

        if not order:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)


class BuyerOrderCancelView(views.APIView):
    """Allows an authenticated buyer to cancel an order still in PENDING_CONFIRMATION status."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        import uuid
        from apps.marketplace.models import Order, OrderStatusChoices, StockMovementReasonChoices
        from apps.marketplace.serializers import OrderSerializer
        from apps.marketplace.services import adjust_stock
        from platform_core.audit.writer import record_audit_entry

        is_uuid = False
        try:
            uuid.UUID(str(identifier))
            is_uuid = True
        except (ValueError, AttributeError):
            is_uuid = False

        if is_uuid:
            order = Order.objects.filter(id=identifier, buyer=request.user).prefetch_related('items__listing').first()
        else:
            order = Order.objects.filter(order_number=identifier, buyer=request.user).prefetch_related('items__listing').first()

        if not order:
            return Response({"error": "Order not found or not owned by you."}, status=status.HTTP_404_NOT_FOUND)

        if order.status != OrderStatusChoices.PENDING_CONFIRMATION:
            return Response(
                {
                    "error": f"Cannot cancel order with status '{order.status}'. Only orders with status 'PENDING_CONFIRMATION' can be cancelled by the buyer."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            order.status = OrderStatusChoices.CANCELLED
            order.save(update_fields=['status', 'updated_at'])

            # Restock inventory items
            for item in order.items.all():
                if item.listing:
                    adjust_stock(
                        listing=item.listing,
                        delta=item.quantity,
                        reason=StockMovementReasonChoices.RETURN,
                        actor=request.user,
                        note=f"Buyer cancellation for order {order.order_number}",
                    )

            record_audit_entry(
                event_type="marketplace.order.buyer_cancelled",
                action="marketplace:order.cancel",
                resource_type="Order",
                resource_id=str(order.id),
                actor_id=request.user.id,
                metadata={
                    "order_number": order.order_number,
                    "previous_status": OrderStatusChoices.PENDING_CONFIRMATION,
                    "new_status": OrderStatusChoices.CANCELLED,
                },
            )

        return Response(
            {
                "status": "success",
                "message": f"Order {order.order_number} has been cancelled successfully and inventory returned.",
                "order": OrderSerializer(order).data,
            },
            status=status.HTTP_200_OK,
        )


class SellerOrderListView(generics.ListAPIView):
    """
    Lists orders containing items owned by the authenticated seller (or seller's organisations).
    Enforces multi-seller isolation by returning SellerOrderSerializer.
    GET /api/v1/marketplace/seller/orders/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        from apps.marketplace.serializers import SellerOrderSerializer
        return SellerOrderSerializer

    def get_queryset(self):
        from apps.marketplace.models import Order
        from apps.organisations.models import OrganisationMembership, OrganisationRoleChoices
        from django.db.models import Q

        user = self.request.user
        if user.is_staff or user.is_superuser:
            qs = Order.objects.all()
        else:
            org_ids = OrganisationMembership.objects.filter(
                user=user,
                is_active=True,
                role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
            ).values_list('organisation_id', flat=True)

            qs = Order.objects.filter(
                Q(items__listing__seller=user) | Q(items__listing__organisation_id__in=org_ids)
            ).distinct()

        status_param = self.request.query_params.get('status')
        if status_param and status_param.upper() != 'ALL':
            qs = qs.filter(status=status_param.upper())

        search_param = self.request.query_params.get('search')
        if search_param:
            qs = qs.filter(
                Q(order_number__icontains=search_param)
                | Q(buyer__email__icontains=search_param)
                | Q(shipping_name__icontains=search_param)
            )

        return qs.select_related('buyer').prefetch_related(
            'items__listing__seller', 'items__listing__organisation'
        ).order_by('-created_at')


class SellerOrderDetailView(views.APIView):
    """
    Retrieves isolated order details for the authenticated seller.
    Only the items and financials belonging to the seller are returned.
    GET /api/v1/marketplace/seller/orders/<str:identifier>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, identifier):
        import uuid
        from apps.marketplace.models import Order
        from apps.marketplace.serializers import SellerOrderSerializer
        from apps.organisations.models import OrganisationMembership, OrganisationRoleChoices
        from django.db.models import Q

        is_uuid = False
        try:
            uuid.UUID(str(identifier))
            is_uuid = True
        except (ValueError, AttributeError):
            is_uuid = False

        user = request.user
        query_filter = Q(id=identifier) if is_uuid else Q(order_number=identifier)

        if not (user.is_staff or user.is_superuser):
            org_ids = OrganisationMembership.objects.filter(
                user=user,
                is_active=True,
                role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
            ).values_list('organisation_id', flat=True)

            query_filter &= (Q(items__listing__seller=user) | Q(items__listing__organisation_id__in=org_ids))

        order = Order.objects.filter(query_filter).select_related('buyer').prefetch_related(
            'items__listing__seller', 'items__listing__organisation'
        ).distinct().first()

        if not order:
            return Response(
                {"error": "Order not found or you are not authorized to view this order."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = SellerOrderSerializer(order, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class SellerOrderStatusUpdateView(views.APIView):
    """
    Updates the status of an order containing the seller's items.
    Enforces valid status transitions and role authorization.
    Restocks inventory on transition to CANCELLED.
    PATCH /api/v1/marketplace/seller/orders/<str:identifier>/status/
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, identifier):
        return self._update_status(request, identifier)

    def post(self, request, identifier):
        return self._update_status(request, identifier)

    def _update_status(self, request, identifier):
        import uuid
        from apps.marketplace.models import Order, OrderStatusChoices, StockMovementReasonChoices
        from apps.marketplace.serializers import (
            SellerOrderSerializer,
            OrderStatusUpdateSerializer,
            VALID_ORDER_STATUS_TRANSITIONS,
        )
        from apps.marketplace.services import adjust_stock
        from apps.organisations.models import OrganisationMembership, OrganisationRoleChoices
        from platform_core.audit.writer import record_audit_entry
        from django.db.models import Q

        is_uuid = False
        try:
            uuid.UUID(str(identifier))
            is_uuid = True
        except (ValueError, AttributeError):
            is_uuid = False

        user = request.user
        query_filter = Q(id=identifier) if is_uuid else Q(order_number=identifier)

        if not (user.is_staff or user.is_superuser):
            org_ids = OrganisationMembership.objects.filter(
                user=user,
                is_active=True,
                role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
            ).values_list('organisation_id', flat=True)

            query_filter &= (Q(items__listing__seller=user) | Q(items__listing__organisation_id__in=org_ids))

        order = Order.objects.filter(query_filter).select_related('buyer').prefetch_related(
            'items__listing__seller', 'items__listing__organisation'
        ).distinct().first()

        if not order:
            return Response(
                {"error": "Order not found or you are not authorized to update this order."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = OrderStatusUpdateSerializer(data=request.data, context={'order': order})
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data['status']
        old_status = order.status
        notes = serializer.validated_data.get('notes', '')

        if new_status == old_status:
            return Response(
                {
                    "status": "success",
                    "message": f"Order status is already '{new_status}'.",
                    "order": SellerOrderSerializer(order, context={'request': request}).data,
                },
                status=status.HTTP_200_OK,
            )

        with transaction.atomic():
            order.status = new_status
            order.save(update_fields=['status', 'updated_at'])

            # If cancelled, restock inventory items
            if new_status == OrderStatusChoices.CANCELLED and old_status != OrderStatusChoices.CANCELLED:
                for item in order.items.all():
                    if item.listing:
                        adjust_stock(
                            listing=item.listing,
                            delta=item.quantity,
                            reason=StockMovementReasonChoices.RETURN,
                            actor=request.user,
                            note=f"Seller order cancellation for order {order.order_number}" + (f": {notes}" if notes else ""),
                        )

            record_audit_entry(
                event_type="marketplace.order.status_updated",
                action="marketplace:order.update_status",
                resource_type="Order",
                resource_id=str(order.id),
                actor_id=request.user.id,
                metadata={
                    "order_number": order.order_number,
                    "previous_status": old_status,
                    "new_status": new_status,
                    "notes": notes,
                },
            )

        return Response(
            {
                "status": "success",
                "message": f"Order {order.order_number} status updated to {new_status}.",
                "order": SellerOrderSerializer(order, context={'request': request}).data,
            },
            status=status.HTTP_200_OK,
        )


# =====================================================================
# 11. Vehicle Enquiry APIs (Direct Buyer–Seller Connection)
# =====================================================================

class VehicleEnquiryCreateView(views.APIView):
    """
    Submits a direct buyer enquiry for an approved vehicle listing.
    POST /api/v1/marketplace/vehicles/<uuid:id>/enquire/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        try:
            listing = VehicleListing.objects.select_related('seller', 'organisation').get(pk=id)
        except VehicleListing.DoesNotExist:
            return Response({"detail": "Vehicle listing not found."}, status=status.HTTP_404_NOT_FOUND)

        if listing.status != ListingStatusChoices.APPROVED or not listing.is_active:
            return Response(
                {"detail": "Enquiries can only be submitted for active, approved vehicle listings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if listing.seller_id == request.user.id:
            return Response(
                {"detail": "You cannot submit an enquiry on your own vehicle listing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if listing.organisation and listing.organisation.is_member(request.user):
            return Response(
                {"detail": "You cannot submit an enquiry on a vehicle listing owned by your organisation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Anti-spam & duplicate protection: 60s cooldown for same vehicle
        recent = VehicleEnquiry.objects.filter(
            buyer=request.user,
            listing=listing,
            created_at__gte=timezone.now() - timezone.timedelta(seconds=60),
        ).exists()
        if recent:
            return Response(
                {"detail": "You recently submitted an enquiry for this vehicle. Please wait a moment before sending another."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = VehicleEnquiryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        enquiry = VehicleEnquiry.objects.create(
            listing=listing,
            buyer=request.user,
            seller=listing.seller,
            organisation=listing.organisation,
            message=serializer.validated_data['message'],
            buyer_phone=serializer.validated_data.get('buyer_phone', ''),
        )

        record_audit_entry(
            event_type="marketplace.vehicle_enquiry.created",
            action="marketplace:enquiry.create",
            resource_type="VehicleEnquiry",
            resource_id=str(enquiry.id),
            actor_id=request.user.id,
            operating_org_id=listing.organisation_id,
            metadata={
                "enquiry_id": str(enquiry.id),
                "listing_id": str(listing.id),
                "seller_id": str(listing.seller_id),
                "buyer_email": request.user.email,
            },
        )

        return Response(VehicleEnquiryBuyerSerializer(enquiry).data, status=status.HTTP_201_CREATED)


class SellerVehicleEnquiryListView(generics.ListAPIView):
    """
    Allows a seller to view enquiries submitted for their vehicle listings.
    GET /api/v1/marketplace/seller/enquiries/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VehicleEnquirySellerSerializer

    def get_queryset(self):
        user = self.request.user
        org_ids = OrganisationMembership.objects.filter(
            user=user,
            is_active=True,
            role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
        ).values_list('organisation_id', flat=True)

        queryset = VehicleEnquiry.objects.filter(
            Q(seller=user) | Q(organisation_id__in=org_ids)
        ).select_related(
            'listing', 'listing__make', 'listing__model', 'buyer', 'seller', 'organisation'
        ).distinct()

        status_param = self.request.query_params.get('status')
        if status_param and status_param.upper() != 'ALL':
            queryset = queryset.filter(status=status_param.upper())

        listing_id = self.request.query_params.get('listing_id')
        if listing_id:
            queryset = queryset.filter(listing_id=listing_id)

        return queryset


class SellerVehicleEnquiryDetailView(views.APIView):
    """
    Allows an authorized seller to view or update status/notes of an enquiry.
    GET, PATCH /api/v1/marketplace/seller/enquiries/<uuid:id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get_enquiry(self, user, enquiry_id):
        org_ids = OrganisationMembership.objects.filter(
            user=user,
            is_active=True,
            role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
        ).values_list('organisation_id', flat=True)

        try:
            return VehicleEnquiry.objects.select_related(
                'listing', 'listing__make', 'listing__model', 'buyer', 'seller', 'organisation'
            ).get(
                Q(pk=enquiry_id) & (Q(seller=user) | Q(organisation_id__in=org_ids))
            )
        except VehicleEnquiry.DoesNotExist:
            raise Http404("Enquiry not found or you are not authorized to view it.")

    def get(self, request, id):
        enquiry = self._get_enquiry(request.user, id)
        return Response(VehicleEnquirySellerSerializer(enquiry).data)

    def patch(self, request, id):
        enquiry = self._get_enquiry(request.user, id)
        serializer = VehicleEnquiryStatusUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data.get('status')
        new_notes = serializer.validated_data.get('seller_notes')
        new_reply = serializer.validated_data.get('seller_reply')

        update_fields = ['updated_at']
        if new_status:
            enquiry.status = new_status
            update_fields.append('status')
            if new_status == VehicleEnquiryStatusChoices.RESPONDED and not enquiry.responded_at:
                enquiry.responded_at = timezone.now()
                update_fields.append('responded_at')

        if new_notes is not None:
            enquiry.seller_notes = new_notes
            update_fields.append('seller_notes')

        if new_reply is not None:
            enquiry.seller_reply = new_reply
            update_fields.append('seller_reply')
            if new_reply.strip():
                now = timezone.now()
                enquiry.replied_at = now
                update_fields.append('replied_at')
                # If currently NEW and no status was explicitly given, automatically advance to RESPONDED
                if enquiry.status == VehicleEnquiryStatusChoices.NEW and not new_status:
                    enquiry.status = VehicleEnquiryStatusChoices.RESPONDED
                    if 'status' not in update_fields:
                        update_fields.append('status')
                if not enquiry.responded_at:
                    enquiry.responded_at = now
                    if 'responded_at' not in update_fields:
                        update_fields.append('responded_at')

        enquiry.save(update_fields=update_fields)

        record_audit_entry(
            event_type="marketplace.vehicle_enquiry.updated",
            action="marketplace:enquiry.update",
            resource_type="VehicleEnquiry",
            resource_id=str(enquiry.id),
            actor_id=request.user.id,
            operating_org_id=enquiry.organisation_id,
            metadata={
                "enquiry_id": str(enquiry.id),
                "status": enquiry.status,
                "has_reply": bool(enquiry.seller_reply),
            },
        )

        return Response(VehicleEnquirySellerSerializer(enquiry).data)


class BuyerVehicleEnquiryListView(generics.ListAPIView):
    """
    Allows an authenticated buyer to view all enquiries they have sent.
    GET /api/v1/marketplace/buyer/enquiries/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VehicleEnquiryBuyerSerializer

    def get_queryset(self):
        return VehicleEnquiry.objects.filter(
            buyer=self.request.user
        ).select_related(
            'listing', 'listing__make', 'listing__model', 'seller', 'organisation'
        )


# ============================================================================
# Phase 5: Payment Gateway, Webhooks, and Cash on Delivery (COD) Endpoints
# ============================================================================

def _resolve_order_by_identifier(identifier: str):
    """Helper to resolve an Order by UUID or order_number."""
    import uuid
    from apps.marketplace.models import Order
    try:
        uuid.UUID(str(identifier))
        return Order.objects.filter(id=identifier).first()
    except (ValueError, AttributeError):
        return Order.objects.filter(order_number=identifier).first()


class AvailablePaymentMethodsView(views.APIView):
    """
    Returns available payment options (Online Razorpay/Stripe, Cash on Delivery)
    based on country, currency, and cart/order amount.
    GET /api/v1/marketplace/orders/payment-methods/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from decimal import Decimal
        country = request.query_params.get('country', 'India').strip()
        country_code = PaymentService.normalize_country_code(country)
        default_curr = 'GBP' if country_code == 'GB' else 'INR'
        currency = request.query_params.get('currency', default_curr).strip().upper()
        amount_str = request.query_params.get('amount', '0.00').strip()
        try:
            amount = Decimal(amount_str)
        except Exception:
            amount = Decimal('0.00')

        methods = PaymentService.get_available_payment_methods(
            country=country,
            currency=currency,
            amount=amount,
        )
        return Response({
            "status": "success",
            "country": PaymentService.normalize_country_code(country),
            "currency": currency,
            "amount": str(amount),
            "payment_methods": methods,
        }, status=status.HTTP_200_OK)


class OrderPaymentSessionCreateView(views.APIView):
    """
    Creates or retrieves an authoritative online payment session (Razorpay Order / Stripe PaymentIntent)
    for an existing order.
    POST /api/v1/marketplace/orders/<identifier>/payment/create/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        order = _resolve_order_by_identifier(identifier)
        if not order:
            return Response({"error": f"Order '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        # Access check: Buyer or Staff
        is_staff = request.user.is_staff or request.user.is_superuser or request.user.has_role('STAFF') or request.user.has_role('ADMIN')
        if order.buyer_id != request.user.id and not is_staff:
            return Response({"error": "You do not have permission to pay for this order."}, status=status.HTTP_403_FORBIDDEN)

        if order.payment_status == PaymentStatusChoices.PAID:
            return Response({
                "status": "already_paid",
                "message": "Order is already paid.",
                "payment_status": order.payment_status,
                "payment_reference": order.payment_reference,
            }, status=status.HTTP_200_OK)

        if order.status == OrderStatusChoices.CANCELLED:
            return Response({"error": "Cannot initialize payment for a cancelled order."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            session_data = PaymentService.create_payment_session(order)
            return Response({
                "status": "success",
                "order_number": order.order_number,
                "payment_session": session_data,
            }, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({"error": f"Failed to initialize payment session: {str(exc)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OrderPaymentVerifyView(views.APIView):
    """
    Cryptographically verifies client payment confirmation (Razorpay signature / Stripe confirmation).
    Never marks order as paid without server-authoritative verification.
    POST /api/v1/marketplace/orders/<identifier>/payment/verify/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        order = _resolve_order_by_identifier(identifier)
        if not order:
            return Response({"error": f"Order '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        is_staff = request.user.is_staff or request.user.is_superuser or request.user.has_role('STAFF') or request.user.has_role('ADMIN')
        if order.buyer_id != request.user.id and not is_staff:
            return Response({"error": "You do not have permission to verify payment for this order."}, status=status.HTTP_403_FORBIDDEN)

        serializer = PaymentVerifyPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        is_valid, ref_or_err, extra = PaymentService.verify_payment(
            order=order,
            payload=serializer.validated_data,
            actor=request.user,
        )

        if is_valid:
            return Response({
                "status": "success",
                "message": "Payment successfully verified and confirmed.",
                "payment_reference": ref_or_err,
                "payment_status": order.payment_status,
                "order": OrderSerializer(order).data,
                "extra": extra,
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                "status": "failed",
                "error": ref_or_err,
                "payment_status": order.payment_status,
                "extra": extra,
            }, status=status.HTTP_400_BAD_REQUEST)


class OrderPaymentSimulateTestView(views.APIView):
    """
    Clearly isolated server-side test payment execution for development and staging environments.
    Enforces that test-mode cannot be enabled via client flags in production.
    POST /api/v1/marketplace/orders/<identifier>/payment/simulate/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        import hmac
        import hashlib

        # 1. Strict Server Environment Guard: strictly disabled in production
        is_test_env = getattr(settings, 'PAYMENT_TEST_MODE', False) and (
            getattr(settings, 'DEBUG', False) or getattr(settings, 'IS_TESTING', False)
        )
        if not is_test_env:
            return Response(
                {"error": "Simulated test-mode payments are strictly disabled in production environments."},
                status=status.HTTP_403_FORBIDDEN,
            )

        order = _resolve_order_by_identifier(identifier)
        if not order:
            return Response({"error": f"Order '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        # Access check: Buyer or Staff
        is_staff = request.user.is_staff or request.user.is_superuser or request.user.has_role('STAFF') or request.user.has_role('ADMIN')
        if order.buyer_id != request.user.id and not is_staff:
            return Response({"error": "You do not have permission to pay for this order."}, status=status.HTTP_403_FORBIDDEN)

        if order.payment_method == PaymentMethodChoices.COD:
            return Response({"error": "Cannot simulate online payment for a Cash on Delivery order."}, status=status.HTTP_400_BAD_REQUEST)

        if order.payment_status == PaymentStatusChoices.PAID:
            return Response({
                "status": "success",
                "message": "Order is already marked as paid.",
                "already_paid": True,
                "order": OrderSerializer(order).data,
            }, status=status.HTTP_200_OK)

        # 2. Ensure payment session exists
        if not order.payment_reference:
            PaymentService.create_payment_session(order)
            order.refresh_from_db()

        # 3. Server-authoritative test verification based on order provider
        provider = PaymentService.get_provider_for_order(order)
        if provider.provider_name == 'STRIPE':
            verify_payload = {
                "payment_intent_id": order.payment_reference,
            }
        else:  # RAZORPAY
            sim_payment_id = f"pay_sim_{uuid.uuid4().hex[:14]}"
            msg = f"{order.payment_reference}|{sim_payment_id}".encode('utf-8')
            valid_sig = hmac.new(
                provider.key_secret.encode('utf-8'),
                msg,
                hashlib.sha256,
            ).hexdigest()
            verify_payload = {
                "razorpay_order_id": order.payment_reference,
                "razorpay_payment_id": sim_payment_id,
                "razorpay_signature": valid_sig,
            }

        is_valid, ref_or_err, extra = PaymentService.verify_payment(
            order=order,
            payload=verify_payload,
            actor=request.user,
        )

        if is_valid:
            order.refresh_from_db()
            return Response({
                "status": "success",
                "message": "Simulated payment successfully verified and confirmed in test mode.",
                "payment_reference": ref_or_err,
                "payment_status": order.payment_status,
                "order": OrderSerializer(order).data,
                "extra": extra,
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                "status": "failed",
                "error": ref_or_err,
                "payment_status": order.payment_status,
                "extra": extra,
            }, status=status.HTTP_400_BAD_REQUEST)


class PaymentWebhookView(views.APIView):
    """
    Ingests and validates webhooks from payment gateways (Razorpay / Stripe)
    with signature verification, duplicate-event defense, and idempotent processing.
    POST /api/v1/marketplace/payments/webhook/<provider>/
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, provider):
        headers = {}
        for key, value in request.META.items():
            if key.startswith('HTTP_'):
                header_name = key[5:].replace('_', '-').lower()
                headers[header_name] = value
            elif key in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
                headers[key.replace('_', '-').lower()] = value

        success, status_code, response_data = PaymentService.process_webhook(
            provider_name=provider,
            request_body=request.body,
            headers=headers,
        )
        return Response(response_data, status=status_code)


class OrderCODCollectionUpdateView(views.APIView):
    """
    Updates the Cash on Delivery collection status.
    Strictly restricted to authorized operations staff, delivery agents, or admin roles.
    POST /api/v1/marketplace/orders/<identifier>/cod-collection/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        order = _resolve_order_by_identifier(identifier)
        if not order:
            return Response({"error": f"Order '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CODCollectionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_status = serializer.validated_data['cod_collection_status']
        notes = serializer.validated_data.get('notes', '')

        success, message, extra = PaymentService.update_cod_collection(
            order=order,
            actor=request.user,
            target_status=target_status,
            notes=notes,
        )

        if not success:
            status_code = status.HTTP_403_FORBIDDEN if "Permission denied" in message else status.HTTP_400_BAD_REQUEST
            return Response({"error": message}, status=status_code)

        return Response({
            "status": "success",
            "message": message,
            "order": OrderSerializer(order).data,
            "details": extra,
        }, status=status.HTTP_200_OK)


class OrderPaymentDetailView(views.APIView):
    """
    Returns payment status, payment method, COD collection details,
    and the transaction audit ledger for an order.
    Access restricted to the order buyer, seller of items in the order, or staff.
    GET /api/v1/marketplace/orders/<identifier>/payment/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, identifier):
        order = _resolve_order_by_identifier(identifier)
        if not order:
            return Response({"error": f"Order '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        is_staff = user.is_staff or user.is_superuser or user.has_role('STAFF') or user.has_role('ADMIN')
        is_buyer = (order.buyer_id == user.id)
        is_seller = OrderItem.objects.filter(order=order, listing__seller=user).exists()

        if not (is_staff or is_buyer or is_seller):
            return Response({"error": "You do not have permission to view payment details for this order."}, status=status.HTTP_403_FORBIDDEN)

        transactions = PaymentTransaction.objects.filter(order=order).order_by('-created_at')
        tx_data = [
            {
                "id": str(tx.id),
                "transaction_type": tx.transaction_type,
                "provider": tx.provider,
                "amount": str(tx.amount),
                "currency": tx.currency,
                "status": tx.status,
                "provider_transaction_id": tx.provider_transaction_id,
                "provider_order_id": tx.provider_order_id,
                "error_message": tx.error_message,
                "created_at": tx.created_at.isoformat(),
            }
            for tx in transactions
        ]

        return Response({
            "order_number": order.order_number,
            "currency": order.currency,
            "total_amount": str(order.total_amount),
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
            "payment_reference": order.payment_reference,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "cod_collection_status": order.cod_collection_status,
            "cod_collected_at": order.cod_collected_at.isoformat() if order.cod_collected_at else None,
            "cod_collected_by": order.cod_collected_by.email if order.cod_collected_by else None,
            "cod_collection_notes": order.cod_collection_notes,
            "transactions": tx_data,
        }, status=status.HTTP_200_OK)


# =============================================================================
# Phase 5 Task 2: Shipping, Logistics and Order Tracking Endpoints
# =============================================================================

def _resolve_shipment_by_identifier(identifier: str):
    """Helper to resolve a Shipment by UUID or shipment_number."""
    import uuid
    from apps.marketplace.models import Shipment
    try:
        uuid.UUID(str(identifier))
        return Shipment.objects.filter(id=identifier).select_related('order', 'seller', 'organisation').first()
    except (ValueError, AttributeError):
        return Shipment.objects.filter(shipment_number=identifier).select_related('order', 'seller', 'organisation').first()


def _is_seller_authorized_for_order(user, order) -> bool:
    """Checks if the user is a staff member or seller owning items in the order."""
    if user.is_staff or user.is_superuser:
        return True
    from apps.organisations.models import OrganisationMembership, OrganisationRoleChoices
    org_ids = set(OrganisationMembership.objects.filter(
        user=user,
        is_active=True,
        role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
    ).values_list('organisation_id', flat=True))

    return order.items.filter(
        models.Q(listing__seller=user) | models.Q(listing__organisation_id__in=org_ids)
    ).exists()


def _is_seller_authorized_for_shipment(user, shipment) -> bool:
    """Checks if the user is a staff member or the seller who owns the shipment."""
    if user.is_staff or user.is_superuser:
        return True
    if shipment.seller_id == user.id:
        return True
    if shipment.organisation_id:
        from apps.organisations.models import OrganisationMembership, OrganisationRoleChoices
        return OrganisationMembership.objects.filter(
            user=user,
            organisation_id=shipment.organisation_id,
            is_active=True,
            role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
        ).exists()
    return False


class SellerOrderShipmentListCreateView(views.APIView):
    """
    POST: Creates a fulfillment shipment for the seller's items in an order.
    GET: Lists shipments for this order owned by the seller.
    POST /api/v1/marketplace/seller/orders/<identifier>/shipments/
    GET  /api/v1/marketplace/seller/orders/<identifier>/shipments/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, identifier):
        order = _resolve_order_by_identifier(identifier)
        if not order:
            return Response({"error": f"Order '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        if not _is_seller_authorized_for_order(request.user, order):
            return Response({"error": "You do not have permission to view shipments for this order."}, status=status.HTTP_403_FORBIDDEN)

        user = request.user
        if user.is_staff or user.is_superuser:
            shipments = order.shipments.all().prefetch_related('items__order_item', 'tracking_events')
        else:
            from apps.organisations.models import OrganisationMembership, OrganisationRoleChoices
            org_ids = set(OrganisationMembership.objects.filter(
                user=user,
                is_active=True,
                role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
            ).values_list('organisation_id', flat=True))

            shipments = order.shipments.filter(
                models.Q(seller=user) | models.Q(organisation_id__in=org_ids)
            ).prefetch_related('items__order_item', 'tracking_events').distinct()

        serializer = ShipmentSerializer(shipments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, identifier):
        order = _resolve_order_by_identifier(identifier)
        if not order:
            return Response({"error": f"Order '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        if not _is_seller_authorized_for_order(request.user, order):
            return Response({"error": "You do not have permission to create shipments for this order."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ShipmentCreatePayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            shipment = ShipmentService.create_seller_shipment(
                order=order,
                seller=request.user,
                items_payload=data['items'],
                carrier=data.get('carrier', CarrierChoices.OTHER),
                carrier_name=data.get('carrier_name', ''),
                tracking_number=data.get('tracking_number', ''),
                tracking_url=data.get('tracking_url', ''),
                estimated_delivery_at=data.get('estimated_delivery_at'),
                delivery_notes=data.get('delivery_notes', ''),
                dispatch_immediately=data.get('dispatch_immediately', False),
                actor=request.user,
            )
            return Response(
                {
                    "status": "success",
                    "message": f"Shipment {shipment.shipment_number} created successfully.",
                    "shipment": ShipmentSerializer(shipment).data,
                },
                status=status.HTTP_201_CREATED,
            )
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SellerShipmentDetailView(views.APIView):
    """
    Retrieves full details and tracking timeline for a specific shipment.
    GET /api/v1/marketplace/seller/shipments/<identifier>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, identifier):
        shipment = _resolve_shipment_by_identifier(identifier)
        if not shipment:
            return Response({"error": f"Shipment '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        if not _is_seller_authorized_for_shipment(request.user, shipment):
            return Response({"error": "You do not have permission to view this shipment."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ShipmentSerializer(shipment)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SellerShipmentStatusUpdateView(views.APIView):
    """
    Updates the lifecycle status of a shipment (e.g. DISPATCHED, IN_TRANSIT, DELIVERED).
    PATCH /api/v1/marketplace/seller/shipments/<identifier>/status/
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, identifier):
        shipment = _resolve_shipment_by_identifier(identifier)
        if not shipment:
            return Response({"error": f"Shipment '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        if not _is_seller_authorized_for_shipment(request.user, shipment):
            return Response({"error": "You do not have permission to update this shipment."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ShipmentStatusUpdatePayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            updated_shipment = ShipmentService.update_shipment_status(
                shipment=shipment,
                new_status=data['status'],
                location=data.get('location', ''),
                description=data.get('description', ''),
                carrier_reference=data.get('carrier_reference', ''),
                actor=request.user,
            )
            return Response(
                {
                    "status": "success",
                    "message": f"Shipment {updated_shipment.shipment_number} status updated to '{updated_shipment.status}'.",
                    "shipment": ShipmentSerializer(updated_shipment).data,
                },
                status=status.HTTP_200_OK,
            )
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SellerShipmentTrackingEventCreateView(views.APIView):
    """
    Appends an operational or carrier checkpoint tracking event to a shipment.
    POST /api/v1/marketplace/seller/shipments/<identifier>/events/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        shipment = _resolve_shipment_by_identifier(identifier)
        if not shipment:
            return Response({"error": f"Shipment '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        if not _is_seller_authorized_for_shipment(request.user, shipment):
            return Response({"error": "You do not have permission to update tracking for this shipment."}, status=status.HTTP_403_FORBIDDEN)

        serializer = TrackingEventCreatePayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        event = ShipmentService.add_tracking_event(
            shipment=shipment,
            status=data.get('status') or shipment.status,
            description=data['description'],
            location=data.get('location', ''),
            event_timestamp=data.get('event_timestamp'),
            external_checkpoint_id=data.get('external_checkpoint_id', ''),
            actor=request.user,
        )

        return Response(
            {
                "status": "success",
                "message": "Tracking event recorded successfully.",
                "event": TrackingEventSerializer(event).data,
                "shipment": ShipmentSerializer(shipment).data,
            },
            status=status.HTTP_201_CREATED,
        )


class BuyerOrderShipmentListView(views.APIView):
    """
    Lists all shipments and delivery tracking timelines for an order owned by the authenticated buyer.
    GET /api/v1/marketplace/buyer/orders/<identifier>/shipments/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, identifier):
        order = _resolve_order_by_identifier(identifier)
        if not order:
            return Response({"error": f"Order '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        # Buyer ownership check (or staff)
        if order.buyer_id != request.user.id and not (request.user.is_staff or request.user.is_superuser):
            return Response({"error": "You do not have permission to view shipments for this order."}, status=status.HTTP_403_FORBIDDEN)

        shipments = order.shipments.all().prefetch_related('items__order_item', 'tracking_events')
        serializer = ShipmentSerializer(shipments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ShipmentTrackingLookupView(views.APIView):
    """
    Direct tracking lookup by tracking number or shipment reference number.
    Access is open to the buyer of the order, seller of the shipment, or staff.
    GET /api/v1/marketplace/shipments/track/<tracking_number>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, tracking_number):
        from apps.marketplace.models import Shipment
        shipment = Shipment.objects.filter(
            models.Q(tracking_number=tracking_number) | models.Q(shipment_number=tracking_number)
        ).select_related('order', 'seller', 'organisation').prefetch_related('items__order_item', 'tracking_events').first()

        if not shipment:
            return Response({"error": f"No shipment found with tracking reference '{tracking_number}'."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        is_staff = user.is_staff or user.is_superuser
        is_buyer = shipment.order.buyer_id == user.id
        is_seller = _is_seller_authorized_for_shipment(user, shipment)

        if not (is_staff or is_buyer or is_seller):
            return Response({"error": "You do not have permission to view this tracking information."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ShipmentSerializer(shipment)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AvailableCarriersView(views.APIView):
    """
    Returns supported logistics carriers appropriate for the order's destination country.
    GET /api/v1/marketplace/logistics/carriers/?country=India
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        country = request.query_params.get('country', 'India')
        from apps.marketplace.pricing import normalize_destination_country
        try:
            country_iso, _ = normalize_destination_country(country)
        except Exception:
            country_iso = 'IN' if str(country).strip().upper() in ['IN', 'INDIA'] else 'GB'
        carriers = get_available_carriers_for_country(country_iso)
        return Response({
            "country": country_iso,
            "count": len(carriers),
            "carriers": carriers,
        }, status=status.HTTP_200_OK)


# =============================================================================
# Phase 5 Task 3: Returns, Refunds & Dispute Management API Views
# =============================================================================

from apps.marketplace.models import (
    ReturnRequest,
    ReturnRequestTypeChoices,
    ReturnRequestStatusChoices,
    ReturnReasonChoices,
    Refund,
    RefundStatusChoices,
    RefundMethodChoices,
    Dispute,
    DisputeEvent,
    DisputeCategoryChoices,
    DisputeStatusChoices,
    DisputePriorityChoices,
    DisputeResolutionChoices,
    DisputeEventTypeChoices,
)
from apps.marketplace.returns.service import (
    ReturnService,
    RefundService,
    DisputeService,
    _is_staff_or_admin,
    _has_permission,
    _is_seller_authorized_for_order,
    _is_seller_authorized_for_return,
)
from apps.marketplace.serializers import (
    ReturnRequestSerializer,
    ReturnRequestCreatePayloadSerializer,
    ReturnRequestReviewPayloadSerializer,
    RefundSerializer,
    RefundCreatePayloadSerializer,
    DisputeSerializer,
    DisputeEventSerializer,
    DisputeCreatePayloadSerializer,
    DisputeStatusUpdatePayloadSerializer,
    DisputeMessagePayloadSerializer,
)


def _resolve_return_by_identifier(identifier: str):
    """Helper to resolve a ReturnRequest by UUID or request_number."""
    import uuid
    from apps.marketplace.models import ReturnRequest
    try:
        uuid.UUID(str(identifier))
        return ReturnRequest.objects.filter(id=identifier).select_related('order', 'order_item', 'buyer', 'seller', 'reviewed_by').first()
    except (ValueError, AttributeError):
        return ReturnRequest.objects.filter(request_number=identifier).select_related('order', 'order_item', 'buyer', 'seller', 'reviewed_by').first()


def _resolve_dispute_by_identifier(identifier: str):
    """Helper to resolve a Dispute by UUID or dispute_number."""
    import uuid
    from apps.marketplace.models import Dispute
    try:
        uuid.UUID(str(identifier))
        return Dispute.objects.filter(id=identifier).select_related('order', 'buyer', 'seller', 'resolved_by').first()
    except (ValueError, AttributeError):
        return Dispute.objects.filter(dispute_number=identifier).select_related('order', 'buyer', 'seller', 'resolved_by').first()


def _resolve_refund_by_identifier(identifier: str):
    """Helper to resolve a Refund by UUID or refund_number."""
    import uuid
    from apps.marketplace.models import Refund
    try:
        uuid.UUID(str(identifier))
        return Refund.objects.filter(id=identifier).select_related('order', 'return_request', 'dispute', 'created_by', 'approved_by').first()
    except (ValueError, AttributeError):
        return Refund.objects.filter(refund_number=identifier).select_related('order', 'return_request', 'dispute', 'created_by', 'approved_by').first()


class BuyerOrderReturnEligibilityView(views.APIView):
    """
    GET /api/v1/marketplace/buyer/orders/<identifier>/return-eligibility/
    Evaluates cancellation and return eligibility for an order and its items.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, identifier):
        order = _resolve_order_by_identifier(identifier)
        if not order:
            return Response({"error": f"Order '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        if order.buyer_id != request.user.id and not _is_staff_or_admin(request.user):
            return Response({"error": "You do not have permission to inspect this order."}, status=status.HTTP_403_FORBIDDEN)

        can_cancel, cancel_reason, cancel_amount = ReturnService.get_cancellation_eligibility(order, request.user)
        can_return, return_reason, return_amount = ReturnService.get_return_eligibility(order, request.user)

        items_eligibility = []
        for item in order.items.all():
            i_can_cancel, i_cancel_reason, i_cancel_amt = ReturnService.get_cancellation_eligibility(order, request.user, order_item=item)
            i_can_return, i_return_reason, i_return_amt = ReturnService.get_return_eligibility(order, request.user, order_item=item)
            items_eligibility.append({
                "order_item_id": str(item.id),
                "title": item.title,
                "quantity": item.quantity,
                "total_amount": str(item.total_amount),
                "cancellation": {
                    "eligible": i_can_cancel,
                    "reason": i_cancel_reason,
                    "estimated_refund": str(i_cancel_amt),
                },
                "return": {
                    "eligible": i_can_return,
                    "reason": i_return_reason,
                    "estimated_refund": str(i_return_amt),
                },
            })

        return Response({
            "order_number": order.order_number,
            "currency": order.currency,
            "order_total": str(order.total_amount),
            "order_status": order.status,
            "payment_status": order.payment_status,
            "order_cancellation": {
                "eligible": can_cancel,
                "reason": cancel_reason,
                "estimated_refund": str(cancel_amount),
            },
            "order_return": {
                "eligible": can_return,
                "reason": return_reason,
                "estimated_refund": str(return_amount),
            },
            "items": items_eligibility,
        }, status=status.HTTP_200_OK)


class BuyerOrderReturnRequestCreateView(views.APIView):
    """
    POST /api/v1/marketplace/buyer/orders/<identifier>/returns/
    Creates a cancellation or return request for the order or a specific item.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        order = _resolve_order_by_identifier(identifier)
        if not order:
            return Response({"error": f"Order '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        if order.buyer_id != request.user.id and not _is_staff_or_admin(request.user):
            return Response({"error": "You can only create return/cancellation requests for your own orders."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ReturnRequestCreatePayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        order_item = None
        item_id = data.get('order_item_id')
        if item_id:
            order_item = order.items.filter(id=item_id).first()
            if not order_item:
                return Response({"error": f"Item '{item_id}' not found in order {order.order_number}."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            req = ReturnService.create_return_request(
                order=order,
                buyer=request.user,
                request_type=data.get('request_type', ReturnRequestTypeChoices.RETURN),
                reason=data['reason'],
                description=data['description'],
                evidence_urls=data.get('evidence_urls', []),
                order_item=order_item,
                requested_quantity=data.get('requested_quantity', 1),
                actor=request.user,
            )
            return Response({
                "status": "success",
                "message": f"{req.get_request_type_display()} request {req.request_number} submitted successfully.",
                "return_request": ReturnRequestSerializer(req).data,
            }, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class BuyerReturnRequestListView(generics.ListAPIView):
    """
    GET /api/v1/marketplace/buyer/returns/
    Lists all return and cancellation requests created by the buyer.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ReturnRequestSerializer

    def get_queryset(self):
        qs = ReturnRequest.objects.filter(buyer=self.request.user).select_related('order', 'order_item', 'buyer', 'seller', 'reviewed_by')
        req_type = self.request.query_params.get('type')
        if req_type:
            qs = qs.filter(request_type=req_type.strip().upper())
        st = self.request.query_params.get('status')
        if st:
            qs = qs.filter(status=st.strip().upper())
        return qs


class BuyerReturnRequestDetailView(views.APIView):
    """
    GET /api/v1/marketplace/buyer/returns/<identifier>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, identifier):
        req = _resolve_return_by_identifier(identifier)
        if not req or req.buyer_id != request.user.id:
            return Response({"error": "Return request not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ReturnRequestSerializer(req).data, status=status.HTTP_200_OK)


class BuyerReturnRequestCancelView(views.APIView):
    """
    POST /api/v1/marketplace/buyer/returns/<identifier>/cancel/
    Allows buyer to withdraw their pending return request.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        req = _resolve_return_by_identifier(identifier)
        if not req or req.buyer_id != request.user.id:
            return Response({"error": "Return request not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            updated = ReturnService.cancel_return_request_by_buyer(req, request.user)
            return Response({
                "status": "success",
                "message": f"Request {updated.request_number} has been cancelled.",
                "return_request": ReturnRequestSerializer(updated).data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SellerReturnRequestListView(generics.ListAPIView):
    """
    GET /api/v1/marketplace/seller/returns/
    Lists returns relating to the authenticated seller or seller's organisation.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ReturnRequestSerializer

    def get_queryset(self):
        user = self.request.user
        if _is_staff_or_admin(user):
            qs = ReturnRequest.objects.all()
        else:
            from apps.organisations.models import OrganisationMembership, OrganisationRoleChoices
            org_ids = set(OrganisationMembership.objects.filter(
                user=user,
                is_active=True,
                role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
            ).values_list('organisation_id', flat=True))

            qs = ReturnRequest.objects.filter(
                models.Q(seller=user) | models.Q(order_item__listing__organisation_id__in=org_ids)
            ).distinct()

        st = self.request.query_params.get('status')
        if st:
            qs = qs.filter(status=st.strip().upper())
        req_type = self.request.query_params.get('type')
        if req_type:
            qs = qs.filter(request_type=req_type.strip().upper())
        return qs.select_related('order', 'order_item', 'buyer', 'seller', 'reviewed_by')


class SellerReturnRequestDetailView(views.APIView):
    """
    GET /api/v1/marketplace/seller/returns/<identifier>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, identifier):
        req = _resolve_return_by_identifier(identifier)
        if not req:
            return Response({"error": "Return request not found."}, status=status.HTTP_404_NOT_FOUND)

        if not _is_seller_authorized_for_return(request.user, req):
            return Response({"error": "You do not have permission to view this return request."}, status=status.HTTP_403_FORBIDDEN)

        return Response(ReturnRequestSerializer(req).data, status=status.HTTP_200_OK)


class SellerReturnRequestReviewView(views.APIView):
    """
    POST /api/v1/marketplace/seller/returns/<identifier>/review/
    Seller approves or rejects a return request.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        req = _resolve_return_by_identifier(identifier)
        if not req:
            return Response({"error": "Return request not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ReturnRequestReviewPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            updated = ReturnService.review_return_request(
                return_request=req,
                actor=request.user,
                action=data['action'],
                seller_notes=data.get('seller_notes', ''),
                rejection_reason=data.get('rejection_reason', ''),
            )
            return Response({
                "status": "success",
                "message": f"Request {updated.request_number} has been {updated.status.lower()}.",
                "return_request": ReturnRequestSerializer(updated).data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SellerReturnRequestCompleteView(views.APIView):
    """
    POST /api/v1/marketplace/seller/returns/<identifier>/complete/
    Confirms physical receipt of returned item and restocks inventory.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        req = _resolve_return_by_identifier(identifier)
        if not req:
            return Response({"error": "Return request not found."}, status=status.HTTP_404_NOT_FOUND)

        notes = request.data.get('notes', '')
        try:
            completed = ReturnService.complete_return_request(
                return_request=req,
                actor=request.user,
                notes=notes,
            )
            return Response({
                "status": "success",
                "message": f"Return {completed.request_number} completed and items restocked successfully.",
                "return_request": ReturnRequestSerializer(completed).data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class BuyerOrderDisputeCreateView(views.APIView):
    """
    POST /api/v1/marketplace/buyer/orders/<identifier>/disputes/
    Buyer opens a commercial dispute for an order.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        order = _resolve_order_by_identifier(identifier)
        if not order:
            return Response({"error": f"Order '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        if order.buyer_id != request.user.id and not _is_staff_or_admin(request.user):
            return Response({"error": "You can only raise disputes for your own orders."}, status=status.HTTP_403_FORBIDDEN)

        serializer = DisputeCreatePayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            dispute = DisputeService.create_dispute(
                order=order,
                buyer=request.user,
                category=data['category'],
                description=data['description'],
                evidence_urls=data.get('evidence_urls', []),
                priority=data.get('priority', DisputePriorityChoices.MEDIUM),
            )
            return Response({
                "status": "success",
                "message": f"Dispute {dispute.dispute_number} created successfully.",
                "dispute": DisputeSerializer(dispute).data,
            }, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class BuyerDisputeListView(generics.ListAPIView):
    """
    GET /api/v1/marketplace/buyer/disputes/
    Lists disputes raised by the buyer.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DisputeSerializer

    def get_queryset(self):
        return Dispute.objects.filter(buyer=self.request.user).select_related('order', 'buyer', 'seller', 'resolved_by').prefetch_related('events__actor')


class SellerDisputeListView(generics.ListAPIView):
    """
    GET /api/v1/marketplace/seller/disputes/
    Lists disputes involving the seller's items/orders.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DisputeSerializer

    def get_queryset(self):
        user = self.request.user
        if _is_staff_or_admin(user):
            return Dispute.objects.all().select_related('order', 'buyer', 'seller', 'resolved_by').prefetch_related('events__actor')

        from apps.organisations.models import OrganisationMembership, OrganisationRoleChoices
        org_ids = set(OrganisationMembership.objects.filter(
            user=user,
            is_active=True,
            role__in=[OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN],
        ).values_list('organisation_id', flat=True))

        return Dispute.objects.filter(
            models.Q(seller=user) | models.Q(order__items__listing__organisation_id__in=org_ids)
        ).distinct().select_related('order', 'buyer', 'seller', 'resolved_by').prefetch_related('events__actor')


class DisputeDetailView(views.APIView):
    """
    GET /api/v1/marketplace/disputes/<identifier>/
    Accessible to buyer, seller, or staff.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, identifier):
        dispute = _resolve_dispute_by_identifier(identifier)
        if not dispute:
            return Response({"error": "Dispute not found."}, status=status.HTTP_404_NOT_FOUND)

        is_buyer = dispute.buyer_id == request.user.id
        is_seller = dispute.seller_id == request.user.id or _is_seller_authorized_for_order(request.user, dispute.order)
        is_staff = _is_staff_or_admin(request.user) or _has_permission(request.user, 'dispute.manage')

        if not (is_buyer or is_seller or is_staff):
            return Response({"error": "You do not have permission to view this dispute."}, status=status.HTTP_403_FORBIDDEN)

        return Response(DisputeSerializer(dispute).data, status=status.HTTP_200_OK)


class DisputeMessageCreateView(views.APIView):
    """
    POST /api/v1/marketplace/disputes/<identifier>/messages/
    Allows buyer, seller, or staff to post messages and evidence to the dispute thread.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        dispute = _resolve_dispute_by_identifier(identifier)
        if not dispute:
            return Response({"error": "Dispute not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = DisputeMessagePayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            evt = DisputeService.add_dispute_message(
                dispute=dispute,
                actor=request.user,
                message=data['message'],
                attachments=data.get('attachments', []),
            )
            return Response({
                "status": "success",
                "message": "Message posted successfully.",
                "event": DisputeEventSerializer(evt).data,
            }, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_403_FORBIDDEN if "Permission" in str(e) else status.HTTP_400_BAD_REQUEST)


class OrderRefundSummaryView(views.APIView):
    """
    GET /api/v1/marketplace/orders/<identifier>/refund-summary/
    Calculates current refundable balance, paid amount, and existing refunds.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, identifier):
        order = _resolve_order_by_identifier(identifier)
        if not order:
            return Response({"error": f"Order '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        is_authorized = (
            order.buyer_id == request.user.id
            or _is_seller_authorized_for_order(request.user, order)
            or _is_staff_or_admin(request.user)
            or _has_permission(request.user, 'order.refund')
        )
        if not is_authorized:
            return Response({"error": "Permission denied to inspect refund summary."}, status=status.HTTP_403_FORBIDDEN)

        summary = RefundService.get_order_refund_summary(order)
        return Response(summary, status=status.HTTP_200_OK)


class AdminOrderRefundCreateView(views.APIView):
    """
    POST /api/v1/marketplace/admin/orders/<identifier>/refund/
    Staff or Admin issues a refund for an order.
    Requires 'order.refund' permission.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        order = _resolve_order_by_identifier(identifier)
        if not order:
            return Response({"error": f"Order '{identifier}' not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = RefundCreatePayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        return_request = None
        if data.get('return_request_id'):
            return_request = _resolve_return_by_identifier(data['return_request_id'])
            if return_request and return_request.order_id != order.id:
                return_request = None

        dispute = None
        if data.get('dispute_id'):
            dispute = _resolve_dispute_by_identifier(data['dispute_id'])
            if dispute and dispute.order_id != order.id:
                dispute = None

        try:
            refund = RefundService.create_refund(
                order=order,
                amount=data['amount'],
                reason=data['reason'],
                actor=request.user,
                return_request=return_request,
                dispute=dispute,
                refund_method=data.get('refund_method'),
                notes=data.get('notes', ''),
                auto_process=data.get('auto_process', False),
            )
            return Response({
                "status": "success",
                "message": f"Refund {refund.refund_number} ({refund.currency} {refund.amount}) created successfully.",
                "refund": RefundSerializer(refund).data,
            }, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminRefundListView(generics.ListAPIView):
    """
    GET /api/v1/marketplace/admin/refunds/
    Lists all platform refunds for operations staff.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RefundSerializer

    def get_queryset(self):
        user = self.request.user
        if not (_is_staff_or_admin(user) or _has_permission(user, 'order.refund') or _has_permission(user, 'finance.payout')):
            raise PermissionDenied("You do not have permission to view platform refunds.")
        qs = Refund.objects.all().select_related('order', 'return_request', 'dispute', 'created_by', 'approved_by')
        st = self.request.query_params.get('status')
        if st:
            qs = qs.filter(status=st.strip().upper())
        return qs


class AdminRefundProcessView(views.APIView):
    """
    POST /api/v1/marketplace/admin/refunds/<identifier>/process/
    Marks a pending or manual refund as processed/settled.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        refund = _resolve_refund_by_identifier(identifier)
        if not refund:
            return Response({"error": "Refund not found."}, status=status.HTTP_404_NOT_FOUND)

        gateway_reference = request.data.get('gateway_reference', '')
        notes = request.data.get('notes', '')

        try:
            processed = RefundService.process_refund(
                refund=refund,
                actor=request.user,
                gateway_reference=gateway_reference,
                notes=notes,
            )
            return Response({
                "status": "success",
                "message": f"Refund {processed.refund_number} marked as {processed.status}.",
                "refund": RefundSerializer(processed).data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AdminDisputeListView(generics.ListAPIView):
    """
    GET /api/v1/marketplace/admin/disputes/
    Lists all commercial disputes for adjudication by staff with 'dispute.manage'.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DisputeSerializer

    def get_queryset(self):
        user = self.request.user
        if not (_is_staff_or_admin(user) or _has_permission(user, 'dispute.manage')):
            raise PermissionDenied("You do not have permission to review disputes.")
        qs = Dispute.objects.all().select_related('order', 'buyer', 'seller', 'resolved_by').prefetch_related('events__actor')
        st = self.request.query_params.get('status')
        if st:
            qs = qs.filter(status=st.strip().upper())
        cat = self.request.query_params.get('category')
        if cat:
            qs = qs.filter(category=cat.strip().upper())
        return qs


class AdminDisputeStatusUpdateView(views.APIView):
    """
    POST /api/v1/marketplace/admin/disputes/<identifier>/status/
    Adjudicates a dispute, changes its status, and records official decisions.
    Requires 'dispute.manage' permission.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        dispute = _resolve_dispute_by_identifier(identifier)
        if not dispute:
            return Response({"error": "Dispute not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = DisputeStatusUpdatePayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            updated = DisputeService.update_dispute_status(
                dispute=dispute,
                actor=request.user,
                new_status=data['status'],
                resolution=data.get('resolution', ''),
                resolution_notes=data.get('resolution_notes', ''),
            )
            return Response({
                "status": "success",
                "message": f"Dispute {updated.dispute_number} updated to {updated.status}.",
                "dispute": DisputeSerializer(updated).data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


