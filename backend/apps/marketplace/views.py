from rest_framework import generics, permissions, status, views
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError
from django.db import transaction
from django.db.models import Q, F
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from common.permissions import IsPlatformStaff, HasPermission
from platform_core.audit.writer import record_audit_entry
from apps.marketplace.models import (
    VehicleListing,
    SparePartListing,
    ListingStatusChoices,
    StockMovementReasonChoices,
)
from apps.marketplace.serializers import (
    VehicleListingSellerSerializer,
    SparePartListingSellerSerializer,
    VehicleListingPublicSerializer,
    SparePartListingPublicSerializer,
    ListingReviewSerializer,
    StockMovementSerializer,
    StockAdjustmentSerializer,
)
from apps.marketplace.services import adjust_stock


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


class MarketplacePartListView(generics.ListAPIView):
    """Public / Buyer endpoint to search and browse approved spare parts for sale.

    GET /api/v1/marketplace/browse/parts/
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = SparePartListingPublicSerializer

    def get_queryset(self):
        queryset = SparePartListing.objects.filter(
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        ).select_related('category', 'seller', 'organisation').prefetch_related('compatible_variants')

        params = self.request.query_params

        category = params.get('category') or params.get('category_id')
        category_slug = params.get('category_slug')
        if category:
            queryset = queryset.filter(Q(category_id=category) | Q(category__parent_id=category))
        elif category_slug:
            queryset = queryset.filter(
                Q(category__slug=category_slug) | Q(category__parent__slug=category_slug)
            )

        brand = params.get('brand')
        if brand:
            queryset = queryset.filter(brand__iexact=brand)

        mpn = params.get('mpn')
        if mpn:
            queryset = queryset.filter(mpn__icontains=mpn)

        price_min = params.get('price_min')
        if price_min:
            queryset = queryset.filter(price__gte=price_min)
        price_max = params.get('price_max')
        if price_max:
            queryset = queryset.filter(price__lte=price_max)

        variant_id = params.get('variant_id') or params.get('vehicle_variant_id')
        if variant_id:
            queryset = queryset.filter(compatible_variants__id=variant_id)

        search = params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(brand__icontains=search)
                | Q(mpn__icontains=search)
                | Q(description__icontains=search)
            )

        return queryset.distinct()


class MarketplacePartDetailView(generics.RetrieveAPIView):
    """Public / Buyer endpoint to view full details of an approved spare part for sale.

    GET /api/v1/marketplace/browse/parts/<id>/
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = SparePartListingPublicSerializer
    lookup_field = 'id'

    def get_queryset(self):
        return SparePartListing.objects.filter(
            status=ListingStatusChoices.APPROVED,
            is_active=True,
        ).select_related('category', 'seller', 'organisation').prefetch_related('compatible_variants')


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
                'price', 'description', 'name', 'brand', 'mpn', 'oem_numbers',
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
    serializer_class = SparePartListingSellerSerializer

    def get_queryset(self):
        queryset = SparePartListing.objects.all().select_related(
            'category', 'seller', 'organisation', 'reviewed_by'
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
    serializer_class = SparePartListingSellerSerializer
    lookup_field = 'id'
    queryset = SparePartListing.objects.all().select_related(
        'category', 'seller', 'organisation', 'reviewed_by'
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

        detail_serializer = SparePartListingSellerSerializer(listing, context={'request': request})
        return Response(
            {
                "status": "success",
                "message": f"Spare part listing {action.lower()}d successfully.",
                "listing": detail_serializer.data,
            },
            status=status.HTTP_200_OK,
        )
