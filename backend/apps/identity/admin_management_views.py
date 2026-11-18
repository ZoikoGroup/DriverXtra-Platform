"""
Centralized administrative account management views for DriverXtra.
Provides scalable, database-backed inspection, search, filtering, and governance
over Sellers, Workshops, Buyers, Staff, and Platform Orders.
"""
from decimal import Decimal
from django.db import transaction
from django.db.models import Q, Count, Sum
from django.utils import timezone
from rest_framework import views, generics, status, permissions
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError

from apps.identity.models import User, RoleChoices, AccountStatusChoices
from apps.onboarding.models import SellerApplication, SellerApplicationStatusChoices, BusinessTypeChoices
from apps.workshops.models import WorkshopProfile, WorkshopBooking, WorkshopService, WorkOrder
from apps.marketplace.models import VehicleListing, SparePartListing, Order, VehicleOrder, Dispute
from apps.organisations.models import Organisation, OrganisationMembership
from common.pagination import ScalableAdminPagination
from common.permissions import IsPlatformStaff, IsMarketplaceAdmin, HasPermission
from platform_core.audit.writer import record_audit_entry, record_denied_audit_entry
from common.middleware import get_current_correlation_id


def _guard_account_status_target(request, target, required_role, action_code):
    """Refuse account-status changes on targets outside the endpoint's scope.

    Account suspension/reactivation endpoints may only act on ordinary marketplace accounts
    of the expected type. Platform staff, administrators, superusers and the acting user are
    never valid targets, and arbitrary user IDs cannot be used to bypass the type check.
    Denials are audited. Raises NotFound/PermissionDenied; returns None when allowed.
    """
    corr_id = getattr(request, 'correlation_id', '') or get_current_correlation_id()

    def deny(reason_code, exc):
        record_denied_audit_entry(
            action=action_code,
            resource_type="User",
            resource_id=str(target.id),
            actor_id=request.user.id,
            reason_code=reason_code,
            correlation_id=corr_id,
        )
        raise exc

    if target.id == request.user.id:
        deny("SELF_TARGET", PermissionDenied("You cannot change the status of your own account."))
    if (
        target.is_superuser
        or target.is_staff
        or target.has_role(RoleChoices.ADMIN)
        or target.has_role(RoleChoices.STAFF)
    ):
        deny("PRIVILEGED_TARGET", PermissionDenied(
            "Platform staff and administrator accounts cannot be managed through this endpoint."
        ))
    if not target.has_role(required_role):
        label = RoleChoices(required_role).label.split(' /')[0]
        deny("TARGET_ROLE_MISMATCH", NotFound(f"{label} account not found."))


# =============================================================================
# 1. Admin Dashboard Overview Metrics View
# =============================================================================

class AdminOverviewMetricsView(views.APIView):
    """
    Returns real-time, dynamic database-backed aggregated metrics for the
    DriverXtra platform administrator overview dashboard.
    GET /api/v1/admin/overview/metrics/
    """
    permission_classes = [IsPlatformStaff]

    def get(self, request):
        now = timezone.now()

        # Database-level aggregate counts
        total_buyers = User.objects.filter(user_roles__role=RoleChoices.BUYER).distinct().count()
        total_sellers = User.objects.filter(user_roles__role=RoleChoices.SELLER).distinct().count()
        total_workshops = WorkshopProfile.objects.count()
        total_staff = User.objects.filter(
            Q(is_staff=True) | Q(user_roles__role=RoleChoices.STAFF)
        ).distinct().count()

        pending_seller_applications = SellerApplication.objects.filter(
            status=SellerApplicationStatusChoices.PENDING
        ).count()
        approved_sellers = SellerApplication.objects.filter(
            status=SellerApplicationStatusChoices.APPROVED
        ).count()

        approved_workshops = WorkshopProfile.objects.filter(is_verified=True).count()
        pending_workshop_applications = SellerApplication.objects.filter(
            status=SellerApplicationStatusChoices.PENDING
        ).filter(
            Q(requested_roles__icontains=RoleChoices.WORKSHOP)
            | Q(business_type=BusinessTypeChoices.WORKSHOP)
        ).count()

        suspended_accounts = User.objects.filter(
            status=AccountStatusChoices.SUSPENDED
        ).count()

        pending_vehicle_listings = VehicleListing.objects.filter(
            status='PENDING_APPROVAL'
        ).count()
        pending_part_listings = SparePartListing.objects.filter(
            status='PENDING_APPROVAL'
        ).count()

        total_part_orders = Order.objects.count()
        total_vehicle_orders = VehicleOrder.objects.count()
        total_orders = total_part_orders + total_vehicle_orders

        pending_disputes = Dispute.objects.filter(
            status__in=['OPEN', 'IN_MEDIATION', 'UNDER_INVESTIGATION']
        ).count()

        # Pending Administrative Tasks queue
        pending_tasks = [
            {
                "id": "seller_apps",
                "type": "SELLER_APPLICATIONS",
                "label": "Pending Seller & Dealer Applications",
                "count": pending_seller_applications,
                "target_tab": "admin_sellers",
                "severity": "high" if pending_seller_applications > 0 else "neutral",
            },
            {
                "id": "vehicle_mod",
                "type": "VEHICLE_MODERATION",
                "label": "Vehicles Awaiting Marketplace Approval",
                "count": pending_vehicle_listings,
                "target_tab": "admin_marketplace_review",
                "severity": "high" if pending_vehicle_listings > 0 else "neutral",
            },
            {
                "id": "part_mod",
                "type": "PART_MODERATION",
                "label": "Spare Parts Awaiting Approval",
                "count": pending_part_listings,
                "target_tab": "admin_marketplace_review",
                "severity": "medium" if pending_part_listings > 0 else "neutral",
            },
            {
                "id": "disputes",
                "type": "DISPUTES",
                "label": "Active Customer Disputes Requiring Adjudication",
                "count": pending_disputes,
                "target_tab": "admin_disputes_refunds",
                "severity": "high" if pending_disputes > 0 else "neutral",
            },
        ]

        # Recent administrative activity log
        recent_activity = []
        recent_users = User.objects.order_by('-created_at')[:5]
        for u in recent_users:
            recent_activity.append({
                "id": str(u.id),
                "type": "USER_REGISTRATION",
                "description": f"New user registered: {u.email}",
                "timestamp": u.created_at.isoformat() if u.created_at else now.isoformat(),
            })

        recent_applications = SellerApplication.objects.order_by('-created_at')[:5]
        for a in recent_applications:
            recent_activity.append({
                "id": str(a.id),
                "type": "APPLICATION_SUBMISSION",
                "description": f"Seller application ({a.business_name}) status: {a.status}",
                "timestamp": a.created_at.isoformat() if a.created_at else now.isoformat(),
            })

        # Sort combined recent activity descending
        recent_activity.sort(key=lambda x: x["timestamp"], reverse=True)
        recent_activity = recent_activity[:8]

        return Response({
            "metrics": {
                "total_buyers": total_buyers,
                "total_sellers": total_sellers,
                "total_workshops": total_workshops,
                "total_staff": total_staff,
                "pending_seller_applications": pending_seller_applications,
                "pending_workshop_applications": pending_workshop_applications,
                "approved_sellers": approved_sellers,
                "approved_workshops": approved_workshops,
                "suspended_accounts": suspended_accounts,
                "pending_vehicle_listings": pending_vehicle_listings,
                "pending_part_listings": pending_part_listings,
                "total_orders": total_orders,
                "total_part_orders": total_part_orders,
                "total_vehicle_orders": total_vehicle_orders,
                "pending_disputes": pending_disputes,
            },
            "pending_tasks": pending_tasks,
            "recent_activity": recent_activity,
        })


