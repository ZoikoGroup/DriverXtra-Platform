"""Fitment evaluation engine for marketplace spare part listings.

Bridges seller inventory claims with canonical PartCompatibility engineering records.
"""

from typing import Iterable, List, Dict, Any, Optional
from apps.catalogue.models import (
    Part,
    VehicleVariant,
    PartCompatibility,
    FitmentTypeChoices,
)

FITMENT_STATUS_VERIFIED = "VERIFIED"
FITMENT_STATUS_CONDITIONAL = "CONDITIONAL"
FITMENT_STATUS_CONFLICT = "CONFLICT"
FITMENT_STATUS_SELLER_CLAIMED = "SELLER_CLAIMED"
FITMENT_STATUS_UNKNOWN = "UNKNOWN"

FITMENT_SOURCE_CATALOGUE = "CATALOGUE"
FITMENT_SOURCE_SELLER = "SELLER"
FITMENT_SOURCE_NONE = "NONE"


def evaluate_listing_single_variant(listing: Any, variant: VehicleVariant) -> Dict[str, Any]:
    """Evaluate fitment for a single listing against a single vehicle variant."""
    results = evaluate_listing_fitment(listing, [variant])
    if results:
        res = results[0]
        return {
            "status": res["status"],
            "qualifications": res["qualifications"],
            "source": res["source"],
        }
    return {
        "status": FITMENT_STATUS_UNKNOWN,
        "qualifications": "No confirmed compatibility record found for this part and vehicle variant.",
        "source": FITMENT_SOURCE_NONE,
    }


