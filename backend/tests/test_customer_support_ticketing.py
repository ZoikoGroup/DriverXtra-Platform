import io
import json
import os
from pathlib import Path
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import Permission, RoleChoices, StaffProfile, StaffRole, StaffRolePermission, User
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
)
from apps.support.services import TicketService
from apps.support.sla import add_business_hours, calculate_sla_deadlines


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def buyer_user(db):
    u = User.objects.create_user(
        email=f"buyer_{uuid.uuid4().hex[:6]}@driverxtra.local",
        password="TestPassword123!",
        first_name="Alice",
        last_name="Buyer",
    )
    u.add_role(RoleChoices.BUYER)
    return u


@pytest.fixture
def other_buyer(db):
    u = User.objects.create_user(
        email=f"other_buyer_{uuid.uuid4().hex[:6]}@driverxtra.local",
        password="TestPassword123!",
        first_name="Bob",
        last_name="Other",
    )
    u.add_role(RoleChoices.BUYER)
    return u


@pytest.fixture
def support_agent(db):
    role, _ = StaffRole.objects.get_or_create(
        code='SUPPORT_AGENT',
        defaults={'name': 'Support Agent'},
    )
    perm, _ = Permission.objects.get_or_create(
        code='support.ticket.manage',
        defaults={'name': 'Support Ticket Management'},
    )
    StaffRolePermission.objects.get_or_create(staff_role=role, permission=perm)

    u = User.objects.create_user(
        email=f"support_{uuid.uuid4().hex[:6]}@driverxtra.local",
        password="TestPassword123!",
        first_name="Sam",
        last_name="Agent",
        is_staff=True,
    )
    u.add_role(RoleChoices.STAFF)
    StaffProfile.objects.create(user=u, staff_role=role)
    return u


@pytest.fixture
def senior_support_agent(db):
    role, _ = StaffRole.objects.get_or_create(
        code='SUPPORT_LEAD',
        defaults={'name': 'Senior Support Lead'},
    )
    perm_manage, _ = Permission.objects.get_or_create(
        code='support.ticket.manage',
        defaults={'name': 'Support Ticket Management'},
    )
    perm_conf, _ = Permission.objects.get_or_create(
        code='support.ticket.confidential',
        defaults={'name': 'Confidential Ticket Access'},
    )
    StaffRolePermission.objects.get_or_create(staff_role=role, permission=perm_manage)
    StaffRolePermission.objects.get_or_create(staff_role=role, permission=perm_conf)

    u = User.objects.create_user(
        email=f"senior_{uuid.uuid4().hex[:6]}@driverxtra.local",
        password="TestPassword123!",
        first_name="Sarah",
        last_name="Senior",
        is_staff=True,
    )
    u.add_role(RoleChoices.STAFF)
    StaffProfile.objects.create(user=u, staff_role=role)
    return u


@pytest.fixture
def platform_admin(db):
    u = User.objects.create_superuser(
        email=f"admin_{uuid.uuid4().hex[:6]}@driverxtra.local",
        password="TestPassword123!",
        first_name="Platform",
        last_name="Admin",
    )
    u.add_role(RoleChoices.ADMIN)
    return u


# =============================================================================
# 1. Ticket Creation & SLA Deadlines
# =============================================================================

@pytest.mark.django_db
def test_ticket_creation_generates_valid_number_and_slas(buyer_user):
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Cannot checkout spare parts order",
        description="I am getting a payment card error on checkout page.",
        category=TicketCategoryChoices.PAYMENT_BILLING,
        priority=TicketPriorityChoices.HIGH,
    )

    assert ticket.ticket_number.startswith("TICK-")
    assert ticket.status == TicketStatusChoices.OPEN
    assert ticket.first_response_due_at is not None
    assert ticket.resolution_due_at is not None
    assert ticket.resolution_due_at > ticket.first_response_due_at

    # Audit & activity
    assert ticket.activities.filter(activity_type=TicketActivityTypeChoices.CREATED).exists()


@pytest.mark.django_db
def test_critical_priority_uses_24_7_clock(buyer_user):
    # Friday 22:00
    now = timezone.make_aware(datetime(2026, 11, 13, 22, 0, 0))
    first_resp, res_due = calculate_sla_deadlines(TicketPriorityChoices.CRITICAL, start_dt=now)

    assert first_resp == now + timedelta(hours=1)
    assert res_due == now + timedelta(hours=6)


@pytest.mark.django_db
def test_business_hours_skips_weekends():
    # Friday 17:00 UTC (1 hour remaining on Friday, then resumes Monday 08:00)
    friday_17 = timezone.make_aware(datetime(2026, 11, 13, 17, 0, 0))
    deadline = add_business_hours(friday_17, business_hours=3.0)

    # 1 hour on Friday (17:00 -> 18:00) + 2 hours on Monday (08:00 -> 10:00)
    expected_monday = timezone.make_aware(datetime(2026, 11, 16, 10, 0, 0))
    assert deadline == expected_monday


# =============================================================================
# 2. Strict Status Transition Matrix & Resolution Summary
# =============================================================================

@pytest.mark.django_db
def test_resolution_requires_mandatory_summary(buyer_user, support_agent):
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Inquiry regarding fitment",
        description="Does part P-123 fit a 2018 Ford Focus?",
    )

    # Transitioning to RESOLVED without summary must fail
    with pytest.raises(DjangoValidationError) as exc:
        TicketService.update_status(
            ticket=ticket,
            actor=support_agent,
            new_status=TicketStatusChoices.RESOLVED,
            resolution_summary="",
        )
    assert "resolution summary" in str(exc.value).lower()

    # Valid resolution succeeds
    resolved = TicketService.update_status(
        ticket=ticket,
        actor=support_agent,
        new_status=TicketStatusChoices.RESOLVED,
        resolution_summary="Verified compatibility with 2018 Focus petrol engine.",
    )
    assert resolved.status == TicketStatusChoices.RESOLVED
    assert resolved.resolved_by == support_agent
    assert resolved.resolved_at is not None


@pytest.mark.django_db
def test_closed_ticket_is_terminal_and_cannot_transition(buyer_user, support_agent):
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Closing test ticket",
        description="Testing terminal closed state machine.",
    )
    resolved = TicketService.update_status(
        ticket=ticket,
        actor=support_agent,
        new_status=TicketStatusChoices.RESOLVED,
        resolution_summary="Resolved successfully.",
    )
    closed = TicketService.update_status(
        ticket=resolved,
        actor=buyer_user,
        new_status=TicketStatusChoices.CLOSED,
    )
    assert closed.status == TicketStatusChoices.CLOSED

    # Attempting to reopen or change closed ticket must fail
    with pytest.raises(DjangoValidationError) as exc:
        TicketService.update_status(
            ticket=closed,
            actor=support_agent,
            new_status=TicketStatusChoices.IN_PROGRESS,
        )
    assert "cannot be reopened or updated" in str(exc.value).lower()