# =============================================================================
# 2. Admin Seller Management Views
# =============================================================================

class AdminSellerListView(views.APIView):
    """
    Scalable server-side paginated list of all seller accounts.
    GET /api/v1/admin/sellers/?page=1&page_size=20&q=apex&verification_status=APPROVED
    """
    permission_classes = [IsPlatformStaff, HasPermission('seller.verify')]
    pagination_class = ScalableAdminPagination

    def get(self, request):
        queryset = User.objects.filter(
            Q(user_roles__role=RoleChoices.SELLER) | Q(seller_applications__isnull=False)
        ).distinct().select_related().prefetch_related(
            'seller_applications',
            'organisation_memberships__organisation'
        )

        # Search parameter across user and business fields
        q = request.query_params.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(seller_applications__business_name__icontains=q)
                | Q(seller_applications__company_registration_number__icontains=q)
                | Q(organisation_memberships__organisation__name__icontains=q)
            ).distinct()

        # Verification status filter
        v_status = request.query_params.get('verification_status', '').strip().upper()
        if v_status and v_status != 'ALL':
            if v_status in ('APPROVED', 'PENDING', 'REJECTED'):
                queryset = queryset.filter(seller_applications__status=v_status).distinct()
            elif v_status == 'UNVERIFIED':
                queryset = queryset.filter(
                    Q(seller_applications__isnull=True) | Q(seller_applications__status='DRAFT')
                ).distinct()

        # Account status filter
        acc_status = request.query_params.get('status', '').strip().upper()
        if acc_status and acc_status != 'ALL':
            queryset = queryset.filter(status=acc_status)

        # Sorting
        ordering = request.query_params.get('ordering', '-created_at')
        valid_orderings = ['-created_at', 'created_at', 'email', '-email', 'date_joined', '-date_joined']
        if ordering in valid_orderings:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by('-created_at')

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)

        results = []
        for user in page:
            # Latest seller application
            latest_app = user.seller_applications.order_by('-created_at').first()
            membership = user.organisation_memberships.filter(is_active=True).first()
            org = membership.organisation if membership else None

            # Operational metrics (dynamic database queries)
            v_count = VehicleListing.objects.filter(seller=user).count()
            p_count = SparePartListing.objects.filter(seller=user).count()
            o_count = Order.objects.filter(items__listing__seller=user).distinct().count()

            results.append({
                "id": str(user.id),
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "full_name": user.full_name,
                "phone_number": user.phone_number,
                "status": user.status,
                "is_active": user.is_active,
                "is_email_verified": user.is_email_verified,
                "date_joined": user.date_joined.isoformat() if user.date_joined else None,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "business_name": latest_app.business_name if latest_app else (org.name if org else "Independent Trader"),
                "business_type": latest_app.business_type if latest_app else (org.type if org else "INDIVIDUAL_TRADER"),
                "company_registration_number": latest_app.company_registration_number if latest_app else "",
                "tax_id": latest_app.tax_id if latest_app else "",
                "verification_status": latest_app.status if latest_app else ("APPROVED" if user.has_role(RoleChoices.SELLER) else "UNVERIFIED"),
                "application_id": str(latest_app.id) if latest_app else None,
                "organisation": {
                    "id": str(org.id),
                    "name": org.name,
                    "slug": org.slug,
                    "type": org.type,
                    "country": org.country,
                } if org else None,
                "metrics": {
                    "vehicle_listings_count": v_count,
                    "part_listings_count": p_count,
                    "orders_count": o_count,
                },
            })

        return paginator.get_paginated_response(results)


