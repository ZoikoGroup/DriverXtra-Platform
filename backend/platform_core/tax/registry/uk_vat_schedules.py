"""Authoritative UK VAT statutory schedules under VATA 1994 and official HMRC guidance.

Grounded in:
- Value Added Tax Act 1994 (VATA 1994), Sections 2, 29A, 30, Schedules 7A, 8, 9.
- HMRC VAT Notice 700 (The VAT Guide), Section 25.4 (MOT test fees and disbursements).
- HMRC VAT Notice 701/23 (Protective equipment), Section 3 (Motorcycle helmets).
- HMRC VAT Notice 701/10 (Zero-rating of books and printed matter), Section 3 & 4.
"""

from decimal import Decimal
from typing import Optional, Dict, Any, Tuple
from platform_core.tax.choices import ClassificationGovernanceStatus, TaxCategory


UK_VAT_STANDARD_RATE = Decimal("20.00")
UK_VAT_REDUCED_RATE = Decimal("5.00")
UK_VAT_ZERO_RATE = Decimal("0.00")


def resolve_uk_vat_classification(
    item_type: str,
    description: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[Decimal, TaxCategory, str, ClassificationGovernanceStatus, Optional[str]]:
    """Resolves statutory UK VAT rate, category, and legal citation for an item.

    Returns:
        (rate, tax_category, legal_citation, governance_status, review_reason)
    """
    clean_desc = (description or "").lower().strip()
    clean_type = (item_type or "").upper().strip()
    meta = metadata or {}

    # 1. Statutory MOT Test Fee (Outside the Scope of VAT under Notice 700 §25.4)
    if "mot" in clean_desc and any(k in clean_desc for k in ("test", "fee", "inspection", "statutory")):
        # Check if this is an explicit markup or arrangement charge
        if any(k in clean_desc for k in ("markup", "arrangement fee", "handling fee", "booking charge")):
            return (
                UK_VAT_STANDARD_RATE,
                TaxCategory.STANDARD,
                "VATA 1994 Section 2(1); HMRC Notice 700 Section 25.4 (Garage arrangement markup)",
                ClassificationGovernanceStatus.CONFIRMED,
                None,
            )
        # Check if billed as a combined MOT and service package
        if any(k in clean_desc for k in ("and service", "package", "& service", "with service")):
            return (
                UK_VAT_STANDARD_RATE,
                TaxCategory.STANDARD,
                "VATA 1994 Section 2(1); Notice 700 §25.4 (Combined unitemized MOT package)",
                ClassificationGovernanceStatus.PROVISIONAL,
                "Combined MOT and service package must itemise MOT test fee to qualify for outside-scope disbursement.",
            )
        # Standalone statutory MOT test inspection fee
        return (
            UK_VAT_ZERO_RATE,
            TaxCategory.OUTSIDE_SCOPE,
            "HMRC VAT Notice 700 Section 25.4 (Statutory DVSA MOT test inspection fee)",
            ClassificationGovernanceStatus.CONFIRMED,
            None,
        )

    # 2. Children's Car Seats (Reduced Rate 5.00% under VATA 1994 Schedule 7A Group 5)
    if any(k in clean_desc for k in ("child seat", "car seat", "isofix child", "booster seat", "infant carrier", "carrycot")):
        # Must be genuinely for child safety restraint
        return (
            UK_VAT_REDUCED_RATE,
            TaxCategory.REDUCED,
            "VATA 1994 Section 29A, Schedule 7A, Group 5 (Children's car seats)",
            ClassificationGovernanceStatus.CONFIRMED,
            None,
        )

    # 3. Protective Motorcycle Helmets (VATA 1994 Schedule 8 Group 16 & Notice 701/23 §3)
    if any(k in clean_desc for k in ("motorcycle helmet", "crash helmet", "motorbike helmet", "riding helmet")):
        # Check if standalone accessory or replacement part
        if any(k in clean_desc for k in ("visor", "shield", "earphone", "headset", "cheek pad", "intercom", "tear-off")):
            return (
                UK_VAT_STANDARD_RATE,
                TaxCategory.STANDARD,
                "VATA 1994 Section 2(1); Notice 701/23 Section 3 (Standalone helmet accessory)",
                ClassificationGovernanceStatus.CONFIRMED,
                None,
            )
        # For complete helmet: check conformity evidence
        has_ppe_conformity = meta.get("has_ppe_conformity", True)
        has_conformity_mark = meta.get("has_conformity_mark", True)
        if has_ppe_conformity and has_conformity_mark:
            return (
                UK_VAT_ZERO_RATE,
                TaxCategory.ZERO_RATED,
                "VATA 1994 Section 30, Schedule 8, Group 16; Notice 701/23 Section 3 (Qualifying PPE Reg 8(2) motorcycle helmet)",
                ClassificationGovernanceStatus.CONFIRMED,
                None,
            )
        return (
            UK_VAT_STANDARD_RATE,
            TaxCategory.STANDARD,
            "VATA 1994 Section 2(1); Notice 701/23 §3 (Helmet lacking statutory PPE conformity mark)",
            ClassificationGovernanceStatus.PROVISIONAL,
            "Motorcycle helmet lacking verified Regulation 8(2) conformity mark is standard-rated (20%).",
        )

    # 4. Technical Publications, Software, Diagnostic Tools, and Stationery (Schedule 8 Group 3 & Notice 701/10)
    pub_keywords = (
        "manual", "handbook", "workshop book", "service book", "wiring diagram",
        "logbook", "checklist", "worksheet", "form", "e-book", "ebook", "pdf",
        "diagnostic software", "diagnostic tool", "scanner software", "app",
    )
    if any(k in clean_desc for k in pub_keywords):
        # A. Software, diagnostic applications, executable tools, digital subscriptions (Standard-rated 20%)
        is_software = any(k in clean_desc for k in (
            "software", "diagnostic tool", "diagnostic app", "scanner tool", "scanner software",
            "ecu tune", "tuning software", "obd software", "database", "subscription",
            "portal", "interactive tool", "license", "application", "executable",
        ))
        is_manual = any(k in clean_desc for k in ("manual", "handbook", "guide", "book", "instructions", "e-book", "ebook", "pdf"))

        if is_software:
            # Check if bundled with manual/text without itemisation
            if is_manual and any(k in clean_desc for k in ("bundle", "package", "with software", "+ software", "kit")):
                return (
                    UK_VAT_STANDARD_RATE,
                    TaxCategory.STANDARD,
                    "VATA 1994 Section 2(1); Notice 701/10 (Bundled digital package with software)",
                    ClassificationGovernanceStatus.PROVISIONAL,
                    "Bundled digital package combining technical manual with software or interactive diagnostic access requires apportionment review.",
                )
            return (
                UK_VAT_STANDARD_RATE,
                TaxCategory.STANDARD,
                "VATA 1994 Section 2(1); Notice 701/10 Section 4 (Automotive software, diagnostic tools, and database services)",
                ClassificationGovernanceStatus.CONFIRMED,
                None,
            )

        # B. Completion-oriented publications, stationery, forms, checklists, worksheets (Standard-rated 20%)
        if any(k in clean_desc for k in (
            "checklist", "worksheet", "form", "inspection pad", "logbook", "service history book",
            "stamp book", "blank", "job card", "record sheet", "template to complete",
        )):
            return (
                UK_VAT_STANDARD_RATE,
                TaxCategory.STANDARD,
                "VATA 1994 Section 2(1), Schedule 8 Group 3 Note 1(a); Notice 701/10 (Stationery, forms, and completion-oriented publications)",
                ClassificationGovernanceStatus.CONFIRMED,
                None,
            )

        # C. Single-sheet diagrams, wall charts, posters (Standard-rated 20%)
        if any(k in clean_desc for k in ("poster", "wall chart", "single sheet", "diagram print")):
            return (
                UK_VAT_STANDARD_RATE,
                TaxCategory.STANDARD,
                "VATA 1994 Section 2(1); Notice 701/10 Section 3.7 (Single-sheet diagrams/plans)",
                ClassificationGovernanceStatus.CONFIRMED,
                None,
            )

        # D. Qualifying printed technical repair manuals or standalone electronic text manuals (e-book / PDF) -> Zero-rated 0%
        return (
            UK_VAT_ZERO_RATE,
            TaxCategory.ZERO_RATED,
            "VATA 1994 Section 30, Schedule 8, Group 3; Notice 701/10 Section 3 & 4 (Qualifying technical repair manual / e-book)",
            ClassificationGovernanceStatus.CONFIRMED,
            None,
        )

    # 5. Standard Motor Repairs, Servicing, Diagnostic Labour and Replacement Parts
    return (
        UK_VAT_STANDARD_RATE,
        TaxCategory.STANDARD,
        "VATA 1994 Section 2(1) (Standard rate on automotive services and parts)",
        ClassificationGovernanceStatus.CONFIRMED,
        None,
    )

