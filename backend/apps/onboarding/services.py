import logging
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.organisations.models import (
    Organisation,
    OrganisationMembership,
    OrganisationTypeChoices,
    OrganisationRoleChoices,
)
from platform_core.regional import (
    normalize_country_code,
    validate_country_code,
    validate_jurisdiction,
    derive_jurisdiction_from_tax_id,
    get_default_jurisdiction_for_country,
    get_country_spec,
    is_supported_country,
)

logger = logging.getLogger(__name__)


def provision_workshop_organisation(application):
    """
    Idempotently provisions an Organisation of type WORKSHOP, an OWNER/ADMIN membership,
    and a WorkshopProfile for an approved SellerApplication that includes the WORKSHOP role.

    Guarantees:
    - Transaction-safe and idempotent with row locking.
    - Resolves applicant's country and jurisdiction using platform_core.regional.
    - Enforces country and jurisdiction consistency (IN with IN-TG/IN-MH; GB with GB-ENG).
    - Indian workshops receive INR, UK workshops receive GBP.
    - Preserves existing approval status, reviewer, role assignments, and unrelated memberships.
    - Does NOT automatically promote an existing ADMIN to OWNER.
    - Does NOT overwrite an existing dealership organisation association on application.organisation.
    - Detects multiple active workshop memberships and refuses to select an arbitrary organisation.
    - Sets initial is_accepting_bookings=False so an unconfigured workshop cannot accept bookings.
    - Distinguishes tax registration from country configuration without inventing arbitrary defaults.
    """
    user = application.user
    existing_org = application.organisation
    workshop_org = None

    # 1. Resolve country and jurisdiction from application
    raw_country = application.country or 'GB'
    norm_country = normalize_country_code(raw_country)
    valid_country = validate_country_code(norm_country)

    # Derive or validate jurisdiction
    jurisdiction = getattr(application, 'jurisdiction', None)
    if not jurisdiction and application.tax_id:
        jurisdiction = derive_jurisdiction_from_tax_id(application.tax_id, valid_country)
    if not jurisdiction:
        jurisdiction = get_default_jurisdiction_for_country(valid_country)

    valid_jurisdiction = validate_jurisdiction(valid_country, jurisdiction)
    regional_spec = get_country_spec(valid_country)

    with transaction.atomic():
        # Query active workshop memberships for user with lock
        active_ws_memberships = list(
            user.organisation_memberships.select_for_update()
            .filter(
                is_active=True,
                organisation__type=OrganisationTypeChoices.WORKSHOP,
                organisation__is_active=True,
            )
            .select_related('organisation')
        )

        # 2. Resolve or create the WORKSHOP Organisation
        if existing_org:
            if existing_org.type == OrganisationTypeChoices.WORKSHOP:
                # Re-use existing workshop organisation attached to the application
                workshop_org = existing_org
            else:
                # application.organisation points to another type (e.g. DEALER_GROUP).
                # Do NOT overwrite application.organisation!
                if len(active_ws_memberships) == 1:
                    workshop_org = active_ws_memberships[0].organisation
                elif len(active_ws_memberships) > 1:
                    matching = [m.organisation for m in active_ws_memberships if m.organisation.name == application.business_name]
                    if len(matching) == 1:
                        workshop_org = matching[0]
                    else:
                        raise ValidationError(
                            f"User '{user.email}' has multiple active workshop organisations. "
                            "Cannot arbitrarily select a workshop organisation during provisioning; "
                            "link the application to the intended organisation explicitly."
                        )
                else:
                    workshop_name = f"{application.business_name} (Workshop)" if application.business_name else f"{existing_org.name} (Workshop)"
                    workshop_org = Organisation.objects.create(
                        name=workshop_name,
                        type=OrganisationTypeChoices.WORKSHOP,
                        country=valid_country,
                        jurisdiction=valid_jurisdiction,
                        created_by=user,
                        is_active=True,
                    )
        else:
            # application.organisation is None.
            if len(active_ws_memberships) == 1:
                workshop_org = active_ws_memberships[0].organisation
                application.organisation = workshop_org
                application.save(update_fields=['organisation', 'updated_at'])
            elif len(active_ws_memberships) > 1:
                matching = [m.organisation for m in active_ws_memberships if m.organisation.name == application.business_name]
                if len(matching) == 1:
                    workshop_org = matching[0]
                    application.organisation = workshop_org
                    application.save(update_fields=['organisation', 'updated_at'])
                else:
                    raise ValidationError(
                        f"User '{user.email}' has multiple active workshop organisations. "
                        "Cannot arbitrarily select a workshop organisation during provisioning; "
                        "link the application to the intended organisation explicitly."
                    )
            else:
                workshop_org = Organisation.objects.create(
                    name=application.business_name or f"{user.get_full_name() or user.email} Workshop",
                    type=OrganisationTypeChoices.WORKSHOP,
                    country=valid_country,
                    jurisdiction=valid_jurisdiction,
                    created_by=user,
                    is_active=True,
                )
                application.organisation = workshop_org
                application.save(update_fields=['organisation', 'updated_at'])

        # 3. Manage OrganisationMembership
        # If a membership already exists, do NOT automatically promote ADMIN to OWNER!
        membership, created = OrganisationMembership.objects.get_or_create(
            organisation=workshop_org,
            user=user,
            defaults={
                'role': OrganisationRoleChoices.OWNER,
                'is_active': True,
            },
        )
        if not created and not membership.is_active:
            membership.is_active = True
            membership.save(update_fields=['is_active'])

        # 4. Create or fetch WorkshopProfile with regional defaults
        from apps.workshops.models import WorkshopProfile
        from platform_core.regional import validate_gstin_format, validate_uk_vat_format

        currency = regional_spec.default_currency.value  # 'INR' for IN, 'GBP' for GB

        # Tax Registration Safety:
        # Separate:
        # 1. Tax ID supplied: application.tax_id is non-empty.
        # 2. Tax ID format validated: statutory structural check (GSTIN 15-char structure / UK VAT 9-12 digits).
        # 3. Registration status verified: external statutory verification (HMRC/GST portal) - out of scope.
        # 4. Tax collection eligibility: legal authorization to collect tax.
        #
        # Safety guarantee:
        # - Do not automatically mark an organisation as tax registered solely because tax_id contains text.
        # - Passing structural format validation indicates only syntactic format compliance, NOT government verification.
        # - Do NOT authorize tax collection solely because tax ID passed regex validation.
        # - can_collect_tax is explicitly set to False upon provisioning; authorization requires explicit configuration.
        raw_tax_id = application.tax_id and str(application.tax_id).strip()
        tax_id_format_validated = False
        if raw_tax_id:
            if valid_country == 'IN':
                tax_id_format_validated = validate_gstin_format(raw_tax_id)
            elif valid_country == 'GB':
                tax_id_format_validated = validate_uk_vat_format(raw_tax_id)

        is_tax_registered = tax_id_format_validated
        default_tax_rate = (
            regional_spec.tax_config.default_candidate_rate_motor_repair
            if is_tax_registered
            else Decimal('0.00')
        )

        # Sanitize contact phone: do not accept dummy placeholders like '1234'
        phone = (application.contact_phone or '').strip()
        if len(phone) < 7:
            phone = ''

        profile, _ = WorkshopProfile.objects.get_or_create(
            organisation=workshop_org,
            defaults={
                'business_name': application.business_name or workshop_org.name,
                'contact_email': application.contact_email or user.email,
                'contact_phone': phone,
                'address_line1': application.address_line1,
                'address_line2': application.address_line2,
                'city': application.city,
                'postal_code': application.postal_code,
                'country': valid_country,
                'currency': currency,
                'is_tax_registered': is_tax_registered,
                'can_collect_tax': False,  # Structural validation does NOT authorize tax collection
                'default_tax_rate_percent': default_tax_rate,
                'is_accepting_bookings': False,
            },
        )

    return workshop_org, profile