class AdminSellerDetailView(views.APIView):
    """
    Retrieve full seller account profile, organisation, application KYC,
    inventory, and business activity for platform administrators.
    GET /api/v1/admin/sellers/<uuid:pk>/
    """
    permission_classes = [IsPlatformStaff, HasPermission('seller.verify')]

    def get(self, request, pk):
        try:
            user = User.objects.select_related().prefetch_related(
                'seller_applications',
                'organisation_memberships__organisation'
            ).get(id=pk)
        except User.DoesNotExist:
            raise NotFound("Seller account not found.")

        latest_app = user.seller_applications.order_by('-created_at').first()
        membership = user.organisation_memberships.filter(is_active=True).first()
        org = membership.organisation if membership else None

        # Recent vehicles
        recent_vehicles = []
        for v in VehicleListing.objects.filter(seller=user).order_by('-created_at')[:10]:
            recent_vehicles.append({
                "id": str(v.id),
                "title": v.title,
                "price": str(v.price),
                "status": v.status,
                "year": v.year,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            })

        # Recent parts
        recent_parts = []
        for p in SparePartListing.objects.filter(seller=user).order_by('-created_at')[:10]:
            recent_parts.append({
                "id": str(p.id),
                "title": getattr(p, 'title', None) or getattr(p, 'name', '') or "Spare Part",
                "part_number": getattr(p, 'part_number', None) or getattr(p, 'mpn', '') or "",
                "price": str(p.price),
                "stock_quantity": p.stock_quantity,
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            })

        # Recent orders
        recent_orders = []
        for o in Order.objects.filter(items__listing__seller=user).distinct().order_by('-created_at')[:10]:
            recent_orders.append({
                "id": str(o.id),
                "order_number": o.order_number,
                "total_amount": str(o.total_amount),
                "currency": o.currency,
                "status": o.status,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            })

        return Response({
            "seller": {
                "id": str(user.id),
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "full_name": user.full_name,
                "phone_number": user.phone_number,
                "status": user.status,
                "is_active": user.is_active,
                "is_email_verified": user.is_email_verified,
                "date_joined": user.date_joined.isoformat() if user.date_joined else None,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "roles": user.roles,
            },
            "application": {
                "id": str(latest_app.id),
                "business_name": latest_app.business_name,
                "business_type": latest_app.business_type,
                "requested_roles": latest_app.requested_roles,
                "company_registration_number": latest_app.company_registration_number,
                "tax_id": latest_app.tax_id,
                "contact_email": latest_app.contact_email,
                "contact_phone": latest_app.contact_phone,
                "address_line1": latest_app.address_line1,
                "address_line2": latest_app.address_line2,
                "city": latest_app.city,
                "postal_code": latest_app.postal_code,
                "country": latest_app.country,
                "jurisdiction": latest_app.jurisdiction,
                "website_url": latest_app.website_url,
                "description": latest_app.description,
                "status": latest_app.status,
                "submitted_at": latest_app.submitted_at.isoformat() if latest_app.submitted_at else None,
                "reviewed_at": latest_app.reviewed_at.isoformat() if latest_app.reviewed_at else None,
                "rejection_reason": latest_app.rejection_reason,
            } if latest_app else None,
            "organisation": {
                "id": str(org.id),
                "name": org.name,
                "slug": org.slug,
                "type": org.type,
                "country": org.country,
                "jurisdiction": org.jurisdiction,
            } if org else None,
            "recent_vehicles": recent_vehicles,
            "recent_parts": recent_parts,
            "recent_orders": recent_orders,
            "metrics": {
                "vehicle_listings_count": VehicleListing.objects.filter(seller=user).count(),
                "part_listings_count": SparePartListing.objects.filter(seller=user).count(),
                "orders_count": Order.objects.filter(items__listing__seller=user).distinct().count(),
            },
        })


