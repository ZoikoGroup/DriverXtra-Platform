import logging
from decimal import Decimal, ROUND_HALF_UP
from apps.identity.models import User
from apps.catalogue.models import Part
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import generics, status, views, permissions
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError

logger = logging.getLogger(__name__)

from apps.workshops.models import (
    WorkshopProfile,
    WorkshopOperatingHours,
    WorkshopServiceCategory,
    WorkshopService,
    WorkshopBooking,
    WorkshopQuotation,
    DayOfWeekChoices,
    BookingStatusChoices,
    QuotationStatusChoices,
    DepositStatusChoices,
    WorkOrder,
    WorkOrderTask,
    WorkOrderPartUsage,
    WorkOrderStatusChoices,
    WorkOrderTaskStatusChoices,
    WorkOrderSettlementStatusChoices,
    WorkOrderInvoice,
    WorkOrderInvoiceStatusChoices,
    ChangeOrder,
    ChangeOrderLineItem,
    ChangeOrderStatusChoices,
    WorkshopReview,
    ReviewStatusChoices,
    WorkshopConversation,
    WorkshopMessage,
)
from apps.workshops.serializers import (
    WorkshopProfilePublicSerializer,
    WorkshopProfileManageSerializer,
    WorkshopOperatingHoursSerializer,
    WorkshopServiceCategorySerializer,
    WorkshopServiceSerializer,
    WorkshopBookingDetailSerializer,
    BuyerBookingCreateSerializer,
    BookingStatusUpdateSerializer,
    BookingCancellationSerializer,
    WorkshopQuotationSerializer,
    QuotationCreateUpdateSerializer,
    QuotationResponseSerializer,
    QuotationDepositSessionCreateSerializer,
    QuotationDepositVerifySerializer,
    WorkOrderSerializer,
    WorkOrderListSerializer,
    WorkOrderTaskSerializer,
    WorkOrderPartUsageSerializer,
    WorkOrderAssignTechnicianSerializer,
    WorkOrderStatusUpdateSerializer,
    WorkOrderTaskCreateUpdateSerializer,
    WorkOrderPartUsageCreateSerializer,
    WorkshopTechnicianMemberSerializer,
    BuyerWorkOrderSerializer,
    WorkOrderPaymentSerializer,
    WorkOrderInvoiceSerializer,
    WorkOrderSettlementDetailSerializer,
    ChangeOrderSerializer,
    BuyerChangeOrderSerializer,
    ChangeOrderCreateSerializer,
    ChangeOrderDecisionSerializer,
    AdminWorkshopTaxAuthorizationSerializer,
    WorkshopReviewSerializer,
    WorkshopReviewCreateSerializer,
    WorkshopReviewReplySerializer,
    WorkshopReviewModerationSerializer,
    WorkshopConversationSerializer,
    WorkshopMessageSerializer,
    CreateWorkshopMessageSerializer,
)
from apps.workshops.services import (
    BookingService,
    QuotationService,
    WorkOrderService,
    ChangeOrderService,
    CapacityExceededError,
    WorkshopTaxAuthorizationService,
    WorkshopReviewService,
)
from apps.workshops.deposit_service import WorkshopDepositPaymentService
from apps.workshops.settlement_service import WorkOrderSettlementService
from apps.workshops.permissions import (
    IsWorkshopOwnerOrAdmin,
    IsWorkshopStaffOrMember,
    IsBookingBuyerOrWorkshopStaff,
    is_platform_admin_or_staff,
)
from apps.organisations.models import Organisation, OrganisationTypeChoices, OrganisationRoleChoices


def get_user_workshop_profile(user_or_request, organisation_id=None) -> WorkshopProfile:
    """
    Resolves the WorkshopProfile associated with an authenticated user's active WORKSHOP organisation.

    Strictly READ-ONLY: does not create or modify Organisation, Membership, or WorkshopProfile records.
    Detects ambiguous multiple workshop organisations if organisation_id is not specified.
    """
    if hasattr(user_or_request, 'user'):
        request = user_or_request
        user = request.user
        if not organisation_id:
            organisation_id = request.headers.get('X-Organisation-ID') or request.query_params.get('organisation_id')
    else:
        user = user_or_request
        if not organisation_id:
            organisation_id = getattr(user, '_target_organisation_id', None)

    if is_platform_admin_or_staff(user):
        if organisation_id:
            profile = WorkshopProfile.objects.filter(organisation_id=organisation_id, is_verified=True).first()
            if profile:
                return profile
        # Platform admins default to first active workshop if not linked directly
        profile = WorkshopProfile.objects.filter(is_verified=True).first()
        if profile:
            return profile

    # Look for active membership in a WORKSHOP organisation
    memberships = user.organisation_memberships.filter(
        is_active=True,
        organisation__type=OrganisationTypeChoices.WORKSHOP,
        organisation__is_active=True,
    ).select_related('organisation')

    if organisation_id:
        memberships = memberships.filter(organisation_id=organisation_id)

    count = memberships.count()
    if count == 0:
        raise PermissionDenied("You are not an active member of any registered workshop organisation.")
    if count > 1:
        raise PermissionDenied("Multiple active workshop organisations found. Please specify the target organisation.")

    membership = memberships.first()
    org = membership.organisation
    try:
        return org.workshop_profile
    except (WorkshopProfile.DoesNotExist, AttributeError):
        raise PermissionDenied("No workshop profile exists for your organisation. Please contact support.")


# =========================================================
# PUBLIC / BUYER BROWSE WORKSHOPS
# =========================================================

class WorkshopListPublicView(generics.ListAPIView):
    """
    Public listing of approved workshops accepting bookings.
    GET /api/v1/workshops/
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = WorkshopProfilePublicSerializer

    def get_queryset(self):
        from django.db.models import Avg, Count
        qs = WorkshopProfile.objects.filter(
            is_verified=True,
            organisation__is_active=True,
        ).select_related('organisation').prefetch_related('services', 'operating_hours').annotate(
            avg_rating=Avg('reviews__rating', filter=Q(reviews__status=ReviewStatusChoices.APPROVED)),
            total_reviews=Count('reviews', filter=Q(reviews__status=ReviewStatusChoices.APPROVED), distinct=True),
        )

        city = self.request.query_params.get('city')
        if city:
            qs = qs.filter(city__icontains=city)

        search = self.request.query_params.get('q')
        if search:
            qs = qs.filter(
                Q(business_name__icontains=search)
                | Q(organisation__name__icontains=search)
                | Q(city__icontains=search)
                | Q(description__icontains=search)
            )

        accepting = self.request.query_params.get('accepting_only')
        if accepting and accepting.lower() in ('1', 'true', 'yes'):
            qs = qs.filter(is_accepting_bookings=True)

        min_rating = self.request.query_params.get('min_rating')
        if min_rating:
            try:
                qs = qs.filter(avg_rating__gte=float(min_rating))
            except ValueError:
                pass

        ordering = self.request.query_params.get('ordering')
        if ordering in ('-rating', '-avg_rating'):
            return qs.order_by('-avg_rating', 'business_name')
        elif ordering in ('rating', 'avg_rating'):
            return qs.order_by('avg_rating', 'business_name')

        return qs.order_by('business_name')


class WorkshopDetailPublicView(views.APIView):
    """
    Public detail of a specific workshop by UUID or slug.
    GET /api/v1/workshops/<id_or_slug>/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, id_or_slug):
        try:
            profile = WorkshopProfile.objects.select_related('organisation').prefetch_related(
                'services', 'operating_hours'
            ).get(id=id_or_slug)
        except (WorkshopProfile.DoesNotExist, ValueError, DjangoValidationError):
            profile = get_object_or_404(
                WorkshopProfile.objects.select_related('organisation').prefetch_related(
                    'services', 'operating_hours'
                ),
                slug=id_or_slug,
            )

        serializer = WorkshopProfilePublicSerializer(profile)
        return Response(serializer.data)


class WorkshopServiceCategoryListView(generics.ListAPIView):
    """
    Public listing of active workshop service categories.
    GET /api/v1/workshops/categories/
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = WorkshopServiceCategorySerializer
    queryset = WorkshopServiceCategory.objects.filter(is_active=True).order_by('display_order', 'name')


# =========================================================
# BUYER BOOKINGS & QUOTATION RESPONSES
# =========================================================

class BuyerBookingListCreateView(views.APIView):
    """
    Buyer creates a new workshop booking request or lists their own bookings.
    GET  /api/v1/workshops/bookings/my/
    POST /api/v1/workshops/bookings/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        status_filter = request.query_params.get('status')
        qs = WorkshopBooking.objects.filter(buyer=request.user).select_related(
            'workshop', 'workshop__organisation', 'buyer', 'vehicle', 'assigned_technician'
        ).prefetch_related('service_items', 'quotations', 'quotations__line_items').order_by('-created_at')

        if status_filter:
            status_val = status_filter.upper()
            if status_val == BookingStatusChoices.QUOTED:
                qs = qs.filter(
                    Q(status=BookingStatusChoices.QUOTED) |
                    Q(quotations__status=QuotationStatusChoices.ISSUED)
                ).distinct()
            else:
                qs = qs.filter(status=status_val)

        serializer = WorkshopBookingDetailSerializer(qs, many=True)
        return Response({'results': serializer.data, 'count': qs.count()})

    def post(self, request):
        serializer = BuyerBookingCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        try:
            booking = BookingService.create_booking(buyer=request.user, data=serializer.validated_data)
            output = WorkshopBookingDetailSerializer(booking)
            return Response(output.data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)


