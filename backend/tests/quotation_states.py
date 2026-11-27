"""
Test-only helpers for seeding WorkshopQuotation states (G23 / DX-GC-06 AUT-01).

Production code changes quotation status only through QuotationService. Some fixtures need a
quotation in a given state without the service side effects (for example an ACCEPTED quotation with
a hand-built WorkOrder). These helpers create the quotation as DRAFT and walk it through the same
legal, service-owned transitions, using the internal transition grant. They never allow an edge
that QUOTATION_SERVICE_TRANSITIONS does not define.
"""
from django.utils import timezone

from apps.workshops.models import (
    WorkshopQuotation,
    QuotationStatusChoices,
    QUOTATION_TRANSITION_FIELDS,
    QUOTATION_TRANSITION_REQUIRED,
    _quotation_transition,
)

_PATHS = {
    QuotationStatusChoices.DRAFT: [],
    QuotationStatusChoices.ISSUED: [QuotationStatusChoices.ISSUED],
    QuotationStatusChoices.ACCEPTED: [QuotationStatusChoices.ISSUED, QuotationStatusChoices.ACCEPTED],
    QuotationStatusChoices.REJECTED: [QuotationStatusChoices.ISSUED, QuotationStatusChoices.REJECTED],
    QuotationStatusChoices.SUPERSEDED: [QuotationStatusChoices.ISSUED, QuotationStatusChoices.SUPERSEDED],
}


def advance_quotation(quote, target, **lifecycle):
    """Move `quote` from its current status to `target` along legal edges, recording lifecycle values."""
    path = _PATHS[target]
    if quote.status in path:
        path = path[path.index(quote.status) + 1:]
    for step in path:
        current = quote.status
        quote.status = step
        update_fields = ['status', 'updated_at']
        required = QUOTATION_TRANSITION_REQUIRED.get(step)
        if required and lifecycle.get(required) is None:
            lifecycle[required] = timezone.now()  # every transition records its timestamp
        for field in QUOTATION_TRANSITION_FIELDS[step]:
            if lifecycle.get(field) is not None:
                setattr(quote, field, lifecycle[field])
                update_fields.append(field)
        with _quotation_transition([quote.pk], current, step):
            quote.save(update_fields=update_fields)
    return quote


def make_quotation(status=QuotationStatusChoices.DRAFT, issued_at=None, accepted_at=None,
                   rejected_at=None, customer_rejection_reason=None, **fields):
    """Create a quotation as DRAFT, then advance it to `status`."""
    quote = WorkshopQuotation.objects.create(status=QuotationStatusChoices.DRAFT, **fields)
    return advance_quotation(
        quote, status,
        issued_at=issued_at, accepted_at=accepted_at,
        rejected_at=rejected_at, customer_rejection_reason=customer_rejection_reason,
    )