class AdminSellerStatusView(views.APIView):
    """
    Suspend or reactivate a seller account.
    POST /api/v1/admin/sellers/<uuid:pk>/status/
    Body: {"action": "SUSPEND" | "REACTIVATE", "reason": "Optional notes"}
    """
    permission_classes = [IsPlatformStaff, HasPermission('seller.verify')]

    def post(self, request, pk):
        try:
            user = User.objects.get(id=pk)
        except User.DoesNotExist:
            raise NotFound("Seller account not found.")

        action = request.data.get('action', '').strip().upper()
        reason = request.data.get('reason', '').strip()

        if action not in ('SUSPEND', 'REACTIVATE'):
            raise ValidationError({"action": "Action must be either 'SUSPEND' or 'REACTIVATE'."})

        # S2: only ordinary SELLER accounts; never staff/admins/superusers/self.
        _guard_account_status_target(request, user, RoleChoices.SELLER, "admin:seller.status")

        corr_id = getattr(request, 'correlation_id', '') or get_current_correlation_id()

        if action == 'SUSPEND':
            user.status = AccountStatusChoices.SUSPENDED
            user.is_active = False
            user.save(update_fields=['status', 'is_active', 'updated_at'])

            record_audit_entry(
                event_type="seller.account.suspended",
                action="admin:seller.suspend",
                resource_type="User",
                resource_id=str(user.id),
                actor_id=request.user.id,
                correlation_id=corr_id,
                metadata={"reason": reason, "seller_email": user.email},
            )
        else:
            user.status = AccountStatusChoices.ACTIVE
            user.is_active = True
            user.save(update_fields=['status', 'is_active', 'updated_at'])

            record_audit_entry(
                event_type="seller.account.reactivated",
                action="admin:seller.reactivate",
                resource_type="User",
                resource_id=str(user.id),
                actor_id=request.user.id,
                correlation_id=corr_id,
                metadata={"reason": reason, "seller_email": user.email},
            )

        return Response({
            "status": "success",
            "message": f"Seller account {action.lower()}ed successfully.",
            "account_status": user.status,
            "is_active": user.is_active,
        })


# =============================================================================
# 3. Admin Workshop Management Views
# =============================================================================

class AdminWorkshopListView(views.APIView):
    """
    Scalable server-side paginated list of all workshop service accounts.
    GET /api/v1/admin/workshops/?page=1&page_size=20&q=garage&is_verified=true
    """
    permission_classes = [IsPlatformStaff]
    pagination_class = ScalableAdminPagination

    def get(self, request):
        queryset = WorkshopProfile.objects.select_related(
            'organisation', 'organisation__created_by'
        ).all()

        # Search parameter
        q = request.query_params.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(business_name__icontains=q)
                | Q(slug__icontains=q)
                | Q(contact_email__icontains=q)
                | Q(contact_phone__icontains=q)
                | Q(city__icontains=q)
                | Q(organisation__name__icontains=q)
            )

        # Verification status filter
        v_param = request.query_params.get('is_verified')
        if v_param is not None and v_param != '' and v_param.upper() != 'ALL':
            is_v = v_param.lower() in ('true', '1')
            queryset = queryset.filter(is_verified=is_v)

        # Accepting bookings filter
        b_param = request.query_params.get('is_accepting_bookings')
        if b_param is not None and b_param != '' and b_param.upper() != 'ALL':
            is_b = b_param.lower() in ('true', '1')
            queryset = queryset.filter(is_accepting_bookings=is_b)

        # Ordering
        ordering = request.query_params.get('ordering', '-created_at')
        valid_orderings = ['-created_at', 'created_at', 'business_name', '-business_name', 'city']
        if ordering in valid_orderings:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by('-created_at')

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)

        results = []
        for wp in page:
            org = wp.organisation
            owner = org.created_by if org else None

            # Operational metrics (wp is WorkshopProfile)
            s_count = WorkshopService.objects.filter(workshop=wp, is_active=True).count()
            b_count = WorkshopBooking.objects.filter(workshop=wp).count()
            wo_count = WorkOrder.objects.filter(workshop=wp).count()

            results.append({
                "id": str(wp.id),
                "organisation_id": str(org.id) if org else None,
                "business_name": wp.business_name or (org.name if org else "Workshop"),
                "slug": wp.slug,
                "description": wp.description,
                "contact_email": wp.contact_email,
                "contact_phone": wp.contact_phone,
                "city": wp.city,
                "state_province": wp.state_province,
                "postal_code": wp.postal_code,
                "country": wp.country,
                "bay_capacity": wp.bay_capacity,
                "is_accepting_bookings": wp.is_accepting_bookings,
                "is_verified": wp.is_verified,
                "is_tax_registered": wp.is_tax_registered,
                "can_collect_tax": wp.can_collect_tax,
                "default_tax_rate_percent": str(wp.default_tax_rate_percent),
                "created_at": wp.created_at.isoformat() if wp.created_at else None,
                "owner": {
                    "id": str(owner.id),
                    "email": owner.email,
                    "full_name": owner.full_name,
                    "status": owner.status,
                } if owner else None,
                "metrics": {
                    "services_count": s_count,
                    "bookings_count": b_count,
                    "work_orders_count": wo_count,
                },
            })

        return paginator.get_paginated_response(results)


