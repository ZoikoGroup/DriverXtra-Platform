"""Authoritative Indian statutory HSN classification registry with full 8-digit tariff items.

Grounded in CBIC Notification No. 1/2017-Central Tax (Rate), rate amendments,
and the 2025 GST Council rate rationalisation.
"""

from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple
from platform_core.tax.choices import ClassificationGovernanceStatus, TaxCategory
from .base import BaseClassificationRegistry


# =============================================================================
# STATUTORY 8-DIGIT TARIFF CLASSIFICATION ENTRIES
# =============================================================================

STATUTORY_INDIAN_HSN_REGISTRY: Dict[str, List[Dict[str, Any]]] = {
    # 8708 29 00: Body parts (bumpers, body panels, grilles)
    "87082900": [
        {
            "tariff_item": "87082900",
            "heading": "8708",
            "description": "Other parts and accessories of bodies (including cabs) of motor vehicles",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2025-09-22",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Sched. IV, Entry 390; 2025 GST Council Rate Rationalisation",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
        {
            "tariff_item": "87082900",
            "heading": "8708",
            "description": "Other parts and accessories of bodies (including cabs) of motor vehicles",
            "rate": Decimal("28.00"),
            "cgst_rate": Decimal("14.00"),
            "sgst_rate": Decimal("14.00"),
            "igst_rate": Decimal("28.00"),
            "effective_from": "2017-07-01",
            "effective_to": "2025-09-21",
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule IV, Entry 390",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8708 30 00: Brakes and servo-brakes and parts thereof (brake pads, calipers, drums)
    "87083000": [
        {
            "tariff_item": "87083000",
            "heading": "8708",
            "description": "Mounted brake linings, brakes, servo-brakes and parts thereof",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2025-09-22",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Sched. IV, Entry 390; 2025 GST Council Rate Rationalisation",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
        {
            "tariff_item": "87083000",
            "heading": "8708",
            "description": "Mounted brake linings, brakes, servo-brakes and parts thereof",
            "rate": Decimal("28.00"),
            "cgst_rate": Decimal("14.00"),
            "sgst_rate": Decimal("14.00"),
            "igst_rate": Decimal("28.00"),
            "effective_from": "2017-07-01",
            "effective_to": "2025-09-21",
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule IV, Entry 390",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8708 40 00: Gear boxes and parts thereof
    "87084000": [
        {
            "tariff_item": "87084000",
            "heading": "8708",
            "description": "Gear boxes and parts thereof",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2025-09-22",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Sched. IV, Entry 390; 2025 GST Council Rate Rationalisation",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
        {
            "tariff_item": "87084000",
            "heading": "8708",
            "description": "Gear boxes and parts thereof",
            "rate": Decimal("28.00"),
            "cgst_rate": Decimal("14.00"),
            "sgst_rate": Decimal("14.00"),
            "igst_rate": Decimal("28.00"),
            "effective_from": "2017-07-01",
            "effective_to": "2025-09-21",
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule IV, Entry 390",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8708 50 00: Drive-axles with differential
    "87085000": [
        {
            "tariff_item": "87085000",
            "heading": "8708",
            "description": "Drive-axles with differential; non-driving axles and parts thereof",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2025-09-22",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Sched. IV, Entry 390; 2025 GST Council Rate Rationalisation",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
        {
            "tariff_item": "87085000",
            "heading": "8708",
            "description": "Drive-axles with differential; non-driving axles and parts thereof",
            "rate": Decimal("28.00"),
            "cgst_rate": Decimal("14.00"),
            "sgst_rate": Decimal("14.00"),
            "igst_rate": Decimal("28.00"),
            "effective_from": "2017-07-01",
            "effective_to": "2025-09-21",
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule IV, Entry 390",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8708 70 00: Road wheels and parts and accessories thereof
    "87087000": [
        {
            "tariff_item": "87087000",
            "heading": "8708",
            "description": "Road wheels and parts and accessories thereof",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2025-09-22",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Sched. IV, Entry 390; 2025 GST Council Rate Rationalisation",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
        {
            "tariff_item": "87087000",
            "heading": "8708",
            "description": "Road wheels and parts and accessories thereof",
            "rate": Decimal("28.00"),
            "cgst_rate": Decimal("14.00"),
            "sgst_rate": Decimal("14.00"),
            "igst_rate": Decimal("28.00"),
            "effective_from": "2017-07-01",
            "effective_to": "2025-09-21",
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule IV, Entry 390",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8708 80 00: Suspension systems and parts thereof (shock absorbers)
    "87088000": [
        {
            "tariff_item": "87088000",
            "heading": "8708",
            "description": "Suspension systems and parts thereof (including shock absorbers)",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2025-09-22",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Sched. IV, Entry 390; 2025 GST Council Rate Rationalisation",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
        {
            "tariff_item": "87088000",
            "heading": "8708",
            "description": "Suspension systems and parts thereof (including shock absorbers)",
            "rate": Decimal("28.00"),
            "cgst_rate": Decimal("14.00"),
            "sgst_rate": Decimal("14.00"),
            "igst_rate": Decimal("28.00"),
            "effective_from": "2017-07-01",
            "effective_to": "2025-09-21",
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule IV, Entry 390",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8708 91 00: Radiators and parts thereof
    "87089100": [
        {
            "tariff_item": "87089100",
            "heading": "8708",
            "description": "Radiators and parts thereof",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2025-09-22",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Sched. IV, Entry 390; 2025 GST Council Rate Rationalisation",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
        {
            "tariff_item": "87089100",
            "heading": "8708",
            "description": "Radiators and parts thereof",
            "rate": Decimal("28.00"),
            "cgst_rate": Decimal("14.00"),
            "sgst_rate": Decimal("14.00"),
            "igst_rate": Decimal("28.00"),
            "effective_from": "2017-07-01",
            "effective_to": "2025-09-21",
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule IV, Entry 390",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8708 92 00: Silencers and exhaust pipes
    "87089200": [
        {
            "tariff_item": "87089200",
            "heading": "8708",
            "description": "Silencers (mufflers) and exhaust pipes; parts thereof",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2025-09-22",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Sched. IV, Entry 390; 2025 GST Council Rate Rationalisation",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
        {
            "tariff_item": "87089200",
            "heading": "8708",
            "description": "Silencers (mufflers) and exhaust pipes; parts thereof",
            "rate": Decimal("28.00"),
            "cgst_rate": Decimal("14.00"),
            "sgst_rate": Decimal("14.00"),
            "igst_rate": Decimal("28.00"),
            "effective_from": "2017-07-01",
            "effective_to": "2025-09-21",
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule IV, Entry 390",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8708 93 00: Clutches and parts thereof
    "87089300": [
        {
            "tariff_item": "87089300",
            "heading": "8708",
            "description": "Clutches and parts thereof",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2025-09-22",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Sched. IV, Entry 390; 2025 GST Council Rate Rationalisation",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
        {
            "tariff_item": "87089300",
            "heading": "8708",
            "description": "Clutches and parts thereof",
            "rate": Decimal("28.00"),
            "cgst_rate": Decimal("14.00"),
            "sgst_rate": Decimal("14.00"),
            "igst_rate": Decimal("28.00"),
            "effective_from": "2017-07-01",
            "effective_to": "2025-09-21",
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule IV, Entry 390",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8708 94 00: Steering wheels, steering columns and boxes
    "87089400": [
        {
            "tariff_item": "87089400",
            "heading": "8708",
            "description": "Steering wheels, steering columns and steering boxes; parts thereof",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2025-09-22",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Sched. IV, Entry 390; 2025 GST Council Rate Rationalisation",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
        {
            "tariff_item": "87089400",
            "heading": "8708",
            "description": "Steering wheels, steering columns and steering boxes; parts thereof",
            "rate": Decimal("28.00"),
            "cgst_rate": Decimal("14.00"),
            "sgst_rate": Decimal("14.00"),
            "igst_rate": Decimal("28.00"),
            "effective_from": "2017-07-01",
            "effective_to": "2025-09-21",
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule IV, Entry 390",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8409 91 00: IC Piston engine parts (pistons, cylinder blocks, heads, valves)
    "84099100": [
        {
            "tariff_item": "84099100",
            "heading": "8409",
            "description": "Parts suitable for use solely or principally with spark-ignition internal combustion piston engines",
            "rate": Decimal("28.00"),
            "cgst_rate": Decimal("14.00"),
            "sgst_rate": Decimal("14.00"),
            "igst_rate": Decimal("28.00"),
            "effective_from": "2017-07-01",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule IV, Entry 318",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8507 10 00: Lead-acid starting batteries
    "85071000": [
        {
            "tariff_item": "85071000",
            "heading": "8507",
            "description": "Electric accumulators, lead-acid, of a kind used for starting piston engines",
            "rate": Decimal("28.00"),
            "cgst_rate": Decimal("14.00"),
            "sgst_rate": Decimal("14.00"),
            "igst_rate": Decimal("28.00"),
            "effective_from": "2017-07-01",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule IV, Entry 377",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8507 60 00: Lithium-ion batteries
    "85076000": [
        {
            "tariff_item": "85076000",
            "heading": "8507",
            "description": "Lithium-ion accumulators (including battery packs for electric vehicles)",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2018-07-27",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 18/2018-CT(R), Schedule III, Entry 378A",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8504 40 90: EV static converters / on-board chargers
    "85044090": [
        {
            "tariff_item": "85044090",
            "heading": "8504",
            "description": "Electric vehicle static converters, on-board chargers, power electronics",
            "rate": Decimal("5.00"),
            "cgst_rate": Decimal("2.50"),
            "sgst_rate": Decimal("2.50"),
            "igst_rate": Decimal("5.00"),
            "effective_from": "2019-08-01",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 12/2019-CT(R), Schedule I, Entry 244B",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8421 23 00: Oil or petrol-filters for IC engines
    "84212300": [
        {
            "tariff_item": "84212300",
            "heading": "8421",
            "description": "Oil or petrol-filters for internal combustion engines",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2017-07-01",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule III, Entry 322",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8421 31 00: Intake air filters for IC engines
    "84213100": [
        {
            "tariff_item": "84213100",
            "heading": "8421",
            "description": "Intake air filters for internal combustion engines",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2017-07-01",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule III, Entry 322",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8413 30 10: Fuel injection pumps for diesel engines
    "84133010": [
        {
            "tariff_item": "84133010",
            "heading": "8413",
            "description": "Fuel injection pumps for diesel engines",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2017-07-01",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule III, Entry 319",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8413 30 20: Water circulating pumps
    "84133020": [
        {
            "tariff_item": "84133020",
            "heading": "8413",
            "description": "Water circulating pumps for motor vehicle cooling systems",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2017-07-01",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule III, Entry 319",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 4016 93 20: Rubber seals, weather strips
    "40169320": [
        {
            "tariff_item": "40169320",
            "heading": "4016",
            "description": "Rubber seals, gaskets, and weather strips of vulcanised rubber",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2017-07-01",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule III, Entry 111",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 2710 19 81: Lubricating engine oils
    "27101981": [
        {
            "tariff_item": "27101981",
            "heading": "2710",
            "description": "Lubricating engine oils (mineral, synthetic, semi-synthetic)",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2017-07-01",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule III, Entry 34",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 6813 81 00: Brake linings and pads of mineral substances
    "68138100": [
        {
            "tariff_item": "68138100",
            "heading": "6813",
            "description": "Friction material and articles thereof (brake linings and unmounted pads)",
            "rate": Decimal("18.00"),
            "cgst_rate": Decimal("9.00"),
            "sgst_rate": Decimal("9.00"),
            "igst_rate": Decimal("18.00"),
            "effective_from": "2017-07-01",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule III, Entry 181",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 8511 10 00: Spark plugs
    "85111000": [
        {
            "tariff_item": "85111000",
            "heading": "8511",
            "description": "Spark plugs for internal combustion engines",
            "rate": Decimal("28.00"),
            "cgst_rate": Decimal("14.00"),
            "sgst_rate": Decimal("14.00"),
            "igst_rate": Decimal("28.00"),
            "effective_from": "2017-07-01",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule IV, Entry 380",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
    # 7007 21 00: Laminated automotive windscreens
    "70072100": [
        {
            "tariff_item": "70072100",
            "heading": "7007",
            "description": "Laminated automotive safety glass (front windscreens)",
            "rate": Decimal("28.00"),
            "cgst_rate": Decimal("14.00"),
            "sgst_rate": Decimal("14.00"),
            "igst_rate": Decimal("28.00"),
            "effective_from": "2017-07-01",
            "effective_to": None,
            "legal_citation": "CBIC Notif. No. 1/2017-CT(R), Schedule IV, Entry 185",
            "governance_status": ClassificationGovernanceStatus.CONFIRMED,
        },
    ],
}


def normalize_code(code: Optional[str]) -> str:
    """Normalize tariff or HSN code to digits without spaces or dots."""
    if not code:
        return ""
    return str(code).replace(" ", "").replace(".", "").strip()


def get_tariff_entry_for_date(
    tariff_code: str,
    transaction_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve full 8-digit tariff entry effective on specified transaction date."""
    clean = normalize_code(tariff_code)
    if not clean:
        return None

    # Check direct 8-digit match
    candidates = STATUTORY_INDIAN_HSN_REGISTRY.get(clean)
    if not candidates:
        # Check if 4-digit or 6-digit prefix maps to a known tariff item
        for code, entries in STATUTORY_INDIAN_HSN_REGISTRY.items():
            if code.startswith(clean) or clean.startswith(code[:4]):
                candidates = entries
                break

    if not candidates:
        return None

    target_date = transaction_date or "2099-12-31"

    for entry in candidates:
        eff_from = entry.get("effective_from") or "2017-07-01"
        eff_to = entry.get("effective_to")
        if target_date >= eff_from:
            if eff_to is None or target_date <= eff_to:
                return entry

    return candidates[0] if candidates else None


def validate_tariff_classification(
    tariff_code: Optional[str],
    gst_rate: Optional[Decimal],
    transaction_date: Optional[str] = None,
) -> Tuple[bool, Optional[str], ClassificationGovernanceStatus]:
    """Validate tariff code and GST rate against statutory CBIC schedules.

    Returns:
        (is_valid: bool, error_message: Optional[str], governance_status)
    """
    if not tariff_code:
        return False, "Tariff classification code is required under Indian GST law.", ClassificationGovernanceStatus.UNRESOLVED_LEGAL_QUESTION

    entry = get_tariff_entry_for_date(tariff_code, transaction_date)
    if not entry:
        return (
            False,
            f"Code '{tariff_code}' is not a recognized automotive tariff classification.",
            ClassificationGovernanceStatus.UNRESOLVED_LEGAL_QUESTION,
        )

    if gst_rate is None:
        return False, f"Applicable GST rate must be specified for {entry['tariff_item']}.", entry["governance_status"]

    claimed_rate = Decimal(str(gst_rate))
    expected_rate = entry["rate"]

    # Allow valid historical 28% if transaction occurred prior to rate rationalisation
    if claimed_rate != expected_rate:
        # Check if claimed rate matches an alternative effective-date bracket
        clean = normalize_code(tariff_code)
        all_brackets = STATUTORY_INDIAN_HSN_REGISTRY.get(clean, [])
        allowed_rates = {b["rate"] for b in all_brackets}
        if claimed_rate in allowed_rates:
            return True, None, entry["governance_status"]

        return (
            False,
            f"GST rate {claimed_rate}% is not legally applicable for tariff {entry['tariff_item']} "
            f"({entry['description']}). Statutory rate is {expected_rate}%.",
            ClassificationGovernanceStatus.UNRESOLVED_LEGAL_QUESTION,
        )

    return True, None, entry["governance_status"]


def resolve_automotive_part_hsn(description: str) -> Optional[str]:
    """Resolves statutory 8-digit HSN code for automotive parts based on description keywords."""
    text = (description or "").lower()
    if any(k in text for k in ("clutch", "flywheel", "pressure plate", "release bearing")):
        return "87089300"
    if any(k in text for k in ("brake", "pad", "caliper", "rotor", "lining", "disc", "drum")):
        return "87083000"
    if any(k in text for k in ("gear", "gearbox", "transmission", "shifter")):
        return "87084000"
    if any(k in text for k in ("axle", "half shaft", "differential")):
        return "87085000"
    if any(k in text for k in ("wheel", "rim", "alloy", "hub")):
        return "87087000"
    if any(k in text for k in ("suspension", "shock", "strut", "damper", "spring")):
        return "87088000"
    if any(k in text for k in ("radiator", "intercooler", "oil cooler")):
        return "87089100"
    if any(k in text for k in ("silencer", "muffler", "exhaust", "tailpipe", "catalytic")):
        return "87089200"
    if any(k in text for k in ("steering", "rack", "pinion", "tie rod")):
        return "87089400"
    if any(k in text for k in ("bumper", "fender", "bonnet", "hood", "grille", "door", "mirror", "panel", "body")):
        return "87082900"
    if any(k in text for k in ("filter", "element", "purif")):
        if "air" in text:
            return "84213100"
        return "84212300"
    if any(k in text for k in ("pump",)):
        if "water" in text:
            return "84133020"
        return "84133010"
    if any(k in text for k in ("battery", "accumulator")):
        if "lithium" in text or "li-ion" in text:
            return "85076000"
        return "85071000"
    if any(k in text for k in ("spark", "plug", "ignition", "distributor")):
        return "85111000"
    if any(k in text for k in ("oil", "fluid", "lubricant", "grease")):
        return "27101981"
    if any(k in text for k in ("glass", "windscreen", "windshield")):
        return "70072100"
    if any(k in text for k in ("gasket", "seal", "washer", "o-ring")):
        return "40169320"
    return None
