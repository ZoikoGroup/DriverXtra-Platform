from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import generics, status, views, permissions
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError

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
)
from apps.workshops.services import BookingService, QuotationService, CapacityExceededError
from apps.workshops.permissions import (
    IsWorkshopOwnerOrAdmin,
    IsWorkshopStaffOrMember,
    IsBookingBuyerOrWorkshopStaff,
    is_platform_admin_or_staff,
)
from apps.organisations.models import Organisation, OrganisationTypeChoices, OrganisationRoleChoices


def get_user_workshop_profile(user) -> WorkshopProfile:
    """
    Resolves the WorkshopProfile associated with an authenticated user's active WORKSHOP organisation.
    """
    if is_platform_admin_or_staff(user):
        # Platform admins default to first active workshop if not linked directly
        profile = WorkshopProfile.objects.filter(is_verified=True).first()
        if profile:
            return profile

    # Look for active membership in a WORKSHOP organisation
    membership = user.organisation_memberships.filter(
        is_active=True,
        organisation__type=OrganisationTypeChoices.WORKSHOP,
        organisation__is_active=True,
    ).select_related('organisation').first()

    if not membership:
        raise PermissionDenied("You are not an active member of any registered workshop organisation.")

    org = membership.organisation
    profile, _ = WorkshopProfile.objects.get_or_create(
        organisation=org,
        defaults={
            'business_name': org.name,
            'slug': org.slug,
            'currency': 'GBP',
            'is_accepting_bookings': True,
        }
    )
    return profile


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
        qs = WorkshopProfile.objects.filter(
            is_verified=True,
            organisation__is_active=True,
        ).select_related('organisation').prefetch_related('services', 'operating_hours')

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
            qs = qs.filter(status=status_filter.upper())

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
    Buyer cancels their booking request.
    POST /api/v1/workshops/bookings/my/<id>/cancel/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        booking = get_object_or_404(WorkshopBooking, id=id, buyer=request.user)
        serializer = BookingCancellationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            updated = BookingService.cancel_booking(
                booking=booking,
                reason=serializer.validated_data['reason'],
                actor=request.user,
            )
            return Response(WorkshopBookingDetailSerializer(updated).data)
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
        profile = get_user_workshop_profile(request.user)
        serializer = WorkshopProfilePublicSerializer(profile)
        return Response(serializer.data)

    def patch(self, request):
        profile = get_user_workshop_profile(request.user)
        # Verify Owner or Admin role
        if not is_platform_admin_or_staff(request.user):
            role = profile.organisation.get_member_role(request.user)
            if role not in (OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN):
                raise PermissionDenied("Only workshop Owners and Admins can update profile settings.")

        serializer = WorkshopProfileManageSerializer(profile, data=request.data, partial=True)
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
        services = profile.services.filter(is_active=True).select_related('category').order_by('name')
        serializer = WorkshopServiceSerializer(services, many=True)
        return Response(serializer.data)

    def post(self, request):
        profile = get_user_workshop_profile(request.user)
        if not is_platform_admin_or_staff(request.user):
            role = profile.organisation.get_member_role(request.user)
            if role not in (OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN):
                raise PermissionDenied("Only workshop Owners and Admins can create services.")

        serializer = WorkshopServiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = serializer.save(workshop=profile)
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
        if not is_platform_admin_or_staff(request.user):
            role = service.workshop.organisation.get_member_role(request.user)
            if role not in (OrganisationRoleChoices.OWNER, OrganisationRoleChoices.ADMIN):
                raise PermissionDenied("Only workshop Owners and Admins can update services.")

        serializer = WorkshopServiceSerializer(service, data=request.data, partial=True)
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
            qs = qs.filter(status=status_filter.upper())
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

        serializer = QuotationCreateUpdateSerializer(data=request.data)
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
            'workshop', 'workshop__organisation', 'buyer', 'vehicle', 'assigned_technician'
        ).prefetch_related('service_items', 'quotations').order_by('-created_at')

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param.upper())
        return qs

    serializer_class = WorkshopBookingDetailSerializer