class AdminWorkshopDetailView(views.APIView):
    """
    Retrieve full workshop profile, organisation, services, operating hours,
    and booking activity for platform administrators.
    GET /api/v1/admin/workshops/<uuid:pk>/
    """
    permission_classes = [IsPlatformStaff]

    def get(self, request, pk):
        try:
            wp = WorkshopProfile.objects.select_related(
                'organisation', 'organisation__created_by'
            ).get(id=pk)
        except WorkshopProfile.DoesNotExist:
            raise NotFound("Workshop profile not found.")

        org = wp.organisation
        owner = org.created_by if org else None

        # Services list
        services = []
        for s in WorkshopService.objects.filter(workshop=wp, is_active=True)[:20]:
            services.append({
                "id": str(s.id),
                "name": s.name,
                "price": str(s.price),
                "estimated_duration_minutes": s.estimated_duration_minutes,
                "is_active": s.is_active,
            })

        # Recent bookings
        recent_bookings = []
        for b in WorkshopBooking.objects.filter(workshop=wp).select_related('buyer').order_by('-created_at')[:10]:
            recent_bookings.append({
                "id": str(b.id),
                "booking_number": b.booking_number,
                "customer_name": b.buyer.full_name if b.buyer else "Guest",
                "customer_email": b.buyer.email if b.buyer else "",
                "status": b.status,
                "scheduled_date": b.scheduled_date.isoformat() if b.scheduled_date else None,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            })

        # Recent work orders
        recent_work_orders = []
        for wo in WorkOrder.objects.filter(workshop=wp).order_by('-created_at')[:10]:
            recent_work_orders.append({
                "id": str(wo.id),
                "work_order_number": wo.work_order_number,
                "status": wo.status,
                "total_amount": str(wo.total_amount) if hasattr(wo, 'total_amount') else "0.00",
                "created_at": wo.created_at.isoformat() if wo.created_at else None,
            })

        return Response({
            "workshop": {
                "id": str(wp.id),
                "business_name": wp.business_name or (org.name if org else "Workshop"),
                "slug": wp.slug,
                "description": wp.description,
                "contact_email": wp.contact_email,
                "contact_phone": wp.contact_phone,
                "address_line1": wp.address_line1,
                "address_line2": wp.address_line2,
                "city": wp.city,
                "state_province": wp.state_province,
                "postal_code": wp.postal_code,
                "country": wp.country,
                "bay_capacity": wp.bay_capacity,
                "is_accepting_bookings": wp.is_accepting_bookings,
                "is_verified": wp.is_verified,
                "is_tax_registered": wp.is_tax_registered,
                "can_collect_tax": wp.can_collect_tax,
                "default_tax_rate_percent": str(wp.default_tax_rate_percent),
                "created_at": wp.created_at.isoformat() if wp.created_at else None,
            },
            "organisation": {
                "id": str(org.id),
                "name": org.name,
                "slug": org.slug,
                "country": org.country,
                "jurisdiction": org.jurisdiction,
            } if org else None,
            "owner": {
                "id": str(owner.id),
                "email": owner.email,
                "full_name": owner.full_name,
                "status": owner.status,
            } if owner else None,
            "services": services,
            "recent_bookings": recent_bookings,
            "recent_work_orders": recent_work_orders,
            "metrics": {
                "services_count": WorkshopService.objects.filter(workshop=wp).count(),
                "bookings_count": WorkshopBooking.objects.filter(workshop=wp).count(),
                "work_orders_count": WorkOrder.objects.filter(workshop=wp).count(),
            },
        })


class AdminWorkshopStatusView(views.APIView):
    """
    Approve, verify, suspend or reactivate a workshop.
    POST /api/v1/admin/workshops/<uuid:pk>/status/
    Body: {"action": "VERIFY" | "UNVERIFY" | "SUSPEND" | "REACTIVATE", "reason": "Notes"}

    S3: requires 'seller.verify' (VERIFICATION_OFFICER; platform admins hold every permission).
    VERIFY grants the WORKSHOP role to the owner, so general staff must not reach it.
    """
    permission_classes = [IsPlatformStaff, HasPermission('seller.verify')]

    def post(self, request, pk):
        try:
            wp = WorkshopProfile.objects.select_related('organisation', 'organisation__created_by').get(id=pk)
        except WorkshopProfile.DoesNotExist:
            raise NotFound("Workshop profile not found.")

        action = request.data.get('action', '').strip().upper()
        reason = request.data.get('reason', '').strip()

        if action not in ('VERIFY', 'UNVERIFY', 'SUSPEND', 'REACTIVATE'):
            raise ValidationError({"action": "Invalid action. Must be VERIFY, UNVERIFY, SUSPEND, or REACTIVATE."})

        corr_id = getattr(request, 'correlation_id', '') or get_current_correlation_id()

        if action == 'VERIFY':
            wp.is_verified = True
            wp.save(update_fields=['is_verified', 'updated_at'])
            # Ensure owner has WORKSHOP role assigned
            if wp.organisation and wp.organisation.created_by:
                wp.organisation.created_by.add_role(RoleChoices.WORKSHOP)
            event_type = "workshop.verified"
        elif action == 'UNVERIFY':
            wp.is_verified = False
            wp.save(update_fields=['is_verified', 'updated_at'])
            event_type = "workshop.unverified"
        elif action == 'SUSPEND':
            wp.is_accepting_bookings = False
            wp.save(update_fields=['is_accepting_bookings', 'updated_at'])
            event_type = "workshop.suspended"
        else: # REACTIVATE
            wp.is_accepting_bookings = True
            wp.save(update_fields=['is_accepting_bookings', 'updated_at'])
            event_type = "workshop.reactivated"

        record_audit_entry(
            event_type=event_type,
            action=f"admin:workshop.{action.lower()}",
            resource_type="WorkshopProfile",
            resource_id=str(wp.id),
            actor_id=request.user.id,
            correlation_id=corr_id,
            metadata={"reason": reason, "business_name": wp.business_name},
        )

        return Response({
            "status": "success",
            "message": f"Workshop status updated to {action.lower()}.",
            "is_verified": wp.is_verified,
            "is_accepting_bookings": wp.is_accepting_bookings,
        })


# =============================================================================
# 4. Admin Buyer Management Views
# =============================================================================

