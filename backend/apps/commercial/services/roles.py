"""Party role profiles and snapshots (§2 role separation, §9 role mapping, §21 party_role_snapshot)."""

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from ..choices import (
    RoleProfileStatusChoices as Status,
    SellerOfRecordChoices,
    ServicePerformerChoices,
)
from ..errors import CommercialRuleViolation
from ..models import PartyRoleProfile, PartyRoleSnapshot
from .common import audit, canonical_hash, normalize_code, normalize_country, require_text

PROFILE_EDITABLE_FIELDS = (
    'name', 'profile_type', 'country_code', 'vertical', 'seller_of_record', 'service_performer', 'platform_role',
    'payment_role', 'tax_party', 'invoice_issuer', 'licensed_partner_required', 'legal_memo_reference',
    'effective_from', 'effective_to',
)
PROFILE_TRANSITIONS = {
    Status.DRAFT: {Status.APPROVED, Status.RETIRED},
    Status.APPROVED: {Status.RETIRED},
    Status.RETIRED: set(),
}


def _validate_window(effective_from, effective_to):
    if effective_from is None:
        raise CommercialRuleViolation('EFFECTIVE_FROM_REQUIRED', 'effective_from is required.', 400)
    if effective_to is not None and effective_to <= effective_from:
        raise CommercialRuleViolation('INVALID_EFFECTIVE_WINDOW', 'effective_to must be after effective_from.', 400)


def create_profile(data: dict, actor) -> PartyRoleProfile:
    code = normalize_code(data.get('code'), 'code')
    if PartyRoleProfile.objects.filter(code=code).exists():
        raise CommercialRuleViolation('ROLE_PROFILE_EXISTS', f'Role profile {code} already exists; create a new version.')
    profile = PartyRoleProfile(code=code, version=1, status=Status.DRAFT, created_by=actor)
    for field in PROFILE_EDITABLE_FIELDS:
        if field in data:
            setattr(profile, field, data[field])
    profile.country_code = normalize_country(profile.country_code)
    _validate_window(profile.effective_from, profile.effective_to)
    with transaction.atomic():
        profile.save()
        audit(actor, 'commercial.role_profile.created', 'commercial:role_profile.create', 'PartyRoleProfile',
              profile.id, {'code': code, 'version': 1})
    return profile


def update_profile(profile: PartyRoleProfile, data: dict, actor) -> PartyRoleProfile:
    with transaction.atomic():
        profile = PartyRoleProfile.objects.select_for_update().get(pk=profile.pk)
        if profile.status != Status.DRAFT:
            raise CommercialRuleViolation('ROLE_PROFILE_FROZEN', f'{profile.code} v{profile.version} is {profile.status}.')
        for field in PROFILE_EDITABLE_FIELDS:
            if field in data:
                setattr(profile, field, data[field])
        profile.country_code = normalize_country(profile.country_code)
        _validate_window(profile.effective_from, profile.effective_to)
        profile.save()
        audit(actor, 'commercial.role_profile.updated', 'commercial:role_profile.update', 'PartyRoleProfile',
              profile.id, {'code': profile.code, 'version': profile.version})
    return profile


def transition_profile(profile: PartyRoleProfile, to_status: str, actor, reason: str,
                       approval_reference: str = '') -> PartyRoleProfile:
    reason = require_text(reason, 'REASON_REQUIRED', 'A reason is required for every role profile status change.')
    with transaction.atomic():
        profile = PartyRoleProfile.objects.select_for_update().get(pk=profile.pk)
        if to_status not in PROFILE_TRANSITIONS.get(profile.status, set()):
            raise CommercialRuleViolation('INVALID_TRANSITION', f'Role profile cannot move from {profile.status} to {to_status}.')
        if to_status == Status.APPROVED:
            if profile.is_gated:
                raise CommercialRuleViolation(
                    'GATED_ROLE_PROFILE',
                    f'{profile.profile_type} / {profile.payment_role} role profiles are gated and cannot be approved in R1.',
                )
            if profile.created_by_id and profile.created_by_id == actor.id:
                raise CommercialRuleViolation('SEPARATION_OF_DUTIES', 'The profile author cannot approve their own profile.')
            require_text(profile.legal_memo_reference, 'LEGAL_MEMO_REQUIRED',
                         'Approving a role profile requires a legal/compliance memo reference (D02).')
            profile.approval_reference = require_text(
                approval_reference, 'APPROVAL_REFERENCE_REQUIRED', 'Approval requires an approval reference.',
            )
            profile.approved_by = actor
            profile.approved_at = timezone.now()
            for previous in PartyRoleProfile.objects.select_for_update().filter(
                code=profile.code, status=Status.APPROVED,
            ).exclude(pk=profile.pk):
                previous.status = Status.RETIRED
                previous.status_reason = f'Superseded by v{profile.version}.'
                previous.save(update_fields=['status', 'status_reason', 'updated_at'])
        previous_status = profile.status
        profile.status = to_status
        profile.status_reason = reason
        profile.save()
        audit(actor, f'commercial.role_profile.{to_status.lower()}', 'commercial:role_profile.transition',
              'PartyRoleProfile', profile.id,
              {'code': profile.code, 'version': profile.version, 'from': previous_status, 'to': to_status,
               'reason': reason})
    return profile