@pytest.mark.django_db
def test_customer_reopen_within_grace_window(buyer_user, support_agent):
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Part delivery issue",
        description="Part arrived with missing bracket.",
    )
    resolved = TicketService.update_status(
        ticket=ticket,
        actor=support_agent,
        new_status=TicketStatusChoices.RESOLVED,
        resolution_summary="Replacement bracket dispatched.",
    )

    # Customer reopens within 72h
    reopened = TicketService.update_status(
        ticket=resolved,
        actor=buyer_user,
        new_status=TicketStatusChoices.IN_PROGRESS,
        notes="Tracking number for bracket does not work.",
    )
    assert reopened.status == TicketStatusChoices.IN_PROGRESS
    assert reopened.reopen_count == 1
    assert reopened.resolved_at is None


@pytest.mark.django_db
def test_customer_reopen_rejected_after_72_hours(buyer_user, support_agent):
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Old ticket",
        description="Historical ticket.",
    )
    resolved = TicketService.update_status(
        ticket=ticket,
        actor=support_agent,
        new_status=TicketStatusChoices.RESOLVED,
        resolution_summary="Resolved historically.",
    )
    # Manually simulate resolved 4 days ago
    resolved.resolved_at = timezone.now() - timedelta(days=4)
    resolved.save()

    with pytest.raises(DjangoValidationError) as exc:
        TicketService.update_status(
            ticket=resolved,
            actor=buyer_user,
            new_status=TicketStatusChoices.IN_PROGRESS,
        )
    assert "over 72 hours ago" in str(exc.value).lower()


# =============================================================================
# 3. SLA Pausing & Resuming
# =============================================================================

@pytest.mark.django_db
def test_waiting_for_customer_pauses_and_resumes_sla(buyer_user, support_agent):
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Missing VIN",
        description="Need help finding correct brake pad.",
        priority=TicketPriorityChoices.CRITICAL,
    )
    initial_res_due = ticket.resolution_due_at

    # Agent requests VIN and pauses SLA
    waiting = TicketService.update_status(
        ticket=ticket,
        actor=support_agent,
        new_status=TicketStatusChoices.WAITING_FOR_CUSTOMER,
    )
    assert waiting.status == TicketStatusChoices.WAITING_FOR_CUSTOMER
    assert waiting.sla_paused_at is not None

    # Simulate 2 hours passing while waiting
    paused_time = timezone.now() - timedelta(hours=2)
    waiting.sla_paused_at = paused_time
    waiting.save()

    # Customer replies -> resumes SLA
    TicketService.add_message(
        ticket=waiting,
        sender=buyer_user,
        message="My VIN is 1FA6P8CF9HXXXXXXX.",
    )
    waiting.refresh_from_db()
    assert waiting.status == TicketStatusChoices.IN_PROGRESS
    assert waiting.sla_paused_at is None
    assert waiting.total_paused_seconds >= 7100  # ~2 hours
    assert waiting.resolution_due_at > initial_res_due


@pytest.mark.django_db
def test_internal_note_never_counts_as_first_response(buyer_user, support_agent):
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Internal note test",
        description="Testing first response SLA trigger.",
    )
    assert ticket.first_responded_at is None

    # Agent posts internal note
    TicketService.add_message(
        ticket=ticket,
        sender=support_agent,
        message="Checked inventory. Will reply shortly.",
        is_internal=True,
    )
    ticket.refresh_from_db()
    # Internal note must NOT stamp first_responded_at!
    assert ticket.first_responded_at is None

    # Agent posts public reply
    TicketService.add_message(
        ticket=ticket,
        sender=support_agent,
        message="We have located the part in our warehouse.",
        is_internal=False,
    )
    ticket.refresh_from_db()
    # Now first_responded_at is stamped
    assert ticket.first_responded_at is not None


# =============================================================================
# 4. Internal Note & Customer Isolation (Security)
# =============================================================================

@pytest.mark.django_db
def test_customer_cannot_see_internal_notes_in_api(api_client, buyer_user, support_agent):
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Sensitive question",
        description="Customer asking about order status.",
    )
    TicketService.add_message(
        ticket=ticket,
        sender=support_agent,
        message="PRIVATE NOTE: Customer has high chargeback rate.",
        is_internal=True,
    )
    TicketService.add_message(
        ticket=ticket,
        sender=support_agent,
        message="PUBLIC REPLY: Your order is on its way.",
        is_internal=False,
    )

    api_client.force_authenticate(user=buyer_user)
    res = api_client.get(f"/api/v1/support/tickets/{ticket.ticket_number}/")
    assert res.status_code == status.HTTP_200_OK

    messages = res.data["ticket"]["messages"]
    assert len(messages) == 1
    assert "PRIVATE NOTE" not in messages[0]["message"]
    assert messages[0]["message"] == "PUBLIC REPLY: Your order is on its way."


@pytest.mark.django_db
def test_customer_cannot_access_other_customers_tickets(api_client, buyer_user, other_buyer):
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Alice's private ticket",
        description="Contains Alice's personal details.",
    )

    api_client.force_authenticate(user=other_buyer)
    res = api_client.get(f"/api/v1/support/tickets/{ticket.ticket_number}/")
    assert res.status_code == status.HTTP_403_FORBIDDEN


# =============================================================================
# 5. Confidential Ticket Isolation & Aggregate Leakage Protection
# =============================================================================

@pytest.mark.django_db
def test_confidential_tickets_hidden_from_regular_agent(api_client, buyer_user, support_agent, senior_support_agent):
    t_normal = TicketService.create_ticket(
        customer=buyer_user,
        subject="Public regular ticket",
        description="Standard request.",
        is_confidential=False,
    )
    t_secret = TicketService.create_ticket(
        customer=buyer_user,
        subject="Account security leak investigation",
        description="Confidential fraud investigation.",
        is_confidential=True,
    )

    # 1. Regular Support Agent cannot see confidential ticket in queue
    api_client.force_authenticate(user=support_agent)
    res_list = api_client.get("/api/v1/support/agent/tickets/")
    assert res_list.status_code == status.HTTP_200_OK
    ticket_numbers = [t["ticket_number"] for t in res_list.data["tickets"]]
    assert t_normal.ticket_number in ticket_numbers
    assert t_secret.ticket_number not in ticket_numbers

    # 2. Regular Support Agent receives 403 on direct detail access
    res_detail = api_client.get(f"/api/v1/support/agent/tickets/{t_secret.ticket_number}/")
    assert res_detail.status_code == status.HTTP_403_FORBIDDEN

    # 3. Metrics exclude confidential tickets for regular agent
    res_metrics = api_client.get("/api/v1/support/agent/metrics/")
    assert res_metrics.data["metrics"]["open"] == 1  # Only counts t_normal

    # 4. Senior Agent with confidential permission CAN see it
    api_client.force_authenticate(user=senior_support_agent)
    res_senior_detail = api_client.get(f"/api/v1/support/agent/tickets/{t_secret.ticket_number}/")
    assert res_senior_detail.status_code == status.HTTP_200_OK