class AdminBuyerListView(views.APIView):
    """
    Scalable server-side paginated list of all registered buyer accounts.
    GET /api/v1/admin/buyers/?page=1&page_size=20&q=john&status=ACTIVE
    """
    permission_classes = [IsPlatformStaff]
    pagination_class = ScalableAdminPagination

    def get(self, request):
        queryset = User.objects.filter(
            user_roles__role=RoleChoices.BUYER
        ).distinct()

        # Search parameter
        q = request.query_params.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(phone_number__icontains=q)
            )

        # Status filter
        acc_status = request.query_params.get('status', '').strip().upper()
        if acc_status and acc_status != 'ALL':
            queryset = queryset.filter(status=acc_status)

        # Email verified filter
        v_param = request.query_params.get('is_email_verified')
        if v_param is not None and v_param != '' and v_param.upper() != 'ALL':
            is_v = v_param.lower() in ('true', '1')
            queryset = queryset.filter(is_email_verified=is_v)

        # Ordering
        ordering = request.query_params.get('ordering', '-created_at')
        valid_orderings = ['-created_at', 'created_at', 'email', '-email', 'date_joined', '-date_joined']
        if ordering in valid_orderings:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by('-created_at')

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)

        results = []
        for buyer in page:
            # Metrics
            orders_count = Order.objects.filter(buyer=buyer).count() + VehicleOrder.objects.filter(buyer=buyer).count()
            disputes_count = Dispute.objects.filter(buyer=buyer).count()

            results.append({
                "id": str(buyer.id),
                "email": buyer.email,
                "first_name": buyer.first_name,
                "last_name": buyer.last_name,
                "full_name": buyer.full_name,
                "phone_number": buyer.phone_number,
                "status": buyer.status,
                "is_active": buyer.is_active,
                "is_email_verified": buyer.is_email_verified,
                "date_joined": buyer.date_joined.isoformat() if buyer.date_joined else None,
                "created_at": buyer.created_at.isoformat() if buyer.created_at else None,
                "metrics": {
                    "orders_count": orders_count,
                    "disputes_count": disputes_count,
                },
            })

        return paginator.get_paginated_response(results)


class AdminBuyerDetailView(views.APIView):
    """
    Retrieve full buyer account profile, order history, enquiries,
    and dispute history for platform administrators.
    GET /api/v1/admin/buyers/<uuid:pk>/
    """
    permission_classes = [IsPlatformStaff]

    def get(self, request, pk):
        try:
            buyer = User.objects.get(id=pk)
        except User.DoesNotExist:
            raise NotFound("Buyer account not found.")

        # Recent orders
        recent_orders = []
        for o in Order.objects.filter(buyer=buyer).order_by('-created_at')[:10]:
            recent_orders.append({
                "id": str(o.id),
                "order_number": o.order_number,
                "total_amount": str(o.total_amount),
                "currency": o.currency,
                "status": o.status,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            })

        for vo in VehicleOrder.objects.filter(buyer=buyer).order_by('-created_at')[:5]:
            recent_orders.append({
                "id": str(vo.id),
                "order_number": vo.order_number,
                "total_amount": str(vo.total_price),
                "currency": vo.currency,
                "status": vo.status,
                "created_at": vo.created_at.isoformat() if vo.created_at else None,
            })

        # Recent disputes
        recent_disputes = []
        for d in Dispute.objects.filter(buyer=buyer).order_by('-created_at')[:10]:
            recent_disputes.append({
                "id": str(d.id),
                "dispute_number": d.dispute_number,
                "category": d.category,
                "status": d.status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            })

        return Response({
            "buyer": {
                "id": str(buyer.id),
                "email": buyer.email,
                "first_name": buyer.first_name,
                "last_name": buyer.last_name,
                "full_name": buyer.full_name,
                "phone_number": buyer.phone_number,
                "status": buyer.status,
                "is_active": buyer.is_active,
                "is_email_verified": buyer.is_email_verified,
                "date_joined": buyer.date_joined.isoformat() if buyer.date_joined else None,
                "created_at": buyer.created_at.isoformat() if buyer.created_at else None,
                "roles": buyer.roles,
            },
            "recent_orders": recent_orders,
            "recent_disputes": recent_disputes,
            "metrics": {
                "orders_count": Order.objects.filter(buyer=buyer).count() + VehicleOrder.objects.filter(buyer=buyer).count(),
                "disputes_count": Dispute.objects.filter(buyer=buyer).count(),
            },
        })


