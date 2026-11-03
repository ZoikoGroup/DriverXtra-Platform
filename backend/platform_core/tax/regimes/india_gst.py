"""Statutory India GST calculation regime engine.

Implements:
- Section 12(2)(a) B2B place of supply with recipient establishment evidence rules.
- Section 12(2)(b) B2C place of supply prioritizing address on record over supplier location.
- Section 10(1) goods place of supply for marketplace and workshop counter delivery.
- Exact paise rounding with ROUND_HALF_UP and balancing guarantee (CGST + SGST == GST).
"""

from decimal import Decimal
from typing import List, Tuple, Dict, Any, Optional
from platform_core.tax.choices import (
    TaxScheme,
    TaxType,
    TaxCategory,
    DocumentType,
    SupplierRegistrationState,
    ClassificationGovernanceStatus,
)
from platform_core.tax.models_data import (
    TaxTransactionContext,
    TaxLineInput,
    TaxComponentBreakdown,
    TaxLineResult,
    TaxCalculationResult,
)
from platform_core.tax.registry.india_hsn import (
    get_tariff_entry_for_date,
    normalize_code,
    resolve_automotive_part_hsn,
)
from platform_core.tax.registry.india_sac import (
    get_sac_entry,
    resolve_workshop_service_sac,
)
from .base import BaseTaxRegime, quantize_currency