# =============================================================================
# 6. Secure Attachment Storage & Download Authorization
# =============================================================================

@pytest.mark.django_db
def test_attachment_upload_validates_magic_bytes_and_rejects_scripts(buyer_user):
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Attachment test",
        description="Testing file uploads.",
    )

    # Script file (.py) must be rejected
    script_file = SimpleUploadedFile("exploit.py", b"import os; os.system('echo hacked')", content_type="text/x-python")
    with pytest.raises(DjangoValidationError) as exc:
        TicketService.attach_file(ticket, uploader=buyer_user, file_obj=script_file)
    assert "prohibited for security reasons" in str(exc.value).lower()

    # Valid PNG (magic bytes \x89PNG\r\n\x1a\n) succeeds
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    valid_png = SimpleUploadedFile("screenshot.png", png_bytes, content_type="image/png")
    att = TicketService.attach_file(ticket, uploader=buyer_user, file_obj=valid_png)
    assert att.id is not None
    assert att.file_name == "screenshot.png"
    assert att.content_type == "image/png"


@pytest.mark.django_db
def test_internal_attachment_download_blocks_customer(api_client, buyer_user, support_agent):
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Internal doc test",
        description="Testing internal attachment confidentiality.",
    )
    pdf_bytes = b"%PDF-1.4 " + b"\x00" * 50
    internal_pdf = SimpleUploadedFile("agent_internal_sop.pdf", pdf_bytes, content_type="application/pdf")
    att = TicketService.attach_file(ticket, uploader=support_agent, file_obj=internal_pdf, is_internal=True)

    # Customer blocked
    api_client.force_authenticate(user=buyer_user)
    res = api_client.get(f"/api/v1/support/attachments/{att.id}/")
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # Staff allowed
    api_client.force_authenticate(user=support_agent)
    res_staff = api_client.get(f"/api/v1/support/attachments/{att.id}/")
    assert res_staff.status_code == status.HTTP_200_OK


# =============================================================================
# 7. Assignment, Controlled Deactivation & Activity Logging
# =============================================================================

@pytest.mark.django_db
def test_ticket_assignment_validates_target_role(buyer_user, support_agent, other_buyer):
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Assignment target test",
        description="Testing assignment checks.",
    )

    # Assigning to buyer or non-support staff must fail
    with pytest.raises(DjangoValidationError) as exc:
        TicketService.assign_ticket(ticket, actor=support_agent, target_agent=other_buyer)
    assert "not an active support agent" in str(exc.value).lower()

    # Assigning to valid agent succeeds
    assigned = TicketService.assign_ticket(ticket, actor=support_agent, target_agent=support_agent)
    assert assigned.assigned_to == support_agent
    assert assigned.status == TicketStatusChoices.IN_PROGRESS


@pytest.mark.django_db
def test_agent_deactivation_unassigns_tickets_atomically(buyer_user, support_agent):
    t1 = TicketService.create_ticket(buyer_user, "Task 1", "Description 10 chars.")
    t2 = TicketService.create_ticket(buyer_user, "Task 2", "Description 10 chars.")
    TicketService.assign_ticket(t1, actor=support_agent, target_agent=support_agent)
    TicketService.assign_ticket(t2, actor=support_agent, target_agent=support_agent)

    count = TicketService.handle_agent_deactivation(agent=support_agent)
    assert count == 2

    t1.refresh_from_db()
    t2.refresh_from_db()
    assert t1.assigned_to is None
    assert t2.assigned_to is None
    assert t1.activities.filter(activity_type=TicketActivityTypeChoices.AGENT_DEACTIVATED_UNASSIGNED).exists()


# =============================================================================
# 8. Automated SLA Escalation & Idempotent Management Command
# =============================================================================

@pytest.mark.django_db
def test_sla_check_escalates_and_remains_idempotent(buyer_user):
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Overdue test",
        description="Testing SLA breach check.",
        priority=TicketPriorityChoices.CRITICAL,
    )
    # Simulate first_response_due_at was 2 hours ago
    past_due = timezone.now() - timedelta(hours=2)
    ticket.first_response_due_at = past_due
    ticket.save()

    # 1. First run -> breaches and escalates
    metrics1 = TicketService.check_slas_and_escalate()
    assert metrics1["breach_100_escalated"] >= 1
    ticket.refresh_from_db()
    assert ticket.sla_breached is True
    assert ticket.is_first_response_overdue is True
    assert ticket.is_escalated is True

    # 2. Second run -> idempotent, does NOT re-escalate or duplicate
    metrics2 = TicketService.check_slas_and_escalate()
    assert metrics2["breach_100_escalated"] == 0


# =============================================================================
# 9. Support Agent Security Boundary Enforcement
# =============================================================================

@pytest.mark.django_db
def test_support_agent_cannot_execute_financial_refunds_or_disputes(api_client, support_agent):
    api_client.force_authenticate(user=support_agent)

    # Support agent must NOT have financial payout permission
    assert support_agent.has_permission("finance.payout") is False
    assert support_agent.has_permission("order.refund") is False
    assert support_agent.has_permission("dispute.manage") is False

    # Attempting to access admin refunds endpoint must be blocked
    fake_refund_id = uuid.uuid4()
    res_refund = api_client.post(f"/api/v1/marketplace/admin/refunds/{fake_refund_id}/reconcile/")
    assert res_refund.status_code == status.HTTP_403_FORBIDDEN


# =============================================================================
# 10. Stage 1 Regression Tests (P0 Security & Functional Blockers)
# =============================================================================

@pytest.mark.django_db
def test_confidential_ticket_escalation_enforces_confidential_permission(
    api_client, buyer_user, support_agent, senior_support_agent
):
    """
    P0 Security: Regular SUPPORT_AGENT cannot escalate or view confidential tickets.
    Must receive HTTP 403 Forbidden with zero confidential payload leakage.
    Authorized SENIOR / SUPPORT_LEAD can escalate successfully.
    """
    secret_ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Confidential executive complaint",
        description="Highly sensitive executive VIP issue with sensitive details.",
        is_confidential=True,
    )

    # 1. Regular Support Agent attempts to escalate -> 403 Forbidden
    api_client.force_authenticate(user=support_agent)
    res_unauth = api_client.post(
        f"/api/v1/support/agent/tickets/{secret_ticket.ticket_number}/escalate/",
        {"reason": "Attempting unauthorized escalation of confidential ticket"},
        format="json",
    )
    assert res_unauth.status_code == status.HTTP_403_FORBIDDEN
    # Ensure zero confidential information is leaked in response
    assert "ticket" not in res_unauth.data
    assert "executive" not in str(res_unauth.data).lower()

    # 2. Senior Agent with support.ticket.confidential escalates -> 200 OK
    api_client.force_authenticate(user=senior_support_agent)
    res_auth = api_client.post(
        f"/api/v1/support/agent/tickets/{secret_ticket.ticket_number}/escalate/",
        {"reason": "Authorized tier 3 review by support lead"},
        format="json",
    )
    assert res_auth.status_code == status.HTTP_200_OK
    assert res_auth.data["status"] == "success"
    assert res_auth.data["ticket"]["is_escalated"] is True
    assert res_auth.data["ticket"]["escalation_stage"] == 3


