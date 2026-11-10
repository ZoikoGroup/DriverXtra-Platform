import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.identity.models import RoleChoices, User
from apps.support.models import (
    EscalationStageChoices,
    SenderTypeChoices,
    Ticket,
    TicketActivity,
    TicketActivityTypeChoices,
    TicketAttachment,
    TicketCategoryChoices,
    TicketMessage,
    TicketPriorityChoices,
    TicketStatusChoices,
    ticket_attachment_upload_path,
)
from apps.support.sla import (
    calculate_business_seconds_between,
    calculate_sla_deadlines,
    is_within_reopen_window,
)
from platform_core.audit.writer import record_audit_entry, record_denied_audit_entry

logger = logging.getLogger(__name__)

# Allowed MIME types and magic byte headers for attachment verification
ALLOWED_MIME_TYPES = {
    'image/jpeg': [b'\xff\xd8\xff'],
    'image/png': [b'\x89PNG\r\n\x1a\n'],
    'image/webp': [b'RIFF'],  # RIFF....WEBP
    'application/pdf': [b'%PDF'],
    'text/plain': [],  # Verified via utf-8 text decoding
}


def _is_platform_admin(user: Any) -> bool:
    if not user or not user.is_authenticated:
        return False
    return bool(user.is_superuser or user.has_role(RoleChoices.ADMIN))


def _has_permission(user: Any, perm_code: str) -> bool:
    if not user or not user.is_authenticated:
        return False
    if _is_platform_admin(user):
        return True
    if hasattr(user, 'has_permission'):
        return user.has_permission(perm_code)
    return False


def _generate_ticket_number() -> str:
    """Generates candidate ticket number: TICK-YYYYMMDD-XXXXXX."""
    date_str = timezone.now().strftime("%Y%m%d")
    random_suffix = secrets.token_hex(3).upper()
    return f"TICK-{date_str}-{random_suffix}"


