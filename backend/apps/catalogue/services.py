"""Shared fitment evaluation service for canonical catalogue parts and vehicle variants."""

from apps.catalogue.models import (
    Part,
    VehicleVariant,
    PartCompatibility,
    FitmentTypeChoices,
)


def evaluate_canonical_fitment(part: Part, variant: VehicleVariant) -> dict:
    """Evaluate compatibility between a canonical Part and a VehicleVariant.

    Preserves 100% exact parity with the existing FitmentEvaluationView response schema.
    """
    # 1. Check for verified engineering compatibility record
    compatibility = PartCompatibility.objects.filter(
        part=part,
        vehicle_variant=variant,
    ).first()

    if compatibility:
        is_compatible = compatibility.fitment_type in (
            FitmentTypeChoices.CONFIRMED_FIT,
            FitmentTypeChoices.CONDITIONAL_FIT,
        )
        confidence = "HIGH" if compatibility.fitment_type == FitmentTypeChoices.CONFIRMED_FIT else "MEDIUM"
        evidence_level = "VERIFIED_MAPPING"
        reason = (
            compatibility.qualifications
            or compatibility.notes
            or "Confirmed fit verified against vehicle engineering database."
        )
        return {
            "outcome": compatibility.fitment_type,
            "status": compatibility.fitment_type,
            "fitment_type": compatibility.fitment_type,
            "is_compatible": is_compatible,
            "confidence": confidence,
            "evidence_level": evidence_level,
            "reason": reason,
            "qualifications": compatibility.qualifications or compatibility.notes or "Compatibility record verified in canonical database.",
            "part_id": str(part.id),
            "part_name": part.name,
            "part_mpn": part.mpn,
            "part_brand": part.brand,
            "vehicle_variant_id": str(variant.id),
            "vehicle_display": variant.display_name,
        }

    # 2. Universal Part Handling:
    # Universal parts must not automatically receive CONFIRMED_FIT with HIGH confidence
    # solely because they are marked universal by a source. Return CONDITIONAL_FIT with unverified declaration.
    if part.is_universal:
        return {
            "outcome": FitmentTypeChoices.CONDITIONAL_FIT,
            "status": FitmentTypeChoices.CONDITIONAL_FIT,
            "fitment_type": FitmentTypeChoices.CONDITIONAL_FIT,
            "is_compatible": True,
            "confidence": "LOW",
            "evidence_level": "UNVERIFIED_UNIVERSAL_DECLARATION",
            "reason": "Component is self-declared universal by supplier, but vehicle-specific clearance and capacity are not independently verified. Check handbook before fitting.",
            "qualifications": "Universal component declaration; independent vehicle clearance and specification check required.",
            "part_id": str(part.id),
            "part_name": part.name,
            "part_mpn": part.mpn,
            "part_brand": part.brand,
            "vehicle_variant_id": str(variant.id),
            "vehicle_display": variant.display_name,
        }

    # 3. Missing record: strict rule to never assume or guarantee compatibility
    return {
        "outcome": FitmentTypeChoices.UNKNOWN,
        "status": FitmentTypeChoices.UNKNOWN,
        "fitment_type": FitmentTypeChoices.UNKNOWN,
        "is_compatible": False,
        "confidence": "NONE",
        "evidence_level": "NO_EVIDENCE",
        "reason": "No confirmed compatibility record found for this part and vehicle variant. Consult vehicle handbook or workshop specialist.",
        "qualifications": "No verified compatibility record found for this part and vehicle variant combination. Consult vehicle handbook or workshop specialist.",
        "part_id": str(part.id),
        "part_name": part.name,
        "part_mpn": part.mpn,
        "part_brand": part.brand,
        "vehicle_variant_id": str(variant.id),
        "vehicle_display": variant.display_name,
    }
