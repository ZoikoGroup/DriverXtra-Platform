"""Maker-Checker Approval Engine Service.

Enforces dual-authorization principles on high-value and sensitive platform operations.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from apps.identity.models import ApprovalRequest, ApprovalStatusChoices, User
from platform_core.audit.models import AuditLog
from platform_core.audit.writer import record_audit_entry, record_denied_audit_entry

logger = logging.getLogger(__name__)


class ApprovalService:
    @staticmethod
    def is_platform_admin(user: Any) -> bool:
        if not user or not user.is_authenticated:
            return False
        return bool(
            user.is_superuser
            or getattr(user, "role", "") in ("ADMIN", "MARKETPLACE_ADMIN")
            or (hasattr(user, "has_role") and (user.has_role("ADMIN") or user.has_role("MARKETPLACE_ADMIN")))
        )

    @staticmethod
    def has_permission(user: Any, perm_code: str) -> bool:
        if not user or not user.is_authenticated:
            return False
        if ApprovalService.is_platform_admin(user):
            return True
        if hasattr(user, "has_permission"):
            return user.has_permission(perm_code)
        return False

    @classmethod
    def get_threshold_for_currency(cls, currency: str) -> Decimal:
        curr = (currency or "GBP").upper()
        thresholds = getattr(settings, "MAKER_CHECKER_THRESHOLDS", {})
        default_thresh = getattr(settings, "MAKER_CHECKER_DEFAULT_THRESHOLD", Decimal("500.00"))
        return thresholds.get(curr, default_thresh)

    @classmethod
    def is_approval_required(
        cls,
        action_type: str,
        amount: Optional[Decimal] = None,
        currency: str = "GBP",
    ) -> bool:
        """Determines whether an operation requires maker-checker approval.

        High-value financial operations (> currency threshold) strictly require dual-authorization.
        """
        if amount is None:
            return False
        threshold = cls.get_threshold_for_currency(currency)
        return Decimal(str(amount)) > threshold

    @classmethod
    def create_request(
        cls,
        requester: User,
        action_type: str,
        target_type: str,
        target_id: str,
        amount: Optional[Decimal] = None,
        currency: str = "GBP",
        reason: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRequest:
        """Creates a new Maker-Checker approval request in PENDING status."""
        # Check if an identical active pending request already exists
        existing_pending = ApprovalRequest.objects.filter(
            action_type=action_type,
            target_type=target_type,
            target_id=str(target_id),
            status=ApprovalStatusChoices.PENDING,
        ).first()
        if existing_pending:
            return existing_pending

        with transaction.atomic():
            req = ApprovalRequest.objects.create(
                requester=requester,
                action_type=action_type,
                target_type=target_type,
                target_id=str(target_id),
                amount=amount,
                currency=(currency or "GBP").upper(),
                reason=reason or "",
                payload=payload or {},
                status=ApprovalStatusChoices.PENDING,
                requested_at=timezone.now(),
            )

            record_audit_entry(
                event_type="approval.request.created",
                action="approval:request.create",
                resource_type="ApprovalRequest",
                resource_id=str(req.id),
                actor_id=requester.id,
                metadata={
                    "action_type": req.action_type,
                    "target_type": req.target_type,
                    "target_id": req.target_id,
                    "amount": str(req.amount) if req.amount is not None else None,
                    "currency": req.currency,
                    "reason": req.reason,
                    "requester_email": requester.email,
                },
            )

        return req

    @classmethod
    def approve_request(
        cls,
        approval_request_id: Any,
        approver: User,
        notes: str = "",
        required_perm: str = "finance.payout",
    ) -> ApprovalRequest:
        """Approves a pending request. Enforces that requester cannot approve their own request."""
        with transaction.atomic():
            req = ApprovalRequest.objects.select_for_update().get(id=approval_request_id)

            # Maker-Checker Rule 1: Maker cannot be checker
            if str(approver.id) == str(req.requester_id):
                record_denied_audit_entry(
                    action="approval:request.approve",
                    resource_type="ApprovalRequest",
                    resource_id=str(req.id),
                    actor_id=approver.id,
                    reason_code="MAKER_CANNOT_APPROVE_OWN_REQUEST",
                    event_type="approval.request.approve.denied",
                    metadata={"error": "Maker-checker violation: Requester cannot approve their own request."},
                )
                raise DjangoValidationError("Maker-checker violation: Requester cannot approve their own request.")

            # Maker-Checker Rule 2: Approver must possess required permission or be platform admin
            if not (cls.is_platform_admin(approver) or cls.has_permission(approver, required_perm)):
                record_denied_audit_entry(
                    action="approval:request.approve",
                    resource_type="ApprovalRequest",
                    resource_id=str(req.id),
                    actor_id=approver.id,
                    reason_code="INSUFFICIENT_CHECKER_PERMISSIONS",
                    event_type="approval.request.approve.denied",
                    metadata={"required_permission": required_perm},
                )
                raise DjangoValidationError(
                    f"Permission denied: Approver must possess the '{required_perm}' permission or be an administrator."
                )

            # Maker-Checker Rule 3: Must be pending
            if req.status != ApprovalStatusChoices.PENDING:
                raise DjangoValidationError(f"Cannot approve request with status '{req.status}'.")

            req.approve(approver=approver, notes=notes)

            record_audit_entry(
                event_type="approval.request.approved",
                action="approval:request.approve",
                resource_type="ApprovalRequest",
                resource_id=str(req.id),
                actor_id=approver.id,
                metadata={
                    "action_type": req.action_type,
                    "target_type": req.target_type,
                    "target_id": req.target_id,
                    "amount": str(req.amount) if req.amount is not None else None,
                    "currency": req.currency,
                    "approver_email": approver.email,
                    "notes": notes,
                },
            )

        return req

    @classmethod
    def reject_request(
        cls,
        approval_request_id: Any,
        approver: User,
        reason: str,
        notes: str = "",
        required_perm: str = "finance.payout",
    ) -> ApprovalRequest:
        """Rejects a pending request. Enforces maker-checker rules and required checker permissions."""
        if not reason or not reason.strip():
            raise DjangoValidationError("A rejection reason is required.")

        with transaction.atomic():
            req = ApprovalRequest.objects.select_for_update().get(id=approval_request_id)

            # Maker-Checker Rule 1: Maker cannot review own request
            if str(approver.id) == str(req.requester_id):
                record_denied_audit_entry(
                    action="approval:request.reject",
                    resource_type="ApprovalRequest",
                    resource_id=str(req.id),
                    actor_id=approver.id,
                    reason_code="MAKER_CANNOT_REVIEW_OWN_REQUEST",
                    event_type="approval.request.reject.denied",
                    metadata={"error": "Maker-checker violation: Requester cannot review their own request."},
                )
                raise DjangoValidationError("Maker-checker violation: Requester cannot review their own request.")

            # Maker-Checker Rule 2: Approver must possess required permission or be admin
            if not (cls.is_platform_admin(approver) or cls.has_permission(approver, required_perm)):
                record_denied_audit_entry(
                    action="approval:request.reject",
                    resource_type="ApprovalRequest",
                    resource_id=str(req.id),
                    actor_id=approver.id,
                    reason_code="INSUFFICIENT_CHECKER_PERMISSIONS",
                    event_type="approval.request.reject.denied",
                    metadata={"required_permission": required_perm},
                )
                raise DjangoValidationError(
                    f"Permission denied: Approver must possess the '{required_perm}' permission or be an administrator."
                )

            # Maker-Checker Rule 3: Must be pending
            if req.status != ApprovalStatusChoices.PENDING:
                raise DjangoValidationError(f"Cannot reject request with status '{req.status}'.")

            req.reject(approver=approver, reason=reason, notes=notes)

            record_audit_entry(
                event_type="approval.request.rejected",
                action="approval:request.reject",
                resource_type="ApprovalRequest",
                resource_id=str(req.id),
                actor_id=approver.id,
                metadata={
                    "action_type": req.action_type,
                    "target_type": req.target_type,
                    "target_id": req.target_id,
                    "rejection_reason": reason,
                    "notes": notes,
                    "approver_email": approver.email,
                },
            )

        return req

    @classmethod
    def cancel_request(
        cls,
        approval_request_id: Any,
        actor: User,
        notes: str = "",
    ) -> ApprovalRequest:
        """Cancels a pending request. Only requester or platform admin can cancel."""
        with transaction.atomic():
            req = ApprovalRequest.objects.select_for_update().get(id=approval_request_id)

            if str(actor.id) != str(req.requester_id) and not cls.is_platform_admin(actor):
                raise DjangoValidationError("Permission denied: Only the requester or platform admin can cancel this request.")

            if req.status != ApprovalStatusChoices.PENDING:
                raise DjangoValidationError(f"Cannot cancel request with status '{req.status}'.")

            req.cancel(actor=actor, notes=notes)

            record_audit_entry(
                event_type="approval.request.cancelled",
                action="approval:request.cancel",
                resource_type="ApprovalRequest",
                resource_id=str(req.id),
                actor_id=actor.id,
                metadata={
                    "action_type": req.action_type,
                    "target_type": req.target_type,
                    "target_id": req.target_id,
                    "notes": notes,
                    "cancelled_by_email": actor.email,
                },
            )

        return req

    @classmethod
    def execute_request(
        cls,
        approval_request_id: Any,
        executor: User,
    ) -> Tuple[ApprovalRequest, Any]:
        """Executes an approved request. Prevents duplicate execution or execution of unapproved requests."""
        with transaction.atomic():
            req = ApprovalRequest.objects.select_for_update().get(id=approval_request_id)

            if req.status == ApprovalStatusChoices.REJECTED:
                raise DjangoValidationError("Cannot execute a rejected approval request.")
            if req.status == ApprovalStatusChoices.CANCELLED:
                raise DjangoValidationError("Cannot execute a cancelled approval request.")
            if req.status == ApprovalStatusChoices.EXECUTED:
                raise DjangoValidationError("Approval request has already been executed.")
            if req.status != ApprovalStatusChoices.APPROVED:
                raise DjangoValidationError(
                    f"Approval request must be in APPROVED status before execution (current: '{req.status}')."
                )

            # Check executor permission
            if not (cls.is_platform_admin(executor) or cls.has_permission(executor, "finance.payout")):
                raise DjangoValidationError("Permission denied: Executor must possess the 'finance.payout' permission.")

        record_audit_entry(
            event_type="approval.request.execution.attempted",
            action="approval:request.execute",
            resource_type="ApprovalRequest",
            resource_id=str(req.id),
            actor_id=executor.id,
            metadata={
                "action_type": req.action_type,
                "target_type": req.target_type,
                "target_id": req.target_id,
                "executor_email": executor.email,
            },
        )

        # Dispatch based on action_type / target_type
        if req.action_type in ("REFUND_DISPATCH", "MANUAL_REFUND_RESOLUTION") or req.target_type == "Refund":
            if req.target_type != "Refund" or req.action_type not in ("REFUND_DISPATCH", "MANUAL_REFUND_RESOLUTION"):
                raise DjangoValidationError(
                    f"Integrity violation: Approval request action '{req.action_type}' and target '{req.target_type}' do not match expected actions on Refund."
                )

            from apps.marketplace.models import Refund, RefundStatusChoices
            from apps.marketplace.returns.service import RefundService

            try:
                refund = Refund.objects.get(id=req.target_id)
            except Refund.DoesNotExist:
                req.execution_error = f"Refund {req.target_id} not found."
                req.save(update_fields=["execution_error", "updated_at"])
                record_audit_entry(
                    event_type="approval.request.execution.failed",
                    action="approval:request.execute",
                    resource_type="ApprovalRequest",
                    resource_id=str(req.id),
                    actor_id=executor.id,
                    metadata={"error": req.execution_error},
                )
                raise DjangoValidationError(req.execution_error)

            # Prevent executing modified refund with outdated approval
            if req.amount is not None and Decimal(str(req.amount)) != Decimal(str(refund.amount)):
                raise DjangoValidationError(
                    f"Integrity violation: Approved amount ({req.currency} {req.amount}) does not match target refund amount ({refund.currency} {refund.amount}). Re-authorization is required."
                )
            if req.currency and req.currency.upper() != refund.currency.upper():
                raise DjangoValidationError(
                    f"Integrity violation: Approved currency ({req.currency}) does not match target refund currency ({refund.currency}). Re-authorization is required."
                )

            if req.action_type == "MANUAL_REFUND_RESOLUTION":
                payload = req.payload or {}
                raw_resolution = payload.get("resolution")
                if not raw_resolution or not str(raw_resolution).strip():
                    req.execution_error = "Integrity violation: Approval request payload is missing approved resolution."
                    req.save(update_fields=["execution_error", "updated_at"])
                    record_audit_entry(
                        event_type="approval.request.execution.failed",
                        action="approval:request.execute",
                        resource_type="ApprovalRequest",
                        resource_id=str(req.id),
                        actor_id=executor.id,
                        metadata={"error": req.execution_error},
                    )
                    raise DjangoValidationError(req.execution_error)

                resolution = str(raw_resolution).strip().upper()
                reason = payload.get("reason") or req.reason
                evidence = payload.get("evidence")
                gw_ref = payload.get("gateway_reference")
                tkt_ref = payload.get("ticket_reference")
                try:
                    resolved_refund = RefundService.manual_resolve_unknown_refund(
                        refund=refund,
                        actor=executor,
                        resolution=resolution,
                        reason=reason,
                        evidence=evidence,
                        approved_request=req,
                        gateway_reference=gw_ref,
                        ticket_reference=tkt_ref,
                    )
                    return req, resolved_refund
                except Exception as exc:
                    req.execution_error = str(exc)
                    req.save(update_fields=["execution_error", "updated_at"])
                    record_audit_entry(
                        event_type="approval.request.execution.failed",
                        action="approval:request.execute",
                        resource_type="ApprovalRequest",
                        resource_id=str(req.id),
                        actor_id=executor.id,
                        metadata={"error": str(exc)},
                    )
                    raise

            try:
                dispatched_refund = RefundService.dispatch_gateway_refund(
                    refund=refund,
                    actor=executor,
                    approved_request=req,
                )
            except Exception as exc:
                req.execution_error = str(exc)
                req.save(update_fields=["execution_error", "updated_at"])
                record_audit_entry(
                    event_type="approval.request.execution.failed",
                    action="approval:request.execute",
                    resource_type="ApprovalRequest",
                    resource_id=str(req.id),
                    actor_id=executor.id,
                    metadata={"error": str(exc)},
                )
                raise

            if dispatched_refund.status == RefundStatusChoices.SUCCEEDED:
                # mark_executed is handled or confirmed here
                if req.status != ApprovalStatusChoices.EXECUTED:
                    if req.execution_error:
                        req.execution_error = ""
                        req.save(update_fields=["execution_error", "updated_at"])
                    req.mark_executed(executor=executor, notes="Gateway refund dispatched successfully.")
                    record_audit_entry(
                        event_type="approval.request.execution.success",
                        action="approval:request.execute",
                        resource_type="ApprovalRequest",
                        resource_id=str(req.id),
                        actor_id=executor.id,
                        metadata={
                            "gateway_refund_id": dispatched_refund.gateway_refund_id,
                            "refund_number": dispatched_refund.refund_number,
                        },
                    )
                return req, dispatched_refund
            else:
                req.execution_error = dispatched_refund.failure_reason or "Gateway refund dispatch failed."
                req.save(update_fields=["execution_error", "updated_at"])
                record_audit_entry(
                    event_type="approval.request.execution.failed",
                    action="approval:request.execute",
                    resource_type="ApprovalRequest",
                    resource_id=str(req.id),
                    actor_id=executor.id,
                    metadata={"error": req.execution_error},
                )
                raise DjangoValidationError(f"Execution failed: {req.execution_error}")

        # Fallback for generic actions
        req.mark_executed(executor=executor, notes="Generic approval action executed.")
        record_audit_entry(
            event_type="approval.request.execution.success",
            action="approval:request.execute",
            resource_type="ApprovalRequest",
            resource_id=str(req.id),
            actor_id=executor.id,
            metadata={"notes": "Executed generic action"},
        )
        return req, None

