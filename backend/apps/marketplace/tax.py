"""Authoritative Indian GST rules, HSN classifications, and calculation engine for automotive spare parts.

Based on official CBIC Rate Schedules and Notification No. 1/2017-Central Tax (Rate).
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional, List, Tuple


# Currency quantizer for 2 decimal places (paise/pence)
PAISE = Decimal('0.01')


def quantize_currency(amount: Decimal) -> Decimal:
    """Quantize currency amounts strictly using ROUND_HALF_UP to 2 decimal places."""
    return amount.quantize(PAISE, rounding=ROUND_HALF_UP)


# =============================================================================
# STATUTORY HSN CLASSIFICATION REGISTRY FOR AUTOMOTIVE SPARE PARTS
# =============================================================================

OFFICIAL_AUTOMOTIVE_HSN_REGISTRY: Dict[str, Dict[str, Any]] = {
    "8708": {
        "hsn_code": "8708",
        "description": "Parts and accessories of motor vehicles (brakes, gear boxes, axles, road wheels, suspension shock absorbers, radiators, steering wheels, silencers)",
        "schedule": "Schedule IV",
        "standard_rate": Decimal("28.00"),
        "allowed_rates": (Decimal("28.00"), Decimal("18.00"), Decimal("12.00")),
        "is_verified": True,
        "effective_from": "2017-07-01",
        "legal_reference": "CBIC Notification No. 1/2017-Central Tax (Rate), Schedule IV, Entry 390; Schedule II, Entry 195B (tractor variants).",
        "notes": "Standard 28% for passenger and commercial vehicle components; 12% for specified tractor parts.",
    },
    "8409": {
        "hsn_code": "8409",
        "description": "Parts suitable for use solely or principally with spark-ignition or compression-ignition internal combustion piston engines (pistons, cylinder blocks, valves)",
        "schedule": "Schedule IV",
        "standard_rate": Decimal("28.00"),
        "allowed_rates": (Decimal("28.00"), Decimal("18.00")),
        "is_verified": True,
        "effective_from": "2017-07-01",
        "legal_reference": "CBIC Notification No. 1/2017-Central Tax (Rate), Schedule IV, Entry 318.",
        "notes": "Standard 28% for vehicle engine assemblies and cylinder components.",
    },
    "8507": {
        "hsn_code": "8507",
        "description": "Electric accumulators, including separators; automotive lead-acid storage batteries and lithium-ion batteries",
        "schedule": "Schedule IV / Schedule III",
        "standard_rate": Decimal("28.00"),
        "allowed_rates": (Decimal("28.00"), Decimal("18.00")),
        "is_verified": True,
        "effective_from": "2017-07-01",
        "legal_reference": "CBIC Notification No. 1/2017-Central Tax (Rate), Schedule IV, Entry 377; Schedule III, Entry 378 (Lithium-ion).",
        "notes": "28% applies to lead-acid car batteries (8507 10 00); 18% applies to Lithium-ion batteries (8507 60 00).",
    },
    "8511": {
        "hsn_code": "8511",
        "description": "Electrical ignition or starting equipment (spark plugs, ignition coils, starter motors, generators, alternators)",
        "schedule": "Schedule IV",
        "standard_rate": Decimal("28.00"),
        "allowed_rates": (Decimal("28.00"), Decimal("18.00")),
        "is_verified": True,
        "effective_from": "2017-07-01",
        "legal_reference": "CBIC Notification No. 1/2017-Central Tax (Rate), Schedule IV, Entry 380.",
        "notes": "Standard 28% for motor vehicle spark plugs and ignition distributors.",
    },
    "8512": {
        "hsn_code": "8512",
        "description": "Electrical lighting or signalling equipment, windscreen wipers, defrosters and demisters of a kind used for motor vehicles",
        "schedule": "Schedule IV",
        "standard_rate": Decimal("28.00"),
        "allowed_rates": (Decimal("28.00"), Decimal("18.00")),
        "is_verified": True,
        "effective_from": "2017-07-01",
        "legal_reference": "CBIC Notification No. 1/2017-Central Tax (Rate), Schedule IV, Entry 381.",
        "notes": "Standard 28% for headlights, tail lights, direction indicators, and horn assemblies.",
    },
    "7007": {
        "hsn_code": "7007",
        "description": "Safety glass, consisting of toughened (tempered) or laminated glass (automotive windscreens and rear glass)",
        "schedule": "Schedule IV",
        "standard_rate": Decimal("28.00"),
        "allowed_rates": (Decimal("28.00"),),
        "is_verified": True,
        "effective_from": "2017-07-01",
        "legal_reference": "CBIC Notification No. 1/2017-Central Tax (Rate), Schedule IV, Entry 185.",
        "notes": "Standard 28% for laminated automotive safety glass.",
    },
    "4011": {
        "hsn_code": "4011",
        "description": "New pneumatic tyres of rubber for motor cars, buses, lorries, and agricultural tractors",
        "schedule": "Schedule IV / Schedule III",
        "standard_rate": Decimal("28.00"),
        "allowed_rates": (Decimal("28.00"), Decimal("18.00")),
        "is_verified": True,
        "effective_from": "2017-07-01",
        "legal_reference": "CBIC Notification No. 1/2017-Central Tax (Rate), Schedule IV, Entry 60; Schedule III, Entry 104.",
        "notes": "28% for passenger motor car and truck tyres (4011 10, 4011 20); 18% for tractor tyres (4011 70 00).",
    },
    "8421": {
        "hsn_code": "8421",
        "description": "Filtering or purifying machinery and apparatus for liquids or gases (oil filters, fuel filters, air intake filters for IC engines)",
        "schedule": "Schedule III",
        "standard_rate": Decimal("18.00"),
        "allowed_rates": (Decimal("18.00"),),
        "is_verified": True,
        "effective_from": "2017-07-01",
        "legal_reference": "CBIC Notification No. 1/2017-Central Tax (Rate), Schedule III, Entry 322 (HSN 8421 23 00, 8421 31 00).",
        "notes": "Standard 18% for oil filters, petrol/diesel fuel filters, and intake air filters.",
    },
    "8413": {
        "hsn_code": "8413",
        "description": "Pumps for liquids (fuel pumps, engine lubricating oil pumps, coolant water circulating pumps)",
        "schedule": "Schedule III",
        "standard_rate": Decimal("18.00"),
        "allowed_rates": (Decimal("18.00"), Decimal("12.00")),
        "is_verified": True,
        "effective_from": "2017-07-01",
        "legal_reference": "CBIC Notification No. 1/2017-Central Tax (Rate), Schedule III, Entry 319.",
        "notes": "18% for motor vehicle fuel injection pumps and engine cooling water pumps.",
    },
    "8483": {
        "hsn_code": "8483",
        "description": "Transmission shafts, camshafts, crankshafts, bearing housings, plain shaft bearings, gears and gearing",
        "schedule": "Schedule III",
        "standard_rate": Decimal("18.00"),
        "allowed_rates": (Decimal("18.00"), Decimal("28.00")),
        "is_verified": True,
        "effective_from": "2017-07-01",
        "legal_reference": "CBIC Notification No. 1/2017-Central Tax (Rate), Schedule III, Entry 368.",
        "notes": "18% for generic transmission shafts and plain bearings.",
    },
    "4016": {
        "hsn_code": "4016",
        "description": "Other articles of vulcanised rubber other than hard rubber (gaskets, washers, oil seals, engine mountings, rubber bushings)",
        "schedule": "Schedule III",
        "standard_rate": Decimal("18.00"),
        "allowed_rates": (Decimal("18.00"),),
        "is_verified": True,
        "effective_from": "2017-07-01",
        "legal_reference": "CBIC Notification No. 1/2017-Central Tax (Rate), Schedule III, Entry 111 (HSN 4016 93, 4016 99).",
        "notes": "Standard 18% for rubber weather strips, suspension bushings, and oil seals.",
    },
    "6813": {
        "hsn_code": "6813",
        "description": "Friction material and articles thereof (brake linings and unmounted brake pads based on mineral substances)",
        "schedule": "Schedule III",
        "standard_rate": Decimal("18.00"),
        "allowed_rates": (Decimal("18.00"),),
        "is_verified": True,
        "effective_from": "2017-07-01",
        "legal_reference": "CBIC Notification No. 1/2017-Central Tax (Rate), Schedule III, Entry 181.",
        "notes": "Standard 18% for raw/unmounted friction material and brake linings.",
    },
    "2710": {
        "hsn_code": "2710",
        "description": "Petroleum oils and preparations (lubricating engine oils, brake fluids, hydraulic transmission fluids)",
        "schedule": "Schedule III",
        "standard_rate": Decimal("18.00"),
        "allowed_rates": (Decimal("18.00"),),
        "is_verified": True,
        "effective_from": "2017-07-01",
        "legal_reference": "CBIC Notification No. 1/2017-Central Tax (Rate), Schedule III, Entry 34.",
        "notes": "Standard 18% for motor vehicle engine oils, gear oils, and hydraulic fluids.",
    },
    "8504": {
        "hsn_code": "8504",
        "description": "Electric vehicle powertrain parts, on-board chargers, and power electronics under concessional EV notifications",
        "schedule": "Schedule I",
        "standard_rate": Decimal("5.00"),
        "allowed_rates": (Decimal("5.00"), Decimal("18.00")),
        "is_verified": True,
        "effective_from": "2019-08-01",
        "legal_reference": "CBIC Notification No. 12/2019-Central Tax (Rate) amending Schedule I, Entry 244B.",
        "notes": "Concessional 5% rate for dedicated electric vehicle charging and powertrain components.",
    },
}


def get_official_hsn_entry(hsn_code: Optional[str]) -> Optional[Dict[str, Any]]:
    """Retrieve official HSN classification entry if registered."""
    if not hsn_code:
        return None
    code_clean = str(hsn_code).strip()
    # Try exact match, then 4-digit prefix
    if code_clean in OFFICIAL_AUTOMOTIVE_HSN_REGISTRY:
        return OFFICIAL_AUTOMOTIVE_HSN_REGISTRY[code_clean]
    if len(code_clean) >= 4 and code_clean[:4] in OFFICIAL_AUTOMOTIVE_HSN_REGISTRY:
        return OFFICIAL_AUTOMOTIVE_HSN_REGISTRY[code_clean[:4]]
    return None


def validate_gst_classification(
    hsn_code: Optional[str],
    gst_rate: Optional[Decimal],
) -> Tuple[bool, Optional[str], bool]:
    """Validate submitted HSN code and GST rate against official CBIC rules.

    Returns:
        (is_valid: bool, error_message: Optional[str], is_verified: bool)
    """
    if not hsn_code:
        # HSN code missing: requires verification
        return False, "HSN code is required for tax classification under Indian GST rules.", False

    code_clean = str(hsn_code).strip()
    entry = get_official_hsn_entry(code_clean)

    if not entry:
        # Unrecognized HSN code: Flag for verification rather than rejecting blindly
        # if a valid rate from standard GST slabs (5%, 12%, 18%, 28%) was provided
        standard_slabs = (Decimal("5.00"), Decimal("12.00"), Decimal("18.00"), Decimal("28.00"))
        if gst_rate is not None and Decimal(str(gst_rate)) in standard_slabs:
            return True, None, False  # Validated slab, but unverified HSN code
        return (
            False,
            f"HSN code '{hsn_code}' is not in the recognized automotive rate schedule. "
            f"Please select a verified classification or submit for tax officer verification.",
            False,
        )

    if gst_rate is None:
        return False, f"Applicable GST rate must be specified for HSN {code_clean}.", False

    rate_dec = Decimal(str(gst_rate))
    allowed = entry["allowed_rates"]

    if rate_dec not in allowed:
        allowed_str = ", ".join(f"{r}%" for r in allowed)
        return (
            False,
            f"GST rate {rate_dec}% is not legally applicable for HSN {code_clean} ({entry['description']}). "
            f"Legally supported rate(s) under official CBIC schedules: {allowed_str}.",
            False,
        )

    return True, None, entry["is_verified"]


def calculate_gst_breakdown(
    price: Decimal,
    gst_rate: Optional[Decimal],
    place_of_supply: Optional[str] = None,
    seller_state: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate decimal-exact GST breakdown including CGST/SGST/IGST splits.

    All arithmetic uses Decimal and quantizes to 2 decimal places using ROUND_HALF_UP.
    Guarantees:
        total_price = price_before_gst + gst_amount
        cgst_amount + sgst_amount == gst_amount (in intra-state transactions)
        igst_amount == gst_amount (in inter-state transactions)
    """
    price_before_gst = quantize_currency(Decimal(str(price)))

    if gst_rate is None or Decimal(str(gst_rate)) <= Decimal("0"):
        return {
            "price_before_gst": price_before_gst,
            "gst_rate": Decimal("0.00"),
            "gst_amount": Decimal("0.00"),
            "total_price": price_before_gst,
            "tax_type": "NONE",
            "cgst_rate": Decimal("0.00"),
            "cgst_amount": Decimal("0.00"),
            "sgst_rate": Decimal("0.00"),
            "sgst_amount": Decimal("0.00"),
            "igst_rate": Decimal("0.00"),
            "igst_amount": Decimal("0.00"),
        }

    rate = Decimal(str(gst_rate))
    # Full GST amount before rounding
    raw_gst = price_before_gst * (rate / Decimal("100"))
    gst_amount = quantize_currency(raw_gst)
    total_price = price_before_gst + gst_amount

    # Place of supply determination
    # If both place_of_supply and seller_state are supplied:
    #   intra-state if normalized states match, inter-state if different
    pos_clean = place_of_supply.strip().upper() if place_of_supply else None
    seller_clean = seller_state.strip().upper() if seller_state else None

    if pos_clean and seller_clean:
        is_intra_state = pos_clean == seller_clean
    else:
        # Default to intra-state breakdown with CGST/SGST split display
        is_intra_state = True

    half_rate = rate / Decimal("2")

    if is_intra_state:
        tax_type = "INTRA_STATE"
        # Split GST amount into CGST and SGST down to the exact paise
        cgst_amount = quantize_currency(gst_amount / Decimal("2"))
        sgst_amount = gst_amount - cgst_amount  # Ensures exact balance
        cgst_rate = half_rate
        sgst_rate = half_rate
        igst_rate = Decimal("0.00")
        igst_amount = Decimal("0.00")
    else:
        tax_type = "INTER_STATE"
        cgst_rate = Decimal("0.00")
        cgst_amount = Decimal("0.00")
        sgst_rate = Decimal("0.00")
        sgst_amount = Decimal("0.00")
        igst_rate = rate
        igst_amount = gst_amount

    return {
        "price_before_gst": price_before_gst,
        "gst_rate": rate,
        "gst_amount": gst_amount,
        "total_price": total_price,
        "tax_type": tax_type,
        "cgst_rate": cgst_rate,
        "cgst_amount": cgst_amount,
        "sgst_rate": sgst_rate,
        "sgst_amount": sgst_amount,
        "igst_rate": igst_rate,
        "igst_amount": igst_amount,
    }