class AdminBuyerStatusView(views.APIView):
    """
    Suspend or reactivate a buyer account.
    POST /api/v1/admin/buyers/<uuid:pk>/status/
    Body: {"action": "SUSPEND" | "REACTIVATE", "reason": "Notes"}

    S1: platform administrators only (ADMIN / MARKETPLACE_ADMIN / superuser). Support agents and
    other staff cannot suspend or reactivate accounts. Suspension is enforced immediately by the
    session-version trigger (existing tokens are revoked and stay revoked after reactivation).
    """
    permission_classes = [IsMarketplaceAdmin]

    def post(self, request, pk):
        try:
            buyer = User.objects.get(id=pk)
        except User.DoesNotExist:
            raise NotFound("Buyer account not found.")

        action = request.data.get('action', '').strip().upper()
        reason = request.data.get('reason', '').strip()

        if action not in ('SUSPEND', 'REACTIVATE'):
            raise ValidationError({"action": "Action must be either SUSPEND or REACTIVATE."})

        # S1: only ordinary BUYER accounts; never staff/admins/superusers/self.
        _guard_account_status_target(request, buyer, RoleChoices.BUYER, "admin:buyer.status")

        corr_id = getattr(request, 'correlation_id', '') or get_current_correlation_id()

        if action == 'SUSPEND':
            buyer.status = AccountStatusChoices.SUSPENDED
            buyer.is_active = False
            buyer.save(update_fields=['status', 'is_active', 'updated_at'])

            record_audit_entry(
                event_type="buyer.account.suspended",
                action="admin:buyer.suspend",
                resource_type="User",
                resource_id=str(buyer.id),
                actor_id=request.user.id,
                correlation_id=corr_id,
                metadata={"reason": reason, "buyer_email": buyer.email},
            )
        else:
            buyer.status = AccountStatusChoices.ACTIVE
            buyer.is_active = True
            buyer.save(update_fields=['status', 'is_active', 'updated_at'])

            record_audit_entry(
                event_type="buyer.account.reactivated",
                action="admin:buyer.reactivate",
                resource_type="User",
                resource_id=str(buyer.id),
                actor_id=request.user.id,
                correlation_id=corr_id,
                metadata={"reason": reason, "buyer_email": buyer.email},
            )

        return Response({
            "status": "success",
            "message": f"Buyer account {action.lower()}ed successfully.",
            "account_status": buyer.status,
            "is_active": buyer.is_active,
        })


# =============================================================================
# 5. Admin Platform Orders Monitoring View
# =============================================================================