class IndiaGSTRegime(BaseTaxRegime):
    """Calculates Indian Goods and Services Tax (GST) compliant with statutory CBIC rules."""

    def _determine_place_of_supply(
        self,
        context: TaxTransactionContext,
        is_goods_supply: bool = False,
    ) -> Tuple[str, str, TaxType, bool, str]:
        """Resolves statutory place of supply, legal basis, and tax type.

        Returns:
            (place_of_supply, legal_basis, tax_type, requires_tax_review, review_reason)
        """
        supplier_jur = (context.supplier_jurisdiction or "IN-TG").strip().upper()

        # 1. Supply of Goods (Section 10 of IGST Act)
        if is_goods_supply:
            # If shipment involves movement to delivery jurisdiction
            if context.delivery_jurisdiction:
                delivery_jur = context.delivery_jurisdiction.strip().upper()
                pos = delivery_jur
                basis = "IGST Act Section 10(1)(a) - Location where movement terminates for delivery"
                def _norm_code(c: str) -> str:
                    clean = (c or "").strip().upper()
                    return clean[3:] if clean.startswith("IN-") else clean
                tax_type = TaxType.INTRA_STATE if _norm_code(pos) == _norm_code(supplier_jur) else TaxType.INTER_STATE
                return pos, basis, tax_type, False, ""
            else:
                # No movement (counter delivery / fitted in workshop)
                pos = supplier_jur
                basis = "IGST Act Section 10(1)(c) - Location of goods at delivery without movement"
                return pos, basis, TaxType.INTRA_STATE, False, ""

        # 2. Supply of Services (Section 12 of IGST Act)
        # Case A: B2B Supply (Section 12(2)(a))
        if context.is_b2b:
            # Extract contracting jurisdiction
            contracting_jur = (
                context.b2b_contracting_jurisdiction
                or context.customer_jurisdiction
                or (context.customer_tax_id[:2] if context.customer_tax_id and len(context.customer_tax_id) >= 2 else None)
            )
            if contracting_jur:
                contracting_jur = contracting_jur.strip().upper()
                # Normalize 2-digit state code if passed (e.g. '36' -> 'IN-TG')
                from platform_core.regional.subdivisions import get_subdivision_by_gst_state_code
                sub = get_subdivision_by_gst_state_code(contracting_jur)
                if sub:
                    contracting_jur = sub.code

            if not contracting_jur:
                # B2B claimed without contracting establishment data
                return (
                    supplier_jur,
                    "IGST Act Sec 12(2)(a) [UNRESOLVED - Missing Recipient Establishment]",
                    TaxType.BLOCKED,
                    True,
                    "B2B service claimed but statutory recipient establishment is missing. Requires tax review.",
                )

            # Check distinct person conflict: vehicle operated locally, out-of-state GSTIN claimed without evidence
            if contracting_jur != supplier_jur:
                perf_jur = (context.physical_performance_jurisdiction or supplier_jur).strip().upper()
                if perf_jur == supplier_jur and not context.b2b_evidence_present:
                    return (
                        contracting_jur,
                        "IGST Act Sec 12(2)(a) / CGST Sec 25(4) [CONFLICT - Local Service vs Out-of-State GSTIN]",
                        TaxType.BLOCKED,
                        True,
                        "Conflicting recipient establishment: physical service received in supplier state; out-of-state GSTIN claimed without supporting purchase order or contracting agreement.",
                    )

                # Valid inter-state B2B supply
                return (
                    contracting_jur,
                    "IGST Act Section 12(2)(a) - Location of registered recipient establishment",
                    TaxType.INTER_STATE,
                    False,
                    "",
                )
            else:
                # Intra-state B2B
                return (
                    supplier_jur,
                    "IGST Act Section 12(2)(a) - Location of registered recipient establishment",
                    TaxType.INTRA_STATE,
                    False,
                    "",
                )

        # Case B: B2C Supply (Section 12(2)(b))
        # Primary statutory rule: Address on record (Section 12(2)(b)(i))
        if context.customer_address_on_record or context.customer_jurisdiction:
            cust_jur = (context.customer_jurisdiction or "").strip().upper()
            if cust_jur:
                pos = cust_jur
                basis = "IGST Act Section 12(2)(b)(i) - Recipient address on record with supplier"
                tax_type = TaxType.INTRA_STATE if pos == supplier_jur else TaxType.INTER_STATE
                return pos, basis, tax_type, False, ""

        # Fallback statutory rule: Supplier location (Section 12(2)(b)(ii))
        pos = supplier_jur
        basis = "IGST Act Section 12(2)(b)(ii) - Location of supplier (no recipient address on record)"
        return pos, basis, TaxType.INTRA_STATE, False, ""

    def calculate_tax(
        self,
        context: TaxTransactionContext,
        lines: List[TaxLineInput],
        discount_amount: Decimal = Decimal('0.00'),
    ) -> TaxCalculationResult:
        """Calculates statutory India GST calculation result and snapshot."""
        supplier_state = context.supplier_registration_state
        can_collect = context.can_collect_tax
        currency = context.currency or "INR"

        # 1. Determine if this is primarily goods (marketplace) or services (workshop)
        has_services = any(line.item_type.upper() in ("LABOUR", "SERVICE", "TOWING", "DIAGNOSTIC") for line in lines)
        pos, pos_basis, tax_type, pos_review_req, pos_review_reason = self._determine_place_of_supply(
            context=context,
            is_goods_supply=not has_services,
        )

        requires_review = pos_review_req
        review_reasons = [pos_review_reason] if pos_review_reason else []

        # 2. Check Supplier Registration and Invoicing Status
        document_type = DocumentType.TAX_INVOICE

        if tax_type == TaxType.BLOCKED:
            document_type = DocumentType.BLOCKED
            requires_review = True
        elif supplier_state == SupplierRegistrationState.NOT_LIABLE_TO_REGISTER:
            # Below threshold: Issues non-tax Bill of Supply under Section 31(3)(c)
            document_type = DocumentType.BILL_OF_SUPPLY
        elif supplier_state in (SupplierRegistrationState.SUSPENDED_OR_CANCELLED, SupplierRegistrationState.UNVERIFIED_REGISTRATION):
            # Prohibited from issuing tax invoice
            document_type = DocumentType.BLOCKED
            requires_review = True
            review_reasons.append(f"Supplier registration status is '{supplier_state.value}'. Tax invoicing prohibited.")
        elif not can_collect:
            # Registration active but platform tax collection authorization withheld
            document_type = DocumentType.BLOCKED
            requires_review = True
            review_reasons.append("Supplier is not authorized to collect tax (can_collect_tax=False).")

        # 3. Calculate Line Items
        calculated_lines: List[TaxLineResult] = []
        total_taxable = Decimal('0.00')
        total_tax = Decimal('0.00')
        total_cgst = Decimal('0.00')
        total_sgst = Decimal('0.00')
        total_igst = Decimal('0.00')

        # Compute line discount proportion if header discount exists
        gross_taxable = sum((l.taxable_amount for l in lines), Decimal('0.00'))
        net_taxable_pool = max(Decimal('0.00'), gross_taxable - discount_amount)
        discount_ratio = (net_taxable_pool / gross_taxable) if gross_taxable > Decimal('0.00') else Decimal('1.00')

        for line in lines:
            adj_taxable = quantize_currency(line.taxable_amount * discount_ratio)
            total_taxable += adj_taxable

            line_type = (line.item_type or "").upper().strip()
            rate = Decimal('0.00')
            citation = ""
            code = ""
            status = ClassificationGovernanceStatus.CONFIRMED

            # Non-taxable document type (Bill of Supply issued by unregistered supplier)
            if document_type == DocumentType.BILL_OF_SUPPLY:
                category = TaxCategory.UNREGISTERED
                rate = Decimal('0.00')
                citation = "CGST Act 2017 Section 31(3)(c) - Bill of supply issued by unregistered supplier"
                code = line.classification_code or "UNREGISTERED"
            else:
                # Registered Tax Invoice or Blocked Invoicing (underlying statutory rate preserved)
                if line_type in ("PART", "GOODS"):
                    # Resolve HSN
                    hsn_clean = normalize_code(line.classification_code)
                    entry = get_tariff_entry_for_date(hsn_clean, context.transaction_date) if hsn_clean else None
                    if not entry:
                        resolved_hsn = resolve_automotive_part_hsn(line.description)
                        if resolved_hsn:
                            entry = get_tariff_entry_for_date(resolved_hsn, context.transaction_date)
                    if entry:
                        rate = entry["rate"]
                        citation = entry["legal_citation"]
                        code = entry["tariff_item"]
                        status = entry["governance_status"]
                        if line.candidate_rate is not None:
                            if line.candidate_rate == Decimal("0.00"):
                                rate = Decimal("0.00")
                            else:
                                from platform_core.tax.registry.india_hsn import validate_tariff_classification
                                is_valid, _err, _stat = validate_tariff_classification(code, line.candidate_rate, context.transaction_date)
                                if is_valid:
                                    rate = line.candidate_rate
                    else:
                        requires_review = True
                        status = ClassificationGovernanceStatus.UNRESOLVED_LEGAL_QUESTION
                        code = line.classification_code or "CLASSIFICATION_REQUIRED"
                        review_reasons.append(f"Line '{line.description}' lacks statutory HSN tariff classification.")
                        citation = "UNRESOLVED - Statutory tariff classification required"
                else:
                    # Resolve SAC
                    sac_code, sac_status, sac_reason = resolve_workshop_service_sac(line_type, line.description)
                    if line.classification_code:
                        sac_code = normalize_code(line.classification_code)
                    sac_entry = get_sac_entry(sac_code)
                    if sac_entry:
                        rate = sac_entry["rate"]
                        citation = sac_entry["legal_citation"]
                        code = sac_entry["sac_code"]
                        status = sac_status
                        if not sac_entry.get("is_production_invoicing_permitted", True) or sac_status != ClassificationGovernanceStatus.CONFIRMED:
                            requires_review = True
                            if sac_reason:
                                review_reasons.append(sac_reason)
                    else:
                        requires_review = True
                        status = ClassificationGovernanceStatus.UNRESOLVED_LEGAL_QUESTION
                        code = sac_code or "SAC_REQUIRED"
                        review_reasons.append(f"Line '{line.description}' lacks confirmed SAC classification.")
                        citation = "UNRESOLVED - Statutory SAC classification required"

                category = TaxCategory.STANDARD

                if document_type == DocumentType.BLOCKED:
                    status = ClassificationGovernanceStatus.PROVISIONAL
                    citation = f"BLOCKED - Invoicing withheld pending compliance resolution; underlying statutory rate {rate}% preserved"

            # Calculate line tax amount and exact paise split
            line_tax = quantize_currency(adj_taxable * (rate / Decimal('100.00')))
            line_cgst = Decimal('0.00')
            line_sgst = Decimal('0.00')
            line_igst = Decimal('0.00')

            if tax_type == TaxType.INTRA_STATE:
                # Split down to the exact paise with balance guarantee
                line_cgst = quantize_currency(line_tax / Decimal('2.00'))
                line_sgst = line_tax - line_cgst
                cgst_rate = rate / Decimal('2.00')
                sgst_rate = rate / Decimal('2.00')
                igst_rate = Decimal('0.00')
            elif tax_type == TaxType.INTER_STATE:
                line_igst = line_tax
                cgst_rate = Decimal('0.00')
                sgst_rate = Decimal('0.00')
                igst_rate = rate
            else:
                # TaxType.BLOCKED: retain underlying tax under IGST component pending POS resolution
                line_igst = line_tax
                cgst_rate = Decimal('0.00')
                sgst_rate = Decimal('0.00')
                igst_rate = rate

            total_tax += line_tax
            total_cgst += line_cgst
            total_sgst += line_sgst
            total_igst += line_igst

            components = TaxComponentBreakdown(
                cgst_rate=cgst_rate,
                cgst_amount=line_cgst,
                sgst_rate=sgst_rate,
                sgst_amount=line_sgst,
                igst_rate=igst_rate,
                igst_amount=line_igst,
                vat_rate=Decimal('0.00'),
                vat_amount=Decimal('0.00'),
            )

            calculated_lines.append(
                TaxLineResult(
                    line_id=line.line_id,
                    item_type=line.item_type,
                    description=line.description,
                    classification_code=code,
                    governance_status=status,
                    statutory_category=category,
                    legal_citation=citation,
                    taxable_amount=adj_taxable,
                    tax_rate=rate,
                    tax_amount=line_tax,
                    total_amount=adj_taxable + line_tax,
                    components=components,
                )
            )

        from dataclasses import replace

        # Rate-band balancing to resolve rounding discrepancies on multi-line discounted totals
        by_rate: Dict[Decimal, List[TaxLineResult]] = {}
        for cl in calculated_lines:
            by_rate.setdefault(cl.tax_rate, []).append(cl)

        for band_rate, band_lines in by_rate.items():
            if band_rate > Decimal('0.00'):
                band_taxable = sum((bl.taxable_amount for bl in band_lines), Decimal('0.00'))
                expected_band_tax = quantize_currency(band_taxable * (band_rate / Decimal('100.00')))
                actual_band_tax = sum((bl.tax_amount for bl in band_lines), Decimal('0.00'))
                diff = expected_band_tax - actual_band_tax
                if diff != Decimal('0.00') and band_lines:
                    largest = max(band_lines, key=lambda x: x.taxable_amount)
                    idx = calculated_lines.index(largest)
                    new_tax = largest.tax_amount + diff
                    total_tax += diff
                    if tax_type == TaxType.INTRA_STATE:
                        new_cgst = quantize_currency(new_tax / Decimal('2.00'))
                        new_sgst = new_tax - new_cgst
                        total_cgst += (new_cgst - largest.components.cgst_amount)
                        total_sgst += (new_sgst - largest.components.sgst_amount)
                        new_comp = replace(largest.components, cgst_amount=new_cgst, sgst_amount=new_sgst)
                    else:
                        total_igst += diff
                        new_comp = replace(largest.components, igst_amount=new_tax)
                    updated = replace(
                        largest,
                        tax_amount=new_tax,
                        total_amount=largest.taxable_amount + new_tax,
                        components=new_comp,
                    )
                    calculated_lines[idx] = updated

        # 4. Synthesize Transaction Totals
        total_amount = total_taxable + total_tax
        effective_rate = (
            quantize_currency((total_tax / total_taxable) * Decimal('100.00'))
            if total_taxable > Decimal('0.00')
            else Decimal('0.00')
        )

        overall_components = TaxComponentBreakdown(
            cgst_rate=effective_rate / Decimal('2.00') if tax_type == TaxType.INTRA_STATE else Decimal('0.00'),
            cgst_amount=total_cgst,
            sgst_rate=effective_rate / Decimal('2.00') if tax_type == TaxType.INTRA_STATE else Decimal('0.00'),
            sgst_amount=total_sgst,
            igst_rate=effective_rate if tax_type in (TaxType.INTER_STATE, TaxType.BLOCKED) else Decimal('0.00'),
            igst_amount=total_igst,
            vat_rate=Decimal('0.00'),
            vat_amount=Decimal('0.00'),
        )

        return TaxCalculationResult(
            document_type=document_type,
            tax_scheme=TaxScheme.GST,
            tax_type=tax_type,
            place_of_supply=pos,
            legal_place_of_supply_basis=pos_basis,
            supplier_jurisdiction=context.supplier_jurisdiction,
            supplier_registration_state=supplier_state,
            can_collect_tax=can_collect,
            currency=currency,
            taxable_amount=total_taxable,
            effective_tax_rate=effective_rate,
            tax_amount=total_tax,
            total_amount=total_amount,
            requires_tax_review=requires_review,
            review_reason="; ".join(review_reasons) if review_reasons else "",
            components=overall_components,
            lines=calculated_lines,
        )
