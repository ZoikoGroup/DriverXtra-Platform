"""Authoritative supplier tax registration and indirect tax collection authorization resolver.

Derives statutory supplier registration status and indirect tax collection authorization
from verified platform records:
- WorkshopProfile (is_tax_registered, can_collect_tax, gstin_or_vat)
- SellerApplication (verified tax_id format, approval status)
- Direct Organisation / User tax attributes

Statutory Compliance Guarantees:
1. GSTIN/VAT format validation is NEVER treated as government registration verification.
   Regex/format checks validate syntactic structure only and do not query government registries.
2. SellerApplication approval is trade/merchant onboarding approval, NEVER treated as proof
   of active indirect tax registration.
3. Catalogue item classification (listing.is_tax_verified) is a product tariff classification
   under official CBIC schedules, NEVER treated as proof of supplier tax registration.
4. Test overrides require explicit in-memory SupplierRegistrationState enum instances and
   cannot accidentally become production registration defaults.
5. Suspended, cancelled, unverified, voluntarily registered, and below-threshold suppliers
   are cleanly distinguished and mapped to statutory DocumentType determinations.
6. The UK £90,000 threshold (VATA 1994 Schedule 1) is a registration-liability threshold,
   not proof of active registration. Unregistered suppliers below threshold issue non-tax
   Commercial Invoices with 0% VAT.
"""

from decimal import Decimal
from typing import Any, Optional
from django.utils import timezone

from .choices import SupplierRegistrationState
from .models_data import TaxTransactionContext
from platform_core.regional.validators import (
    validate_gstin_format,
    validate_uk_vat_format,
    normalize_country_code,
)


def _normalize_jurisdiction(jur: Optional[str], country_code: str) -> str:
    """Normalizes state/subdivision string to canonical ISO 3166-2 format."""
    if not jur or not str(jur).strip():
        return "GB-ENG" if country_code == "GB" else "IN-MH"

    clean = str(jur).strip().upper()
    if country_code == "IN":
        if clean.startswith("IN-"):
            return clean
        from platform_core.regional.subdivisions import get_subdivision_by_gst_state_code
        sub = get_subdivision_by_gst_state_code(clean)
        if sub:
            return sub.code
        return f"IN-{clean}"
    elif country_code == "GB":
        if clean.startswith("GB-"):
            return clean
        if clean in ("LONDON", "ENG", "ENGLAND"):
            return "GB-ENG"
        if clean in ("SCOTLAND", "SCT"):
            return "GB-SCT"
        if clean in ("WALES", "WLS"):
            return "GB-WLS"
        if clean in ("NORTHERN IRELAND", "NIR"):
            return "GB-NIR"
        return "GB-ENG"

    return clean


