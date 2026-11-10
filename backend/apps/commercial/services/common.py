import hashlib
import json
import re

from common.middleware import get_current_correlation_id
from platform_core.audit.writer import record_audit_entry

from ..errors import CommercialRuleViolation

COUNTRY_CODE_PATTERN = re.compile(r'^[A-Z]{2}$')
CODE_PATTERN = re.compile(r'^[A-Z0-9][A-Z0-9_-]{2,63}$')


def normalize_country(value) -> str:
    code = (value or '').strip().upper()
    if not COUNTRY_CODE_PATTERN.match(code):
        raise CommercialRuleViolation(
            'INVALID_COUNTRY_CODE', f"'{value}' is not an ISO 3166-1 alpha-2 country code.", status_code=400,
        )
    return code


def normalize_code(value, field: str) -> str:
    code = (value or '').strip().upper()
    if not CODE_PATTERN.match(code):
        raise CommercialRuleViolation(
            'INVALID_CODE',
            f"{field} must be 3–64 characters of A–Z, 0–9, '-' or '_' (got '{value}').",
            status_code=400,
        )
    return code


def require_text(value, rule: str, message: str) -> str:
    text = (value or '').strip()
    if not text:
        raise CommercialRuleViolation(rule, message, status_code=400)
    return text


def canonical_hash(payload) -> str:
    """SHA-256 of canonical JSON (sorted keys, no whitespace)."""
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def audit(actor, event_type: str, action: str, resource_type: str, resource_id, metadata=None):
    record_audit_entry(
        event_type=event_type,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        actor_id=getattr(actor, 'id', None),
        correlation_id=get_current_correlation_id(),
        metadata=metadata or {},
    )