def evaluate_listing_fitment(listing: Any, variants: Iterable[VehicleVariant]) -> List[Dict[str, Any]]:
    """Evaluate compatibility for a spare part listing against an iterable of vehicle variants.

    Batches all PartCompatibility lookups in a single database query.
    """
    if variants is None:
        return []

    # Materialize variants to a list
    if hasattr(variants, 'all') and callable(getattr(variants, 'all')):
        variant_list = list(variants.all())
    elif isinstance(variants, (list, tuple, set)):
        variant_list = list(variants)
    else:
        variant_list = list(variants)

    if not variant_list:
        return []

    # Ensure variant instances are loaded with display metadata
    variant_ids = []
    normalized_variants = []
    for v in variant_list:
        if isinstance(v, VehicleVariant):
            variant_ids.append(v.id)
            normalized_variants.append(v)
        else:
            variant_ids.append(v)

    if len(normalized_variants) != len(variant_ids):
        # Some items were passed as IDs; load full instances
        loaded = {
            v.id: v
            for v in VehicleVariant.objects.filter(id__in=variant_ids).select_related('model', 'model__make')
        }
        normalized_variants = [loaded.get(v_id) for v_id in variant_ids if loaded.get(v_id)]

    # Determine seller-claimed variant IDs
    claimed_variant_ids = set()
    if hasattr(listing, '_claimed_variant_ids'):
        claimed_variant_ids = set(listing._claimed_variant_ids)
    elif hasattr(listing, 'compatible_variants'):
        # If prefetched, hits in-memory cache
        claimed_variant_ids = {v.id for v in listing.compatible_variants.all()}

    # Batch PartCompatibility lookup in exactly 1 query
    catalogue_part = getattr(listing, 'catalogue_part', None)
    catalogue_part_id = getattr(listing, 'catalogue_part_id', None)
    if catalogue_part_id is None and catalogue_part is not None:
        catalogue_part_id = catalogue_part.id

    compatibilities: Dict[Any, PartCompatibility] = {}
    if catalogue_part_id:
        compat_qs = PartCompatibility.objects.filter(
            part_id=catalogue_part_id,
            vehicle_variant_id__in=variant_ids,
        )
        for c in compat_qs:
            compatibilities[c.vehicle_variant_id] = c

    # Evaluate each variant
    results = []
    for variant in normalized_variants:
        v_id = variant.id
        display_name = getattr(variant, 'display_name', str(variant))
        is_claimed = v_id in claimed_variant_ids
        compat = compatibilities.get(v_id)

        if compat:
            if compat.fitment_type == FitmentTypeChoices.CONFIRMED_FIT:
                status = FITMENT_STATUS_VERIFIED
                qualifications = (
                    compat.qualifications
                    or compat.notes
                    or "Confirmed fit verified against vehicle engineering database."
                )
                source = FITMENT_SOURCE_CATALOGUE
            elif compat.fitment_type == FitmentTypeChoices.CONDITIONAL_FIT:
                status = FITMENT_STATUS_CONDITIONAL
                qualifications = (
                    compat.qualifications
                    or compat.notes
                    or "Compatibility record verified in canonical database."
                )
                source = FITMENT_SOURCE_CATALOGUE
            elif compat.fitment_type == FitmentTypeChoices.DOES_NOT_FIT:
                status = FITMENT_STATUS_CONFLICT
                qualifications = (
                    compat.qualifications
                    or compat.notes
                    or "Component does not fit this vehicle variant according to catalogue database."
                )
                source = FITMENT_SOURCE_CATALOGUE
            else:
                # UNKNOWN record in catalogue
                if is_claimed:
                    status = FITMENT_STATUS_SELLER_CLAIMED
                    qualifications = (
                        getattr(listing, 'compatibility_notes', '')
                        or "Seller-declared compatibility (unverified by catalogue)."
                    )
                    source = FITMENT_SOURCE_SELLER
                else:
                    status = FITMENT_STATUS_UNKNOWN
                    qualifications = (
                        compat.qualifications
                        or compat.notes
                        or "No confirmed compatibility record found for this part and vehicle variant."
                    )
                    source = FITMENT_SOURCE_NONE
        else:
            # No PartCompatibility row
            if catalogue_part and getattr(catalogue_part, 'is_universal', False):
                status = FITMENT_STATUS_CONDITIONAL
                qualifications = (
                    "Component is self-declared universal by supplier, but vehicle-specific "
                    "clearance and capacity are not independently verified. Check handbook before fitting."
                )
                source = FITMENT_SOURCE_CATALOGUE
            else:
                if is_claimed:
                    status = FITMENT_STATUS_SELLER_CLAIMED
                    qualifications = (
                        getattr(listing, 'compatibility_notes', '')
                        or "Seller-declared compatibility (unverified by catalogue)."
                    )
                    source = FITMENT_SOURCE_SELLER
                else:
                    status = FITMENT_STATUS_UNKNOWN
                    qualifications = (
                        "No confirmed compatibility record found for this part and vehicle variant. "
                        "Consult vehicle handbook or workshop specialist."
                    )
                    source = FITMENT_SOURCE_NONE

        results.append({
            "variant_id": str(v_id),
            "display_name": display_name,
            "status": status,
            "qualifications": qualifications,
            "source": source,
        })

    return results


