import logging
import os
import shutil
import uuid
from typing import Any, Dict, List, Optional
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import permissions, status, views
from rest_framework.response import Response

from apps.identity.models import RoleChoices, StaffRole, User
from apps.support.models import (
    EscalationStageChoices,
    Ticket,
    TicketAttachment,
    TicketCategoryChoices,
    TicketPriorityChoices,
    TicketStatusChoices,
)
from apps.support.serializers import (
    AssignTicketPayloadSerializer,
    CreateTicketPayloadSerializer,
    CustomerTicketDetailSerializer,
    CustomerTicketListSerializer,
    EscalateTicketPayloadSerializer,
    StaffTicketDetailSerializer,
    StaffTicketListSerializer,
    TicketAttachmentSerializer,
    TicketMessagePayloadSerializer,
    TicketMessageSerializer,
    UpdateTicketStatusPayloadSerializer,
    UserBasicSerializer,
)
from apps.support.services import TicketService
from common.permissions import HasPermission, IsPlatformStaff

logger = logging.getLogger(__name__)


def _is_platform_admin(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return bool(user.is_superuser or user.has_role(RoleChoices.ADMIN))


def _has_confidential_access(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if _is_platform_admin(user):
        return True
    return bool(hasattr(user, 'has_permission') and user.has_permission('support.ticket.confidential'))


def _resolve_ticket_by_identifier(identifier: str) -> Optional[Ticket]:
    """Finds ticket by UUID primary key or ticket_number."""
    try:
        val = uuid.UUID(identifier)
        return Ticket.objects.filter(id=val).first()
    except (ValueError, AttributeError):
        return Ticket.objects.filter(ticket_number__iexact=identifier.strip()).first()


# =============================================================================
# Customer Endpoints
# =============================================================================

class CustomerTicketListCreateView(views.APIView):
    """
    GET  /api/v1/support/tickets/ - List authenticated customer's own tickets.
    POST /api/v1/support/tickets/ - Open a new support ticket.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Ticket.objects.filter(customer=request.user).order_by('-created_at')

        status_param = request.query_params.get('status')
        if status_param and status_param in TicketStatusChoices.values:
            qs = qs.filter(status=status_param)

        category_param = request.query_params.get('category')
        if category_param and category_param in TicketCategoryChoices.values:
            qs = qs.filter(category=category_param)

        serializer = CustomerTicketListSerializer(qs, many=True, context={'request': request})
        return Response({"status": "success", "count": qs.count(), "tickets": serializer.data}, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = CreateTicketPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            ticket = TicketService.create_ticket(
                customer=request.user,
                subject=data['subject'],
                description=data['description'],
                category=data.get('category', TicketCategoryChoices.GENERAL_INQUIRY),
                priority=data.get('priority', TicketPriorityChoices.MEDIUM),
                related_order_number=data.get('related_order_number', ''),
            )
            return Response({
                "status": "success",
                "message": f"Support ticket {ticket.ticket_number} created successfully.",
                "ticket": CustomerTicketDetailSerializer(ticket, context={'request': request}).data,
            }, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CustomerTicketDetailView(views.APIView):
    """
    GET /api/v1/support/tickets/<identifier>/
    Customer retrieves their own ticket details and public conversation thread.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, identifier):
        ticket = _resolve_ticket_by_identifier(identifier)
        if not ticket:
            return Response({"error": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        if ticket.customer_id != request.user.id and not _is_platform_admin(request.user):
            return Response({"error": "You do not have permission to view this ticket."}, status=status.HTTP_403_FORBIDDEN)

        serializer = CustomerTicketDetailSerializer(ticket, context={'request': request})
        return Response({"status": "success", "ticket": serializer.data}, status=status.HTTP_200_OK)


class CustomerTicketMessageView(views.APIView):
    """
    POST /api/v1/support/tickets/<identifier>/messages/
    Customer replies to their open support ticket.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        ticket = _resolve_ticket_by_identifier(identifier)
        if not ticket:
            return Response({"error": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        if ticket.customer_id != request.user.id and not _is_platform_admin(request.user):
            return Response({"error": "You do not have permission to post messages to this ticket."}, status=status.HTTP_403_FORBIDDEN)

        serializer = TicketMessagePayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            msg = TicketService.add_message(
                ticket=ticket,
                sender=request.user,
                message=data['message'],
                is_internal=False,  # Customers can NEVER post internal notes
            )
            return Response({
                "status": "success",
                "message": "Reply posted successfully.",
                "message_detail": TicketMessageSerializer(msg, context={'request': request}).data,
            }, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CustomerTicketCloseView(views.APIView):
    """
    POST /api/v1/support/tickets/<identifier>/close/
    Customer confirms resolution and closes the ticket.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        ticket = _resolve_ticket_by_identifier(identifier)
        if not ticket:
            return Response({"error": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        if ticket.customer_id != request.user.id and not _is_platform_admin(request.user):
            return Response({"error": "You do not have permission to close this ticket."}, status=status.HTTP_403_FORBIDDEN)

        try:
            updated = TicketService.update_status(
                ticket=ticket,
                actor=request.user,
                new_status=TicketStatusChoices.CLOSED,
                notes="Customer confirmed resolution and closed ticket.",
            )
            return Response({
                "status": "success",
                "message": f"Ticket {updated.ticket_number} closed successfully.",
                "ticket": CustomerTicketDetailSerializer(updated, context={'request': request}).data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


# =============================================================================
# Staff / Support Agent Endpoints
# =============================================================================

class StaffTicketListView(views.APIView):
    """
    GET /api/v1/support/agent/tickets/
    Staff queue management with multi-faceted filtering, search, and confidential masking.
    Requires 'support.ticket.manage' or Platform Admin.
    """
    permission_classes = [IsPlatformStaff, HasPermission('support.ticket.manage')]

    def get(self, request):
        has_confidential = _has_confidential_access(request.user)

        qs = Ticket.objects.select_related('customer', 'assigned_to').all()

        # Confidential ticket protection
        if not has_confidential:
            qs = qs.filter(is_confidential=False)

        # Queue filter
        queue = request.query_params.get('queue', 'all').lower()
        if queue == 'mine':
            qs = qs.filter(assigned_to=request.user)
        elif queue == 'unassigned':
            qs = qs.filter(assigned_to__isnull=True)

        # Status filter
        status_param = request.query_params.get('status')
        if status_param and status_param in TicketStatusChoices.values:
            qs = qs.filter(status=status_param)

        # Priority filter
        priority_param = request.query_params.get('priority')
        if priority_param and priority_param in TicketPriorityChoices.values:
            qs = qs.filter(priority=priority_param)

        # Category filter
        category_param = request.query_params.get('category')
        if category_param and category_param in TicketCategoryChoices.values:
            qs = qs.filter(category=category_param)

        # Escalation & SLA breach filters
        if request.query_params.get('is_escalated') == 'true':
            qs = qs.filter(is_escalated=True)
        if request.query_params.get('sla_breached') == 'true':
            qs = qs.filter(sla_breached=True)

        # Search filter
        search_query = request.query_params.get('search', '').strip()
        if search_query:
            qs = qs.filter(
                models.Q(ticket_number__icontains=search_query)
                | models.Q(subject__icontains=search_query)
                | models.Q(customer__email__icontains=search_query)
                | models.Q(related_order_number__icontains=search_query)
            )

        serializer = StaffTicketListSerializer(qs.order_by('-created_at')[:100], many=True, context={'request': request})
        return Response({
            "status": "success",
            "count": qs.count(),
            "tickets": serializer.data,
        }, status=status.HTTP_200_OK)


class StaffTicketDetailView(views.APIView):
    """
    GET /api/v1/support/agent/tickets/<identifier>/
    Full ticket details, private internal notes, and activity timeline for authorized staff.
    """
    permission_classes = [IsPlatformStaff, HasPermission('support.ticket.manage')]

    def get(self, request, identifier):
        ticket = _resolve_ticket_by_identifier(identifier)
        if not ticket:
            return Response({"error": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        if ticket.is_confidential and not _has_confidential_access(request.user):
            return Response({"error": "Access restricted: This ticket is marked confidential."}, status=status.HTTP_403_FORBIDDEN)

        serializer = StaffTicketDetailSerializer(ticket, context={'request': request})
        return Response({"status": "success", "ticket": serializer.data}, status=status.HTTP_200_OK)


class StaffTicketAssignView(views.APIView):
    """
    POST /api/v1/support/agent/tickets/<identifier>/assign/
    Assign or reassign a ticket to self or a colleague.
    """
    permission_classes = [IsPlatformStaff, HasPermission('support.ticket.manage')]

    def post(self, request, identifier):
        ticket = _resolve_ticket_by_identifier(identifier)
        if not ticket:
            return Response({"error": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        if ticket.is_confidential and not _has_confidential_access(request.user):
            return Response({"error": "Access restricted: This ticket is marked confidential."}, status=status.HTTP_403_FORBIDDEN)

        serializer = AssignTicketPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        agent_id = serializer.validated_data.get('agent_id')

        target_agent = None
        if agent_id:
            try:
                target_agent = User.objects.get(id=agent_id)
            except User.DoesNotExist:
                return Response({"error": "Target agent not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            updated = TicketService.assign_ticket(
                ticket=ticket,
                actor=request.user,
                target_agent=target_agent,
            )
            return Response({
                "status": "success",
                "message": f"Ticket {updated.ticket_number} assigned to {target_agent.email if target_agent else 'Unassigned'}.",
                "ticket": StaffTicketDetailSerializer(updated, context={'request': request}).data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StaffTicketStatusView(views.APIView):
    """
    POST /api/v1/support/agent/tickets/<identifier>/status/
    Update ticket status, enforcing state machine and resolution summaries.
    """
    permission_classes = [IsPlatformStaff, HasPermission('support.ticket.manage')]

    def post(self, request, identifier):
        ticket = _resolve_ticket_by_identifier(identifier)
        if not ticket:
            return Response({"error": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        if ticket.is_confidential and not _has_confidential_access(request.user):
            return Response({"error": "Access restricted: This ticket is marked confidential."}, status=status.HTTP_403_FORBIDDEN)

        serializer = UpdateTicketStatusPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            updated = TicketService.update_status(
                ticket=ticket,
                actor=request.user,
                new_status=data['status'],
                resolution_summary=data.get('resolution_summary', ''),
                notes=data.get('notes', ''),
            )
            return Response({
                "status": "success",
                "message": f"Ticket {updated.ticket_number} status updated to {updated.status}.",
                "ticket": StaffTicketDetailSerializer(updated, context={'request': request}).data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StaffTicketPriorityView(views.APIView):
    """
    POST /api/v1/support/agent/tickets/<identifier>/priority/
    Adjust ticket priority and recalculate SLA.
    """
    permission_classes = [IsPlatformStaff, HasPermission('support.ticket.manage')]

    def post(self, request, identifier):
        ticket = _resolve_ticket_by_identifier(identifier)
        if not ticket:
            return Response({"error": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        if ticket.is_confidential and not _has_confidential_access(request.user):
            return Response({"error": "Access restricted: This ticket is marked confidential."}, status=status.HTTP_403_FORBIDDEN)

        new_priority = request.data.get('priority')
        if new_priority not in TicketPriorityChoices.values:
            return Response({"error": f"Invalid priority '{new_priority}'."}, status=status.HTTP_400_BAD_REQUEST)

        old_priority = ticket.priority
        try:
            updated = TicketService.update_ticket_priority(
                ticket=ticket,
                actor=request.user,
                new_priority=new_priority,
            )
            return Response({
                "status": "success",
                "message": f"Priority updated from {old_priority} to {new_priority}.",
                "ticket": StaffTicketDetailSerializer(updated, context={'request': request}).data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StaffTicketMessageView(views.APIView):
    """
    POST /api/v1/support/agent/tickets/<identifier>/messages/
    Post a public agent response or private internal staff note.
    """
    permission_classes = [IsPlatformStaff, HasPermission('support.ticket.manage')]

    def post(self, request, identifier):
        ticket = _resolve_ticket_by_identifier(identifier)
        if not ticket:
            return Response({"error": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        if ticket.is_confidential and not _has_confidential_access(request.user):
            return Response({"error": "Access restricted: This ticket is marked confidential."}, status=status.HTTP_403_FORBIDDEN)

        serializer = TicketMessagePayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            msg = TicketService.add_message(
                ticket=ticket,
                sender=request.user,
                message=data['message'],
                is_internal=data.get('is_internal', False),
            )
            return Response({
                "status": "success",
                "message": "Internal note recorded." if msg.is_internal else "Public reply sent to customer.",
                "message_detail": TicketMessageSerializer(msg, context={'request': request}).data,
            }, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StaffTicketEscalateView(views.APIView):
    """
    POST /api/v1/support/agent/tickets/<identifier>/escalate/
    Manually escalate a ticket to Tier 3 / Lead.
    """
    permission_classes = [IsPlatformStaff, HasPermission('support.ticket.manage')]

    def post(self, request, identifier):
        ticket = _resolve_ticket_by_identifier(identifier)
        if not ticket:
            return Response({"error": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        if ticket.is_confidential and not _has_confidential_access(request.user):
            return Response({"error": "Access restricted: This ticket is marked confidential."}, status=status.HTTP_403_FORBIDDEN)

        serializer = EscalateTicketPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            escalated = TicketService.escalate_ticket(
                ticket=ticket,
                actor=request.user,
                reason=data['reason'],
                stage=data.get('stage', EscalationStageChoices.TIER_3),
            )
            return Response({
                "status": "success",
                "message": f"Ticket {escalated.ticket_number} escalated to stage {escalated.escalation_stage}.",
                "ticket": StaffTicketDetailSerializer(escalated, context={'request': request}).data,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StaffMetricsView(views.APIView):
    """
    GET /api/v1/support/agent/metrics/
    Real-time support operations metrics.
    Excludes confidential tickets from regular agents' totals to prevent aggregate leakage.
    """
    permission_classes = [IsPlatformStaff, HasPermission('support.ticket.manage')]

    def get(self, request):
        has_confidential = _has_confidential_access(request.user)
        base_qs = Ticket.objects.all()
        if not has_confidential:
            base_qs = base_qs.filter(is_confidential=False)

        total_open = base_qs.filter(status=TicketStatusChoices.OPEN).count()
        total_in_progress = base_qs.filter(status=TicketStatusChoices.IN_PROGRESS).count()
        total_waiting = base_qs.filter(status=TicketStatusChoices.WAITING_FOR_CUSTOMER).count()
        total_resolved = base_qs.filter(status=TicketStatusChoices.RESOLVED).count()
        total_closed = base_qs.filter(status=TicketStatusChoices.CLOSED).count()

        sla_breached_count = base_qs.filter(sla_breached=True, status__in=[TicketStatusChoices.OPEN, TicketStatusChoices.IN_PROGRESS]).count()
        escalated_count = base_qs.filter(is_escalated=True, status__in=[TicketStatusChoices.OPEN, TicketStatusChoices.IN_PROGRESS]).count()
        unassigned_count = base_qs.filter(assigned_to__isnull=True, status__in=[TicketStatusChoices.OPEN, TicketStatusChoices.IN_PROGRESS]).count()
        my_assigned_count = base_qs.filter(assigned_to=request.user, status__in=[TicketStatusChoices.OPEN, TicketStatusChoices.IN_PROGRESS, TicketStatusChoices.WAITING_FOR_CUSTOMER]).count()

        return Response({
            "status": "success",
            "metrics": {
                "open": total_open,
                "in_progress": total_in_progress,
                "waiting_for_customer": total_waiting,
                "resolved": total_resolved,
                "closed": total_closed,
                "active_total": total_open + total_in_progress + total_waiting,
                "sla_breached": sla_breached_count,
                "escalated": escalated_count,
                "unassigned": unassigned_count,
                "my_assigned": my_assigned_count,
            }
        }, status=status.HTTP_200_OK)


class StaffSupportMemberListView(views.APIView):
    """
    GET /api/v1/support/agent/staff-list/
    Lists available active Support Agents and Platform Admins for ticket assignment dropdowns.
    """
    permission_classes = [IsPlatformStaff, HasPermission('support.ticket.manage')]

    def get(self, request):
        support_role_codes = ['SUPPORT_AGENT', 'SUPPORT_LEAD', RoleChoices.ADMIN, 'ADMIN']
        agents = User.objects.filter(
            models.Q(user_roles__role__in=support_role_codes)
            | models.Q(staff_profile__staff_role__code__in=['SUPPORT_AGENT', 'SUPPORT_LEAD', 'ADMIN'])
            | models.Q(is_superuser=True),
            is_active=True,
        ).distinct().order_by('first_name', 'email')

        serializer = UserBasicSerializer(agents, many=True)
        return Response({"status": "success", "count": agents.count(), "staff": serializer.data}, status=status.HTTP_200_OK)


# =============================================================================
# Secure Attachment Endpoints
# =============================================================================

class TicketAttachmentUploadView(views.APIView):
    """
    POST /api/v1/support/tickets/<identifier>/attachments/
    Uploads a verified attachment to a ticket (optional linked message).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, identifier):
        ticket = _resolve_ticket_by_identifier(identifier)
        if not ticket:
            return Response({"error": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        is_customer = ticket.customer_id == request.user.id
        is_staff = _is_platform_admin(request.user) or (hasattr(request.user, 'has_permission') and request.user.has_permission('support.ticket.manage'))

        if not (is_customer or is_staff):
            return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({"error": "No file uploaded. Key 'file' is required."}, status=status.HTTP_400_BAD_REQUEST)

        is_internal = request.data.get('is_internal', 'false').lower() in ('true', '1')
        if is_customer and is_internal:
            is_internal = False

        message_id = request.data.get('message_id')
        linked_message = None
        if message_id:
            try:
                linked_message = ticket.messages.get(id=message_id)
            except Exception:
                pass

        try:
            attachment = TicketService.attach_file(
                ticket=ticket,
                uploader=request.user,
                file_obj=file_obj,
                message=linked_message,
                is_internal=is_internal,
            )
            return Response({
                "status": "success",
                "message": "File attached successfully.",
                "attachment": TicketAttachmentSerializer(attachment, context={'request': request}).data,
            }, status=status.HTTP_201_CREATED)
        except DjangoValidationError as e:
            return Response({"error": e.message if hasattr(e, 'message') else str(e)}, status=status.HTTP_400_BAD_REQUEST)


class TicketAttachmentDownloadView(views.APIView):
    """
    GET /api/v1/support/attachments/<attachment_id>/
    Authenticated, verified streaming download.
    Strictly forbids customer access to internal attachments.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, attachment_id):
        try:
            att = TicketAttachment.objects.select_related('ticket').get(id=attachment_id)
        except TicketAttachment.DoesNotExist:
            return Response({"error": "Attachment not found."}, status=status.HTTP_404_NOT_FOUND)

        is_customer = att.ticket.customer_id == request.user.id
        is_staff = _is_platform_admin(request.user) or (hasattr(request.user, 'has_permission') and request.user.has_permission('support.ticket.manage'))

        # Confidential check
        if att.ticket.is_confidential and not _has_confidential_access(request.user):
            return Response({"error": "Access restricted: Confidential ticket."}, status=status.HTTP_403_FORBIDDEN)

        # Internal note attachment check
        if att.is_internal and not is_staff:
            return Response({"error": "Access denied: Internal attachment."}, status=status.HTTP_403_FORBIDDEN)

        # Customer isolation check
        if not is_staff and not is_customer:
            return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        try:
            # Check private storage first; fall back to legacy MEDIA_ROOT if file was uploaded prior to migration
            file_stream = None
            if att.file.storage.exists(att.file.name):
                file_stream = att.file.open('rb')
            else:
                import os
                import shutil
                from django.conf import settings
                legacy_file_path = os.path.join(str(settings.MEDIA_ROOT), att.file.name)
                if os.path.exists(legacy_file_path) and os.path.isfile(legacy_file_path):
                    target_private_path = os.path.join(str(att.file.storage.location), att.file.name)
                    os.makedirs(os.path.dirname(target_private_path), exist_ok=True)
                    shutil.copy2(legacy_file_path, target_private_path)
                    file_stream = open(target_private_path, 'rb')

            if not file_stream:
                logger.error("Attachment %s (%s) not found on disk.", attachment_id, att.file.name)
                return Response({"error": "Attachment file not found on disk."}, status=status.HTTP_404_NOT_FOUND)

            response = FileResponse(file_stream, content_type=att.content_type)
            response['Content-Disposition'] = f'attachment; filename="{att.file_name}"'
            response['X-Content-Type-Options'] = 'nosniff'
            return response
        except Exception as exc:
            logger.exception("Error serving attachment %s: %s", attachment_id, exc)
            return Response({"error": "Failed to stream attachment."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