def resolve_default_hsn_for_category(
    category_name: Optional[str] = None,
    part_name: str = "",
) -> Tuple[str, Decimal]:
    """Provides authoritative default HSN code and standard GST rate based on part/category taxonomy."""
    text = f"{category_name or ''} {part_name or ''}".lower()
    if any(k in text for k in ("filter", "purif")):
        return "8421", Decimal("18.00")
    if any(k in text for k in ("pump", "fuel pump", "water pump")):
        return "8413", Decimal("18.00")
    if any(k in text for k in ("rubber", "gasket", "seal", "bushing", "mount", "hose", "belt")):
        return "4016", Decimal("18.00")
    if any(k in text for k in ("oil", "fluid", "lubricant", "brake fluid")):
        return "2710", Decimal("18.00")
    if any(k in text for k in ("battery", "batteries", "accumulator")):
        return "8507", Decimal("28.00")
    if any(k in text for k in ("spark plug", "ignition", "starter", "alternator", "generator")):
        return "8511", Decimal("28.00")
    if any(k in text for k in ("light", "lamp", "headlamp", "wiper", "horn")):
        return "8512", Decimal("28.00")
    if any(k in text for k in ("glass", "windscreen", "windshield")):
        return "7007", Decimal("28.00")
    if any(k in text for k in ("tyre", "tire")):
        return "4011", Decimal("28.00")
    if any(k in text for k in ("piston", "cylinder", "valve", "engine part")):
        return "8409", Decimal("28.00")
    if any(k in text for k in ("transmission shaft", "camshaft", "bearing", "gear")):
        return "8483", Decimal("18.00")
    if any(k in text for k in ("ev", "electric vehicle", "charging")):
        return "8504", Decimal("5.00")
    # Standard motor vehicle parts default (brakes, suspension, steering, body, etc.)
    return "8708", Decimal("28.00")


def get_all_hsn_options() -> List[Dict[str, Any]]:
    """Return list of supported HSN classifications and options for frontend and API consumers."""
    options = []
    for code, entry in OFFICIAL_AUTOMOTIVE_HSN_REGISTRY.items():
        options.append({
            "hsn_code": entry["hsn_code"],
            "description": entry["description"],
            "schedule": entry["schedule"],
            "standard_rate": str(entry["standard_rate"]),
            "allowed_rates": [str(r) for r in entry["allowed_rates"]],
            "is_verified": entry["is_verified"],
            "legal_reference": entry["legal_reference"],
            "notes": entry["notes"],
        })
    return sorted(options, key=lambda x: x["hsn_code"])