class AdminOrderMonitoringListView(views.APIView):
    """
    Platform-wide orders monitoring view for administrators.
    Allows centralized inspection of customer purchase orders across motor vehicles
    and spare parts inventory with unified server-side pagination, search, and filtering.
    GET /api/v1/admin/orders/?page=1&page_size=20&status=PAID&order_type=ALL&q=ORD-2026
    """
    permission_classes = [IsPlatformStaff]
    pagination_class = ScalableAdminPagination

    def get(self, request):
        q = request.query_params.get('q', '').strip()
        status_param = request.query_params.get('status', '').strip().upper()
        order_type_param = request.query_params.get('order_type', 'ALL').strip().upper()
        ordering_param = request.query_params.get('ordering', '-created_at').strip()

        include_parts = order_type_param in ['ALL', 'SPARE_PART', 'PART']
        include_vehicles = order_type_param in ['ALL', 'VEHICLE', 'MOTOR_VEHICLE']

        all_records = []

        # ---------------------------------------------------------------------
        # 1. Spare Part Orders (Order model)
        # ---------------------------------------------------------------------
        if include_parts:
            part_qs = (
                Order.objects.select_related('buyer')
                .prefetch_related(
                    'items',
                    'items__listing',
                    'items__listing__seller',
                    'items__listing__organisation',
                )
            )

            if q:
                part_qs = part_qs.filter(
                    Q(order_number__icontains=q)
                    | Q(buyer__email__icontains=q)
                    | Q(buyer__first_name__icontains=q)
                    | Q(buyer__last_name__icontains=q)
                    | Q(items__title__icontains=q)
                    | Q(items__mpn__icontains=q)
                ).distinct()

            if status_param and status_param != 'ALL':
                part_qs = part_qs.filter(
                    Q(status__iexact=status_param) | Q(payment_status__iexact=status_param)
                )

            for o in part_qs:
                items_data = []
                seller_emails = set()
                seller_names = set()

                for it in o.items.all():
                    listing = it.listing
                    # Defensively retrieve product attributes using real model fields:
                    # OrderItem has: title, brand, mpn, unit_price, quantity, total_amount
                    # SparePartListing has: name, brand, mpn, seller
                    item_title = it.title or (listing.name if listing else "Spare Part")
                    item_brand = it.brand or (listing.brand if listing else "")
                    item_mpn = it.mpn or (listing.mpn if listing else "")

                    seller_obj = listing.seller if listing else None
                    s_email = seller_obj.email if seller_obj else ""
                    s_name = seller_obj.full_name if seller_obj and seller_obj.full_name else (seller_obj.email if seller_obj else "")

                    if s_email:
                        seller_emails.add(s_email)
                    if s_name:
                        seller_names.add(s_name)

                    items_data.append({
                        "id": str(it.id),
                        "title": item_title,
                        "brand": item_brand,
                        "part_number": item_mpn,
                        "seller_email": s_email,
                        "seller_name": s_name,
                        "quantity": it.quantity,
                        "unit_price": str(it.unit_price),
                        "total_price": str(it.total_amount),
                    })

                all_records.append({
                    "id": str(o.id),
                    "order_number": o.order_number,
                    "order_type": "SPARE_PART",
                    "order_type_display": "Spare Part",
                    "buyer": {
                        "id": str(o.buyer.id) if o.buyer else None,
                        "email": o.buyer.email if o.buyer else "Guest",
                        "full_name": o.buyer.full_name if o.buyer and o.buyer.full_name else (o.buyer.email if o.buyer else "Guest"),
                        "phone_number": getattr(o.buyer, 'phone_number', '') if o.buyer else "",
                    },
                    "seller": {
                        "email": ", ".join(sorted(seller_emails)) if seller_emails else "",
                        "full_name": ", ".join(sorted(seller_names)) if seller_names else "Unassigned Seller",
                    },
                    "total_amount": str(o.total_amount),
                    "numeric_amount": float(o.total_amount or 0),
                    "currency": o.currency,
                    "status": o.status,
                    "fulfilment_status": o.status,
                    "payment_status": getattr(o, 'payment_status', 'PAID'),
                    "payment_method": getattr(o, 'payment_method', 'ONLINE'),
                    "item_count": len(items_data),
                    "items_preview": items_data,
                    "created_at_dt": o.created_at,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                })

        # ---------------------------------------------------------------------
        # 2. Vehicle Orders (VehicleOrder model)
        # ---------------------------------------------------------------------
        if include_vehicles:
            vehicle_qs = (
                VehicleOrder.objects.select_related(
                    'buyer',
                    'seller',
                    'listing',
                    'listing__make',
                    'listing__model',
                    'organisation',
                )
            )

            if q:
                vehicle_qs = vehicle_qs.filter(
                    Q(order_number__icontains=q)
                    | Q(buyer__email__icontains=q)
                    | Q(buyer__first_name__icontains=q)
                    | Q(buyer__last_name__icontains=q)
                    | Q(seller__email__icontains=q)
                    | Q(listing__title__icontains=q)
                )

            if status_param and status_param != 'ALL':
                vehicle_qs = vehicle_qs.filter(status__iexact=status_param)

            for vo in vehicle_qs:
                listing = vo.listing
                listing_snapshot = vo.listing_snapshot or {}

                # Vehicle product name from listing or immutable snapshot
                listing_title = (
                    listing.title if listing else listing_snapshot.get('title', 'Motor Vehicle Purchase')
                )
                listing_vin = (
                    getattr(listing, 'vin', '') if listing else listing_snapshot.get('vin', '')
                )
                listing_brand = (
                    listing.make.name if (listing and listing.make) else listing_snapshot.get('make', '')
                )
                listing_model = (
                    listing.model.name if (listing and listing.model) else listing_snapshot.get('model', '')
                )

                s_email = vo.seller.email if vo.seller else ""
                s_name = vo.seller.full_name if vo.seller and vo.seller.full_name else (vo.seller.email if vo.seller else "")

                vehicle_item = {
                    "id": str(vo.id),
                    "title": listing_title,
                    "brand": listing_brand,
                    "part_number": listing_vin,
                    "model": listing_model,
                    "seller_email": s_email,
                    "seller_name": s_name,
                    "quantity": 1,
                    "unit_price": str(vo.agreed_price),
                    "total_price": str(vo.agreed_price),
                }

                # Derive human payment status
                if vo.status in ['PAYMENT_CONFIRMED', 'READY_FOR_HANDOVER', 'COMPLETED']:
                    p_status = 'PAID'
                elif vo.status == 'PAYMENT_SUBMITTED':
                    p_status = 'SUBMITTED'
                elif vo.status == 'CANCELLED':
                    p_status = 'CANCELLED'
                else:
                    p_status = 'PENDING'

                all_records.append({
                    "id": str(vo.id),
                    "order_number": vo.order_number,
                    "order_type": "VEHICLE",
                    "order_type_display": "Motor Vehicle",
                    "buyer": {
                        "id": str(vo.buyer.id) if vo.buyer else None,
                        "email": vo.buyer.email if vo.buyer else "Guest",
                        "full_name": vo.buyer.full_name if vo.buyer and vo.buyer.full_name else (vo.buyer.email if vo.buyer else "Guest"),
                        "phone_number": getattr(vo.buyer, 'phone_number', '') if vo.buyer else "",
                    },
                    "seller": {
                        "email": s_email,
                        "full_name": s_name or "Vehicle Dealership",
                    },
                    "total_amount": str(vo.agreed_price),
                    "numeric_amount": float(vo.agreed_price or 0),
                    "currency": vo.currency,
                    "status": vo.status,
                    "fulfilment_status": vo.get_status_display() if hasattr(vo, 'get_status_display') else vo.status,
                    "payment_status": p_status,
                    "payment_method": "ESCROW_TRANSFER",
                    "item_count": 1,
                    "items_preview": [vehicle_item],
                    "created_at_dt": vo.created_at,
                    "created_at": vo.created_at.isoformat() if vo.created_at else None,
                })

        # ---------------------------------------------------------------------
        # 3. Server-Side Sorting across the unified dataset
        # ---------------------------------------------------------------------
        if ordering_param == 'created_at':
            all_records.sort(key=lambda r: r['created_at_dt'] or timezone.now())
        elif ordering_param == '-total_amount':
            all_records.sort(key=lambda r: r['numeric_amount'], reverse=True)
        elif ordering_param == 'total_amount':
            all_records.sort(key=lambda r: r['numeric_amount'])
        else:
            # Default: -created_at
            all_records.sort(key=lambda r: r['created_at_dt'] or timezone.now(), reverse=True)

        # Clean temporary sort keys
        for rec in all_records:
            rec.pop('created_at_dt', None)
            rec.pop('numeric_amount', None)

        # ---------------------------------------------------------------------
        # 4. Scalable Pagination
        # ---------------------------------------------------------------------
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(all_records, request)
        return paginator.get_paginated_response(page)
