"""Commercial SKU catalogue lifecycle (§4, §6, §7 approval controls, COM-008)."""

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from platform_core.events.outbox import emit_event

from ..choices import CatalogueStatusChoices as Status
from ..errors import CommercialRuleViolation
from ..models import CommercialSku
from .common import audit, normalize_code, require_text

EDITABLE_STATUSES = {Status.DRAFT, Status.ILLUSTRATIVE}
SKU_EDITABLE_FIELDS = (
    'name', 'description', 'family', 'revenue_code', 'vertical', 'fee_basis', 'entitlement_type',
    'billing_interval', 'tax_class', 'refund_policy_id', 'illustrative_band_note',
)
SKU_TRANSITIONS = {
    Status.DRAFT: {Status.ILLUSTRATIVE, Status.APPROVED, Status.RETIRED},
    Status.ILLUSTRATIVE: {Status.DRAFT, Status.APPROVED, Status.RETIRED},
    Status.APPROVED: {Status.RETIRED},
    Status.RETIRED: set(),
}


def create_sku(data: dict, actor) -> CommercialSku:
    sku_code = normalize_code(data.get('sku_code'), 'sku_code')
    if CommercialSku.objects.filter(sku_code=sku_code).exists():
        raise CommercialRuleViolation(
            'SKU_EXISTS', f"SKU {sku_code} already exists; create a new version instead.", status_code=409,
        )
    with transaction.atomic():
        sku = CommercialSku(sku_code=sku_code, version=1, status=Status.DRAFT, created_by=actor)
        for field in SKU_EDITABLE_FIELDS:
            if field in data:
                setattr(sku, field, data[field])
        sku.save()
        audit(actor, 'commercial.sku.created', 'commercial:sku.create', 'CommercialSku', sku.id,
              {'sku_code': sku.sku_code, 'version': sku.version})
    return sku


def update_sku(sku: CommercialSku, data: dict, actor) -> CommercialSku:
    with transaction.atomic():
        sku = CommercialSku.objects.select_for_update().get(pk=sku.pk)
        if sku.status not in EDITABLE_STATUSES:
            raise CommercialRuleViolation(
                'SKU_FROZEN', f"{sku.sku_code} v{sku.version} is {sku.status}; create a new version to change it.",
            )
        changed = []
        for field in SKU_EDITABLE_FIELDS:
            if field in data and getattr(sku, field) != data[field]:
                setattr(sku, field, data[field])
                changed.append(field)
        if changed:
            sku.save()
            audit(actor, 'commercial.sku.updated', 'commercial:sku.update', 'CommercialSku', sku.id,
                  {'sku_code': sku.sku_code, 'version': sku.version, 'fields': changed})
    return sku


def transition_sku(sku: CommercialSku, to_status: str, actor, reason: str, approval_reference: str = '') -> CommercialSku:
    reason = require_text(reason, 'REASON_REQUIRED', 'A reason is required for every SKU status change.')
    with transaction.atomic():
        sku = CommercialSku.objects.select_for_update().get(pk=sku.pk)
        if to_status not in SKU_TRANSITIONS.get(sku.status, set()):
            raise CommercialRuleViolation(
                'INVALID_TRANSITION', f"SKU cannot move from {sku.status} to {to_status}.",
            )

        if to_status == Status.APPROVED:
            if sku.is_regulated:
                raise CommercialRuleViolation(
                    'REGULATED_SKU_BLOCKED',
                    f"{sku.sku_code} is a regulated/gated product ({sku.revenue_code}); it cannot be approved "
                    "without a signed regulatory perimeter and country gate (D06).",
                )
            if sku.created_by_id and sku.created_by_id == actor.id:
                raise CommercialRuleViolation(
                    'SEPARATION_OF_DUTIES', 'The SKU author cannot approve their own SKU.',
                )
            sku.approval_reference = require_text(
                approval_reference, 'APPROVAL_REFERENCE_REQUIRED', 'Approval requires a CFO/commercial approval reference.',
            )
            sku.approved_by = actor
            sku.approved_at = timezone.now()
            # Only one approved version per SKU code: earlier approved versions are retired going forward.
            for previous in CommercialSku.objects.select_for_update().filter(
                sku_code=sku.sku_code, status=Status.APPROVED,
            ).exclude(pk=sku.pk):
                previous.status = Status.RETIRED
                previous.status_reason = f"Superseded by v{sku.version}."
                previous.save(update_fields=['status', 'status_reason', 'updated_at'])

        previous_status = sku.status
        sku.status = to_status
        sku.status_reason = reason
        sku.save()

        audit(actor, f'commercial.sku.{to_status.lower()}', 'commercial:sku.transition', 'CommercialSku', sku.id,
              {'sku_code': sku.sku_code, 'version': sku.version, 'from': previous_status, 'to': to_status,
               'reason': reason, 'approval_reference': sku.approval_reference})
        if to_status in (Status.APPROVED, Status.RETIRED):
            topic = 'commercial.sku.published' if to_status == Status.APPROVED else 'commercial.sku.retired'
            emit_event(
                topic,
                aggregate_type='CommercialSku',
                aggregate_id=sku.id,
                payload={'sku_code': sku.sku_code, 'version': sku.version, 'revenue_code': sku.revenue_code,
                         'vertical': sku.vertical, 'status': sku.status},
                idempotency_key=f'{topic}:{sku.id}',
                actor_id=actor.id,
            )
    return sku


def create_new_version(sku: CommercialSku, actor) -> CommercialSku:
    with transaction.atomic():
        latest = CommercialSku.objects.filter(sku_code=sku.sku_code).aggregate(m=Max('version'))['m'] or 0
        new_sku = CommercialSku(sku_code=sku.sku_code, version=latest + 1, status=Status.DRAFT, created_by=actor)
        for field in SKU_EDITABLE_FIELDS:
            setattr(new_sku, field, getattr(sku, field))
        new_sku.save()
        audit(actor, 'commercial.sku.versioned', 'commercial:sku.version', 'CommercialSku', new_sku.id,
              {'sku_code': new_sku.sku_code, 'version': new_sku.version, 'copied_from': str(sku.id)})
    return new_sku