class BuyerBookingDetailView(views.APIView):
    """
    Buyer views detail of their own booking.
    GET /api/v1/workshops/bookings/my/<id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        booking = get_object_or_404(
            WorkshopBooking.objects.select_related(
                'workshop', 'workshop__organisation', 'buyer', 'vehicle', 'assigned_technician'
            ).prefetch_related('service_items', 'quotations', 'quotations__line_items'),
            id=id,
            buyer=request.user,
        )
        serializer = WorkshopBookingDetailSerializer(booking)
        return Response(serializer.data)


class BuyerBookingCancelView(views.APIView):
    """
    Buyer cancels their booking request and triggers automatic refund processing.
    POST /api/v1/workshops/bookings/<id>/cancel/
    POST /api/v1/workshops/bookings/my/<id>/cancel/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        booking = get_object_or_404(
            WorkshopBooking.objects.select_related('buyer', 'workshop', 'workshop__organisation'),
            id=id,
        )
        if booking.buyer_id != request.user.id and not request.user.is_staff and not request.user.is_superuser:
            raise PermissionDenied("You can only cancel your own bookings.")

        serializer = BookingCancellationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get('reason', '').strip() or 'Cancelled by customer'

        try:
            updated = BookingService.cancel_booking(
                booking=booking,
                reason=reason,
                actor=request.user,
            )
            data = WorkshopBookingDetailSerializer(updated).data
            refund_summary = getattr(updated, 'refund_summary', {})
            data.update({
                "cancellation_status": "CANCELLED",
                "refundable_amount": str(refund_summary.get("refundable_amount", Decimal('0.00'))),
                "refunded_amount": str(refund_summary.get("refunded_amount", Decimal('0.00'))),
                "refund_status": refund_summary.get("refund_status", "NOT_APPLICABLE"),
                "refund_details": refund_summary.get("refund_details", []),
            })
            return Response(data, status=status.HTTP_200_OK)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)


class WorkshopRefundReconcileView(views.APIView):
    """
    Inquires the external gateway to reconcile an ambiguous (PROCESSING_UNKNOWN) workshop refund.
    POST /api/v1/workshops/refunds/<id>/reconcile/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        from apps.workshops.refund_service import WorkshopRefundService
        from apps.workshops.models import WorkshopRefund
        from apps.workshops.serializers import WorkshopRefundSerializer

        rfnd = get_object_or_404(WorkshopRefund.objects.select_related('booking', 'booking__buyer'), id=id)
        if rfnd.booking.buyer_id != request.user.id and not request.user.is_staff and not request.user.is_superuser:
            raise PermissionDenied("You do not have permission to reconcile this refund.")

        try:
            reconciled_rfnd, outcome = WorkshopRefundService.reconcile_refund(refund_id=id, actor=request.user)
            return Response({
                "refund": WorkshopRefundSerializer(reconciled_rfnd).data,
                "outcome": outcome,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)


class BuyerQuotationAcceptView(views.APIView):
    """
    Buyer formally accepts an issued quotation.
    POST /api/v1/workshops/quotations/<id>/accept/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        quotation = get_object_or_404(
            WorkshopQuotation.objects.select_related('booking', 'booking__buyer', 'booking__workshop__organisation'),
            id=id,
        )
        if quotation.booking.buyer_id != request.user.id:
            raise PermissionDenied("You can only respond to quotations issued for your own bookings.")

        try:
            accepted_quote = QuotationService.accept_quotation(quotation=quotation, buyer=request.user)
            return Response(WorkshopQuotationSerializer(accepted_quote).data)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)


