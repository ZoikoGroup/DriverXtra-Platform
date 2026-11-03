"""Authoritative Indian Service Accounting Code (SAC) registry for automotive workshops.

Grounded in CBIC Notification No. 11/2017-Central Tax (Rate), as amended,
and the official CBIC Explanatory Notes to the Scheme of Classification of Services (UN CPC).
"""

from decimal import Decimal
from typing import Optional, Dict, Any, Tuple
from platform_core.tax.choices import ClassificationGovernanceStatus, TaxCategory
from .base import BaseClassificationRegistry


STATUTORY_INDIAN_SAC_REGISTRY: Dict[str, Dict[str, Any]] = {
    # 998714: Maintenance and repair services of motor vehicles
    "998714": {
        "sac_code": "998714",
        "description": "Maintenance and repair services of motor vehicles",
        "official_scope": (
            "Includes routine maintenance inspections; mechanical and electrical repairs; "
            "engine overhauls, motor tune-ups; body repairs and panel beating; "
            "automobile washing, cleaning and polishing services; undercoating, rust-proofing, waxing; "
            "automobile emergency road services (breakdown assistance on the road). "
            "Detailing, polishing, waxing, and ceramic protective coating fall within this scope."
        ),
        "rate": Decimal("18.00"),
        "cgst_rate": Decimal("9.00"),
        "sgst_rate": Decimal("9.00"),
        "igst_rate": Decimal("18.00"),
        "legal_citation": "CBIC Notif. No. 11/2017-CT(R), Serial No. 25(ii); UN CPC 87141",
        "effective_from": "2017-07-01",
        "effective_to": None,
        "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        "is_production_invoicing_permitted": True,
    },
    # 996744: Towing services for commercial and private vehicles
    "996744": {
        "sac_code": "996744",
        "description": "Towing services for commercial and private vehicles",
        "official_scope": (
            "Under Heading 9967 (Supporting services in transport), Group 99674 (Supporting services for road transport). "
            "Includes towing services for distressed commercial and private vehicles and towing for parking violations."
        ),
        "rate": Decimal("18.00"),
        "cgst_rate": Decimal("9.00"),
        "sgst_rate": Decimal("9.00"),
        "igst_rate": Decimal("18.00"),
        "legal_citation": "CBIC Notif. No. 11/2017-CT(R), Serial No. 23(iii); UN CPC 74490",
        "effective_from": "2017-07-01",
        "effective_to": None,
        "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        "is_production_invoicing_permitted": True,
    },
    # 998346: Technical inspection services of road transport vehicles
    "998346": {
        "sac_code": "998346",
        "description": "Technical inspection services of road transport vehicles",
        "official_scope": (
            "Under Heading 9983, Group 99834 (Technical testing and analysis services). "
            "Covers periodic technical inspection services of passenger cars, buses, and commercial lorries "
            "(statutory roadworthiness checks, emission / Pollution Under Control testing, computerized brake bench testing). "
            "Excludes routine mechanical fault diagnosis performed as an integral preliminary part of a repair (which is 998714)."
        ),
        "rate": Decimal("18.00"),
        "cgst_rate": Decimal("9.00"),
        "sgst_rate": Decimal("9.00"),
        "igst_rate": Decimal("18.00"),
        "legal_citation": "CBIC Notif. No. 11/2017-CT(R), Serial No. 21(ii); UN CPC 83344",
        "effective_from": "2017-07-01",
        "effective_to": None,
        "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        "is_production_invoicing_permitted": True,
    },
    # 996729: Other storage and warehousing services (PROVISIONAL)
    "996729": {
        "sac_code": "996729",
        "description": "Other storage and warehousing services",
        "official_scope": (
            "Storage of goods in open or covered yards. Applies to vehicle storage strictly when a genuine, "
            "distinct commercial vehicle storage agreement exists. Late vehicle collection charges, demurrage, "
            "or penalties for delay in vehicle pickup are governed by Section 15(2)(d) of the CGST Act 2017 as "
            "an ancillary part of the repair consideration (998714), not storage, unless an independent storage contract exists."
        ),
        "rate": Decimal("18.00"),
        "cgst_rate": Decimal("9.00"),
        "sgst_rate": Decimal("9.00"),
        "igst_rate": Decimal("18.00"),
        "legal_citation": "CBIC Notif. No. 11/2017-CT(R), Serial No. 23(iii); UN CPC 74290",
        "effective_from": "2017-07-01",
        "effective_to": None,
        "governance_status": ClassificationGovernanceStatus.PROVISIONAL,
        "is_production_invoicing_permitted": False,  # Contractual analysis required
    },
    # 999432: Hazardous waste treatment and disposal services (PROVISIONAL)
    "999432": {
        "sac_code": "999432",
        "description": "Hazardous waste treatment and disposal services",
        "official_scope": (
            "Treatment and disposal of toxic, chemical, and hazardous waste. Strictly restricted to spent acid "
            "from lead-acid batteries, toxic transmission fluids, and hazardous coolants. Excludes non-hazardous tyre "
            "recycling and scrap metal disposal (999431 or 99941)."
        ),
        "rate": Decimal("18.00"),
        "cgst_rate": Decimal("9.00"),
        "sgst_rate": Decimal("9.00"),
        "igst_rate": Decimal("18.00"),
        "legal_citation": "CBIC Notif. No. 11/2017-CT(R), Serial No. 32; UN CPC 94320",
        "effective_from": "2017-07-01",
        "effective_to": None,
        "governance_status": ClassificationGovernanceStatus.PROVISIONAL,
        "is_production_invoicing_permitted": False,  # Restricted to verified hazardous waste
    },
}