def create_new_profile_version(profile: PartyRoleProfile, actor) -> PartyRoleProfile:
    with transaction.atomic():
        latest = PartyRoleProfile.objects.filter(code=profile.code).aggregate(m=Max('version'))['m'] or 0
        new_profile = PartyRoleProfile(code=profile.code, version=latest + 1, status=Status.DRAFT, created_by=actor)
        for field in PROFILE_EDITABLE_FIELDS:
            setattr(new_profile, field, getattr(profile, field))
        new_profile.save()
        audit(actor, 'commercial.role_profile.versioned', 'commercial:role_profile.version', 'PartyRoleProfile',
              new_profile.id, {'code': new_profile.code, 'version': new_profile.version})
    return new_profile


def resolve_profile(code: str, country_code: str, vertical: str, at=None, statuses=(Status.APPROVED,)):
    at = at or timezone.now()
    profile = (
        PartyRoleProfile.objects.filter(
            code=(code or '').strip().upper(), country_code=country_code, vertical=vertical,
            status__in=statuses, effective_from__lte=at,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=at))
        .order_by('-version')
        .first()
    )
    if profile is None:
        raise CommercialRuleViolation(
            'COMMERCIAL_ROLE_MISSING',
            f"No {'/'.join(statuses)} role profile '{code}' is effective for {country_code}/{vertical}.",
        )
    return profile


def describe_parties(profile: PartyRoleProfile, seller_organisation=None) -> dict:
    """Resolve concrete party identifiers for a profile; raises if a required party is missing."""
    seller_party = 'none'
    if profile.seller_of_record == SellerOfRecordChoices.THIRD_PARTY_SELLER:
        if seller_organisation is None:
            raise CommercialRuleViolation(
                'SELLER_OF_RECORD_REQUIRED', 'This role profile requires a named seller-of-record organisation.', 400,
            )
        seller_party = f'org:{seller_organisation.id}'
    elif profile.seller_of_record == SellerOfRecordChoices.PLATFORM:
        seller_party = 'platform'

    performer_party = 'none'
    if profile.service_performer == ServicePerformerChoices.THIRD_PARTY_PROVIDER:
        if seller_organisation is None:
            raise CommercialRuleViolation(
                'SERVICE_PERFORMER_REQUIRED', 'This role profile requires a named service-provider organisation.', 400,
            )
        performer_party = f'org:{seller_organisation.id}'
    elif profile.service_performer == ServicePerformerChoices.PLATFORM:
        performer_party = 'platform'

    return {
        'profile_code': profile.code,
        'profile_version': profile.version,
        'profile_type': profile.profile_type,
        'seller_of_record_party': seller_party,
        'service_performer_party': performer_party,
        'platform_role': profile.platform_role,
        'payment_role': profile.payment_role,
        'tax_party': profile.tax_party,
        'invoice_issuer': profile.invoice_issuer,
        'licensed_partner_required': profile.licensed_partner_required,
        'jurisdiction': profile.country_code,
    }


def create_snapshot(profile: PartyRoleProfile, parties: dict) -> PartyRoleSnapshot:
    return PartyRoleSnapshot.objects.create(profile=profile, snapshot_hash=canonical_hash(parties), **parties)
