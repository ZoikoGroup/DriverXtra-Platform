"""Audit log writer module for DriverXtra platform.

Provides synchronous and autonomous audit logging facilities, ensuring
that access decisions and audit trails are recorded reliably and immutably.
"""

import json
import logging
import uuid
from typing import Any, Dict, Optional

from django.db import connection, connections
from django.utils import timezone

from platform_core.audit.models import AuditLog

logger = logging.getLogger(__name__)


def record_audit_entry(
    event_type: str,
    action: str,
    resource_type: str,
    resource_id: str = "",
    actor_id: Optional[uuid.UUID] = None,
    actor_kind: str = "USER",
    operating_org_id: Optional[uuid.UUID] = None,
    status: str = AuditLog.STATUS_ALLOWED,
    correlation_id: str = "",
    reason_code: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """Record an audit entry in the audit ledger within the current transaction."""
    return AuditLog.objects.create(
        event_type=event_type,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else "",
        actor_id=actor_id,
        actor_kind=actor_kind or "USER",
        operating_org_id=operating_org_id,
        status=status,
        correlation_id=correlation_id or "",
        reason_code=reason_code or "",
        metadata=metadata or {},
    )


def record_denied_audit_entry(
    action: str,
    resource_type: str,
    resource_id: str = "",
    reason_code: str = "",
    correlation_id: str = "",
    event_type: Optional[str] = None,
    actor_id: Optional[uuid.UUID] = None,
    actor_kind: str = "USER",
    operating_org_id: Optional[uuid.UUID] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """Record a denied security action autonomously so it survives any surrounding business transaction rollback.

    On PostgreSQL, an independent database connection is used to commit the
    denied audit record immediately out-of-band. On SQLite or other databases,
    standard model creation is used.
    """
    resolved_event_type = event_type or f"{action}.denied"
    resolved_resource_id = str(resource_id) if resource_id is not None else ""
    resolved_reason_code = reason_code or ""
    resolved_correlation_id = correlation_id or ""
    resolved_metadata = metadata or {}
    resolved_actor_kind = actor_kind or "USER"

    default_conn = connections["default"]

    if default_conn.vendor == "postgresql":
        # Create an independent connection to guarantee autonomous write
        alias = f"autonomous_audit_{uuid.uuid4().hex[:8]}"
        new_conn = default_conn.__class__(default_conn.settings_dict, alias=alias)
        new_conn.connect()

        entry_id = uuid.uuid4()
        now = timezone.now()
        meta_json = json.dumps(resolved_metadata)

        try:
            with new_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO "platform"."audit_log" (
                        id, created_at, event_type, action, resource_type,
                        resource_id, actor_id, actor_kind, operating_org_id,
                        status, correlation_id, reason_code, metadata
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s
                    );
                    """,
                    [
                        str(entry_id),
                        now,
                        resolved_event_type,
                        action,
                        resource_type,
                        resolved_resource_id,
                        str(actor_id) if actor_id else None,
                        resolved_actor_kind,
                        str(operating_org_id) if operating_org_id else None,
                        AuditLog.STATUS_DENIED,
                        resolved_correlation_id,
                        resolved_reason_code,
                        meta_json,
                    ],
                )
            new_conn.commit()
        except Exception:
            new_conn.rollback()
            logger.exception("Failed to write autonomous denied audit entry.")
            raise
        finally:
            new_conn.close()

        return AuditLog(
            id=entry_id,
            created_at=now,
            event_type=resolved_event_type,
            action=action,
            resource_type=resource_type,
            resource_id=resolved_resource_id,
            actor_id=actor_id,
            actor_kind=resolved_actor_kind,
            operating_org_id=operating_org_id,
            status=AuditLog.STATUS_DENIED,
            correlation_id=resolved_correlation_id,
            reason_code=resolved_reason_code,
            metadata=resolved_metadata,
        )

    # Fallback for non-PostgreSQL (e.g. SQLite)
    return AuditLog.objects.create(
        event_type=resolved_event_type,
        action=action,
        resource_type=resource_type,
        resource_id=resolved_resource_id,
        actor_id=actor_id,
        actor_kind=resolved_actor_kind,
        operating_org_id=operating_org_id,
        status=AuditLog.STATUS_DENIED,
        correlation_id=resolved_correlation_id,
        reason_code=resolved_reason_code,
        metadata=resolved_metadata,
    )