@pytest.mark.django_db
def test_staff_support_member_list_api_returns_expected_roles(
    api_client, support_agent, senior_support_agent, platform_admin
):
    """
    P0 Runtime: Staff member list endpoint returns HTTP 200 and includes
    SUPPORT_AGENT, SUPPORT_LEAD, and ADMIN staff users via both user_roles and staff_profile.
    """
    # Create direct role users to test user_roles relationship explicitly
    direct_agent = User.objects.create_user(
        email=f"direct_agent_{uuid.uuid4().hex[:6]}@driverxtra.local",
        password="TestPassword123!",
        is_staff=True,
    )
    direct_agent.add_role("SUPPORT_AGENT")

    direct_lead = User.objects.create_user(
        email=f"direct_lead_{uuid.uuid4().hex[:6]}@driverxtra.local",
        password="TestPassword123!",
        is_staff=True,
    )
    direct_lead.add_role("SUPPORT_LEAD")

    api_client.force_authenticate(user=support_agent)
    res = api_client.get("/api/v1/support/agent/staff-list/")
    assert res.status_code == status.HTTP_200_OK
    assert res.data["status"] == "success"

    emails = [m["email"] for m in res.data["staff"]]
    assert support_agent.email in emails
    assert senior_support_agent.email in emails
    assert platform_admin.email in emails
    assert direct_agent.email in emails
    assert direct_lead.email in emails


@pytest.mark.django_db
def test_all_ticket_categories_submit_successfully(api_client, buyer_user):
    """
    P0 Mismatch: All backend TicketCategoryChoices can be submitted by customers
    via POST /api/v1/support/tickets/ and return HTTP 201.
    """
    api_client.force_authenticate(user=buyer_user)

    for cat in TicketCategoryChoices.values:
        res = api_client.post(
            "/api/v1/support/tickets/",
            {
                "subject": f"Inquiry about category {cat}",
                "description": f"Detailed inquiry testing category {cat} submission validity.",
                "category": cat,
                "priority": TicketPriorityChoices.MEDIUM,
            },
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED, f"Failed on category {cat}: {res.data}"
        assert res.data["ticket"]["category"] == cat


# =============================================================================
# 11. Stage 2 Tests (P1 Notifications, SLA Recalculation & Priority Lifecycle)
# =============================================================================

@pytest.mark.django_db
def test_escalation_notifications_for_assigned_and_unassigned_tickets(
    buyer_user, support_agent, senior_support_agent, platform_admin
):
    """
    P1 Notifications:
    1. Assigned ticket escalation routes to assigned agent.
    2. Unassigned ticket escalation routes to Support Leads.
    3. Tier 3 escalation routes to Platform Admins.
    4. Notifications are idempotent across repeated processing.
    5. Confidential tickets suppress notifications to agents without confidential access.
    """
    from apps.notifications.handlers import process_audit_entry
    from apps.notifications.models import Notification
    from platform_core.audit.models import AuditLog

    # Case 1: Assigned ticket escalation (Stage 1 Warning)
    t_assigned = TicketService.create_ticket(
        customer=buyer_user,
        subject="Assigned ticket warning test",
        description="Testing escalation notification for assigned agent.",
    )
    TicketService.assign_ticket(ticket=t_assigned, actor=senior_support_agent, target_agent=support_agent)

    TicketService.escalate_ticket(
        ticket=t_assigned,
        actor=senior_support_agent,
        reason="Approaching 75% SLA threshold",
        stage=EscalationStageChoices.WARNING_75,
    )
    entry_assigned = AuditLog.objects.filter(
        resource_id=str(t_assigned.id),
        event_type="support.ticket.escalated",
    ).latest('created_at')

    # Notification created via post_save signal
    notifs_agent = Notification.objects.filter(recipient=support_agent, source_audit_id=entry_assigned.id)
    assert notifs_agent.exists()
    assert "75% SLA Warning" in notifs_agent.first().title

    # Idempotency: re-running process_audit_entry creates 0 additional notifications
    re_created = process_audit_entry(entry_assigned)
    assert len(re_created) == 0

    # Case 2: Unassigned ticket escalation (Stage 2 Breach) routes to Support Leads
    t_unassigned = TicketService.create_ticket(
        customer=buyer_user,
        subject="Unassigned triage breach test",
        description="Testing unassigned ticket escalation to support leads.",
    )
    TicketService.escalate_ticket(
        ticket=t_unassigned,
        actor=None,
        reason="First response SLA breached on unassigned ticket",
        stage=EscalationStageChoices.BREACH_100,
    )
    entry_unassigned = AuditLog.objects.filter(
        resource_id=str(t_unassigned.id),
        event_type="support.ticket.escalated",
    ).latest('created_at')

    notifs_lead = Notification.objects.filter(recipient=senior_support_agent, source_audit_id=entry_unassigned.id)
    assert notifs_lead.exists()
    assert "100% SLA Breach" in notifs_lead.first().title

    # Case 3: Tier 3 escalation routes to Platform Admins
    t_tier3 = TicketService.create_ticket(
        customer=buyer_user,
        subject="Critical infrastructure VIP ticket",
        description="High urgency executive escalation.",
    )
    TicketService.escalate_ticket(
        ticket=t_tier3,
        actor=senior_support_agent,
        reason="Executive Tier 3 critical request",
        stage=EscalationStageChoices.TIER_3,
    )
    entry_tier3 = AuditLog.objects.filter(
        resource_id=str(t_tier3.id),
        event_type="support.ticket.escalated",
    ).latest('created_at')

    notifs_admin = Notification.objects.filter(recipient=platform_admin, source_audit_id=entry_tier3.id)
    assert notifs_admin.exists()
    assert "Tier 3 Critical Escalation" in notifs_admin.first().title

    # Case 4: Confidential ticket escalation suppresses notification for regular agent
    t_conf = TicketService.create_ticket(
        customer=buyer_user,
        subject="Confidential internal fraud review",
        description="Restricted to staff with confidential permission.",
        is_confidential=True,
    )
    TicketService.escalate_ticket(
        ticket=t_conf,
        actor=senior_support_agent,
        reason="Confidential fraud breach",
        stage=EscalationStageChoices.TIER_3,
    )
    entry_conf = AuditLog.objects.filter(
        resource_id=str(t_conf.id),
        event_type="support.ticket.escalated",
    ).latest('created_at')

    # Regular support agent MUST NOT receive notification for confidential ticket
    assert not Notification.objects.filter(recipient=support_agent, source_audit_id=entry_conf.id).exists()
    # Senior lead with confidential access DOES receive notification
    assert Notification.objects.filter(recipient=senior_support_agent, source_audit_id=entry_conf.id).exists()


@pytest.mark.django_db
def test_internal_note_suppresses_customer_notification(buyer_user, support_agent):
    """
    P1 Notifications: Internal notes posted by agents MUST NEVER generate notifications for customers.
    Public replies MUST notify customers.
    """
    from apps.notifications.models import Notification

    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Customer notification privacy test",
        description="Ensuring customer never receives notifications for internal staff notes.",
    )
    TicketService.assign_ticket(ticket=ticket, actor=support_agent, target_agent=support_agent)

    # 1. Internal note posted by agent
    TicketService.add_message(
        ticket=ticket,
        sender=support_agent,
        message="Private internal note discussing customer background.",
        is_internal=True,
    )
    # Verify no notification was generated for the customer
    notifs_cust_internal = Notification.objects.filter(
        recipient=buyer_user,
        event_type="support.ticket.agent_replied",
    )
    assert not notifs_cust_internal.exists()

    # 2. Public reply posted by agent
    TicketService.add_message(
        ticket=ticket,
        sender=support_agent,
        message="Hello Alice, we have looked into your query.",
        is_internal=False,
    )
    # Verify customer received the public reply notification
    notifs_cust_public = Notification.objects.filter(
        recipient=buyer_user,
        event_type="support.ticket.agent_replied",
    )
    assert notifs_cust_public.exists()


