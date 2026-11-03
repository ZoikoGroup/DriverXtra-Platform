"""Statutory United Kingdom VAT calculation regime engine.

Implements:
- Value Added Tax Act 1994 (VATA 1994), Section 2(1) Standard Rate (20%).
- Section 29A & Schedule 7A Group 5 Reduced Rate (5% for child car seats).
- Section 30 & Schedule 8 Group 16 (Motorcycle helmets under PPE Reg 8(2)) and Group 3 (Books/manuals).
- HMRC VAT Notice 700 Section 25.4 (Statutory MOT test fee outside the scope of VAT and disbursements).
- Single unified VAT line item.
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
from platform_core.tax.registry.uk_vat_schedules import (
    UK_VAT_STANDARD_RATE,
    resolve_uk_vat_classification,
)
from .base import BaseTaxRegime, quantize_currency


class UKVATRegime(BaseTaxRegime):
    """Calculates United Kingdom Value Added Tax (VAT) compliant with VATA 1994 and HMRC rules."""

    def calculate_tax(
        self,
        context: TaxTransactionContext,
        lines: List[TaxLineInput],
        discount_amount: Decimal = Decimal('0.00'),
    ) -> TaxCalculationResult:
        """Calculates statutory UK VAT result and snapshot."""
        supplier_state = context.supplier_registration_state
        can_collect = context.can_collect_tax
        pos = context.supplier_jurisdiction or "GB-ENG"
        currency = context.currency or "GBP"

        requires_review = False
        review_reasons: List[str] = []

        # 1. Determine Document Type and Invoicing Authorization
        document_type = DocumentType.TAX_INVOICE

        if supplier_state == SupplierRegistrationState.NOT_LIABLE_TO_REGISTER:
            # Below UK VAT registration threshold (£90,000): Non-VAT commercial invoice
            document_type = DocumentType.COMMERCIAL_INVOICE
        elif supplier_state in (SupplierRegistrationState.SUSPENDED_OR_CANCELLED, SupplierRegistrationState.UNVERIFIED_REGISTRATION):
            document_type = DocumentType.BLOCKED
            requires_review = True
            review_reasons.append(f"Supplier VAT registration status is '{supplier_state.value}'. VAT invoicing prohibited.")
        elif not can_collect:
            document_type = DocumentType.BLOCKED
            requires_review = True
            review_reasons.append("Supplier is not authorized to collect VAT (can_collect_tax=False).")

        # 2. Calculate Line Items
        calculated_lines: List[TaxLineResult] = []
        total_taxable = Decimal('0.00')
        total_vat = Decimal('0.00')

        gross_taxable = sum((l.taxable_amount for l in lines), Decimal('0.00'))
        net_taxable_pool = max(Decimal('0.00'), gross_taxable - discount_amount)
        discount_ratio = (net_taxable_pool / gross_taxable) if gross_taxable > Decimal('0.00') else Decimal('1.00')

        for line in lines:
            adj_taxable = quantize_currency(line.taxable_amount * discount_ratio)
            total_taxable += adj_taxable

            # Classify line item under VATA 1994 & Notice 700 / 701
            rate, category, citation, status, reason = resolve_uk_vat_classification(
                item_type=line.item_type,
                description=line.description,
            )

            if status != ClassificationGovernanceStatus.CONFIRMED:
                requires_review = True
                if reason:
                    review_reasons.append(reason)

            # Non-VAT document types (Commercial Invoice for unregistered / Blocked)
            if document_type == DocumentType.COMMERCIAL_INVOICE:
                category = TaxCategory.UNREGISTERED
                rate = Decimal('0.00')
                citation = "VATA 1994 Schedule 1 - Commercial invoice issued by business operating below VAT registration threshold"
            elif document_type == DocumentType.BLOCKED:
                status = ClassificationGovernanceStatus.PROVISIONAL
                citation = f"BLOCKED - Invoicing withheld pending compliance resolution; underlying statutory rate {rate}% preserved"

            line_vat = quantize_currency(adj_taxable * (rate / Decimal('100.00')))
            total_vat += line_vat

            components = TaxComponentBreakdown(
                cgst_rate=Decimal('0.00'),
                cgst_amount=Decimal('0.00'),
                sgst_rate=Decimal('0.00'),
                sgst_amount=Decimal('0.00'),
                igst_rate=Decimal('0.00'),
                igst_amount=Decimal('0.00'),
                vat_rate=rate,
                vat_amount=line_vat,
            )

            calculated_lines.append(
                TaxLineResult(
                    line_id=line.line_id,
                    item_type=line.item_type,
                    description=line.description,
                    classification_code="UK-VAT-" + category.value,
                    governance_status=status,
                    statutory_category=category,
                    legal_citation=citation,
                    taxable_amount=adj_taxable,
                    tax_rate=rate,
                    tax_amount=line_vat,
                    total_amount=adj_taxable + line_vat,
                    components=components,
                )
            )

        from dataclasses import replace

        # Rate-band balancing to ensure sum of line VATs equals statutory band VAT exactly
        by_rate: Dict[Decimal, List[TaxLineResult]] = {}
        for cl in calculated_lines:
            by_rate.setdefault(cl.tax_rate, []).append(cl)

        for band_rate, band_lines in by_rate.items():
            if band_rate > Decimal('0.00'):
                band_taxable = sum((bl.taxable_amount for bl in band_lines), Decimal('0.00'))
                expected_band_vat = quantize_currency(band_taxable * (band_rate / Decimal('100.00')))
                actual_band_vat = sum((bl.tax_amount for bl in band_lines), Decimal('0.00'))
                diff = expected_band_vat - actual_band_vat
                if diff != Decimal('0.00') and band_lines:
                    largest = max(band_lines, key=lambda x: x.taxable_amount)
                    idx = calculated_lines.index(largest)
                    new_vat = largest.tax_amount + diff
                    new_comp = replace(largest.components, vat_amount=new_vat)
                    updated = replace(
                        largest,
                        tax_amount=new_vat,
                        total_amount=largest.taxable_amount + new_vat,
                        components=new_comp,
                    )
                    calculated_lines[idx] = updated
                    total_vat += diff

        # 3. Synthesize Transaction Totals
        total_amount = total_taxable + total_vat
        effective_rate = (
            quantize_currency((total_vat / total_taxable) * Decimal('100.00'))
            if total_taxable > Decimal('0.00')
            else Decimal('0.00')
        )

        overall_components = TaxComponentBreakdown(
            cgst_rate=Decimal('0.00'),
            cgst_amount=Decimal('0.00'),
            sgst_rate=Decimal('0.00'),
            sgst_amount=Decimal('0.00'),
            igst_rate=Decimal('0.00'),
            igst_amount=Decimal('0.00'),
            vat_rate=effective_rate,
            vat_amount=total_vat,
        )

        tax_type = TaxType.UK_VAT if document_type != DocumentType.BLOCKED else TaxType.BLOCKED

        return TaxCalculationResult(
            document_type=document_type,
            tax_scheme=TaxScheme.VAT,
            tax_type=tax_type,
            place_of_supply=pos,
            legal_place_of_supply_basis="VATA 1994 Section 2(1) - Single national UK VAT jurisdiction",
            supplier_jurisdiction=context.supplier_jurisdiction,
            supplier_registration_state=supplier_state,
            can_collect_tax=can_collect,
            currency=currency,
            taxable_amount=total_taxable,
            effective_tax_rate=effective_rate,
            tax_amount=total_vat,
            total_amount=total_amount,
            requires_tax_review=requires_review,
            review_reason="; ".join(review_reasons) if review_reasons else "",
            components=overall_components,
            lines=calculated_lines,
        )