class BuyerQuotationRejectView(views.APIView):
    """
    Buyer rejects an issued quotation with optional feedback.
    POST /api/v1/workshops/quotations/<id>/reject/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        quotation = get_object_or_404(
            WorkshopQuotation.objects.select_related('booking', 'booking__buyer', 'booking__workshop__organisation'),
            id=id,
        )
        if quotation.booking.buyer_id != request.user.id:
            raise PermissionDenied("You can only respond to quotations issued for your own bookings.")

        serializer = QuotationResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get('rejection_reason', '')

        try:
            rejected_quote = QuotationService.reject_quotation(
                quotation=quotation,
                buyer=request.user,
                reason=reason,
            )
            return Response(WorkshopQuotationSerializer(rejected_quote).data)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)


class QuotationDepositSessionCreateView(views.APIView):
    """
    Buyer initiates an authoritative payment session for a quotation deposit.
    POST /api/v1/workshops/quotations/<id>/deposit/create/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        quotation = get_object_or_404(
            WorkshopQuotation.objects.select_related('booking', 'booking__buyer', 'booking__workshop__organisation'),
            id=id,
        )
        if quotation.booking.buyer_id != request.user.id:
            raise PermissionDenied("You can only pay deposits for quotations issued for your own bookings.")

        serializer = QuotationDepositSessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            session_data = WorkshopDepositPaymentService.create_deposit_session(
                quotation=quotation,
                buyer=request.user,
                preferred_provider=serializer.validated_data.get('preferred_provider'),
                return_url=serializer.validated_data.get('return_url'),
                cancel_url=serializer.validated_data.get('cancel_url'),
            )
            return Response(session_data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)
        except RuntimeError as exc:
            return Response({'status': 'error', 'message': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class QuotationDepositVerifyView(views.APIView):
    """
    Buyer verifies payment gateway confirmation payload for quotation deposit.
    Cryptographically validates HMAC signature or gateway intent status,
    transitions deposit to PAID, quotation to ACCEPTED, and creates WorkOrder.
    POST /api/v1/workshops/quotations/<id>/deposit/verify/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        quotation = get_object_or_404(
            WorkshopQuotation.objects.select_related('booking', 'booking__buyer', 'booking__workshop__organisation'),
            id=id,
        )
        if quotation.booking.buyer_id != request.user.id:
            raise PermissionDenied("You can only verify deposits for quotations issued for your own bookings.")

        serializer = QuotationDepositVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            verified_quotation = WorkshopDepositPaymentService.verify_deposit_payment(
                quotation_id=quotation.id,
                payload=serializer.validated_data,
                actor=request.user,
                preferred_provider=serializer.validated_data.get('preferred_provider'),
            )
            return Response({
                'status': 'success',
                'message': 'Deposit verified successfully. Quotation accepted and booking confirmed.',
                'quotation': WorkshopQuotationSerializer(verified_quotation).data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)


class QuotationDepositDetailView(views.APIView):
    """
    Inspect deposit status and payment details for a quotation.
    GET /api/v1/workshops/quotations/<id>/deposit/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        quotation = get_object_or_404(
            WorkshopQuotation.objects.select_related('booking', 'booking__buyer', 'booking__workshop'),
            id=id,
        )
        is_buyer = quotation.booking.buyer_id == request.user.id
        from apps.workshops.permissions import is_platform_admin_or_staff, is_workshop_staff_or_admin
        is_staff = is_platform_admin_or_staff(request.user) or is_workshop_staff_or_admin(request.user, quotation.booking.workshop)
        if not (is_buyer or is_staff):
            raise PermissionDenied("You do not have permission to view deposit details for this quotation.")

        return Response({
            'quotation_id': str(quotation.id),
            'quotation_number': quotation.quotation_number,
            'booking_number': quotation.booking.booking_number,
            'requires_deposit': quotation.requires_deposit,
            'deposit_percentage': str(quotation.deposit_percentage),
            'deposit_amount': str(quotation.deposit_amount),
            'deposit_status': quotation.deposit_status,
            'deposit_provider': quotation.deposit_provider,
            'deposit_order_id': quotation.deposit_order_id,
            'deposit_transaction_id': quotation.deposit_transaction_id,
            'deposit_paid_at': quotation.deposit_paid_at.isoformat() if quotation.deposit_paid_at else None,
            'total_amount': str(quotation.total_amount),
            'currency': quotation.currency,
        })


class QuotationDepositWebhookView(views.APIView):
    """
    Public webhook receiver for payment gateway callbacks (Razorpay/Stripe).
    No authentication required as it is signed by the payment gateway.
    POST /api/v1/workshops/deposit/webhook/<str:provider>/
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, provider):
        headers = {k: v for k, v in request.headers.items()}
        success, message = WorkshopDepositPaymentService.process_deposit_webhook(
            provider_name=provider,
            request_body=request.body,
            headers=headers,
        )
        if success:
            return Response({'status': 'success', 'message': message}, status=status.HTTP_200_OK)
        return Response({'status': 'error', 'message': message}, status=status.HTTP_400_BAD_REQUEST)




# =========================================================
# WORKSHOP OWNER / STAFF MANAGEMENT ENDPOINTS
# =========================================================

class WorkshopProfileManageView(views.APIView):
    """
    Retrieve or update the workshop profile for the authenticated workshop user's organisation.
    GET   /api/v1/workshops/manage/profile/
    PATCH /api/v1/workshops/manage/profile/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = get_user_workshop_profile(request)
        serializer = WorkshopProfilePublicSerializer(profile)
        return Response(serializer.data)

    def patch(self, request):
        profile = get_user_workshop_profile(request)
        # Verify Owner or Admin role
        is_staff_user = is_platform_admin_or_staff(request.user)
        if not is_staff_user:
            role = profile.organisation.get_member_role(request.user)
            if role not in (OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN):
                raise PermissionDenied("Only workshop Owners and Admins can update profile settings.")
            if 'can_collect_tax' in request.data:
                raise PermissionDenied(
                    "Workshop owners and operators cannot modify tax collection authorization. Only platform administrators can grant or revoke tax collection permissions."
                )

        # If staff user explicitly passed can_collect_tax, use the audited authorization service
        if is_staff_user and 'can_collect_tax' in request.data:
            tax_auth_requested = bool(request.data['can_collect_tax'])
            if tax_auth_requested != profile.can_collect_tax:
                try:
                    WorkshopTaxAuthorizationService.set_tax_collection_authorization(
                        workshop=profile,
                        authorized=tax_auth_requested,
                        actor=request.user,
                        reason="Staff profile manage PATCH",
                    )
                except DjangoValidationError as exc:
                    msg = exc.message if hasattr(exc, 'message') else str(exc)
                    return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)

        serializer = WorkshopProfileManageSerializer(profile, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(WorkshopProfilePublicSerializer(profile).data)


class WorkshopOperatingHoursManageView(views.APIView):
    """
    List or bulk update operating hours for the user's workshop.
    GET /api/v1/workshops/manage/operating-hours/
    PUT /api/v1/workshops/manage/operating-hours/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = get_user_workshop_profile(request.user)
        hours = profile.operating_hours.all().order_by('day_of_week')
        serializer = WorkshopOperatingHoursSerializer(hours, many=True)
        return Response(serializer.data)

    def put(self, request):
        profile = get_user_workshop_profile(request.user)
        if not is_platform_admin_or_staff(request.user):
            role = profile.organisation.get_member_role(request.user)
            if role not in (OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN):
                raise PermissionDenied("Only workshop Owners and Admins can update operating hours.")

        items = request.data if isinstance(request.data, list) else request.data.get('hours', [])
        saved = []
        for item in items:
            day_of_week = item.get('day_of_week')
            if day_of_week is None:
                continue
            is_closed = item.get('is_closed', False)
            open_time = item.get('open_time') if not is_closed else None
            close_time = item.get('close_time') if not is_closed else None
            slot_duration = item.get('slot_duration_minutes', 60)

            obj, _ = WorkshopOperatingHours.objects.update_or_create(
                workshop=profile,
                day_of_week=day_of_week,
                defaults={
                    'is_closed': is_closed,
                    'open_time': open_time,
                    'close_time': close_time,
                    'slot_duration_minutes': slot_duration,
                }
            )
            saved.append(obj)

        serializer = WorkshopOperatingHoursSerializer(saved, many=True)
        return Response(serializer.data)


class WorkshopServiceListCreateView(views.APIView):
    """
    List or create services offered by the workshop.
    GET  /api/v1/workshops/manage/services/
    POST /api/v1/workshops/manage/services/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = get_user_workshop_profile(request.user)
        services = profile.services.all().select_related('category').order_by('name')
        active_only = request.query_params.get('active_only')
        if active_only and active_only.lower() in ('1', 'true', 'yes'):
            services = services.filter(is_active=True)
        serializer = WorkshopServiceSerializer(services, many=True)
        return Response(serializer.data)

    def post(self, request):
        profile = get_user_workshop_profile(request.user)
        if not is_platform_admin_or_staff(request.user):
            role = profile.organisation.get_member_role(request.user)
            if role not in (OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN):
                raise PermissionDenied("Only workshop Owners and Admins can create services.")

        serializer = WorkshopServiceSerializer(data=request.data, context={'request': request, 'workshop': profile})
        serializer.is_valid(raise_exception=True)
        service = serializer.save(workshop=profile, currency=profile.currency)
        return Response(WorkshopServiceSerializer(service).data, status=status.HTTP_201_CREATED)


class WorkshopServiceDetailView(views.APIView):
    """
    Retrieve, update or deactivate an individual workshop service.
    GET    /api/v1/workshops/manage/services/<id>/
    PATCH  /api/v1/workshops/manage/services/<id>/
    DELETE /api/v1/workshops/manage/services/<id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_service(self, request, id):
        profile = get_user_workshop_profile(request.user)
        return get_object_or_404(WorkshopService, id=id, workshop=profile)

    def get(self, request, id):
        service = self.get_service(request, id)
        return Response(WorkshopServiceSerializer(service).data)

    def patch(self, request, id):
        service = self.get_service(request, id)
        profile = service.workshop
        if not is_platform_admin_or_staff(request.user):
            role = profile.organisation.get_member_role(request.user)
            if role not in (OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN):
                raise PermissionDenied("Only workshop Owners and Admins can update services.")

        serializer = WorkshopServiceSerializer(service, data=request.data, partial=True, context={'request': request, 'workshop': profile})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(WorkshopServiceSerializer(service).data)

    def delete(self, request, id):
        service = self.get_service(request, id)
        if not is_platform_admin_or_staff(request.user):
            role = service.workshop.organisation.get_member_role(request.user)
            if role not in (OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN):
                raise PermissionDenied("Only workshop Owners and Admins can delete services.")

        service.is_active = False
        service.save(update_fields=['is_active', 'updated_at'])
        return Response({'status': 'success', 'message': 'Service deactivated.'})


class WorkshopBookingManageListView(views.APIView):
    """
    List all bookings for the authenticated staff user's workshop.
    GET /api/v1/workshops/manage/bookings/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = get_user_workshop_profile(request.user)
        status_filter = request.query_params.get('status')
        date_filter = request.query_params.get('date')

        qs = WorkshopBooking.objects.filter(workshop=profile).select_related(
            'workshop', 'workshop__organisation', 'buyer', 'vehicle', 'assigned_technician'
        ).prefetch_related('service_items', 'quotations', 'quotations__line_items').order_by('-created_at')

        if status_filter:
            status_val = status_filter.upper()
            if status_val == BookingStatusChoices.QUOTED:
                qs = qs.filter(
                    Q(status=BookingStatusChoices.QUOTED) |
                    Q(quotations__status=QuotationStatusChoices.ISSUED)
                ).distinct()
            else:
                qs = qs.filter(status=status_val)
        if date_filter:
            qs = qs.filter(preferred_date=date_filter)

        serializer = WorkshopBookingDetailSerializer(qs, many=True)
        return Response({'results': serializer.data, 'count': qs.count()})


class WorkshopBookingManageDetailView(views.APIView):
    """
    Retrieve booking detail for authorised workshop staff.
    GET /api/v1/workshops/manage/bookings/<id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        profile = get_user_workshop_profile(request.user)
        booking = get_object_or_404(
            WorkshopBooking.objects.select_related(
                'workshop', 'workshop__organisation', 'buyer', 'vehicle', 'assigned_technician'
            ).prefetch_related('service_items', 'quotations', 'quotations__line_items'),
            id=id,
            workshop=profile,
        )
        serializer = WorkshopBookingDetailSerializer(booking)
        return Response(serializer.data)


class WorkshopBookingStatusUpdateView(views.APIView):
    """
    Update booking lifecycle status: ACCEPT, REJECT, or SCHEDULE appointment.
    POST /api/v1/workshops/manage/bookings/<id>/status/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        profile = get_user_workshop_profile(request.user)
        booking = get_object_or_404(WorkshopBooking, id=id, workshop=profile)

        serializer = BookingStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        action = data['action']

        try:
            if action == 'ACCEPT':
                updated = BookingService.accept_booking(
                    booking=booking,
                    actor=request.user,
                    internal_notes=data.get('internal_notes', ''),
                )
            elif action == 'REJECT':
                updated = BookingService.reject_booking(
                    booking=booking,
                    reason=data['rejection_reason'],
                    actor=request.user,
                )
            elif action == 'SCHEDULE':
                updated = BookingService.schedule_appointment(
                    booking=booking,
                    start_time=data['scheduled_appointment_start'],
                    end_time=data['scheduled_appointment_end'],
                    technician_id=data.get('assigned_technician_id'),
                    internal_notes=data.get('internal_notes', ''),
                    actor=request.user,
                )
            else:
                return Response({'status': 'error', 'message': f"Unsupported action: {action}"}, status=status.HTTP_400_BAD_REQUEST)

            return Response(WorkshopBookingDetailSerializer(updated).data)

        except CapacityExceededError as exc:
            return Response({'status': 'error', 'code': 'CAPACITY_EXCEEDED', 'message': str(exc)}, status=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)


class WorkshopQuotationCreateReviseView(views.APIView):
    """
    Create a new quotation or revise an existing quotation for a booking.
    POST /api/v1/workshops/manage/bookings/<id>/quotations/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        profile = get_user_workshop_profile(request.user)
        booking = get_object_or_404(WorkshopBooking, id=id, workshop=profile)

        serializer = QuotationCreateUpdateSerializer(data=request.data, context={'request': request, 'booking': booking})
        serializer.is_valid(raise_exception=True)

        try:
            quote = QuotationService.create_or_revise_quotation(
                booking=booking,
                data=serializer.validated_data,
                actor=request.user,
            )
            return Response(WorkshopQuotationSerializer(quote).data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)


class WorkshopQuotationIssueView(views.APIView):
    """
    Issue a draft quotation to the customer.
    POST /api/v1/workshops/manage/quotations/<id>/issue/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        profile = get_user_workshop_profile(request.user)
        quotation = get_object_or_404(
            WorkshopQuotation.objects.select_related('booking', 'booking__workshop'),
            id=id,
            booking__workshop=profile,
        )

        try:
            issued = QuotationService.issue_quotation(quotation=quotation, actor=request.user)
            return Response(WorkshopQuotationSerializer(issued).data)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)


class WorkshopQuotationDetailView(views.APIView):
    """
    Retrieve full line items and breakdown of a quotation.
    GET /api/v1/workshops/manage/quotations/<id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        quotation = get_object_or_404(
            WorkshopQuotation.objects.select_related('booking', 'booking__buyer', 'booking__workshop__organisation').prefetch_related('line_items'),
            id=id,
        )
        # Check permission: buyer, workshop staff, or platform admin
        is_buyer = quotation.booking.buyer_id == request.user.id
        is_staff = is_platform_admin_or_staff(request.user) or quotation.booking.workshop.organisation.is_member(request.user)

        if not (is_buyer or is_staff):
            raise PermissionDenied("You do not have access to this quotation.")

        return Response(WorkshopQuotationSerializer(quotation).data)


# =========================================================
# PLATFORM ADMIN OVERVIEW
# =========================================================

class AdminWorkshopBookingListView(generics.ListAPIView):
    """
    Platform administration list of all workshop bookings.
    GET /api/v1/workshops/admin/bookings/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not is_platform_admin_or_staff(self.request.user):
            raise PermissionDenied("Requires platform staff or admin privileges.")

        qs = WorkshopBooking.objects.all().select_related(
            'workshop', 'workshop__organisation', 'buyer', 'vehicle', 'assigned_technician',
            'work_order', 'work_order__lead_technician'
        ).prefetch_related(
            'service_items',
            'quotations',
            'quotations__line_items',
            'work_order__tasks',
            'work_order__parts_used',
            'work_order__change_orders',
            'work_order__change_orders__line_items',
        ).order_by('-created_at')

        status_param = self.request.query_params.get('status')
        if status_param and status_param.upper() != 'ALL':
            status_val = status_param.upper()
            if status_val == BookingStatusChoices.QUOTED:
                qs = qs.filter(
                    Q(status=BookingStatusChoices.QUOTED) |
                    Q(quotations__status=QuotationStatusChoices.ISSUED)
                )
            else:
                qs = qs.filter(status=status_val)

        q = self.request.query_params.get('q') or self.request.query_params.get('search')
        if q and q.strip():
            query_str = q.strip()
            qs = qs.filter(
                Q(booking_number__icontains=query_str) |
                Q(workshop__business_name__icontains=query_str) |
                Q(workshop__organisation__name__icontains=query_str) |
                Q(buyer__first_name__icontains=query_str) |
                Q(buyer__last_name__icontains=query_str) |
                Q(buyer__email__icontains=query_str) |
                Q(vehicle_registration_plate__icontains=query_str) |
                Q(vehicle__registration_plate__icontains=query_str) |
                Q(quotations__quotation_number__icontains=query_str) |
                Q(work_order__work_order_number__icontains=query_str)
            )

        return qs.distinct()

    serializer_class = WorkshopBookingDetailSerializer


class AdminWorkshopTaxAuthorizationView(views.APIView):
    """
    Platform administration endpoint to explicitly grant or revoke tax collection authorization.
    POST /api/v1/workshops/admin/<uuid:id>/tax-authorization/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        if not is_platform_admin_or_staff(request.user):
            raise PermissionDenied("Only authorized platform administrators and staff can modify workshop tax collection permissions.")

        workshop = get_object_or_404(WorkshopProfile, id=id)
        serializer = AdminWorkshopTaxAuthorizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        can_collect_tax = serializer.validated_data['can_collect_tax']
        reason = serializer.validated_data.get('reason', '')

        try:
            updated_workshop = WorkshopTaxAuthorizationService.set_tax_collection_authorization(
                workshop=workshop,
                authorized=can_collect_tax,
                actor=request.user,
                reason=reason,
            )
            return Response(WorkshopProfilePublicSerializer(updated_workshop).data, status=status.HTTP_200_OK)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)



# =============================================================================
# WORK ORDER MANAGEMENT VIEWS
# =============================================================================

class WorkOrderManageListView(views.APIView):
    """
    List work orders for the authenticated user's workshop.
    GET /api/v1/workshops/manage/work-orders/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = get_user_workshop_profile(request.user)
        queryset = WorkOrder.objects.filter(workshop=profile).select_related(
            'booking', 'quotation', 'buyer', 'lead_technician', 'workshop'
        ).prefetch_related('tasks', 'parts_used')

        status_param = request.query_params.get('status')
        if status_param and status_param != 'ALL':
            queryset = queryset.filter(status=status_param.upper())

        technician_param = request.query_params.get('technician_id')
        if technician_param:
            queryset = queryset.filter(lead_technician_id=technician_param)

        search_query = request.query_params.get('q')
        if search_query:
            q = search_query.strip()
            queryset = queryset.filter(
                Q(work_order_number__icontains=q)
                | Q(booking__booking_number__icontains=q)
                | Q(vehicle_registration_plate__icontains=q)
                | Q(vehicle_vin__icontains=q)
                | Q(buyer__first_name__icontains=q)
                | Q(buyer__last_name__icontains=q)
                | Q(buyer__email__icontains=q)
            )

        serializer = WorkOrderListSerializer(queryset, many=True)
        return Response({
            'status': 'success',
            'count': queryset.count(),
            'results': serializer.data,
        })


class WorkOrderManageDetailView(views.APIView):
    """
    Retrieve single work order details.
    GET /api/v1/workshops/manage/work-orders/<id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        profile = get_user_workshop_profile(request.user)
        work_order = get_object_or_404(
            WorkOrder.objects.select_related(
                'booking', 'quotation', 'buyer', 'lead_technician', 'assigned_by', 'quality_inspected_by', 'workshop'
            ).prefetch_related('tasks', 'parts_used'),
            id=id,
            workshop=profile,
        )
        serializer = WorkOrderSerializer(work_order)
        return Response(serializer.data)


class WorkOrderAssignTechnicianView(views.APIView):
    """
    Assign or reassign lead technician to a work order.
    POST /api/v1/workshops/manage/work-orders/<id>/assign-technician/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        profile = get_user_workshop_profile(request.user)
        work_order = get_object_or_404(WorkOrder, id=id, workshop=profile)

        serializer = WorkOrderAssignTechnicianSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        technician = get_object_or_404(User, id=serializer.validated_data['technician_id'])

        try:
            updated = WorkOrderService.assign_technician(
                work_order=work_order,
                technician=technician,
                actor=request.user,
            )
            return Response({
                'status': 'success',
                'message': f"Technician {technician.full_name or technician.email} assigned to Work Order #{updated.work_order_number}.",
                'work_order': WorkOrderSerializer(updated).data,
            })
        except DjangoValidationError as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class WorkOrderStatusUpdateView(views.APIView):
    """
    Execute validated status transition for a Work Order.
    POST /api/v1/workshops/manage/work-orders/<id>/status/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        profile = get_user_workshop_profile(request.user)
        work_order = get_object_or_404(WorkOrder, id=id, workshop=profile)

        serializer = WorkOrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            updated = WorkOrderService.update_status(
                work_order=work_order,
                new_status=data['status'],
                actor=request.user,
                internal_notes=data.get('internal_notes', ''),
                quality_notes=data.get('quality_notes', ''),
                cancellation_reason=data.get('cancellation_reason', ''),
            )
            resp_data = {
                'status': 'success',
                'message': f"Work order transitioned to {updated.get_status_display()}.",
                'work_order': WorkOrderSerializer(updated).data,
            }
            warnings = getattr(updated, '_status_update_warnings', [])
            if warnings:
                resp_data['warnings'] = warnings
            return Response(resp_data)
        except DjangoValidationError as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class WorkOrderTaskCreateView(views.APIView):
    """
    Add a task to a work order.
    POST /api/v1/workshops/manage/work-orders/<id>/tasks/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        profile = get_user_workshop_profile(request.user)
        work_order = get_object_or_404(WorkOrder, id=id, workshop=profile)

        serializer = WorkOrderTaskCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        assigned_tech = None
        if data.get('assigned_technician_id'):
            assigned_tech = get_object_or_404(User, id=data['assigned_technician_id'])

        try:
            task = WorkOrderService.add_task(
                work_order=work_order,
                description=data['description'],
                assigned_technician=assigned_tech,
                estimated_labour_minutes=data.get('estimated_labour_minutes', 60),
                notes=data.get('notes', ''),
                actor=request.user,
            )
            return Response(WorkOrderTaskSerializer(task).data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class WorkOrderTaskDetailView(views.APIView):
    """
    Update or delete a task on a work order.
    PATCH/DELETE /api/v1/workshops/manage/work-orders/<id>/tasks/<task_id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, id, task_id):
        profile = get_user_workshop_profile(request.user)
        work_order = get_object_or_404(WorkOrder, id=id, workshop=profile)
        task = get_object_or_404(WorkOrderTask, id=task_id, work_order=work_order)

        serializer = WorkOrderTaskCreateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        assigned_tech = None
        if 'assigned_technician_id' in data:
            if data['assigned_technician_id']:
                assigned_tech = get_object_or_404(User, id=data['assigned_technician_id'])

        try:
            updated = WorkOrderService.update_task(
                task=task,
                status=data.get('status'),
                actual_labour_minutes=data.get('actual_labour_minutes'),
                notes=data.get('notes'),
                assigned_technician=assigned_tech,
                actor=request.user,
            )
            return Response(WorkOrderTaskSerializer(updated).data)
        except DjangoValidationError as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id, task_id):
        profile = get_user_workshop_profile(request.user)
        work_order = get_object_or_404(WorkOrder, id=id, workshop=profile)
        task = get_object_or_404(WorkOrderTask, id=task_id, work_order=work_order)

        try:
            WorkOrderService.delete_task(task=task, actor=request.user)
            return Response({'status': 'success', 'message': 'Task removed.'}, status=status.HTTP_204_NO_CONTENT)
        except DjangoValidationError as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class WorkOrderPartUsageListCreateView(views.APIView):
    """
    List or record spare parts consumed on a work order.
    GET/POST /api/v1/workshops/manage/work-orders/<id>/parts/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        profile = get_user_workshop_profile(request.user)
        work_order = get_object_or_404(WorkOrder, id=id, workshop=profile)
        parts = work_order.parts_used.all().select_related('added_by', 'catalogue_part')
        return Response({
            'status': 'success',
            'results': WorkOrderPartUsageSerializer(parts, many=True).data,
            'total_parts_cost': str(work_order.total_parts_cost),
        })

    def post(self, request, id):
        profile = get_user_workshop_profile(request.user)
        work_order = get_object_or_404(WorkOrder, id=id, workshop=profile)

        serializer = WorkOrderPartUsageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        catalogue_part = None
        if data.get('catalogue_part_id'):
            catalogue_part = get_object_or_404(Part, id=data['catalogue_part_id'])

        inventory_item = None
        if data.get('inventory_item_id'):
            from apps.marketplace.models import SparePartListing
            inventory_item = get_object_or_404(
                SparePartListing,
                id=data['inventory_item_id'],
                organisation=work_order.workshop.organisation,
            )

        try:
            part_usage = WorkOrderService.record_part_usage(
                work_order=work_order,
                part_name=data['part_name'],
                quantity=data['quantity'],
                unit_cost=data['unit_cost'],
                part_number=data.get('part_number', ''),
                description=data.get('description', ''),
                catalogue_part=catalogue_part,
                inventory_item=inventory_item,
                actor=request.user,
            )
            return Response(WorkOrderPartUsageSerializer(part_usage).data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class WorkOrderPartUsageDetailView(views.APIView):
    """
    Delete a recorded part usage entry.
    DELETE /api/v1/workshops/manage/work-orders/<id>/parts/<part_id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, id, part_id):
        profile = get_user_workshop_profile(request.user)
        work_order = get_object_or_404(WorkOrder, id=id, workshop=profile)
        part = get_object_or_404(WorkOrderPartUsage, id=part_id, work_order=work_order)

        try:
            WorkOrderService.delete_part_usage(part_usage=part, actor=request.user)
            return Response({'status': 'success', 'message': 'Part usage entry removed.'}, status=status.HTTP_204_NO_CONTENT)
        except DjangoValidationError as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class WorkshopTechnicianListView(views.APIView):
    """
    List active technicians and staff members of the caller's workshop organisation.
    GET /api/v1/workshops/manage/technicians/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = get_user_workshop_profile(request.user)
        memberships = profile.organisation.memberships.filter(
            is_active=True
        ).select_related('user')

        serializer = WorkshopTechnicianMemberSerializer(memberships, many=True)
        return Response({
            'status': 'success',
            'results': serializer.data,
        })


class BuyerWorkOrderDetailView(views.APIView):
    """
    Allows a buyer to inspect the active work order and live repair progress for their booking.
    GET /api/v1/workshops/bookings/my/<booking_id>/work-order/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        booking = get_object_or_404(WorkshopBooking, id=id, buyer=request.user)
        if not hasattr(booking, 'work_order') or not booking.work_order:
            return Response({'status': 'error', 'message': 'No work order has been created for this booking yet.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = BuyerWorkOrderSerializer(booking.work_order)
        return Response(serializer.data)


# ==========================================
# Work Order Balance Settlement & Invoicing Views
# ==========================================

class WorkOrderSettlementDetailView(views.APIView):
    """
    Inspect financial standing, authorized total, deposits, change orders,
    previous balance payments, and outstanding balance for a WorkOrder.
    GET /api/v1/workshops/work-orders/<id>/settle/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        work_order = get_object_or_404(
            WorkOrder.objects.select_related('quotation', 'workshop', 'booking', 'buyer'),
            id=id,
        )
        is_buyer = work_order.buyer_id == request.user.id
        from apps.workshops.permissions import is_platform_admin_or_staff, is_workshop_staff_or_admin
        is_staff = is_platform_admin_or_staff(request.user) or is_workshop_staff_or_admin(request.user, work_order.workshop)
        if not (is_buyer or is_staff):
            raise PermissionDenied("You do not have permission to view settlement details for this work order.")

        balance_info = WorkOrderSettlementService.calculate_outstanding_balance(work_order)
        balance_info["work_order_id"] = str(work_order.id)
        balance_info["work_order_number"] = work_order.work_order_number
        balance_info["status"] = work_order.status
        balance_info["payments"] = WorkOrderPaymentSerializer(work_order.payments.all(), many=True).data
        balance_info["invoice"] = WorkOrderInvoiceSerializer(work_order.invoice).data if hasattr(work_order, 'invoice') and work_order.invoice else None

        return Response(balance_info, status=status.HTTP_200_OK)


class WorkOrderSettlementSessionCreateView(views.APIView):
    """
    Buyer creates an authoritative payment session to pay the outstanding balance (or partial balance)
    of a WorkOrder via Razorpay (INR) or Stripe (GBP).
    POST /api/v1/workshops/work-orders/<id>/settle/session/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        work_order = get_object_or_404(
            WorkOrder.objects.select_related('quotation', 'workshop', 'booking', 'buyer'),
            id=id,
        )
        if work_order.buyer_id != request.user.id:
            raise PermissionDenied("You can only pay for work orders assigned to you.")

        partial_amount = request.data.get('partial_amount')
        preferred_provider = request.data.get('preferred_provider')
        return_url = request.data.get('return_url')
        cancel_url = request.data.get('cancel_url')

        try:
            session_data = WorkOrderSettlementService.create_settlement_session(
                work_order=work_order,
                buyer=request.user,
                partial_amount=Decimal(str(partial_amount)) if partial_amount else None,
                preferred_provider=preferred_provider,
                return_url=return_url,
                cancel_url=cancel_url,
            )
            return Response(session_data, status=status.HTTP_201_CREATED)
        except (DjangoValidationError, ValueError) as exc:
            msg = exc.messages[0] if hasattr(exc, 'messages') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Error initiating work order settlement session: %s", exc)
            return Response(
                {'status': 'error', 'message': f"Failed to initiate payment session: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WorkOrderSettlementVerifyView(views.APIView):
    """
    Buyer verifies payment gateway confirmation payload for WorkOrder balance settlement.
    POST /api/v1/workshops/work-orders/<id>/settle/verify/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        work_order = get_object_or_404(
            WorkOrder.objects.select_related('quotation', 'workshop', 'booking', 'buyer'),
            id=id,
        )
        if work_order.buyer_id != request.user.id and not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied("You can only verify payments for your own work orders.")

        preferred_provider = request.data.get('preferred_provider')
        try:
            wo, payment = WorkOrderSettlementService.verify_settlement_payment(
                work_order_id=work_order.id,
                payload=request.data,
                actor=request.user,
                preferred_provider=preferred_provider,
            )
            balance_info = WorkOrderSettlementService.calculate_outstanding_balance(wo)
            invoice_data = WorkOrderInvoiceSerializer(wo.invoice).data if hasattr(wo, 'invoice') and wo.invoice else None

            return Response({
                'status': 'success',
                'work_order_id': str(wo.id),
                'work_order_number': wo.work_order_number,
                'payment_number': payment.payment_number,
                'payment_status': payment.status,
                'amount_paid': str(payment.amount),
                'currency': payment.currency,
                'settlement_status': wo.settlement_status,
                'is_fully_settled': wo.is_fully_settled,
                'outstanding_balance': balance_info["outstanding_balance"],
                'invoice': invoice_data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as exc:
            msg = exc.messages[0] if hasattr(exc, 'messages') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Error verifying work order settlement payment: %s", exc)
            return Response(
                {'status': 'error', 'message': f"Payment verification failed: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WorkOrderInvoiceDetailView(views.APIView):
    """
    Retrieve final commercial/tax invoice for a WorkOrder.
    GET /api/v1/workshops/work-orders/<id>/invoice/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        work_order = get_object_or_404(
            WorkOrder.objects.select_related('invoice', 'workshop', 'buyer'),
            id=id,
        )
        is_buyer = work_order.buyer_id == request.user.id
        from apps.workshops.permissions import is_platform_admin_or_staff, is_workshop_staff_or_admin
        is_staff = is_platform_admin_or_staff(request.user) or is_workshop_staff_or_admin(request.user, work_order.workshop)
        if not (is_buyer or is_staff):
            raise PermissionDenied("You do not have permission to view the invoice for this work order.")

        invoice = getattr(work_order, 'invoice', None)
        if not invoice:
            invoice = WorkOrderSettlementService.generate_or_update_invoice(work_order)

        serializer = WorkOrderInvoiceSerializer(invoice)
        return Response(serializer.data, status=status.HTTP_200_OK)


class WorkOrderSettlementWebhookView(views.APIView):
    """
    Public webhook receiver for payment gateway callbacks (Razorpay/Stripe) for WorkOrder settlements.
    POST /api/v1/workshops/settle/webhook/<str:provider>/
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request, provider):
        headers = {k: v for k, v in request.headers.items()}
        success, message = WorkOrderSettlementService.process_settlement_webhook(
            provider_name=provider,
            request_body=request.body,
            headers=headers,
        )
        if success:
            return Response({'status': 'success', 'message': message}, status=status.HTTP_200_OK)
        return Response({'status': 'error', 'message': message}, status=status.HTTP_400_BAD_REQUEST)


class WorkshopSettlementManageListView(views.APIView):
    """
    List work order settlement records and financial overview metrics
    for the authenticated user's workshop.
    GET /api/v1/workshops/manage/settlements/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = get_user_workshop_profile(request.user)

        # Base queryset for this workshop
        base_queryset = WorkOrder.objects.filter(workshop=profile).select_related(
            'booking', 'quotation', 'buyer', 'workshop', 'invoice'
        ).prefetch_related('change_orders', 'payments')

        # Filtered queryset for results table
        filtered_queryset = base_queryset

        # Search filter
        search_query = request.query_params.get('q', '').strip()
        if search_query:
            filtered_queryset = filtered_queryset.filter(
                Q(work_order_number__icontains=search_query)
                | Q(booking__booking_number__icontains=search_query)
                | Q(vehicle_registration_plate__icontains=search_query)
                | Q(vehicle_vin__icontains=search_query)
                | Q(buyer__first_name__icontains=search_query)
                | Q(buyer__last_name__icontains=search_query)
                | Q(buyer__email__icontains=search_query)
            )

        # Status filter
        status_param = request.query_params.get('status', 'ALL').strip().upper()
        if status_param and status_param != 'ALL':
            if status_param in ('SETTLED', 'FULLY_PAID'):
                filtered_queryset = filtered_queryset.filter(
                    settlement_status=WorkOrderSettlementStatusChoices.FULLY_PAID
                )
            elif status_param == 'PARTIALLY_PAID':
                filtered_queryset = filtered_queryset.filter(
                    settlement_status=WorkOrderSettlementStatusChoices.PARTIALLY_PAID
                )
            elif status_param == 'UNPAID':
                filtered_queryset = filtered_queryset.filter(
                    settlement_status=WorkOrderSettlementStatusChoices.UNPAID
                )

        filtered_queryset = filtered_queryset.order_by('-created_at')

        # Overview summary metrics across active work orders
        active_wo_list = list(
            base_queryset.exclude(status=WorkOrderStatusChoices.CANCELLED)
        )

        total_value = Decimal('0.00')
        advance_deposits = Decimal('0.00')
        final_payments = Decimal('0.00')
        total_collected = Decimal('0.00')
        outstanding_balance = Decimal('0.00')
        fully_paid_count = 0
        partially_paid_count = 0
        unpaid_count = 0

        for wo in active_wo_list:
            b_info = WorkOrderSettlementService.calculate_outstanding_balance(wo)
            total_value += Decimal(b_info["authorized_total_amount"])
            advance_deposits += Decimal(b_info["deposit_paid_amount"])
            final_payments += Decimal(b_info["balance_paid_amount"])
            total_collected += Decimal(b_info["total_paid_amount"])
            outstanding_balance += Decimal(b_info["outstanding_balance"])

            st = b_info["settlement_status"]
            if st == WorkOrderSettlementStatusChoices.FULLY_PAID:
                fully_paid_count += 1
            elif st == WorkOrderSettlementStatusChoices.PARTIALLY_PAID:
                partially_paid_count += 1
            else:
                unpaid_count += 1

        currency = (getattr(profile, 'currency', 'GBP') or 'GBP').upper()
        summary = {
            "total_work_order_value": str(total_value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            "advance_deposits_received": str(advance_deposits.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            "final_payments_received": str(final_payments.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            "total_amount_collected": str(total_collected.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            "outstanding_customer_balance": str(outstanding_balance.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            "currency": currency,
            "total_work_orders": len(active_wo_list),
            "fully_paid_count": fully_paid_count,
            "partially_paid_count": partially_paid_count,
            "unpaid_count": unpaid_count,
        }

        # Pagination
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except ValueError:
            page = 1
        try:
            page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))
        except ValueError:
            page_size = 20

        total_count = filtered_queryset.count()
        import math
        total_pages = max(1, math.ceil(total_count / page_size))
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = filtered_queryset[start_idx:end_idx]

        results = []
        for wo in page_items:
            b_info = WorkOrderSettlementService.calculate_outstanding_balance(wo)
            cust = wo.buyer
            cust_name = ""
            if cust:
                cust_name = cust.full_name if hasattr(cust, 'full_name') and cust.full_name else (cust.get_full_name() if hasattr(cust, 'get_full_name') else '') or cust.email

            booking_date = None
            if wo.booking:
                if wo.booking.scheduled_appointment_start:
                    booking_date = wo.booking.scheduled_appointment_start.isoformat()
                elif wo.booking.preferred_date:
                    booking_date = wo.booking.preferred_date.isoformat()

            inv_data = None
            if hasattr(wo, 'invoice') and wo.invoice:
                inv_data = {
                    "id": str(wo.invoice.id),
                    "invoice_number": wo.invoice.invoice_number,
                    "status": wo.invoice.status,
                    "issued_at": wo.invoice.issued_at.isoformat() if wo.invoice.issued_at else None,
                }

            results.append({
                "id": str(wo.id),
                "work_order_number": wo.work_order_number,
                "booking_id": str(wo.booking.id) if wo.booking else None,
                "booking_number": wo.booking.booking_number if wo.booking else "",
                "booking_date": booking_date,
                "customer": {
                    "id": str(cust.id) if cust else None,
                    "name": cust_name or "Valued Customer",
                    "email": cust.email if cust else "",
                    "phone": getattr(cust, 'phone_number', '') if cust else "",
                },
                "vehicle": {
                    "make": wo.vehicle_make,
                    "model": wo.vehicle_model,
                    "year": wo.vehicle_year,
                    "registration_plate": wo.vehicle_registration_plate,
                    "vin": wo.vehicle_vin,
                },
                "quotation_amount": b_info["original_quotation_amount"],
                "approved_change_orders_amount": b_info["approved_change_orders_amount"],
                "total_amount": b_info["authorized_total_amount"],
                "deposit_paid": b_info["deposit_paid_amount"],
                "final_payment": b_info["balance_paid_amount"],
                "total_paid": b_info["total_paid_amount"],
                "outstanding": b_info["outstanding_balance"],
                "currency": b_info["currency"],
                "settlement_status": b_info["settlement_status"],
                "is_fully_settled": b_info["is_fully_settled"],
                "work_order_status": wo.status,
                "invoice": inv_data,
                "created_at": wo.created_at.isoformat() if wo.created_at else None,
            })

        return Response({
            "status": "success",
            "summary": summary,
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "results": results,
        }, status=status.HTTP_200_OK)


class WorkshopInvoiceManageListView(views.APIView):
    """
    List final commercial/tax invoices for the authenticated user's workshop.
    GET /api/v1/workshops/manage/invoices/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = get_user_workshop_profile(request.user)
        queryset = WorkOrderInvoice.objects.filter(
            work_order__workshop=profile
        ).select_related(
            'work_order', 'work_order__buyer', 'work_order__workshop', 'work_order__quotation'
        )

        search_query = request.query_params.get('q', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(invoice_number__icontains=search_query)
                | Q(work_order__work_order_number__icontains=search_query)
                | Q(work_order__booking__booking_number__icontains=search_query)
                | Q(work_order__buyer__first_name__icontains=search_query)
                | Q(work_order__buyer__last_name__icontains=search_query)
                | Q(work_order__buyer__email__icontains=search_query)
                | Q(work_order__vehicle_registration_plate__icontains=search_query)
            )

        status_param = request.query_params.get('status', 'ALL').strip().upper()
        if status_param and status_param != 'ALL':
            queryset = queryset.filter(status=status_param)

        queryset = queryset.order_by('-created_at')

        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except ValueError:
            page = 1
        try:
            page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))
        except ValueError:
            page_size = 20

        total_count = queryset.count()
        import math
        total_pages = max(1, math.ceil(total_count / page_size))
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = queryset[start_idx:end_idx]

        serializer = WorkOrderInvoiceSerializer(page_items, many=True)
        return Response({
            "status": "success",
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "results": serializer.data,
        }, status=status.HTTP_200_OK)


# ==========================================
# Change Orders Views (Workshop & Buyer)
# ==========================================

class WorkOrderChangeOrderListCreateView(views.APIView):
    """
    List or create change orders for a specific work order.
    GET/POST /api/v1/workshops/manage/work-orders/<id>/change-orders/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        profile = get_user_workshop_profile(request.user)
        work_order = get_object_or_404(WorkOrder, id=id, workshop=profile)
        orders = work_order.change_orders.all().select_related('created_by', 'reviewed_by').prefetch_related('line_items')
        return Response({
            'status': 'success',
            'results': ChangeOrderSerializer(orders, many=True).data,
            'authorized_total_amount': str(work_order.authorized_total_amount),
            'approved_change_orders_amount': str(work_order.approved_change_orders_amount),
            'has_pending_change_orders': work_order.has_pending_change_orders,
        })

    def post(self, request, id):
        profile = get_user_workshop_profile(request.user)
        work_order = get_object_or_404(WorkOrder, id=id, workshop=profile)

        serializer = ChangeOrderCreateSerializer(data=request.data, context={'request': request, 'work_order': work_order})
        serializer.is_valid(raise_exception=True)

        try:
            change_order = ChangeOrderService.create_change_order(
                work_order=work_order,
                data=serializer.validated_data,
                actor=request.user,
            )
            return Response(ChangeOrderSerializer(change_order).data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ChangeOrderDetailView(views.APIView):
    """
    Retrieve change order details for workshop staff.
    GET /api/v1/workshops/manage/change-orders/<id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        profile = get_user_workshop_profile(request.user)
        change_order = get_object_or_404(ChangeOrder, id=id, work_order__workshop=profile)
        return Response(ChangeOrderSerializer(change_order).data)


class ChangeOrderSubmitView(views.APIView):
    """
    Submit a draft change order to the buyer for authorization.
    POST /api/v1/workshops/manage/change-orders/<id>/submit/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        profile = get_user_workshop_profile(request.user)
        change_order = get_object_or_404(ChangeOrder, id=id, work_order__workshop=profile)

        try:
            submitted = ChangeOrderService.submit_change_order(
                change_order=change_order,
                actor=request.user,
            )
            return Response(ChangeOrderSerializer(submitted).data)
        except DjangoValidationError as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ChangeOrderCancelView(views.APIView):
    """
    Cancel an unresolved change order by the workshop.
    POST /api/v1/workshops/manage/change-orders/<id>/cancel/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        profile = get_user_workshop_profile(request.user)
        change_order = get_object_or_404(ChangeOrder, id=id, work_order__workshop=profile)
        reason = request.data.get('reason', '')

        try:
            cancelled = ChangeOrderService.cancel_change_order(
                change_order=change_order,
                actor=request.user,
                reason=reason,
            )
            return Response(ChangeOrderSerializer(cancelled).data)
        except DjangoValidationError as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class BuyerChangeOrderListView(views.APIView):
    """
    List all change orders on an active booking for the authenticated buyer.
    GET /api/v1/workshops/bookings/my/<booking_id>/change-orders/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        booking = get_object_or_404(WorkshopBooking, id=id, buyer=request.user)
        if not hasattr(booking, 'work_order') or not booking.work_order:
            return Response({'status': 'success', 'results': []})

        orders = booking.work_order.change_orders.all().prefetch_related('line_items')
        return Response({
            'status': 'success',
            'results': BuyerChangeOrderSerializer(orders, many=True).data,
            'authorized_total_amount': str(booking.work_order.authorized_total_amount),
            'approved_change_orders_amount': str(booking.work_order.approved_change_orders_amount),
            'has_pending_change_orders': booking.work_order.has_pending_change_orders,
        })


class BuyerChangeOrderApproveView(views.APIView):
    """
    Buyer authorizes the additional repairs and costs for a change order.
    POST /api/v1/workshops/change-orders/<id>/approve/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        change_order = get_object_or_404(ChangeOrder, id=id, work_order__buyer=request.user)
        serializer = ChangeOrderDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notes = serializer.validated_data.get('notes', '')

        try:
            approved = ChangeOrderService.approve_change_order(
                change_order=change_order,
                buyer=request.user,
                notes=notes,
            )
            return Response(BuyerChangeOrderSerializer(approved).data)
        except DjangoValidationError as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class BuyerChangeOrderRejectView(views.APIView):
    """
    Buyer declines the additional repair request.
    POST /api/v1/workshops/change-orders/<id>/reject/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        change_order = get_object_or_404(ChangeOrder, id=id, work_order__buyer=request.user)
        serializer = ChangeOrderDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get('reason') or serializer.validated_data.get('notes', '')

        try:
            rejected = ChangeOrderService.reject_change_order(
                change_order=change_order,
                buyer=request.user,
                reason=reason,
            )
            return Response(BuyerChangeOrderSerializer(rejected).data)
        except DjangoValidationError as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


def _resolve_workshop(id_or_slug):
    """Resolves a WorkshopProfile by UUID primary key or unique slug."""
    try:
        return WorkshopProfile.objects.select_related('organisation').get(id=id_or_slug)
    except (WorkshopProfile.DoesNotExist, ValueError, DjangoValidationError):
        return WorkshopProfile.objects.select_related('organisation').filter(slug=id_or_slug).first()


class BuyerBookingReviewEligibilityView(views.APIView):
    """
    Check if a booking is eligible for customer review.
    GET /api/v1/workshops/bookings/<id>/review-eligibility/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        booking = get_object_or_404(
            WorkshopBooking.objects.select_related('workshop', 'work_order'),
            id=id,
        )
        if booking.buyer_id != request.user.id and not request.user.is_staff:
            raise PermissionDenied("You can only check review eligibility for your own bookings.")

        is_eligible, reason, work_order = WorkshopReviewService.check_review_eligibility(booking, request.user)
        existing_review = getattr(booking, 'review', None)

        return Response({
            "is_eligible": is_eligible,
            "reason": reason,
            "booking_id": str(booking.id),
            "booking_number": booking.booking_number,
            "workshop_id": str(booking.workshop_id),
            "workshop_name": booking.workshop.business_name if booking.workshop else "",
            "work_order_id": str(work_order.id) if work_order else None,
            "work_order_status": work_order.status if work_order else None,
            "completed_at": work_order.completed_at.isoformat() if (work_order and work_order.completed_at) else None,
            "already_reviewed": bool(existing_review),
            "existing_review_id": str(existing_review.id) if existing_review else None,
            "existing_review_rating": existing_review.rating if existing_review else None,
        }, status=status.HTTP_200_OK)


class BuyerBookingReviewCreateView(views.APIView):
    """
    Submit a review for a completed workshop service booking.
    POST /api/v1/workshops/bookings/<id>/review/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        booking = get_object_or_404(
            WorkshopBooking.objects.select_related('workshop', 'work_order', 'workshop__organisation'),
            id=id,
        )
        if booking.buyer_id != request.user.id:
            raise PermissionDenied("You can only submit reviews for your own bookings.")

        serializer = WorkshopReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            review = WorkshopReviewService.create_review(
                booking=booking,
                buyer=request.user,
                data=serializer.validated_data,
                actor=request.user,
            )
            return Response(WorkshopReviewSerializer(review).data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)


class WorkshopReviewsListView(views.APIView):
    """
    Public listing of approved customer reviews and reputation summary for a workshop.
    GET /api/v1/workshops/<id_or_slug>/reviews/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, id_or_slug):
        workshop = _resolve_workshop(id_or_slug)
        if not workshop:
            return Response({'error': f"Workshop '{id_or_slug}' not found."}, status=status.HTTP_404_NOT_FOUND)

        reputation = WorkshopReviewService.get_workshop_reputation_summary(workshop)

        qs = workshop.reviews.filter(
            status=ReviewStatusChoices.APPROVED
        ).select_related('buyer', 'workshop', 'booking', 'work_order', 'workshop_replied_by')

        rating = request.query_params.get('rating')
        if rating:
            try:
                qs = qs.filter(rating=int(rating))
            except ValueError:
                pass

        ordering = request.query_params.get('ordering', '-created_at')
        if ordering in ('-created_at', 'created_at', '-rating', 'rating'):
            qs = qs.order_by(ordering)
        else:
            qs = qs.order_by('-created_at')

        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        paginator.page_size = 10
        page = paginator.paginate_queryset(qs, request)
        serialized_reviews = WorkshopReviewSerializer(page, many=True).data

        response_data = paginator.get_paginated_response(serialized_reviews).data
        response_data['reputation'] = reputation
        return Response(response_data, status=status.HTTP_200_OK)


class WorkshopReviewReplyView(views.APIView):
    """
    Workshop management reply to a customer review.
    POST /api/v1/workshops/manage/reviews/<id>/reply/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        review = get_object_or_404(
            WorkshopReview.objects.select_related('workshop', 'workshop__organisation', 'buyer'),
            id=id,
        )
        serializer = WorkshopReviewReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            updated = WorkshopReviewService.reply_to_review(
                review=review,
                user=request.user,
                reply_text=serializer.validated_data['reply'],
            )
            return Response(WorkshopReviewSerializer(updated).data, status=status.HTTP_200_OK)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)


class AdminWorkshopReviewListView(generics.ListAPIView):
    """
    Platform admin oversight of all workshop reviews across all statuses.
    GET /api/v1/workshops/admin/reviews/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WorkshopReviewSerializer

    def get_queryset(self):
        from apps.workshops.permissions import can_moderate_reviews
        if not can_moderate_reviews(self.request.user):
            raise PermissionDenied("Only authorized platform administrators and staff can view review moderation lists.")

        qs = WorkshopReview.objects.select_related('workshop', 'buyer', 'booking', 'work_order', 'workshop_replied_by').all()

        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter.strip().upper())

        workshop_id = self.request.query_params.get('workshop_id')
        if workshop_id:
            qs = qs.filter(workshop_id=workshop_id)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(comment__icontains=search)
                | Q(title__icontains=search)
                | Q(workshop__business_name__icontains=search)
                | Q(buyer__email__icontains=search)
            )

        return qs.order_by('-created_at')


class AdminWorkshopReviewModerationView(views.APIView):
    """
    Platform admin review status moderation.
    POST /api/v1/workshops/admin/reviews/<id>/moderate/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        from apps.workshops.permissions import can_moderate_reviews
        if not can_moderate_reviews(request.user):
            raise PermissionDenied("Only authorized platform administrators and staff can moderate reviews.")

        review = get_object_or_404(WorkshopReview, id=id)
        serializer = WorkshopReviewModerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            moderated = WorkshopReviewService.moderate_review(
                review=review,
                user=request.user,
                status=serializer.validated_data['status'],
                reason=serializer.validated_data.get('reason', ''),
            )
            return Response(WorkshopReviewSerializer(moderated).data, status=status.HTTP_200_OK)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)


class BookingConversationDetailView(views.APIView):
    """
    Retrieve or create the conversation thread associated with a workshop booking.
    GET /api/v1/workshops/bookings/<identifier>/conversation/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, identifier):
        booking = None
        try:
            import uuid
            uuid_obj = uuid.UUID(str(identifier))
            booking = WorkshopBooking.objects.select_related('workshop', 'buyer').filter(id=uuid_obj).first()
        except ValueError:
            pass

        if not booking:
            booking = WorkshopBooking.objects.select_related('workshop', 'buyer').filter(booking_number=identifier).first()

        if not booking:
            return Response({'status': 'error', 'message': 'Booking not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            from apps.workshops.messaging_service import get_or_create_conversation_for_booking
            conversation = get_or_create_conversation_for_booking(booking, request.user)
            serializer = WorkshopConversationSerializer(conversation, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except PermissionDenied as exc:
            return Response({'status': 'error', 'message': str(exc)}, status=status.HTTP_403_FORBIDDEN)


class WorkshopConversationListView(views.APIView):
    """
    List conversation threads accessible to the authenticated user.
    GET /api/v1/workshops/conversations/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from apps.workshops.messaging_service import get_user_conversations
        conversations = get_user_conversations(request.user)
        serializer = WorkshopConversationSerializer(conversations, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class ConversationMessageListCreateView(views.APIView):
    """
    List messages or post a new message in a conversation.
    GET /api/v1/workshops/conversations/<id>/messages/
    POST /api/v1/workshops/conversations/<id>/messages/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        from apps.workshops.messaging_service import check_user_can_access_conversation
        conversation = get_object_or_404(WorkshopConversation.objects.select_related('workshop', 'buyer'), id=id)

        if not check_user_can_access_conversation(request.user, conversation):
            raise PermissionDenied("You are not authorized to view messages for this conversation.")

        messages = conversation.messages.select_related('sender').order_by('created_at')
        serializer = WorkshopMessageSerializer(messages, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, id):
        from apps.workshops.messaging_service import check_user_can_access_conversation, create_message
        conversation = get_object_or_404(WorkshopConversation.objects.select_related('workshop', 'buyer'), id=id)

        if not check_user_can_access_conversation(request.user, conversation):
            raise PermissionDenied("You are not authorized to send messages in this conversation.")

        serializer = CreateWorkshopMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            message = create_message(
                conversation=conversation,
                sender=request.user,
                content=serializer.validated_data.get('content', ''),
                attachment_url=serializer.validated_data.get('attachment_url', ''),
            )
            return Response(WorkshopMessageSerializer(message).data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as exc:
            return Response({'status': 'error', 'message': str(exc)}, status=status.HTTP_403_FORBIDDEN)


class ConversationMarkReadView(views.APIView):
    """
    Mark unread messages in a conversation as read.
    POST /api/v1/workshops/conversations/<id>/read/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        from apps.workshops.messaging_service import check_user_can_access_conversation, mark_messages_as_read
        conversation = get_object_or_404(WorkshopConversation.objects.select_related('workshop', 'buyer'), id=id)

        if not check_user_can_access_conversation(request.user, conversation):
            raise PermissionDenied("You are not authorized to update messages in this conversation.")

        count = mark_messages_as_read(conversation, request.user)
        return Response({'status': 'success', 'marked_read': count}, status=status.HTTP_200_OK)


# =============================================================================
# TECHNICIAN MOBILE WORKFLOW VIEWS
# =============================================================================

def check_technician_work_order_access(user, work_order) -> bool:
    """
    Validates that user is authorized to view or work on this work order.
    Authorized if:
    - User is staff / superuser
    - User is the lead technician on the work order
    - User is assigned to at least one task on the work order
    - User is the owner or active member of the workshop organisation
    """
    if user.is_staff or user.is_superuser:
        return True
    if work_order.lead_technician_id == user.id:
        return True
    if work_order.tasks.filter(assigned_technician=user).exists():
        return True
    org = work_order.workshop.organisation
    if org.created_by_id == user.id:
        return True
    try:
        from apps.organisations.models import OrganisationMembership
        return OrganisationMembership.objects.filter(
            user=user,
            organisation=org,
            is_active=True,
        ).exists()
    except Exception:
        return False


class TechnicianWorkOrderListView(views.APIView):
    """
    Mobile-friendly assigned work order list for technicians.
    GET /api/v1/workshops/technician/work-orders/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = get_user_workshop_profile(request.user)
        is_owner_or_staff = (profile.organisation.created_by_id == request.user.id) or request.user.is_staff
        show_all = request.query_params.get('all', '').lower() in ('true', '1') and is_owner_or_staff

        base_qs = WorkOrder.objects.filter(workshop=profile).select_related(
            'booking', 'quotation', 'buyer', 'lead_technician', 'workshop'
        ).prefetch_related('tasks', 'parts_used')

        if not show_all:
            base_qs = base_qs.filter(
                Q(lead_technician=request.user) | Q(tasks__assigned_technician=request.user)
            ).distinct()

        status_param = request.query_params.get('status')
        if status_param and status_param != 'ALL':
            base_qs = base_qs.filter(status=status_param.upper())

        search_query = request.query_params.get('q')
        if search_query:
            q = search_query.strip()
            base_qs = base_qs.filter(
                Q(work_order_number__icontains=q)
                | Q(booking__booking_number__icontains=q)
                | Q(vehicle_registration_plate__icontains=q)
                | Q(vehicle_vin__icontains=q)
                | Q(buyer__first_name__icontains=q)
                | Q(buyer__last_name__icontains=q)
                | Q(buyer__email__icontains=q)
            )

        serializer = WorkOrderListSerializer(base_qs, many=True)
        return Response({
            'status': 'success',
            'count': base_qs.count(),
            'results': serializer.data,
        })


class TechnicianWorkOrderDetailView(views.APIView):
    """
    Retrieve mobile technician work order details including vehicle, customer,
    quotation planned parts, tasks, and parts used.
    GET /api/v1/workshops/technician/work-orders/<id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        work_order = get_object_or_404(
            WorkOrder.objects.select_related(
                'booking', 'quotation', 'buyer', 'lead_technician', 'assigned_by', 'quality_inspected_by', 'workshop'
            ).prefetch_related('tasks', 'parts_used', 'change_orders'),
            id=id,
        )

        if not check_technician_work_order_access(request.user, work_order):
            raise PermissionDenied("You are not authorized to view this work order.")

        serializer = WorkOrderSerializer(work_order)
        data = serializer.data

        # Add customer notes & reported faults from booking
        booking = work_order.booking
        data['customer_notes'] = booking.customer_notes if booking else ''
        data['reported_faults'] = booking.reported_faults if booking else ''

        # Add available transitions
        valid_transitions = {
            WorkOrderStatusChoices.ASSIGNED: [WorkOrderStatusChoices.IN_PROGRESS, WorkOrderStatusChoices.CANCELLED],
            WorkOrderStatusChoices.IN_PROGRESS: [WorkOrderStatusChoices.AWAITING_PARTS, WorkOrderStatusChoices.QUALITY_CHECK, WorkOrderStatusChoices.CANCELLED],
            WorkOrderStatusChoices.AWAITING_PARTS: [WorkOrderStatusChoices.IN_PROGRESS, WorkOrderStatusChoices.CANCELLED],
            WorkOrderStatusChoices.QUALITY_CHECK: [WorkOrderStatusChoices.IN_PROGRESS, WorkOrderStatusChoices.COMPLETED, WorkOrderStatusChoices.CANCELLED],
            WorkOrderStatusChoices.COMPLETED: [],
            WorkOrderStatusChoices.CANCELLED: [],
        }
        data['available_transitions'] = valid_transitions.get(work_order.status, [])

        return Response(data)


class TechnicianWorkOrderStatusUpdateView(views.APIView):
    """
    Update work order progress status from technician mobile interface.
    POST /api/v1/workshops/technician/work-orders/<id>/status/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        work_order = get_object_or_404(WorkOrder, id=id)
        if not check_technician_work_order_access(request.user, work_order):
            raise PermissionDenied("You are not authorized to update this work order.")

        serializer = WorkOrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            updated = WorkOrderService.update_status(
                work_order=work_order,
                new_status=data['status'],
                actor=request.user,
                internal_notes=data.get('internal_notes', ''),
                quality_notes=data.get('quality_notes', ''),
                cancellation_reason=data.get('cancellation_reason', ''),
            )
            resp_data = {
                'status': 'success',
                'message': f"Work order transitioned to {updated.get_status_display()}.",
                'work_order': WorkOrderSerializer(updated).data,
            }
            warnings = getattr(updated, '_status_update_warnings', [])
            if warnings:
                resp_data['warnings'] = warnings
            return Response(resp_data)
        except DjangoValidationError as e:
            msg = e.message if hasattr(e, 'message') else str(e)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)


class TechnicianWorkOrderTaskUpdateView(views.APIView):
    """
    Technician updates task progress, actual labour minutes, and status.
    PATCH /api/v1/workshops/technician/work-orders/<id>/tasks/<task_id>/
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, id, task_id):
        work_order = get_object_or_404(WorkOrder, id=id)
        if not check_technician_work_order_access(request.user, work_order):
            raise PermissionDenied("You are not authorized to update tasks on this work order.")

        task = get_object_or_404(WorkOrderTask, id=task_id, work_order=work_order)
        serializer = WorkOrderTaskCreateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            updated = WorkOrderService.update_task(
                task=task,
                status=data.get('status'),
                actual_labour_minutes=data.get('actual_labour_minutes'),
                notes=data.get('notes'),
                actor=request.user,
            )
            return Response(WorkOrderTaskSerializer(updated).data)
        except DjangoValidationError as e:
            msg = e.message if hasattr(e, 'message') else str(e)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)


class TechnicianWorkOrderPartUsageView(views.APIView):
    """
    Record spare part consumption from technician mobile interface, automatically
    validating and decrementing workshop inventory.
    POST /api/v1/workshops/technician/work-orders/<id>/parts/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        from apps.marketplace.models import SparePartListing
        from apps.catalogue.models import Part

        work_order = get_object_or_404(WorkOrder, id=id)
        if not check_technician_work_order_access(request.user, work_order):
            raise PermissionDenied("You are not authorized to record part usage on this work order.")

        serializer = WorkOrderPartUsageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        catalogue_part = None
        if data.get('catalogue_part_id'):
            catalogue_part = get_object_or_404(Part, id=data['catalogue_part_id'])

        inventory_item = None
        if data.get('inventory_item_id'):
            inventory_item = get_object_or_404(SparePartListing, id=data['inventory_item_id'])

        try:
            part_usage = WorkOrderService.record_part_usage(
                work_order=work_order,
                part_name=data['part_name'],
                quantity=data.get('quantity', Decimal('1.00')),
                unit_cost=data.get('unit_cost', Decimal('0.00')),
                part_number=data.get('part_number', ''),
                description=data.get('description', ''),
                catalogue_part=catalogue_part,
                inventory_item=inventory_item,
                actor=request.user,
            )
            return Response(WorkOrderPartUsageSerializer(part_usage).data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            msg = e.message if hasattr(e, 'message') else str(e)
            return Response({'status': 'error', 'message': msg}, status=status.HTTP_400_BAD_REQUEST)