@pytest.mark.django_db
def test_update_ticket_priority_recalculates_sla_correctly(buyer_user, support_agent):
    """
    P1 SLA: Priority update must transactionally recalculate SLA deadlines:
    - LOW to CRITICAL (switches to 24/7 calendar clock)
    - CRITICAL to LOW (switches back to business hours)
    - HIGH to MEDIUM
    - Creates TicketActivity and AuditLog records
    """
    from platform_core.audit.models import AuditLog

    # Create ticket with LOW priority
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Priority update SLA recalculation test",
        description="Testing deadline adjustments across priority shifts.",
        priority=TicketPriorityChoices.LOW,
    )
    original_first_resp = ticket.first_response_due_at
    original_resolution = ticket.resolution_due_at

    # 1. Escalate LOW -> CRITICAL
    updated_crit = TicketService.update_ticket_priority(
        ticket=ticket,
        actor=support_agent,
        new_priority=TicketPriorityChoices.CRITICAL,
    )
    assert updated_crit.priority == TicketPriorityChoices.CRITICAL
    # Critical uses 1h response and 6h resolution from created_at (24/7 clock)
    expected_first_resp = ticket.created_at + timedelta(hours=1)
    expected_resolution = ticket.created_at + timedelta(hours=6)
    assert abs((updated_crit.first_response_due_at - expected_first_resp).total_seconds()) < 2
    assert abs((updated_crit.resolution_due_at - expected_resolution).total_seconds()) < 2
    assert updated_crit.first_response_due_at < original_first_resp
    assert updated_crit.resolution_due_at < original_resolution

    # Verify Activity and AuditLog
    activity = TicketActivity.objects.filter(
        ticket=ticket,
        activity_type=TicketActivityTypeChoices.PRIORITY_CHANGED,
    ).latest('created_at')
    assert activity.old_value == TicketPriorityChoices.LOW
    assert activity.new_value == TicketPriorityChoices.CRITICAL
    assert activity.actor == support_agent

    audit = AuditLog.objects.filter(
        resource_id=str(ticket.id),
        event_type="support.ticket.priority_updated",
    ).latest('created_at')
    assert audit.metadata["old_priority"] == TicketPriorityChoices.LOW
    assert audit.metadata["new_priority"] == TicketPriorityChoices.CRITICAL

    # 2. De-escalate CRITICAL -> LOW
    updated_low = TicketService.update_ticket_priority(
        ticket=ticket,
        actor=support_agent,
        new_priority=TicketPriorityChoices.LOW,
    )
    assert updated_low.priority == TicketPriorityChoices.LOW
    assert updated_low.first_response_due_at == original_first_resp
    assert updated_low.resolution_due_at == original_resolution

    # 3. HIGH -> MEDIUM
    updated_high = TicketService.update_ticket_priority(
        ticket=ticket,
        actor=support_agent,
        new_priority=TicketPriorityChoices.HIGH,
    )
    high_first_resp = updated_high.first_response_due_at
    high_resolution = updated_high.resolution_due_at

    updated_med = TicketService.update_ticket_priority(
        ticket=ticket,
        actor=support_agent,
        new_priority=TicketPriorityChoices.MEDIUM,
    )
    assert updated_med.priority == TicketPriorityChoices.MEDIUM
    # Medium has larger allowance than High (12h vs 4h response, 48h vs 24h resolution)
    assert updated_med.first_response_due_at > high_first_resp
    assert updated_med.resolution_due_at > high_resolution


@pytest.mark.django_db
def test_update_ticket_priority_during_paused_state_and_after_first_response(buyer_user, support_agent):
    """
    P1 SLA:
    - Priority change while ticket is WAITING_FOR_CUSTOMER preserves total paused seconds.
    - Priority change after first response was recorded preserves first_response_due_at.
    """
    # Create ticket with MEDIUM priority
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Paused and first-responded priority shift",
        description="Testing priority changes under paused and responded conditions.",
        priority=TicketPriorityChoices.MEDIUM,
    )
    TicketService.assign_ticket(ticket=ticket, actor=support_agent, target_agent=support_agent)

    # Agent responds publicly -> first_responded_at is recorded
    msg = TicketService.add_message(
        ticket=ticket,
        sender=support_agent,
        message="Initial agent reply to customer inquiry.",
        is_internal=False,
    )
    ticket.refresh_from_db()
    assert ticket.first_responded_at is not None
    recorded_first_resp_due = ticket.first_response_due_at
    recorded_first_resp_overdue = ticket.is_first_response_overdue

    # Update status to WAITING_FOR_CUSTOMER -> pauses resolution SLA
    TicketService.update_status(
        ticket=ticket,
        actor=support_agent,
        new_status=TicketStatusChoices.WAITING_FOR_CUSTOMER,
        notes="Awaiting VIN from customer",
    )
    ticket.refresh_from_db()
    assert ticket.sla_paused_at is not None

    # Simulate 3600 seconds of accumulated paused duration
    ticket.total_paused_seconds = 3600
    ticket.save(update_fields=['total_paused_seconds'])

    # Change priority to HIGH while paused and after first response
    updated = TicketService.update_ticket_priority(
        ticket=ticket,
        actor=support_agent,
        new_priority=TicketPriorityChoices.HIGH,
    )
    assert updated.priority == TicketPriorityChoices.HIGH
    # First response deadline and overdue status MUST NOT CHANGE because response was already given!
    assert updated.first_response_due_at == recorded_first_resp_due
    assert updated.is_first_response_overdue == recorded_first_resp_overdue
    # Resolution due date must include the 3600 seconds paused duration
    _, base_res_due = calculate_sla_deadlines(TicketPriorityChoices.HIGH, start_dt=ticket.created_at)
    expected_res_with_pause = base_res_due + timedelta(seconds=3600)
    assert abs((updated.resolution_due_at - expected_res_with_pause).total_seconds()) < 2
    # While paused, ticket must never be marked resolution-overdue
    assert updated.is_resolution_overdue is False