def resolve_marketplace_supplier_tax_context(
    listing: Any,
    country_code: str,
    delivery_jurisdiction: Optional[str] = None,
    seller_state_hint: Optional[str] = None,
) -> TaxTransactionContext:
    """Derives authoritative TaxTransactionContext for a marketplace listing seller.

    Evaluates verified supplier records in strict hierarchical order:
    1. Direct explicit in-memory test overrides on seller, organisation, or listing
    2. Account lifecycle suspension check (suspended accounts are blocked immediately)
    3. WorkshopProfile on seller or organisation (workshop merchants)
    4. Approved SellerApplication on seller (trade onboarding records)
    5. Direct seller / organisation tax attributes
    6. Default unverified or below-threshold fallback (catalogue classification never implies supplier registration)
    """
    country_clean = (normalize_country_code(country_code) or "IN").upper()
    currency = "GBP" if country_clean == "GB" else "INR"
    deliv_jur = _normalize_jurisdiction(delivery_jurisdiction, country_clean)
    default_supp_jur = "GB-ENG" if country_clean == "GB" else "IN-MH"
    tx_date = timezone.now().strftime("%Y-%m-%d")

    seller = getattr(listing, "seller", None)
    org = getattr(listing, "organisation", None)

    # 1. Direct explicit in-memory test overrides (requires valid SupplierRegistrationState enum instance)
    explicit_state = (
        getattr(seller, "supplier_registration_state", None)
        or getattr(org, "supplier_registration_state", None)
        or getattr(listing, "supplier_registration_state", None)
    )
    if isinstance(explicit_state, SupplierRegistrationState):
        can_collect = bool(
            getattr(seller, "can_collect_tax", False)
            or (getattr(org, "can_collect_tax", False) if org else False)
            or getattr(listing, "can_collect_tax", False)
        )
        # can_collect_tax requires active or voluntary registration
        if explicit_state in (SupplierRegistrationState.NOT_LIABLE_TO_REGISTER, SupplierRegistrationState.SUSPENDED_OR_CANCELLED):
            can_collect = False

        supp_jur = (
            getattr(org, "jurisdiction", None)
            or getattr(seller, "jurisdiction", None)
            or seller_state_hint
            or default_supp_jur
        )
        return TaxTransactionContext(
            country_code=country_clean,
            supplier_jurisdiction=_normalize_jurisdiction(supp_jur, country_clean),
            supplier_tax_id=getattr(seller, "tax_id", None) or (getattr(org, "tax_id", None) if org else None),
            supplier_registration_state=explicit_state,
            can_collect_tax=can_collect,
            currency=currency,
            transaction_date=tx_date,
            delivery_jurisdiction=deliv_jur,
        )

    # 2. Account Lifecycle / Suspension Guard
    # Suspended, cancelled, or inactive accounts cannot collect tax or issue production tax invoices
    is_seller_suspended = (
        getattr(seller, "status", None) in ("SUSPENDED", "BLOCKED", "CANCELLED")
        or getattr(seller, "is_active", True) is False
    )
    is_org_suspended = getattr(org, "is_active", True) is False if org else False
    if is_seller_suspended or is_org_suspended:
        supp_jur = (getattr(org, "jurisdiction", None) if org else None) or seller_state_hint or default_supp_jur
        return TaxTransactionContext(
            country_code=country_clean,
            supplier_jurisdiction=_normalize_jurisdiction(supp_jur, country_clean),
            supplier_tax_id=getattr(seller, "tax_id", None) or (getattr(org, "tax_id", None) if org else None),
            supplier_registration_state=SupplierRegistrationState.SUSPENDED_OR_CANCELLED,
            can_collect_tax=False,
            currency=currency,
            transaction_date=tx_date,
            delivery_jurisdiction=deliv_jur,
        )

    # 3. Workshop Profile (if organisation or seller operates an authorized workshop)
    workshop = getattr(org, "workshop_profile", None) or getattr(seller, "workshop_profile", None)
    if workshop is not None:
        is_registered = getattr(workshop, "is_tax_registered", False)
        can_collect = getattr(workshop, "can_collect_tax", False)
        tax_id = getattr(workshop, "gstin_or_vat", None) or (getattr(org, "tax_id", None) if org else None)
        supp_jur = getattr(workshop, "jurisdiction", None) or (getattr(org, "jurisdiction", None) if org else None) or default_supp_jur

        if not is_registered:
            supp_state = SupplierRegistrationState.NOT_LIABLE_TO_REGISTER
            can_collect = False
        elif can_collect:
            supp_state = (
                SupplierRegistrationState.VOLUNTARILY_REGISTERED
                if getattr(workshop, "is_voluntarily_registered", False)
                else SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION
            )
        else:
            # Registered on record, but administrative platform tax collection authorization withheld
            supp_state = (
                SupplierRegistrationState.VOLUNTARILY_REGISTERED
                if getattr(workshop, "is_voluntarily_registered", False)
                else SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION
            )
            can_collect = False

        return TaxTransactionContext(
            country_code=country_clean,
            supplier_jurisdiction=_normalize_jurisdiction(supp_jur, country_clean),
            supplier_tax_id=tax_id,
            supplier_registration_state=supp_state,
            can_collect_tax=can_collect,
            currency=currency,
            transaction_date=tx_date,
            delivery_jurisdiction=deliv_jur,
        )

    # 4. Approved Seller Application on seller
    # Note: Trade approval of SellerApplication is NOT proof of active government tax registration.
    # Syntactic format validation of a claimed tax ID confirms syntax only, not portal validity.
    app = None
    if seller and hasattr(seller, "seller_applications"):
        app = seller.seller_applications.filter(status="APPROVED").order_by("-created_at").first()

    if app is not None:
        raw_tax_id = (getattr(app, "tax_id", "") or "").strip()
        app_jur = getattr(app, "jurisdiction", None) or (getattr(org, "jurisdiction", None) if org else None) or default_supp_jur
        can_collect = bool(
            getattr(app, "can_collect_tax", False)
            or getattr(seller, "can_collect_tax", False)
            or (getattr(org, "can_collect_tax", False) if org else False)
        )
        is_tax_registered = bool(
            getattr(app, "is_tax_registered", False)
            or getattr(seller, "is_tax_registered", False)
            or (getattr(org, "is_tax_registered", False) if org else False)
        )

        if raw_tax_id:
            valid_format = validate_gstin_format(raw_tax_id) if country_clean == "IN" else validate_uk_vat_format(raw_tax_id)

            if not valid_format:
                # Claimed tax ID is syntactically invalid
                supp_state = SupplierRegistrationState.UNVERIFIED_REGISTRATION
                can_collect = False
            elif is_tax_registered and can_collect:
                # Authoritative staff-verified registration with explicit collection permission
                supp_state = (
                    SupplierRegistrationState.VOLUNTARILY_REGISTERED
                    if getattr(app, "is_voluntarily_registered", False) or getattr(seller, "is_voluntarily_registered", False)
                    else SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION
                )
            elif is_tax_registered and not can_collect:
                # Verified registration on record, but administrative collection authorization withheld
                supp_state = (
                    SupplierRegistrationState.VOLUNTARILY_REGISTERED
                    if getattr(app, "is_voluntarily_registered", False) or getattr(seller, "is_voluntarily_registered", False)
                    else SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION
                )
                can_collect = False
            else:
                # Syntactically valid tax ID entered on application, but unconfirmed on government registry
                supp_state = SupplierRegistrationState.UNVERIFIED_REGISTRATION
                can_collect = False

            return TaxTransactionContext(
                country_code=country_clean,
                supplier_jurisdiction=_normalize_jurisdiction(app_jur, country_clean),
                supplier_tax_id=raw_tax_id,
                supplier_registration_state=supp_state,
                can_collect_tax=can_collect,
                currency=currency,
                transaction_date=tx_date,
                delivery_jurisdiction=deliv_jur,
            )
        else:
            # Approved application without tax ID: supplier operates below registration threshold
            return TaxTransactionContext(
                country_code=country_clean,
                supplier_jurisdiction=_normalize_jurisdiction(app_jur, country_clean),
                supplier_tax_id=None,
                supplier_registration_state=SupplierRegistrationState.NOT_LIABLE_TO_REGISTER,
                can_collect_tax=False,
                currency=currency,
                transaction_date=tx_date,
                delivery_jurisdiction=deliv_jur,
            )

    # 5. Direct seller / organisation tax attributes
    direct_is_reg = getattr(seller, "is_tax_registered", None)
    if direct_is_reg is None and org:
        direct_is_reg = getattr(org, "is_tax_registered", None)

    direct_can_collect = getattr(seller, "can_collect_tax", None)
    if direct_can_collect is None and org:
        direct_can_collect = getattr(org, "can_collect_tax", None)

    direct_tax_id = getattr(seller, "tax_id", None) or (getattr(org, "tax_id", None) if org else None)
    direct_jur = (getattr(org, "jurisdiction", None) if org else None) or getattr(seller, "jurisdiction", None) or seller_state_hint or default_supp_jur

    if direct_is_reg is not None or direct_can_collect is not None or direct_tax_id is not None:
        if direct_is_reg is False:
            supp_state = SupplierRegistrationState.NOT_LIABLE_TO_REGISTER
            can_collect = False
        elif direct_can_collect is True and direct_is_reg is True:
            supp_state = (
                SupplierRegistrationState.VOLUNTARILY_REGISTERED
                if getattr(seller, "is_voluntarily_registered", False) or (org and getattr(org, "is_voluntarily_registered", False))
                else SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION
            )
            can_collect = True
        elif direct_is_reg is True and not direct_can_collect:
            # Explicitly registered, but collection permission withheld
            supp_state = (
                SupplierRegistrationState.VOLUNTARILY_REGISTERED
                if getattr(seller, "is_voluntarily_registered", False) or (org and getattr(org, "is_voluntarily_registered", False))
                else SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION
            )
            can_collect = False
        else:
            # Tax ID provided without verified registration record
            supp_state = SupplierRegistrationState.UNVERIFIED_REGISTRATION if direct_tax_id else SupplierRegistrationState.NOT_LIABLE_TO_REGISTER
            can_collect = False

        return TaxTransactionContext(
            country_code=country_clean,
            supplier_jurisdiction=_normalize_jurisdiction(direct_jur, country_clean),
            supplier_tax_id=direct_tax_id,
            supplier_registration_state=supp_state,
            can_collect_tax=can_collect,
            currency=currency,
            transaction_date=tx_date,
            delivery_jurisdiction=deliv_jur,
        )

    # 6. Fallback: Catalogue classification NEVER implies supplier tax registration.
    # An item having is_tax_verified=True confirms tariff classification of the part,
    # not government tax registration or collection authority of the supplier.
    gst_rate = getattr(listing, "gst_rate", None)
    supp_jur = (getattr(org, "jurisdiction", None) if org else None) or seller_state_hint or default_supp_jur

    if country_clean == "IN":
        if gst_rate is not None and Decimal(str(gst_rate)) > Decimal("0.00"):
            # Taxable good listed by supplier without verified registration on record:
            # Underlying statutory tax is calculated and preserved, but invoice issuance is withheld.
            supp_state = SupplierRegistrationState.UNVERIFIED_REGISTRATION
            can_collect = False
        else:
            # 0% GST or non-taxable part: supplier operates below registration threshold
            supp_state = SupplierRegistrationState.NOT_LIABLE_TO_REGISTER
            can_collect = False
    else:
        # UK: Supplier operates below the £90,000 threshold without verified VAT registration on file.
        supp_state = SupplierRegistrationState.NOT_LIABLE_TO_REGISTER
        can_collect = False

    return TaxTransactionContext(
        country_code=country_clean,
        supplier_jurisdiction=_normalize_jurisdiction(supp_jur, country_clean),
        supplier_tax_id=None,
        supplier_registration_state=supp_state,
        can_collect_tax=can_collect,
        currency=currency,
        transaction_date=tx_date,
        delivery_jurisdiction=deliv_jur,
    )