def batch_evaluate_listings_fitment(listings: Iterable[Any], variant: VehicleVariant) -> Dict[Any, Dict[str, Any]]:
    """Batch evaluate fitment for multiple listings against a single vehicle variant in 1 query.

    Prevents N+1 database queries on public browse list views.
    """
    listings_list = list(listings)
    if not listings_list or not variant:
        return {}

    # Collect all catalogue_part_ids across listings
    catalogue_part_ids = {
        l.catalogue_part_id for l in listings_list if getattr(l, 'catalogue_part_id', None)
    }

    compatibilities: Dict[Any, PartCompatibility] = {}
    if catalogue_part_ids:
        compat_qs = PartCompatibility.objects.filter(
            part_id__in=catalogue_part_ids,
            vehicle_variant=variant,
        )
        for c in compat_qs:
            compatibilities[c.part_id] = c

    v_id = variant.id
    results = {}

    for listing in listings_list:
        # Check seller claim (in-memory if prefetched)
        is_claimed = False
        if hasattr(listing, '_claimed_variant_ids'):
            is_claimed = v_id in listing._claimed_variant_ids
        elif hasattr(listing, 'compatible_variants'):
            is_claimed = any(cv.id == v_id for cv in listing.compatible_variants.all())

        cat_part_id = getattr(listing, 'catalogue_part_id', None)
        cat_part = getattr(listing, 'catalogue_part', None)
        compat = compatibilities.get(cat_part_id) if cat_part_id else None

        if compat:
            if compat.fitment_type == FitmentTypeChoices.CONFIRMED_FIT:
                status = FITMENT_STATUS_VERIFIED
                qualifications = (
                    compat.qualifications
                    or compat.notes
                    or "Confirmed fit verified against vehicle engineering database."
                )
                source = FITMENT_SOURCE_CATALOGUE
            elif compat.fitment_type == FitmentTypeChoices.CONDITIONAL_FIT:
                status = FITMENT_STATUS_CONDITIONAL
                qualifications = (
                    compat.qualifications
                    or compat.notes
                    or "Compatibility record verified in canonical database."
                )
                source = FITMENT_SOURCE_CATALOGUE
            elif compat.fitment_type == FitmentTypeChoices.DOES_NOT_FIT:
                status = FITMENT_STATUS_CONFLICT
                qualifications = (
                    compat.qualifications
                    or compat.notes
                    or "Component does not fit this vehicle variant according to catalogue database."
                )
                source = FITMENT_SOURCE_CATALOGUE
            else:
                if is_claimed:
                    status = FITMENT_STATUS_SELLER_CLAIMED
                    qualifications = (
                        getattr(listing, 'compatibility_notes', '')
                        or "Seller-declared compatibility (unverified by catalogue)."
                    )
                    source = FITMENT_SOURCE_SELLER
                else:
                    status = FITMENT_STATUS_UNKNOWN
                    qualifications = (
                        compat.qualifications
                        or compat.notes
                        or "No confirmed compatibility record found for this part and vehicle variant."
                    )
                    source = FITMENT_SOURCE_NONE
        else:
            if cat_part and getattr(cat_part, 'is_universal', False):
                status = FITMENT_STATUS_CONDITIONAL
                qualifications = (
                    "Component is self-declared universal by supplier, but vehicle-specific "
                    "clearance and capacity are not independently verified. Check handbook before fitting."
                )
                source = FITMENT_SOURCE_CATALOGUE
            else:
                if is_claimed:
                    status = FITMENT_STATUS_SELLER_CLAIMED
                    qualifications = (
                        getattr(listing, 'compatibility_notes', '')
                        or "Seller-declared compatibility (unverified by catalogue)."
                    )
                    source = FITMENT_SOURCE_SELLER
                else:
                    status = FITMENT_STATUS_UNKNOWN
                    qualifications = (
                        "No confirmed compatibility record found for this part and vehicle variant. "
                        "Consult vehicle handbook or workshop specialist."
                    )
                    source = FITMENT_SOURCE_NONE

        results[listing.id] = {
            "status": status,
            "qualifications": qualifications,
            "source": source,
        }

    return results


def get_conflicting_variants(catalogue_part: Optional[Part], variants: Iterable[VehicleVariant]) -> List[Dict[str, Any]]:
    """Return any variants in the given collection that conflict (DOES_NOT_FIT) with the catalogue part."""
    if not catalogue_part or not variants:
        return []

    if hasattr(variants, 'all') and callable(getattr(variants, 'all')):
        variant_list = list(variants.all())
    else:
        variant_list = list(variants)

    if not variant_list:
        return []

    variant_ids = [v.id if isinstance(v, VehicleVariant) else v for v in variant_list]
    conflicts = PartCompatibility.objects.filter(
        part=catalogue_part,
        vehicle_variant_id__in=variant_ids,
        fitment_type=FitmentTypeChoices.DOES_NOT_FIT,
    ).select_related('vehicle_variant', 'vehicle_variant__model', 'vehicle_variant__model__make')

    results = []
    for c in conflicts:
        display = c.vehicle_variant.display_name if c.vehicle_variant else str(c.vehicle_variant_id)
        results.append({
            "variant_id": str(c.vehicle_variant_id),
            "display_name": display,
            "qualifications": (
                c.qualifications
                or c.notes
                or "Component declared DOES_NOT_FIT in canonical catalogue."
            ),
        })
    return results