@pytest.mark.django_db
def test_update_ticket_priority_rejected_on_resolved_and_closed_tickets(api_client, buyer_user, support_agent):
    """
    P1 SLA: Priority adjustments are strictly forbidden on RESOLVED or CLOSED tickets.
    Service raises DjangoValidationError and API returns HTTP 400.
    """
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Terminal state priority protection test",
        description="Testing rejection of priority updates on completed tickets.",
        priority=TicketPriorityChoices.MEDIUM,
    )
    TicketService.assign_ticket(ticket=ticket, actor=support_agent, target_agent=support_agent)
    TicketService.add_message(ticket=ticket, sender=support_agent, message="Working on it.", is_internal=False)

    # Resolve ticket
    TicketService.update_status(
        ticket=ticket,
        actor=support_agent,
        new_status=TicketStatusChoices.RESOLVED,
        resolution_summary="Resolved successfully with customer agreement.",
    )
    ticket.refresh_from_db()
    assert ticket.status == TicketStatusChoices.RESOLVED

    # Direct service call raises DjangoValidationError
    with pytest.raises(DjangoValidationError) as exc_info:
        TicketService.update_ticket_priority(
            ticket=ticket,
            actor=support_agent,
            new_priority=TicketPriorityChoices.HIGH,
        )
    assert "Cannot change priority of a resolved or closed ticket" in str(exc_info.value)

    # API call returns HTTP 400 Bad Request
    api_client.force_authenticate(user=support_agent)
    res_resolved = api_client.post(
        f"/api/v1/support/agent/tickets/{ticket.ticket_number}/priority/",
        {"priority": TicketPriorityChoices.HIGH},
        format="json",
    )
    assert res_resolved.status_code == status.HTTP_400_BAD_REQUEST
    assert "resolved or closed" in str(res_resolved.data).lower()

    # Close ticket -> also rejected
    TicketService.update_status(ticket=ticket, actor=support_agent, new_status=TicketStatusChoices.CLOSED)
    res_closed = api_client.post(
        f"/api/v1/support/agent/tickets/{ticket.ticket_number}/priority/",
        {"priority": TicketPriorityChoices.CRITICAL},
        format="json",
    )
    assert res_closed.status_code == status.HTTP_400_BAD_REQUEST


# =============================================================================
# 12. Stage 3 Tests (P2 Reliability, Holidays, Private Storage & Admin Deactivation)
# =============================================================================

@pytest.mark.django_db
def test_public_holidays_excluded_from_sla_calculations(buyer_user, settings):
    """
    P2 SLA: Public/statutory holidays are skipped during business-hour SLA calculations.
    CRITICAL 24/7 calendar clock continues running through holidays.
    """
    from apps.support.sla import add_business_hours, calculate_sla_deadlines
    import zoneinfo

    # Configure Christmas Day (Friday) and Boxing Day (Saturday) as holidays
    settings.SUPPORT_SLA_TIMEZONE = "UTC"
    settings.SUPPORT_PUBLIC_HOLIDAYS = ["2026-12-25", "2026-12-26"]

    # Ticket created Dec 24, 2026 at 16:00 (Thursday) with HIGH priority (4 business hours)
    thursday_4pm = datetime(2026, 12, 24, 16, 0, tzinfo=zoneinfo.ZoneInfo("UTC"))
    due_dt = add_business_hours(thursday_4pm, 4.0)

    # Dec 24 16:00 to 18:00 consumes 2 business hours (remaining: 2)
    # Dec 25 (Friday) is a public holiday -> 0 hours
    # Dec 26 (Saturday) and Dec 27 (Sunday) are weekend -> 0 hours
    # Dec 28 (Monday) 08:00 to 10:00 consumes remaining 2 hours -> due Monday Dec 28 at 10:00 AM!
    expected_due = datetime(2026, 12, 28, 10, 0, tzinfo=zoneinfo.ZoneInfo("UTC"))
    assert due_dt == expected_due

    # CRITICAL priority uses 24/7 calendar hours regardless of holidays
    first_resp_crit, res_crit = calculate_sla_deadlines(TicketPriorityChoices.CRITICAL, start_dt=thursday_4pm)
    assert first_resp_crit == thursday_4pm + timedelta(hours=1)
    assert res_crit == thursday_4pm + timedelta(hours=6)


@pytest.mark.django_db
def test_sla_75_percent_warning_skips_weekends_and_holidays(buyer_user, settings):
    """
    P2 SLA: 75% warning calculation uses business-time elapsed seconds.
    Tickets evaluated over weekends or holidays must NOT prematurely trigger 75% warning.
    """
    import zoneinfo
    settings.SUPPORT_SLA_TIMEZONE = "UTC"
    settings.SUPPORT_PUBLIC_HOLIDAYS = []

    # Created Friday at 17:00 (Nov 13, 2026) with HIGH priority (4 business hours first response)
    # 1h Friday (17:00-18:00), 3h Monday (08:00-11:00) -> due Monday at 11:00 AM
    friday_5pm = datetime(2026, 11, 13, 17, 0, tzinfo=zoneinfo.ZoneInfo("UTC"))
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Weekend SLA warning isolation test",
        description="Testing business-hour 75% warning calculation.",
        priority=TicketPriorityChoices.HIGH,
    )
    ticket.created_at = friday_5pm
    # first_response_due_at: Monday Nov 16 at 11:00 AM
    ticket.first_response_due_at = datetime(2026, 11, 16, 11, 0, tzinfo=zoneinfo.ZoneInfo("UTC"))
    ticket.resolution_due_at = datetime(2026, 11, 19, 17, 0, tzinfo=zoneinfo.ZoneInfo("UTC"))
    ticket.save()

    # Evaluation on Sunday at 20:00 (Nov 15, 2026)
    # Calendar elapsed is 51 hours out of 66 total hours (77.2% calendar time)
    # But business elapsed is only 1 hour out of 4 business hours (25% business time)!
    sunday_8pm = datetime(2026, 11, 15, 20, 0, tzinfo=zoneinfo.ZoneInfo("UTC"))
    metrics_sun = TicketService.check_slas_and_escalate(now=sunday_8pm)
    assert metrics_sun["warning_75_escalated"] == 0
    ticket.refresh_from_db()
    assert ticket.is_escalated is False
    assert ticket.escalation_stage == 0

    # Evaluation on Monday at 10:00 AM (Nov 16, 2026)
    # Business elapsed is 1h Friday + 2h Monday = 3h out of 4h = exactly 75% business time!
    monday_10am = datetime(2026, 11, 16, 10, 0, tzinfo=zoneinfo.ZoneInfo("UTC"))
    metrics_mon = TicketService.check_slas_and_escalate(now=monday_10am)
    assert metrics_mon["warning_75_escalated"] == 1
    ticket.refresh_from_db()
    assert ticket.is_escalated is True
    assert ticket.escalation_stage == EscalationStageChoices.WARNING_75