def get_sac_entry(sac_code: Optional[str]) -> Optional[Dict[str, Any]]:
    """Retrieve official SAC classification entry if registered."""
    if not sac_code:
        return None
    clean = str(sac_code).replace(" ", "").replace(".", "").strip()
    return STATUTORY_INDIAN_SAC_REGISTRY.get(clean)


def resolve_workshop_service_sac(
    item_type: str,
    description: str,
) -> Tuple[Optional[str], ClassificationGovernanceStatus, Optional[str]]:
    """Resolves statutory SAC code and governance status for a workshop line item.

    Returns:
        (sac_code: Optional[str], governance_status, review_reason: Optional[str])
    """
    clean_desc = (description or "").lower().strip()
    clean_type = (item_type or "").upper().strip()

    # 1. Towing / breakdown vehicle recovery
    if any(k in clean_desc for k in ("towing", "tow ", "recovery", "flatbed", "winch")):
        return "996744", ClassificationGovernanceStatus.CONFIRMED, None

    # 2. Statutory Technical Inspection / Emission Testing
    if any(k in clean_desc for k in ("puc", "pollution under control", "emission test", "roadworthiness inspection", "statutory vehicle inspection")):
        return "998346", ClassificationGovernanceStatus.CONFIRMED, None

    # 3. Storage / Demurrage / Holding Fees
    if any(k in clean_desc for k in ("demurrage", "storage", "parking charge", "late collection", "holding fee")):
        return (
            "996729",
            ClassificationGovernanceStatus.PROVISIONAL,
            "Late vehicle collection or storage charge requires contractual review under CGST Act Section 15(2)(d).",
        )

    # 4. Waste Disposal / Scrap
    if any(k in clean_desc for k in ("waste disposal", "tyre disposal", "scrap fee", "hazardous disposal", "battery acid disposal")):
        return (
            "999432",
            ClassificationGovernanceStatus.PROVISIONAL,
            "Waste disposal requires factual assessment of hazardous vs non-hazardous treatment.",
        )

    # 5. Ceramic Coating, Graphene Coating, and Paint Protection Film (PPF)
    if any(k in clean_desc for k in ("ceramic", "graphene", "ppf", "paint protection film", "paint protection")):
        # Only explicitly routine cleaning / wash / polish touch-up is CONFIRMED under SAC 998714
        is_routine_cleaning = any(k in clean_desc for k in ("routine wash", "ceramic wash", "maintenance wash", "routine cleaning", "polish touch-up", "wax and polish", "routine polish"))
        is_coating_application = any(k in clean_desc for k in ("coat", "coating", "ppf", "film", "graphene", "treatment", "application", "package", "9h", "10h"))

        if is_routine_cleaning and not is_coating_application:
            return "998714", ClassificationGovernanceStatus.CONFIRMED, None

        # All ceramic coating, graphene coating, PPF, and film applications default to PROVISIONAL
        return (
            "998714",
            ClassificationGovernanceStatus.PROVISIONAL,
            "Ceramic coating, graphene coating, and PPF applications require factual verification to confirm composite service vs goods supply under CGST Act Section 8.",
        )

    # 6. Standard Motor Vehicle Maintenance and Repair (Labour, mechanical, electrical, servicing, washing)
    if clean_type in ("LABOUR", "SERVICE", "REPAIR") or any(k in clean_desc for k in ("repair", "service", "maintenance", "overhaul", "fitting", "wash", "polish", "wax", "cleaning")):
        return "998714", ClassificationGovernanceStatus.CONFIRMED, None

    # 7. Unclassified service
    return None, ClassificationGovernanceStatus.UNRESOLVED_LEGAL_QUESTION, f"Unrecognized service activity '{description}'. Explicit SAC classification required."