class TicketService:
    """Authoritative business logic for Customer Support & Ticketing."""

    @classmethod
    def create_ticket(
        cls,
        customer: User,
        subject: str,
        description: str,
        category: str = TicketCategoryChoices.GENERAL_INQUIRY,
        priority: str = TicketPriorityChoices.MEDIUM,
        related_order_number: str = "",
        is_confidential: bool = False,
        correlation_id: str = "",
    ) -> Ticket:
        """Creates a new support ticket with calculated SLA deadlines."""
        if not customer or not customer.is_authenticated:
            raise DjangoValidationError("Authentication required to create a support ticket.")

        clean_subject = (subject or '').strip()
        if not clean_subject or len(clean_subject) < 5:
            raise DjangoValidationError("Ticket subject must be at least 5 characters.")

        clean_desc = (description or '').strip()
        if not clean_desc or len(clean_desc) < 10:
            raise DjangoValidationError("Ticket description must be at least 10 characters.")

        if category not in TicketCategoryChoices.values:
            raise DjangoValidationError(f"Invalid ticket category '{category}'.")

        if priority not in TicketPriorityChoices.values:
            raise DjangoValidationError(f"Invalid ticket priority '{priority}'.")

        # Initial SLA deadlines
        now = timezone.now()
        first_resp_due, res_due = calculate_sla_deadlines(priority, start_dt=now)

        ticket = None
        for attempt in range(5):
            candidate_number = _generate_ticket_number()
            try:
                with transaction.atomic():
                    ticket = Ticket(
                        ticket_number=candidate_number,
                        customer=customer,
                        subject=clean_subject,
                        description=clean_desc,
                        category=category,
                        priority=priority,
                        status=TicketStatusChoices.OPEN,
                        related_order_number=(related_order_number or '').strip(),
                        is_confidential=bool(is_confidential),
                        created_at=now,
                        first_response_due_at=first_resp_due,
                        resolution_due_at=res_due,
                        last_customer_activity_at=now,
                    )
                    ticket.save()
                    # Align deadlines with the exact persisted created_at to eliminate any sub-millisecond drift
                    precise_first_resp, precise_res = calculate_sla_deadlines(priority, start_dt=ticket.created_at)
                    if ticket.first_response_due_at != precise_first_resp or ticket.resolution_due_at != precise_res:
                        ticket.first_response_due_at = precise_first_resp
                        ticket.resolution_due_at = precise_res
                        ticket.save(update_fields=['first_response_due_at', 'resolution_due_at'])

                    TicketActivity.objects.create(
                        ticket=ticket,
                        actor=customer,
                        activity_type=TicketActivityTypeChoices.CREATED,
                        notes=f"Ticket created with priority '{priority}' and category '{category}'.",
                    )
                    record_audit_entry(
                        event_type="support.ticket.created",
                        action="support:ticket.create",
                        resource_type="Ticket",
                        resource_id=str(ticket.id),
                        actor_id=customer.id,
                        correlation_id=correlation_id,
                        metadata={
                            "ticket_number": ticket.ticket_number,
                            "subject": ticket.subject,
                            "category": ticket.category,
                            "priority": ticket.priority,
                            "customer_email": customer.email,
                            "is_confidential": ticket.is_confidential,
                        },
                    )
                    break
            except IntegrityError:
                if attempt == 4:
                    raise DjangoValidationError("Unable to allocate unique ticket number. Please retry.")

        return ticket

    @classmethod
    def add_message(
        cls,
        ticket: Ticket,
        sender: User,
        message: str,
        is_internal: bool = False,
        sender_type: Optional[str] = None,
        correlation_id: str = "",
    ) -> TicketMessage:
        """
        Adds a conversation message or internal staff note.
        Enforces customer vs staff isolation and SLA response/resume behavior.
        """
        clean_msg = (message or '').strip()
        if not clean_msg:
            raise DjangoValidationError("Message content cannot be blank.")

        is_customer = ticket.customer_id == sender.id
        is_staff = _is_platform_admin(sender) or _has_permission(sender, 'support.ticket.manage')

        if not (is_customer or is_staff):
            raise DjangoValidationError("Permission denied: You cannot post messages on this ticket.")

        # Customers can NEVER post internal notes
        if is_customer and is_internal:
            is_internal = False

        if sender_type is None:
            if is_customer:
                sender_type = SenderTypeChoices.CUSTOMER
            elif is_staff:
                sender_type = SenderTypeChoices.AGENT
            else:
                sender_type = SenderTypeChoices.SYSTEM

        now = timezone.now()

        with transaction.atomic():
            locked = Ticket.objects.select_for_update().get(id=ticket.id)

            if locked.status == TicketStatusChoices.CLOSED:
                raise DjangoValidationError(f"Cannot reply to closed ticket {locked.ticket_number}. Closed tickets cannot be modified.")

            msg_record = TicketMessage.objects.create(
                ticket=locked,
                sender=sender,
                sender_type=sender_type,
                message=clean_msg,
                is_internal=is_internal,
            )

            if is_internal:
                # Internal note: record activity & audit, never touch customer SLA or status
                TicketActivity.objects.create(
                    ticket=locked,
                    actor=sender,
                    activity_type=TicketActivityTypeChoices.INTERNAL_NOTE,
                    notes="Internal staff note added.",
                )
                record_audit_entry(
                    event_type="support.ticket.internal_note",
                    action="support:ticket.internal_note",
                    resource_type="Ticket",
                    resource_id=str(locked.id),
                    actor_id=sender.id,
                    correlation_id=correlation_id,
                    metadata={"ticket_number": locked.ticket_number, "note_length": len(clean_msg)},
                )
            else:
                # Public response
                if is_customer:
                    locked.last_customer_activity_at = now
                    # Customer reply resumes SLA if paused in WAITING_FOR_CUSTOMER
                    if locked.status == TicketStatusChoices.WAITING_FOR_CUSTOMER:
                        old_status = locked.status
                        locked.status = TicketStatusChoices.IN_PROGRESS
                        if locked.sla_paused_at:
                            paused_duration = now - locked.sla_paused_at
                            locked.total_paused_seconds += int(paused_duration.total_seconds())
                            if locked.resolution_due_at:
                                locked.resolution_due_at += paused_duration
                            locked.sla_paused_at = None
                            TicketActivity.objects.create(
                                ticket=locked,
                                actor=sender,
                                activity_type=TicketActivityTypeChoices.SLA_RESUMED,
                                notes=f"Resolution SLA resumed after {int(paused_duration.total_seconds() / 60)} minutes.",
                            )
                        TicketActivity.objects.create(
                            ticket=locked,
                            actor=sender,
                            activity_type=TicketActivityTypeChoices.STATUS_CHANGED,
                            old_value=old_status,
                            new_value=locked.status,
                            notes="Customer replied; status moved to IN_PROGRESS.",
                        )
                else:
                    # Agent public response
                    locked.last_agent_activity_at = now
                    # Stamp first response SLA if this is the first public response
                    if locked.first_responded_at is None:
                        locked.first_responded_at = now
                        if locked.first_response_due_at and now > locked.first_response_due_at:
                            locked.is_first_response_overdue = True
                            locked.sla_breached = True

                locked.save()

                TicketActivity.objects.create(
                    ticket=locked,
                    actor=sender,
                    activity_type=TicketActivityTypeChoices.PUBLIC_REPLY,
                    notes="Public message sent.",
                )
                record_audit_entry(
                    event_type="support.ticket.customer_replied" if is_customer else "support.ticket.agent_replied",
                    action="support:ticket.message",
                    resource_type="Ticket",
                    resource_id=str(locked.id),
                    actor_id=sender.id,
                    correlation_id=correlation_id,
                    metadata={
                        "ticket_number": locked.ticket_number,
                        "sender_type": sender_type,
                        "is_internal": False,
                    },
                )

        return msg_record

    @classmethod
    def update_status(
        cls,
        ticket: Ticket,
        actor: User,
        new_status: str,
        resolution_summary: str = "",
        notes: str = "",
        correlation_id: str = "",
    ) -> Ticket:
        """Enforces the strict ticket lifecycle state machine."""
        if new_status not in TicketStatusChoices.values:
            raise DjangoValidationError(f"Invalid ticket status '{new_status}'.")

        is_system = actor is None
        is_customer = bool(actor and ticket.customer_id == actor.id)
        is_staff = bool(actor and (_is_platform_admin(actor) or _has_permission(actor, 'support.ticket.manage')))

        if not (is_system or is_customer or is_staff):
            raise DjangoValidationError("Permission denied: You cannot change the status of this ticket.")

        if is_system and new_status != TicketStatusChoices.CLOSED:
            raise DjangoValidationError("System action can only transition ticket to CLOSED.")

        now = timezone.now()

        with transaction.atomic():
            locked = Ticket.objects.select_for_update().get(id=ticket.id)
            current_status = locked.status

            if current_status == new_status:
                return locked

            # Rule 1: Terminal state
            if current_status == TicketStatusChoices.CLOSED:
                raise DjangoValidationError(f"Ticket {locked.ticket_number} is closed and cannot be reopened or updated.")

            # Rule 2: Customer allowed transitions
            if is_customer and not is_staff:
                # Customer can close a resolved ticket or reopen within 72h
                if current_status == TicketStatusChoices.RESOLVED and new_status == TicketStatusChoices.IN_PROGRESS:
                    # Reopening check
                    if not is_within_reopen_window(locked, now):
                        raise DjangoValidationError(
                            f"Ticket {locked.ticket_number} was resolved over 72 hours ago and cannot be reopened. Please open a new ticket."
                        )
                elif current_status in (TicketStatusChoices.RESOLVED, TicketStatusChoices.WAITING_FOR_CUSTOMER) and new_status == TicketStatusChoices.CLOSED:
                    pass  # Customer accepts resolution
                else:
                    raise DjangoValidationError(
                        f"Customer is not authorized to transition ticket from '{current_status}' to '{new_status}'."
                    )

            # Rule 3: Resolution summary enforcement
            if new_status == TicketStatusChoices.RESOLVED:
                clean_res = (resolution_summary or '').strip()
                if not clean_res or len(clean_res) < 10:
                    raise DjangoValidationError("A comprehensive resolution summary (minimum 10 characters) is required to resolve a ticket.")
                locked.resolution_summary = clean_res
                locked.resolved_at = now
                locked.resolved_by = actor
                if locked.resolution_due_at and now > locked.resolution_due_at:
                    locked.is_resolution_overdue = True
                    locked.sla_breached = True

            # Rule 4: SLA Pausing on WAITING_FOR_CUSTOMER
            if new_status == TicketStatusChoices.WAITING_FOR_CUSTOMER:
                locked.sla_paused_at = now
                TicketActivity.objects.create(
                    ticket=locked,
                    actor=actor,
                    activity_type=TicketActivityTypeChoices.SLA_PAUSED,
                    notes="Resolution SLA paused while awaiting customer response.",
                )

            # Rule 5: SLA Resuming when leaving WAITING_FOR_CUSTOMER
            if current_status == TicketStatusChoices.WAITING_FOR_CUSTOMER and new_status != TicketStatusChoices.WAITING_FOR_CUSTOMER:
                if locked.sla_paused_at:
                    paused_duration = now - locked.sla_paused_at
                    locked.total_paused_seconds += int(paused_duration.total_seconds())
                    if locked.resolution_due_at:
                        locked.resolution_due_at += paused_duration
                    locked.sla_paused_at = None
                    TicketActivity.objects.create(
                        ticket=locked,
                        actor=actor,
                        activity_type=TicketActivityTypeChoices.SLA_RESUMED,
                        notes=f"Resolution SLA resumed after {int(paused_duration.total_seconds() / 60)} minutes.",
                    )

            # Rule 6: Reopening from RESOLVED
            if current_status == TicketStatusChoices.RESOLVED and new_status == TicketStatusChoices.IN_PROGRESS:
                locked.reopen_count += 1
                locked.resolved_at = None
                locked.resolved_by = None
                # Extend resolution due date by 24h for reopened investigation
                if locked.resolution_due_at:
                    locked.resolution_due_at = now + timedelta(hours=24)
                TicketActivity.objects.create(
                    ticket=locked,
                    actor=actor,
                    activity_type=TicketActivityTypeChoices.REOPENED,
                    notes=f"Ticket reopened (Reopen count: {locked.reopen_count}).",
                )

            # Rule 7: Closing ticket
            if new_status == TicketStatusChoices.CLOSED:
                locked.closed_at = now

            locked.status = new_status
            locked.save()

            if is_system:
                activity_type = TicketActivityTypeChoices.SYSTEM_AUTO_CLOSED
                act_notes = notes or "Ticket auto-closed by system due to customer inactivity."
                audit_action = "support:ticket.system_auto_close"
            else:
                activity_type = TicketActivityTypeChoices.STATUS_CHANGED
                act_notes = notes or f"Status changed from {current_status} to {new_status}."
                audit_action = "support:ticket.status_update"

            TicketActivity.objects.create(
                ticket=locked,
                actor=actor,
                activity_type=activity_type,
                old_value=current_status,
                new_value=new_status,
                notes=act_notes,
            )

            record_audit_entry(
                event_type="support.ticket.status_updated",
                action=audit_action,
                resource_type="Ticket",
                resource_id=str(locked.id),
                actor_id=actor.id if actor else None,
                correlation_id=correlation_id,
                metadata={
                    "ticket_number": locked.ticket_number,
                    "previous_status": current_status,
                    "new_status": new_status,
                    "reopen_count": locked.reopen_count,
                    "is_system_action": is_system,
                    "reason": "INACTIVITY_AUTO_CLOSED" if is_system else None,
                },
            )

        return locked

    @classmethod
    def update_ticket_priority(
        cls,
        ticket: Ticket,
        actor: User,
        new_priority: str,
        correlation_id: str = "",
    ) -> Ticket:
        """
        Adjusts ticket priority and recalculates SLA deadlines transactionally.
        Preserves elapsed time, paused time, and respects first-response status.
        """
        if new_priority not in TicketPriorityChoices.values:
            raise DjangoValidationError(f"Invalid priority '{new_priority}'.")

        now = timezone.now()

        with transaction.atomic():
            locked = Ticket.objects.select_for_update().get(id=ticket.id)

            if locked.status in [TicketStatusChoices.RESOLVED, TicketStatusChoices.CLOSED]:
                raise DjangoValidationError("Cannot change priority of a resolved or closed ticket.")

            old_priority = locked.priority
            if old_priority == new_priority:
                return locked

            # Recalculate SLA deadlines based on new priority
            new_first_resp, new_res = calculate_sla_deadlines(new_priority, start_dt=locked.created_at)

            # If first response has NOT been recorded yet, update first response deadline and overdue status
            if not locked.first_responded_at:
                locked.first_response_due_at = new_first_resp
                locked.is_first_response_overdue = (now >= new_first_resp)

            # Apply total paused seconds to the new resolution deadline
            locked.resolution_due_at = new_res + timedelta(seconds=locked.total_paused_seconds)

            # If ticket is currently paused (WAITING_FOR_CUSTOMER), it is never resolution-overdue
            if locked.sla_paused_at is not None:
                locked.is_resolution_overdue = False
            else:
                locked.is_resolution_overdue = (now >= locked.resolution_due_at)

            # Overall SLA breached flag
            locked.sla_breached = locked.is_first_response_overdue or locked.is_resolution_overdue
            locked.priority = new_priority
            locked.save(update_fields=[
                'priority',
                'first_response_due_at',
                'is_first_response_overdue',
                'resolution_due_at',
                'is_resolution_overdue',
                'sla_breached',
                'updated_at',
            ])

            TicketActivity.objects.create(
                ticket=locked,
                actor=actor,
                activity_type=TicketActivityTypeChoices.PRIORITY_CHANGED,
                old_value=old_priority,
                new_value=new_priority,
                notes=f"Priority updated from {old_priority} to {new_priority}. SLA recalculated.",
            )

            record_audit_entry(
                event_type="support.ticket.priority_updated",
                action="support:ticket.priority_update",
                resource_type="Ticket",
                resource_id=str(locked.id),
                actor_id=actor.id if actor else None,
                correlation_id=correlation_id,
                metadata={
                    "ticket_number": locked.ticket_number,
                    "old_priority": old_priority,
                    "new_priority": new_priority,
                    "first_response_due_at": locked.first_response_due_at.isoformat() if locked.first_response_due_at else None,
                    "resolution_due_at": locked.resolution_due_at.isoformat() if locked.resolution_due_at else None,
                },
            )

        return locked

    @classmethod
    def assign_ticket(
        cls,
        ticket: Ticket,
        actor: User,
        target_agent: Optional[User],
        correlation_id: str = "",
    ) -> Ticket:
        """Assigns or reassigns a ticket to an active Support Agent or Platform Admin."""
        has_perm = _is_platform_admin(actor) or _has_permission(actor, 'support.ticket.manage')
        if not has_perm:
            raise DjangoValidationError("Permission denied: You do not have permission to assign support tickets.")

        if target_agent is not None:
            if not target_agent.is_active:
                raise DjangoValidationError("Cannot assign ticket: Target user is inactive.")

            # Must be Support Agent or Platform Admin
            is_valid_agent = _is_platform_admin(target_agent)
            if not is_valid_agent:
                profile = getattr(target_agent, 'staff_profile', None)
                if profile and profile.staff_role and profile.staff_role.code == 'SUPPORT_AGENT':
                    is_valid_agent = True

            if not is_valid_agent:
                raise DjangoValidationError("Cannot assign ticket: Target user is not an active Support Agent.")

        now = timezone.now()

        with transaction.atomic():
            locked = Ticket.objects.select_for_update().get(id=ticket.id)
            old_agent = locked.assigned_to

            if old_agent == target_agent:
                return locked

            locked.assigned_to = target_agent
            locked.assigned_by = actor
            locked.assigned_at = now if target_agent else None

            # If ticket was OPEN, assigning moves it to IN_PROGRESS
            if target_agent and locked.status == TicketStatusChoices.OPEN:
                locked.status = TicketStatusChoices.IN_PROGRESS

            locked.save()

            old_name = old_agent.email if old_agent else "Unassigned"
            new_name = target_agent.email if target_agent else "Unassigned"

            TicketActivity.objects.create(
                ticket=locked,
                actor=actor,
                activity_type=TicketActivityTypeChoices.ASSIGNED,
                old_value=old_name,
                new_value=new_name,
                notes=f"Ticket assigned from {old_name} to {new_name}.",
            )

            record_audit_entry(
                event_type="support.ticket.assigned",
                action="support:ticket.assign",
                resource_type="Ticket",
                resource_id=str(locked.id),
                actor_id=actor.id,
                correlation_id=correlation_id,
                metadata={
                    "ticket_number": locked.ticket_number,
                    "previous_agent_id": str(old_agent.id) if old_agent else None,
                    "new_agent_id": str(target_agent.id) if target_agent else None,
                },
            )

        return locked

    @classmethod
    def handle_agent_deactivation(
        cls,
        agent: User,
        actor: Optional[User] = None,
        correlation_id: str = "",
    ) -> int:
        """
        Controlled transactional method to unassign all active tickets
        when a Support Agent is deactivated or suspended.
        """
        active_statuses = [
            TicketStatusChoices.OPEN,
            TicketStatusChoices.IN_PROGRESS,
            TicketStatusChoices.WAITING_FOR_CUSTOMER,
        ]

        with transaction.atomic():
            tickets_to_unassign = list(
                Ticket.objects.select_for_update()
                .filter(assigned_to=agent, status__in=active_statuses)
            )

            count = len(tickets_to_unassign)
            if count == 0:
                return 0

            for t in tickets_to_unassign:
                t.assigned_to = None
                t.assigned_at = None
                t.save(update_fields=['assigned_to', 'assigned_at', 'updated_at'])

                TicketActivity.objects.create(
                    ticket=t,
                    actor=actor,
                    activity_type=TicketActivityTypeChoices.AGENT_DEACTIVATED_UNASSIGNED,
                    old_value=agent.email,
                    new_value="Unassigned",
                    notes="Assigned agent was deactivated; ticket returned to triage queue.",
                )

                record_audit_entry(
                    event_type="support.ticket.reassigned",
                    action="support:ticket.unassign_deactivated",
                    resource_type="Ticket",
                    resource_id=str(t.id),
                    actor_id=actor.id if actor else None,
                    correlation_id=correlation_id,
                    metadata={
                        "ticket_number": t.ticket_number,
                        "deactivated_agent_id": str(agent.id),
                        "reason": "AGENT_DEACTIVATED",
                    },
                )

            return count

    @classmethod
    def escalate_ticket(
        cls,
        ticket: Ticket,
        actor: User,
        reason: str,
        stage: int = EscalationStageChoices.TIER_3,
        correlation_id: str = "",
    ) -> Ticket:
        """Escalates a ticket. Fully idempotent across repeated calls."""
        now = timezone.now()

        with transaction.atomic():
            locked = Ticket.objects.select_for_update().get(id=ticket.id)

            if locked.status == TicketStatusChoices.CLOSED:
                raise DjangoValidationError("Cannot escalate a closed ticket.")

            # Idempotency check: don't re-escalate to same or lower stage
            if locked.is_escalated and locked.escalation_stage >= stage:
                return locked

            locked.is_escalated = True
            locked.escalation_stage = stage
            locked.escalated_at = now
            locked.escalation_reason = reason.strip()
            locked.save(update_fields=['is_escalated', 'escalation_stage', 'escalated_at', 'escalation_reason', 'updated_at'])

            TicketActivity.objects.create(
                ticket=locked,
                actor=actor,
                activity_type=TicketActivityTypeChoices.ESCALATED,
                new_value=str(stage),
                notes=reason.strip(),
            )

            record_audit_entry(
                event_type="support.ticket.escalated",
                action="support:ticket.escalate",
                resource_type="Ticket",
                resource_id=str(locked.id),
                actor_id=actor.id if actor else None,
                correlation_id=correlation_id,
                metadata={
                    "ticket_number": locked.ticket_number,
                    "escalation_stage": stage,
                    "reason": reason.strip(),
                },
            )

        return locked

    @classmethod
    def check_slas_and_escalate(cls, now: Optional[datetime] = None) -> Dict[str, int]:
        """
        Scheduled SLA monitoring job.
        Evaluates 75% warning, 100% breach, and Tier 3 prolonged breach.
        Idempotent across repeated executions.
        Auto-closes tickets in WAITING_FOR_CUSTOMER exceeding inactivity window.
        """
        if now is None:
            now = timezone.now()

        metrics = {
            "evaluated": 0,
            "warning_75_escalated": 0,
            "breach_100_escalated": 0,
            "tier_3_escalated": 0,
            "auto_closed_inactive": 0,
        }

        active_statuses = [TicketStatusChoices.OPEN, TicketStatusChoices.IN_PROGRESS]

        # 1. First Response SLA evaluation (only unresponded active tickets)
        unresponded = Ticket.objects.filter(
            status__in=active_statuses,
            first_responded_at__isnull=True,
            first_response_due_at__isnull=False,
        )

        for t in unresponded:
            metrics["evaluated"] += 1
            if t.first_responded_at:
                continue

            # Check 100% breach
            if t.first_response_due_at and now >= t.first_response_due_at:
                if not t.is_first_response_overdue or t.escalation_stage < EscalationStageChoices.BREACH_100:
                    t.is_first_response_overdue = True
                    t.sla_breached = True
                    t.save(update_fields=['is_first_response_overdue', 'sla_breached', 'updated_at'])
                    cls.escalate_ticket(
                        ticket=t,
                        actor=None,
                        reason="First response SLA breached.",
                        stage=EscalationStageChoices.BREACH_100,
                    )
                    metrics["breach_100_escalated"] += 1
            elif t.first_response_due_at:
                # Check 75% warning threshold using actual business seconds
                total_window = calculate_business_seconds_between(t.created_at, t.first_response_due_at, priority=t.priority)
                elapsed = calculate_business_seconds_between(t.created_at, now, priority=t.priority)
                if total_window > 0 and (elapsed / total_window) >= 0.75:
                    if t.escalation_stage < EscalationStageChoices.WARNING_75:
                        cls.escalate_ticket(
                            ticket=t,
                            actor=None,
                            reason="Approaching first response SLA breach (75% elapsed).",
                            stage=EscalationStageChoices.WARNING_75,
                        )
                        metrics["warning_75_escalated"] += 1

        # 2. Resolution SLA evaluation (active, not paused)
        active_resolution = Ticket.objects.filter(
            status__in=active_statuses,
            resolution_due_at__isnull=False,
            resolved_at__isnull=True,
            sla_paused_at__isnull=True,  # Paused tickets are NEVER resolution-overdue or warned
        )

        for t in active_resolution:
            metrics["evaluated"] += 1
            if t.resolved_at:
                continue

            if t.resolution_due_at and now >= t.resolution_due_at:
                overdue_seconds = (now - t.resolution_due_at).total_seconds()
                # If CRITICAL or overdue by > 24 hours -> Tier 3
                target_stage = EscalationStageChoices.TIER_3 if (t.priority == TicketPriorityChoices.CRITICAL or overdue_seconds >= 86400) else EscalationStageChoices.BREACH_100

                if not t.is_resolution_overdue or t.escalation_stage < target_stage:
                    t.is_resolution_overdue = True
                    t.sla_breached = True
                    t.save(update_fields=['is_resolution_overdue', 'sla_breached', 'updated_at'])
                    cls.escalate_ticket(
                        ticket=t,
                        actor=None,
                        reason=f"Resolution SLA breached ({'Tier 3 Critical' if target_stage == EscalationStageChoices.TIER_3 else 'Standard Breach'}).",
                        stage=target_stage,
                    )
                    if target_stage == EscalationStageChoices.TIER_3:
                        metrics["tier_3_escalated"] += 1
                    else:
                        metrics["breach_100_escalated"] += 1
            elif t.resolution_due_at:
                # Check 75% resolution warning threshold using business seconds
                total_res_window = calculate_business_seconds_between(t.created_at, t.resolution_due_at, priority=t.priority) - t.total_paused_seconds
                consumed_res = calculate_business_seconds_between(t.created_at, now, priority=t.priority) - t.total_paused_seconds
                if total_res_window > 0 and (consumed_res / total_res_window) >= 0.75:
                    if t.escalation_stage < EscalationStageChoices.WARNING_75:
                        cls.escalate_ticket(
                            ticket=t,
                            actor=None,
                            reason="Approaching resolution SLA breach (75% elapsed).",
                            stage=EscalationStageChoices.WARNING_75,
                        )
                        metrics["warning_75_escalated"] += 1

        # 3. Inactivity auto-closure for tickets in WAITING_FOR_CUSTOMER
        inactivity_days = getattr(settings, 'SUPPORT_INACTIVITY_CLOSE_DAYS', 5)
        inactivity_cutoff = now - timedelta(days=inactivity_days)

        stale_waiting = Ticket.objects.filter(
            status=TicketStatusChoices.WAITING_FOR_CUSTOMER,
            last_customer_activity_at__lt=inactivity_cutoff,
        )

        for t in stale_waiting:
            cls.update_status(
                ticket=t,
                actor=None,
                new_status=TicketStatusChoices.CLOSED,
                notes=f"Auto-closed due to customer inactivity ({inactivity_days} days without response).",
            )
            metrics["auto_closed_inactive"] += 1

        return metrics

    @classmethod
    def attach_file(
        cls,
        ticket: Ticket,
        uploader: User,
        file_obj: Any,
        message: Optional[TicketMessage] = None,
        is_internal: bool = False,
        correlation_id: str = "",
    ) -> TicketAttachment:
        """
        Validates magic bytes, size limits, and securely stores attachments in private storage.
        Cleans up stored private media file if database persistence fails.
        """
        is_customer = ticket.customer_id == uploader.id
        is_staff = _is_platform_admin(uploader) or _has_permission(uploader, 'support.ticket.manage')

        if not (is_customer or is_staff):
            raise DjangoValidationError("Permission denied: You cannot upload attachments to this ticket.")

        if is_customer and is_internal:
            is_internal = False

        # File size check
        max_bytes = getattr(settings, 'SUPPORT_ATTACHMENT_MAX_BYTES', 10485760)  # 10MB
        file_size = getattr(file_obj, 'size', 0)
        if file_size > max_bytes:
            raise DjangoValidationError(f"Attachment exceeds maximum permitted size of {int(max_bytes / (1024 * 1024))} MB.")

        # Per-message attachment count limit
        if message:
            max_files = getattr(settings, 'SUPPORT_ATTACHMENT_MAX_FILES_PER_MESSAGE', 5)
            if message.attachments.count() >= max_files:
                raise DjangoValidationError(f"Maximum limit of {max_files} attachments per message reached.")

        # Magic byte signature verification
        file_obj.seek(0)
        header = file_obj.read(32)
        file_obj.seek(0)

        raw_name = getattr(file_obj, 'name', 'unnamed')
        ext = os.path.splitext(raw_name)[1].lower()

        # Strict extension blocking
        blocked_exts = {'.exe', '.bat', '.cmd', '.sh', '.py', '.js', '.php', '.html', '.svg', '.dll', '.msi'}
        if ext in blocked_exts:
            raise DjangoValidationError(f"File type '{ext}' is prohibited for security reasons.")

        detected_mime = None
        for mime, sigs in ALLOWED_MIME_TYPES.items():
            for sig in sigs:
                if header.startswith(sig):
                    detected_mime = mime
                    break
            if detected_mime:
                break

        if not detected_mime:
            # Check text/plain
            try:
                header.decode('utf-8')
                if ext in ('.txt', '.log', '.csv'):
                    detected_mime = 'text/plain'
            except UnicodeDecodeError:
                pass

        if not detected_mime:
            raise DjangoValidationError(f"Invalid file content or unsupported format for '{raw_name}'. Allowed: JPEG, PNG, WEBP, PDF, TXT.")

        safe_display_name = os.path.basename(raw_name)

        attachment = TicketAttachment(
            ticket=ticket,
            message=message,
            uploader=uploader,
            file_name=safe_display_name,
            file_size=file_size,
            content_type=detected_mime,
            is_internal=is_internal,
        )

        storage_path = ticket_attachment_upload_path(attachment, raw_name)
        saved_name = attachment.file.storage.save(storage_path, file_obj)
        attachment.file.name = saved_name

        try:
            with transaction.atomic():
                attachment.save()
                record_audit_entry(
                    event_type="support.ticket.attachment_uploaded",
                    action="support:ticket.upload_attachment",
                    resource_type="TicketAttachment",
                    resource_id=str(attachment.id),
                    actor_id=uploader.id,
                    correlation_id=correlation_id,
                    metadata={
                        "ticket_number": ticket.ticket_number,
                        "file_name": attachment.file_name,
                        "file_size": attachment.file_size,
                        "content_type": attachment.content_type,
                        "is_internal": is_internal,
                    },
                )
        except Exception:
            # Clean up stored file if database creation failed
            if saved_name:
                try:
                    attachment.file.storage.delete(saved_name)
                except Exception:
                    pass
            raise

        return attachment