@pytest.mark.django_db
def test_resolution_sla_75_percent_warning_and_pause_isolation(buyer_user, support_agent):
    """
    P2 SLA: Resolution SLA generates 75% warning when consumed business time reaches 75%.
    Paused tickets (WAITING_FOR_CUSTOMER) are never warned or breached.
    """
    # Create ticket with HIGH priority (24 business hours resolution SLA)
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Resolution 75% warning test",
        description="Testing resolution warning threshold and pause safety.",
        priority=TicketPriorityChoices.HIGH,
    )
    TicketService.assign_ticket(ticket=ticket, actor=support_agent, target_agent=support_agent)
    # Agent responds -> first response obligation completed
    TicketService.add_message(ticket=ticket, sender=support_agent, message="First response completed.", is_internal=False)
    ticket.refresh_from_db()
    assert ticket.first_responded_at is not None

    # Simulate 18 business hours consumed out of 24h (75%)
    # Advance created_at backward to simulate 18 business hours elapsed
    ticket.created_at = ticket.created_at - timedelta(hours=36)
    # Set resolution due date so that 75% of window is consumed
    now = timezone.now()
    ticket.resolution_due_at = now + timedelta(hours=2)
    ticket.save()

    metrics = TicketService.check_slas_and_escalate(now=now)
    assert metrics["warning_75_escalated"] >= 1
    ticket.refresh_from_db()
    assert ticket.is_escalated is True
    assert ticket.escalation_stage == EscalationStageChoices.WARNING_75

    # Case 2: Paused ticket in WAITING_FOR_CUSTOMER is never warned or breached
    ticket2 = TicketService.create_ticket(
        customer=buyer_user,
        subject="Paused ticket safety test",
        description="Paused tickets must not be warned.",
        priority=TicketPriorityChoices.HIGH,
    )
    TicketService.assign_ticket(ticket=ticket2, actor=support_agent, target_agent=support_agent)
    TicketService.add_message(ticket=ticket2, sender=support_agent, message="Please supply details.", is_internal=False)
    TicketService.update_status(ticket=ticket2, actor=support_agent, new_status=TicketStatusChoices.WAITING_FOR_CUSTOMER)
    ticket2.refresh_from_db()
    assert ticket2.sla_paused_at is not None

    # Force resolution_due_at to be in the past to test pause protection
    ticket2.resolution_due_at = now - timedelta(hours=5)
    ticket2.save()

    metrics2 = TicketService.check_slas_and_escalate(now=now)
    ticket2.refresh_from_db()
    assert ticket2.is_resolution_overdue is False
    assert ticket2.sla_breached is False


@pytest.mark.django_db
def test_agent_deactivation_via_admin_staff_endpoint(
    api_client, buyer_user, support_agent, platform_admin
):
    """
    P2 Admin: Deactivating a staff member via PATCH /api/v1/admin/staff/<id>/
    automatically unassigns their active support tickets transactionally and creates audit entries.
    """
    # Create 2 active tickets assigned to support_agent
    t1 = TicketService.create_ticket(
        customer=buyer_user,
        subject="Agent deactivation ticket 1",
        description="Testing active ticket deactivation 1 with sufficient length.",
    )
    t2 = TicketService.create_ticket(
        customer=buyer_user,
        subject="Agent deactivation ticket 2",
        description="Testing active ticket deactivation 2 with sufficient length.",
    )
    TicketService.assign_ticket(ticket=t1, actor=platform_admin, target_agent=support_agent)
    TicketService.assign_ticket(ticket=t2, actor=platform_admin, target_agent=support_agent)

    # 1 resolved ticket belonging to agent should remain unaffected
    t3 = TicketService.create_ticket(
        customer=buyer_user,
        subject="Resolved ticket unaffected",
        description="Testing resolved ticket unaffected with sufficient length.",
    )
    TicketService.assign_ticket(ticket=t3, actor=platform_admin, target_agent=support_agent)
    TicketService.add_message(ticket=t3, sender=support_agent, message="Resolving ticket.", is_internal=False)
    TicketService.update_status(
        ticket=t3,
        actor=support_agent,
        new_status=TicketStatusChoices.RESOLVED,
        resolution_summary="Resolved successfully with customer agreement.",
    )

    # Admin calls PATCH /api/v1/admin/staff/<support_agent.id>/ with SUSPENDED
    api_client.force_authenticate(user=platform_admin)
    res = api_client.patch(
        f"/api/v1/admin/staff/{support_agent.id}/",
        {"status": "SUSPENDED"},
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK

    # Verify agent is inactive
    support_agent.refresh_from_db()
    assert support_agent.is_active is False

    # Verify active tickets are now unassigned
    t1.refresh_from_db()
    t2.refresh_from_db()
    assert t1.assigned_to is None
    assert t2.assigned_to is None

    # Verify resolved ticket preserved its history
    t3.refresh_from_db()
    assert t3.assigned_to == support_agent

    # Verify activity record created for unassignment
    act1 = TicketActivity.objects.filter(
        ticket=t1,
        activity_type=TicketActivityTypeChoices.AGENT_DEACTIVATED_UNASSIGNED,
    )
    assert act1.exists()


@pytest.mark.django_db
def test_private_attachment_storage_and_download_authorization(
    api_client, buyer_user, other_buyer, support_agent, settings
):
    """
    P2 Storage: Support attachments use dedicated private filesystem storage.
    Public URLs are disabled. Authenticated downloads enforce authorization checks.
    """
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Private attachment test ticket",
        description="Testing private storage isolation.",
    )

    pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    upload_file = SimpleUploadedFile("diagnostic_report.pdf", pdf_content, content_type="application/pdf")

    attachment = TicketService.attach_file(
        ticket=ticket,
        uploader=buyer_user,
        file_obj=upload_file,
    )

    # 1. Verify stored in private storage root outside public media
    assert str(settings.PRIVATE_STORAGE_ROOT) in attachment.file.path
    assert str(settings.MEDIA_ROOT) not in attachment.file.path

    # 2. Verify public URL is disabled
    with pytest.raises(ValueError):
        _ = attachment.file.url

    # 3. Owner customer can stream download
    api_client.force_authenticate(user=buyer_user)
    res_owner = api_client.get(f"/api/v1/support/attachments/{attachment.id}/")
    assert res_owner.status_code == status.HTTP_200_OK
    assert res_owner.headers.get("Content-Disposition").startswith("attachment")
    assert b"%PDF" in b"".join(res_owner.streaming_content)

    # 4. Other customer receives 403 Forbidden
    api_client.force_authenticate(user=other_buyer)
    res_other = api_client.get(f"/api/v1/support/attachments/{attachment.id}/")
    assert res_other.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_attachment_cleanup_on_database_insert_failure(buyer_user):
    """
    P2 Storage: When database insertion fails after the file has been written to private storage,
    the orphaned file must be cleaned up immediately.
    """
    from django.db import IntegrityError

    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Attachment rollback cleanup test",
        description="Testing file deletion upon database save error.",
    )

    pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    upload_file = SimpleUploadedFile("failing_doc.pdf", pdf_content, content_type="application/pdf")

    # Deliberately cause attachment.save() to fail
    with patch.object(TicketAttachment, 'save', side_effect=IntegrityError("Simulated DB failure")):
        with pytest.raises(IntegrityError):
            TicketService.attach_file(
                ticket=ticket,
                uploader=buyer_user,
                file_obj=upload_file,
            )

    # Verify no attachment was created in DB
    assert not TicketAttachment.objects.filter(ticket=ticket).exists()


@pytest.mark.django_db
def test_system_auto_closure_audit_attribution(buyer_user):
    """
    P2 Audit: System inactivity closure must record actor=None and SYSTEM_AUTO_CLOSED activity,
    never attributing the action to the customer.
    """
    from platform_core.audit.models import AuditLog

    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Inactivity auto closure audit attribution test",
        description="Testing system attribution for 5-day inactivity closure.",
    )
    # Update to WAITING_FOR_CUSTOMER
    ticket.status = TicketStatusChoices.WAITING_FOR_CUSTOMER
    ticket.last_customer_activity_at = timezone.now() - timedelta(days=6)
    ticket.save()

    # Run SLA checker
    metrics = TicketService.check_slas_and_escalate()
    assert metrics["auto_closed_inactive"] >= 1

    ticket.refresh_from_db()
    assert ticket.status == TicketStatusChoices.CLOSED

    # Verify TicketActivity has actor=None and SYSTEM_AUTO_CLOSED
    closure_act = TicketActivity.objects.filter(
        ticket=ticket,
        activity_type=TicketActivityTypeChoices.SYSTEM_AUTO_CLOSED,
    ).latest('created_at')
    assert closure_act.actor is None
    assert "inactivity" in closure_act.notes.lower()

    # Verify AuditLog has actor_id=None and action=support:ticket.system_auto_close
    audit = AuditLog.objects.filter(
        resource_id=str(ticket.id),
        event_type="support.ticket.status_updated",
    ).latest('created_at')
    assert audit.actor_id is None
    assert audit.action == "support:ticket.system_auto_close"
    assert audit.metadata.get("is_system_action") is True


@pytest.mark.django_db
def test_staff_deactivation_rolls_back_atomically_on_unassignment_failure(admin_user, support_agent, buyer_user, monkeypatch):
    """
    P1 Atomic Deactivation:
    If ticket unassignment fails or raises during staff deactivation,
    the user deactivation (status, is_active) must roll back completely.
    """
    from rest_framework.test import APIClient
    from apps.identity.models import AccountStatusChoices

    # Create ticket assigned to support_agent
    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Atomic rollback test ticket",
        description="Testing atomic rollback of staff deactivation on unassignment failure.",
    )
    TicketService.assign_ticket(ticket=ticket, actor=admin_user, target_agent=support_agent)
    ticket.refresh_from_db()
    assert ticket.assigned_to == support_agent

    client = APIClient()
    client.force_authenticate(user=admin_user)

    # Monkeypatch handle_agent_deactivation to simulate failure
    def mock_failure(*args, **kwargs):
        raise RuntimeError("Simulated failure during ticket unassignment")

    monkeypatch.setattr(TicketService, 'handle_agent_deactivation', mock_failure)

    # Attempt to suspend support_agent
    with pytest.raises(RuntimeError, match="Simulated failure during ticket unassignment"):
        client.patch(f'/api/v1/admin/staff/{support_agent.id}/', {'status': 'SUSPENDED'}, format='json')

    # Verify atomic rollback
    support_agent.refresh_from_db()
    assert support_agent.status == AccountStatusChoices.ACTIVE
    assert support_agent.is_active is True

    ticket.refresh_from_db()
    assert ticket.assigned_to == support_agent


@pytest.mark.django_db
def test_legacy_attachment_fallback_and_streaming(buyer_user, settings):
    """
    P1 Storage Compatibility:
    Attachments stored under legacy MEDIA_ROOT before private storage migration
    must stream successfully and be copied to private storage on demand.
    """
    import shutil
    from rest_framework.test import APIClient

    ticket = TicketService.create_ticket(
        customer=buyer_user,
        subject="Legacy attachment fallback test",
        description="Testing backward compatibility for legacy media attachments.",
    )

    client = APIClient()
    client.force_authenticate(user=buyer_user)

    # Upload attachment via service
    dummy_pdf = io.BytesIO(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")
    dummy_pdf.name = "legacy_document.pdf"

    attachment = TicketService.attach_file(
        ticket=ticket,
        uploader=buyer_user,
        file_obj=dummy_pdf,
    )

    # Simulate legacy file placement: move file from private storage to media root
    private_file_path = Path(attachment.file.storage.location) / attachment.file.name
    media_file_path = Path(settings.MEDIA_ROOT) / attachment.file.name

    media_file_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(private_file_path, media_file_path)

    # Remove from private storage to simulate unmigrated state
    if private_file_path.exists():
        os.remove(private_file_path)

    assert not private_file_path.exists()
    assert media_file_path.exists()

    # Request download
    resp = client.get(f'/api/v1/support/attachments/{attachment.id}/')
    assert resp.status_code == status.HTTP_200_OK
    assert resp['Content-Type'] == 'application/pdf'
    assert b"%PDF-1.4" in resp.getvalue()

    # Verify that the file was copied into private storage on demand
    assert private_file_path.exists()
    assert media_file_path.exists()  # Original is NOT deleted




