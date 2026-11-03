"""Unit tests for DriverXtra Centralized Statutory Tax Engine (platform_core.tax).

Verifies:
- India GST Section 12(2)(a) B2B recipient establishment identification and conflict blocking.
- India GST Section 12(2)(b) B2C address on record priority.
- SAC classifications: Towing (996744), Detailing/Waxing (998714), Inspection (998346),
  Storage (996729 provisional), Hazardous waste (999432 provisional).
- Full 8-digit tariff items and 2025 GST Council rate rationalisation for HSN 8708.
- UK VAT VATA 1994: Standard 20%, Reduced 5% (child car seats), Zero 0% (helmets with PPE mark, manuals),
  and Notice 700 §25.4 Outside Scope (MOT test inspection fee).
- Supplier registration states: NOT_LIABLE_TO_REGISTER -> Bill of Supply / Commercial Invoice;
  SUSPENDED or can_collect_tax=False -> BLOCKED.
- Decimal ROUND_HALF_UP exact paise/pence balancing.
"""

from decimal import Decimal
import pytest

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
)
from platform_core.tax.engine import TaxEngineService
from platform_core.tax.regimes.base import quantize_currency
from platform_core.tax import (
    resolve_workshop_service_sac,
    resolve_uk_vat_classification,
)


class TestIndiaGSTPlaceOfSupply:
    """Verifies place of supply under Section 12 and Section 10 of the IGST Act, 2017."""

    def test_b2c_service_uses_supplier_location_when_no_address_on_record(self):
        """Under Sec 12(2)(b)(ii), fallback is supplier location if no address on record."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='36AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='INR',
            transaction_date='2026-11-03',
            is_b2b=False,
            customer_jurisdiction=None,
            customer_address_on_record=None,
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='LABOUR',
            description='Periodic vehicle engine maintenance',
            taxable_amount=Decimal('1000.00'),
            classification_code='998714',
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.tax_scheme == TaxScheme.GST
        assert res.tax_type == TaxType.INTRA_STATE
        assert res.place_of_supply == 'IN-TG'
        assert "Section 12(2)(b)(ii)" in res.legal_place_of_supply_basis
        assert res.components.cgst_amount == Decimal('90.00')
        assert res.components.sgst_amount == Decimal('90.00')
        assert res.components.igst_amount == Decimal('0.00')
        assert res.total_amount == Decimal('1180.00')

    def test_b2c_service_prioritizes_address_on_record_over_workshop_location(self):
        """Under Sec 12(2)(b)(i), recipient address on record in another state mandates IGST."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='36AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='INR',
            transaction_date='2026-11-03',
            is_b2b=False,
            customer_jurisdiction='IN-MH',
            customer_address_on_record='Bandra West, Mumbai, Maharashtra 400050',
            physical_performance_jurisdiction='IN-TG',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='LABOUR',
            description='Brake pad fitting service',
            taxable_amount=Decimal('1000.00'),
            classification_code='998714',
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.tax_scheme == TaxScheme.GST
        assert res.tax_type == TaxType.INTER_STATE
        assert res.place_of_supply == 'IN-MH'
        assert "Section 12(2)(b)(i)" in res.legal_place_of_supply_basis
        assert res.components.cgst_amount == Decimal('0.00')
        assert res.components.sgst_amount == Decimal('0.00')
        assert res.components.igst_amount == Decimal('180.00')
        assert res.total_amount == Decimal('1180.00')

    def test_b2b_service_in_state_registered_establishment(self):
        """Under Sec 12(2)(a), registered recipient establishment in same state is intra-state."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='36AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='INR',
            transaction_date='2026-11-03',
            is_b2b=True,
            customer_tax_id='36BBBBB1111B1Z2',
            b2b_contracting_jurisdiction='IN-TG',
            b2b_evidence_present=True,
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='LABOUR',
            description='Fleet vehicle overhaul',
            taxable_amount=Decimal('5000.00'),
            classification_code='998714',
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.tax_type == TaxType.INTRA_STATE
        assert res.place_of_supply == 'IN-TG'
        assert res.components.cgst_amount == Decimal('450.00')
        assert res.components.sgst_amount == Decimal('450.00')

    def test_b2b_conflicting_out_of_state_ho_blocks_automated_determination(self):
        """Local physical service + out-of-state GSTIN without PO evidence blocks determination."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='36AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='INR',
            transaction_date='2026-11-03',
            is_b2b=True,
            customer_tax_id='27CCCCC2222C1Z3',  # Maharashtra GSTIN
            b2b_contracting_jurisdiction='IN-MH',
            physical_performance_jurisdiction='IN-TG',
            b2b_evidence_present=False,  # No PO or corporate fleet contract evidence
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='LABOUR',
            description='Local fleet depot servicing',
            taxable_amount=Decimal('2000.00'),
            classification_code='998714',
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.document_type == DocumentType.BLOCKED
        assert res.requires_tax_review is True
        assert "Conflicting recipient establishment" in res.review_reason


class TestIndiaHSNAndSACGovernance:
    """Verifies tariff-level HSN and SAC discrete classifications."""

    def test_hsn_8708_rate_rationalisation_effective_dates(self):
        """HSN 8708 30 00 transitions from 28% to 18% on September 22, 2025."""
        ctx_prior = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='36AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='INR',
            transaction_date='2024-05-10',  # Prior to 2025 GST Council rationalisation
        )
        ctx_current = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='36AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='INR',
            transaction_date='2026-11-03',  # Current date
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='PART',
            description='Front disc brake pads',
            taxable_amount=Decimal('1000.00'),
            classification_code='87083000',
        )

        res_prior = TaxEngineService.calculate_transaction_tax(context=ctx_prior, lines=[line])
        res_current = TaxEngineService.calculate_transaction_tax(context=ctx_current, lines=[line])

        assert res_prior.lines[0].tax_rate == Decimal('28.00')
        assert res_prior.tax_amount == Decimal('280.00')

        assert res_current.lines[0].tax_rate == Decimal('18.00')
        assert res_current.tax_amount == Decimal('180.00')

    def test_sac_996744_confirmed_for_towing_services(self):
        """Vehicle towing is confirmed under SAC 996744."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='36AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='INR',
            transaction_date='2026-11-03',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='TOWING',
            description='Emergency road towing and flatbed recovery',
            taxable_amount=Decimal('2500.00'),
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.lines[0].classification_code == '996744'
        assert res.lines[0].governance_status == ClassificationGovernanceStatus.CONFIRMED
        assert res.document_type == DocumentType.TAX_INVOICE

    def test_sac_998714_confirmed_for_detailing_and_waxing(self):
        """Vehicle cleaning, washing, polishing, and waxing fall under SAC 998714."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='36AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='INR',
            transaction_date='2026-11-03',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='SERVICE',
            description='Automobile exterior washing and polish waxing',
            taxable_amount=Decimal('1500.00'),
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.lines[0].classification_code == '998714'
        assert res.lines[0].governance_status == ClassificationGovernanceStatus.CONFIRMED
        assert res.document_type == DocumentType.TAX_INVOICE

    def test_sac_998714_routine_ceramic_wash_confirmed(self):
        """Routine ceramic wash touch-up is CONFIRMED under SAC 998714."""
        code, status, reason = resolve_workshop_service_sac('SERVICE', 'Routine ceramic wash and wax')
        assert code == '998714'
        assert status == ClassificationGovernanceStatus.CONFIRMED
        assert reason is None

    def test_sac_998714_ceramic_coating_application_provisional(self):
        """Ceramic coating application defaults to PROVISIONAL and blocks production tax invoice."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='36AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='INR',
            transaction_date='2026-11-03',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='SERVICE',
            description='9H Ceramic Coating Application with 3-year warranty',
            taxable_amount=Decimal('25000.00'),
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.lines[0].classification_code == '998714'
        assert res.lines[0].governance_status == ClassificationGovernanceStatus.PROVISIONAL
        assert res.document_type == DocumentType.BLOCKED
        assert res.requires_tax_review is True
        assert 'composite service vs goods supply' in res.review_reason

    def test_sac_998714_graphene_coating_application_provisional(self):
        """Graphene coating treatment defaults to PROVISIONAL and blocks production tax invoice."""
        code, status, reason = resolve_workshop_service_sac('SERVICE', 'Professional Graphene Coating Treatment')
        assert code == '998714'
        assert status == ClassificationGovernanceStatus.PROVISIONAL
        assert 'composite service vs goods supply' in reason

    def test_sac_998714_paint_protection_film_provisional(self):
        """PPF (Paint Protection Film) application defaults to PROVISIONAL."""
        code, status, reason = resolve_workshop_service_sac('SERVICE', 'Full bonnet PPF paint protection film installation')
        assert code == '998714'
        assert status == ClassificationGovernanceStatus.PROVISIONAL
        assert 'composite service vs goods supply' in reason

    def test_sac_provisional_late_collection_blocks_production_invoice(self):
        """Demurrage/late storage charge under 996729 is provisional and blocks automatic tax invoice."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='36AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='INR',
            transaction_date='2026-11-03',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='OTHER',
            description='Uncollected vehicle late collection demurrage fee',
            taxable_amount=Decimal('500.00'),
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.lines[0].governance_status == ClassificationGovernanceStatus.PROVISIONAL
        assert res.document_type == DocumentType.BLOCKED
        assert res.requires_tax_review is True

    def test_unclassified_part_blocks_production_invoice(self):
        """Part lacking an 8-digit tariff item blocks automated tax invoicing."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='36AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='INR',
            transaction_date='2026-11-03',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='PART',
            description='Novel unclassified aftermarket accessory gadget',
            taxable_amount=Decimal('800.00'),
            classification_code='',
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.document_type == DocumentType.BLOCKED
        assert res.requires_tax_review is True
        assert res.lines[0].governance_status == ClassificationGovernanceStatus.UNRESOLVED_LEGAL_QUESTION


class TestSupplierRegistrationAndAuthorizationStates:
    """Verifies the 5 supplier registration states and zero-undercharging guarantee."""

    def test_not_liable_to_register_issues_bill_of_supply_without_tax(self):
        """Supplier below threshold issues Bill of Supply with zero tax charged."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='',
            supplier_registration_state=SupplierRegistrationState.NOT_LIABLE_TO_REGISTER,
            can_collect_tax=False,
            currency='INR',
            transaction_date='2026-11-03',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='LABOUR',
            description='Car brake repair',
            taxable_amount=Decimal('1000.00'),
            classification_code='998714',
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.document_type == DocumentType.BILL_OF_SUPPLY
        assert res.tax_amount == Decimal('0.00')
        assert res.effective_tax_rate == Decimal('0.00')
        assert res.total_amount == Decimal('1000.00')
        assert res.requires_tax_review is False

    def test_suspended_registration_blocks_invoicing(self):
        """Suspended registration prevents invoice issuance."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='36AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.SUSPENDED_OR_CANCELLED,
            can_collect_tax=False,
            currency='INR',
            transaction_date='2026-11-03',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='LABOUR',
            description='Car brake repair',
            taxable_amount=Decimal('1000.00'),
            classification_code='998714',
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.document_type == DocumentType.BLOCKED
        assert res.requires_tax_review is True
        assert "Tax invoicing prohibited" in res.review_reason
        # Underlying statutory tax rate and amount are preserved rather than silently zeroed
        assert res.tax_amount == Decimal('180.00')
        assert res.effective_tax_rate == Decimal('18.00')
        assert res.total_amount == Decimal('1180.00')

    def test_active_registration_without_can_collect_tax_blocks_invoicing(self):
        """Supplier with active registration but can_collect_tax=False is blocked."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='36AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=False,  # Administrative authorization withheld
            currency='INR',
            transaction_date='2026-11-03',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='LABOUR',
            description='Car brake repair',
            taxable_amount=Decimal('1000.00'),
            classification_code='998714',
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.document_type == DocumentType.BLOCKED
        assert res.requires_tax_review is True
        assert "can_collect_tax=False" in res.review_reason
        # Underlying statutory tax rate and amount are preserved rather than silently zeroed
        assert res.tax_amount == Decimal('180.00')
        assert res.effective_tax_rate == Decimal('18.00')
        assert res.total_amount == Decimal('1180.00')


class TestUKVATStatutoryFramework:
    """Verifies UK VAT rules under VATA 1994 and HMRC Notice 700 / 701."""

    def test_uk_standard_rated_workshop_labour_and_parts(self):
        """Standard 20% VAT applies to automotive repair and parts."""
        ctx = TaxTransactionContext(
            country_code='GB',
            supplier_jurisdiction='GB-ENG',
            supplier_tax_id='GB123456789',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='GBP',
            transaction_date='2026-11-03',
        )
        lines = [
            TaxLineInput(line_id='L1', item_type='LABOUR', description='Engine oil service labour', taxable_amount=Decimal('100.00')),
            TaxLineInput(line_id='L2', item_type='PART', description='Oil filter replacement', taxable_amount=Decimal('20.00')),
        ]

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=lines)

        assert res.tax_scheme == TaxScheme.VAT
        assert res.tax_type == TaxType.UK_VAT
        assert res.taxable_amount == Decimal('120.00')
        assert res.tax_amount == Decimal('24.00')
        assert res.total_amount == Decimal('144.00')
        assert res.components.vat_rate == Decimal('20.00')
        assert res.components.vat_amount == Decimal('24.00')

    def test_uk_reduced_rate_child_car_seat(self):
        """Children's car seats qualify for 5% reduced VAT under VATA Sched 7A Group 5."""
        ctx = TaxTransactionContext(
            country_code='GB',
            supplier_jurisdiction='GB-ENG',
            supplier_tax_id='GB123456789',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='GBP',
            transaction_date='2026-11-03',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='PART',
            description='ISOFIX child car seat booster',
            taxable_amount=Decimal('100.00'),
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.lines[0].tax_rate == Decimal('5.00')
        assert res.lines[0].tax_amount == Decimal('5.00')
        assert res.lines[0].statutory_category == TaxCategory.REDUCED

    def test_uk_zero_rated_motorcycle_helmet(self):
        """Qualifying motorcycle helmet is zero-rated under Sched 8 Group 16 & Notice 701/23."""
        ctx = TaxTransactionContext(
            country_code='GB',
            supplier_jurisdiction='GB-ENG',
            supplier_tax_id='GB123456789',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='GBP',
            transaction_date='2026-11-03',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='PART',
            description='Full face motorcycle helmet ECE 22.06',
            taxable_amount=Decimal('200.00'),
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.lines[0].tax_rate == Decimal('0.00')
        assert res.lines[0].tax_amount == Decimal('0.00')
        assert res.lines[0].statutory_category == TaxCategory.ZERO_RATED

    def test_uk_mot_statutory_test_fee_outside_scope_of_vat(self):
        """Statutory DVSA MOT test inspection fee is outside the scope of VAT under Notice 700 §25.4."""
        ctx = TaxTransactionContext(
            country_code='GB',
            supplier_jurisdiction='GB-ENG',
            supplier_tax_id='GB123456789',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='GBP',
            transaction_date='2026-11-03',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='MOT_FEE',
            description='Statutory DVSA MOT test fee',
            taxable_amount=Decimal('54.85'),
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.lines[0].tax_rate == Decimal('0.00')
        assert res.lines[0].tax_amount == Decimal('0.00')
        assert res.lines[0].statutory_category == TaxCategory.OUTSIDE_SCOPE

    def test_uk_stationery_service_logbook_standard_rated(self):
        """Vehicle service history blank logbook is stationery, standard-rated 20%."""
        ctx = TaxTransactionContext(
            country_code='GB',
            supplier_jurisdiction='GB-ENG',
            supplier_tax_id='GB123456789',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='GBP',
            transaction_date='2026-11-03',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='PART',
            description='Blank vehicle service history stamp logbook',
            taxable_amount=Decimal('15.00'),
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.lines[0].tax_rate == Decimal('20.00')
        assert res.lines[0].tax_amount == Decimal('3.00')
        assert res.lines[0].statutory_category == TaxCategory.STANDARD

    def test_uk_qualifying_digital_workshop_manual_zero_rated(self):
        """Qualifying electronic text workshop manual (PDF/e-book) is zero-rated under VATA 1994 Schedule 8 Group 3."""
        rate, category, citation, status, reason = resolve_uk_vat_classification(
            item_type='MANUAL',
            description='BMW 3 Series Workshop Repair Manual (PDF)',
        )
        assert rate == Decimal('0.00')
        assert category == TaxCategory.ZERO_RATED
        assert status == ClassificationGovernanceStatus.CONFIRMED
        assert reason is None

    def test_uk_diagnostic_software_standard_rated(self):
        """Diagnostic software and scanner applications are standard-rated (20%)."""
        rate, category, citation, status, reason = resolve_uk_vat_classification(
            item_type='SOFTWARE',
            description='Professional OBD2 Diagnostic Software Scanner Tool License',
        )
        assert rate == Decimal('20.00')
        assert category == TaxCategory.STANDARD
        assert status == ClassificationGovernanceStatus.CONFIRMED

    def test_uk_completion_oriented_inspection_checklist_standard_rated(self):
        """Completion-oriented inspection forms and checklists are standard-rated (20%)."""
        rate, category, citation, status, reason = resolve_uk_vat_classification(
            item_type='DOCUMENT',
            description='Vehicle 100-Point Inspection Checklist and Worksheet Template',
        )
        assert rate == Decimal('20.00')
        assert category == TaxCategory.STANDARD
        assert status == ClassificationGovernanceStatus.CONFIRMED

    def test_uk_bundled_manual_with_software_provisional(self):
        """Bundled package combining workshop manual and diagnostic software is provisional and blocks invoice."""
        ctx = TaxTransactionContext(
            country_code='GB',
            supplier_jurisdiction='GB-ENG',
            supplier_tax_id='GB123456789',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='GBP',
            transaction_date='2026-11-03',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='BUNDLE',
            description='Workshop Manual and ECU Diagnostic Software Bundle Package',
            taxable_amount=Decimal('80.00'),
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.lines[0].governance_status == ClassificationGovernanceStatus.PROVISIONAL
        assert res.document_type == DocumentType.BLOCKED
        assert res.requires_tax_review is True
        assert 'apportionment review' in res.review_reason


class TestPaiseRoundingAndSnapshotIntegrity:
    """Verifies decimal precision, paise rounding, and immutable snapshot structure."""

    def test_odd_paise_exact_balancing(self):
        """999.95 @ 18% GST splits to exact paise (CGST 90.00 + SGST 89.99 = 179.99)."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='36AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='INR',
            transaction_date='2026-11-03',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='LABOUR',
            description='Engine tuning service',
            taxable_amount=Decimal('999.95'),
            classification_code='998714',
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.tax_amount == Decimal('179.99')
        assert res.components.cgst_amount == Decimal('90.00')
        assert res.components.sgst_amount == Decimal('89.99')
        assert res.components.cgst_amount + res.components.sgst_amount == res.tax_amount
        assert res.total_amount == Decimal('1179.94')

    def test_immutable_snapshot_serialization(self):
        """to_snapshot() produces a complete serializable dictionary."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-TG',
            supplier_tax_id='36AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='INR',
            transaction_date='2026-11-03',
        )
        line = TaxLineInput(
            line_id='L1',
            item_type='LABOUR',
            description='Brake service',
            taxable_amount=Decimal('1000.00'),
            classification_code='998714',
        )

        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])
        snapshot = res.to_snapshot()

        assert isinstance(snapshot, dict)
        assert snapshot['document_type'] == 'TAX_INVOICE'
        assert snapshot['tax_scheme'] == 'GST'
        assert snapshot['tax_type'] == 'INTRA_STATE'
        assert snapshot['place_of_supply'] == 'IN-TG'
        assert snapshot['taxable_amount'] == '1000.00'
        assert snapshot['tax_amount'] == '180.00'
        assert snapshot['total_amount'] == '1180.00'
        assert len(snapshot['lines']) == 1
        assert snapshot['lines'][0]['classification_code'] == '998714'


@pytest.mark.django_db
class TestTaxSnapshotAndModelImmutability:
    """Verifies that saved order, quotation, and change order tax snapshots cannot be modified."""

    def test_marketplace_order_financial_snapshot_is_immutable(self):
        """Modifying total_amount or tax_breakdown on an existing order is rejected."""
        from django.core.exceptions import ValidationError
        from apps.identity.models import User
        from apps.marketplace.models import Order, OrderStatusChoices, PaymentStatusChoices

        buyer = User.objects.create_user(
            email='tax_immutability_buyer@test.com',
            password='Password123!',
        )
        order = Order.objects.create(
            buyer=buyer,
            order_number='DX-ORD-TEST-001',
            status=OrderStatusChoices.PENDING_CONFIRMATION,
            payment_status=PaymentStatusChoices.PENDING,
            currency='INR',
            subtotal_taxable_amount=Decimal('1000.00'),
            cgst_amount=Decimal('90.00'),
            sgst_amount=Decimal('90.00'),
            igst_amount=Decimal('0.00'),
            total_tax_amount=Decimal('180.00'),
            total_amount=Decimal('1180.00'),
            tax_breakdown={'tax_amount': '180.00', 'total_amount': '1180.00'},
        )

        # 1. Tampering with total_amount raises ValidationError
        order.total_amount = Decimal('500.00')
        with pytest.raises(ValidationError) as exc:
            order.save()
        assert "immutable once created" in str(exc.value)

        # Refresh from database
        order.refresh_from_db()

        # 2. Tampering with tax_breakdown raises ValidationError
        order.tax_breakdown = {'tax_amount': '0.00', 'total_amount': '1000.00'}
        with pytest.raises(ValidationError) as exc:
            order.save()
        assert "tax snapshot is immutable" in str(exc.value)

        # Refresh from db
        order.refresh_from_db()

        # 3. Operational status transitions without financial mutation succeed
        order.status = OrderStatusChoices.CONFIRMED
        order.payment_status = PaymentStatusChoices.PAID
        order.save()

        order.refresh_from_db()
        assert order.status == OrderStatusChoices.CONFIRMED
        assert order.payment_status == PaymentStatusChoices.PAID
        assert order.total_amount == Decimal('1180.00')

    def test_accepted_quotation_recalculation_blocked(self):
        """Calling recalculate_totals() on an ACCEPTED quotation is blocked."""
        from django.core.exceptions import ValidationError
        from apps.workshops.models import WorkshopQuotation, QuotationStatusChoices

        quotation = WorkshopQuotation(
            status=QuotationStatusChoices.ACCEPTED,
            quotation_number='QUO-TEST-001',
            subtotal_labour=Decimal('100.00'),
            total_amount=Decimal('120.00'),
        )
        with pytest.raises(ValidationError) as exc:
            quotation.recalculate_totals()
        assert "already been accepted" in str(exc.value)

    def test_approved_change_order_recalculation_blocked(self):
        """Calling recalculate_totals() on an APPROVED change order is blocked."""
        from django.core.exceptions import ValidationError
        from apps.workshops.models import ChangeOrder, ChangeOrderStatusChoices

        co = ChangeOrder(
            status=ChangeOrderStatusChoices.APPROVED,
            change_order_number='CO-TEST-001',
            subtotal_labour=Decimal('50.00'),
            additional_amount=Decimal('60.00'),
        )
        with pytest.raises(ValidationError) as exc:
            co.recalculate_totals()
        assert "terminal status" in str(exc.value)


@pytest.mark.django_db
class TestSupplierRegistrationAndMultiSellerMarketplaceTax:
    """Verifies statutory supplier registration states, authorization enforcement,

    preservation of underlying tax determinations, and multi-seller marketplace calculations.
    """

    def test_india_registered_and_authorized_tax_invoice(self):
        """Active registered supplier authorized to collect tax issues statutory Tax Invoice."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-MH',
            supplier_tax_id='27AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='INR',
            transaction_date='2026-11-03',
            delivery_jurisdiction='IN-MH',
        )
        line = TaxLineInput(
            line_id='item-1',
            item_type='PART',
            description='Brake Rotor',
            taxable_amount=Decimal('1000.00'),
            classification_code='8708',
            candidate_rate=Decimal('18.00'),
        )
        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.document_type == DocumentType.TAX_INVOICE
        assert res.requires_tax_review is False
        assert res.effective_tax_rate == Decimal('18.00')
        assert res.tax_amount == Decimal('180.00')
        assert res.total_amount == Decimal('1180.00')
        assert res.components.cgst_amount == Decimal('90.00')
        assert res.components.sgst_amount == Decimal('90.00')

    def test_india_unregistered_supplier_issues_bill_of_supply(self):
        """Unregistered supplier below threshold issues Bill of Supply with 0% tax under Section 31(3)(c)."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-MH',
            supplier_tax_id=None,
            supplier_registration_state=SupplierRegistrationState.NOT_LIABLE_TO_REGISTER,
            can_collect_tax=False,
            currency='INR',
            transaction_date='2026-11-03',
            delivery_jurisdiction='IN-MH',
        )
        line = TaxLineInput(
            line_id='item-1',
            item_type='PART',
            description='Brake Rotor',
            taxable_amount=Decimal('1000.00'),
            classification_code='8708',
        )
        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.document_type == DocumentType.BILL_OF_SUPPLY
        assert res.requires_tax_review is False
        assert res.tax_amount == Decimal('0.00')
        assert res.effective_tax_rate == Decimal('0.00')
        assert res.total_amount == Decimal('1000.00')
        assert "Section 31(3)(c)" in res.lines[0].legal_citation

    def test_india_unverified_registration_preserves_tax_and_blocks_invoice(self):
        """Unverified registration preserves underlying statutory tax but blocks tax invoice."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-MH',
            supplier_tax_id='INVALID_GSTIN_123',
            supplier_registration_state=SupplierRegistrationState.UNVERIFIED_REGISTRATION,
            can_collect_tax=False,
            currency='INR',
            transaction_date='2026-11-03',
            delivery_jurisdiction='IN-MH',
        )
        line = TaxLineInput(
            line_id='item-1',
            item_type='PART',
            description='Brake Rotor',
            taxable_amount=Decimal('1000.00'),
            classification_code='8708',
            candidate_rate=Decimal('18.00'),
        )
        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.document_type == DocumentType.BLOCKED
        assert res.requires_tax_review is True
        # Statutory 18% tax must be preserved rather than silently zeroed
        assert res.tax_amount == Decimal('180.00')
        assert res.effective_tax_rate == Decimal('18.00')
        assert res.total_amount == Decimal('1180.00')
        assert "UNVERIFIED_REGISTRATION" in res.review_reason

    def test_india_registered_without_authorization_preserves_tax_and_blocks_invoice(self):
        """Registered supplier without administrative authorization has underlying tax preserved and invoice blocked."""
        ctx = TaxTransactionContext(
            country_code='IN',
            supplier_jurisdiction='IN-MH',
            supplier_tax_id='27AAAAA0000A1Z5',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=False,  # Platform authorization withheld
            currency='INR',
            transaction_date='2026-11-03',
            delivery_jurisdiction='IN-MH',
        )
        line = TaxLineInput(
            line_id='item-1',
            item_type='PART',
            description='Brake Rotor',
            taxable_amount=Decimal('1000.00'),
            classification_code='8708',
            candidate_rate=Decimal('18.00'),
        )
        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.document_type == DocumentType.BLOCKED
        assert res.requires_tax_review is True
        assert res.tax_amount == Decimal('180.00')
        assert res.effective_tax_rate == Decimal('18.00')
        assert res.total_amount == Decimal('1180.00')
        assert "can_collect_tax=False" in res.review_reason

    def test_uk_registered_and_authorized_tax_invoice(self):
        """Active registered UK supplier authorized to collect tax issues statutory VAT invoice."""
        ctx = TaxTransactionContext(
            country_code='GB',
            supplier_jurisdiction='GB-ENG',
            supplier_tax_id='GB123456789',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=True,
            currency='GBP',
            transaction_date='2026-11-03',
            delivery_jurisdiction='GB-ENG',
        )
        line = TaxLineInput(
            line_id='item-1',
            item_type='PART',
            description='Alternator',
            taxable_amount=Decimal('100.00'),
        )
        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.document_type == DocumentType.TAX_INVOICE
        assert res.requires_tax_review is False
        assert res.effective_tax_rate == Decimal('20.00')
        assert res.tax_amount == Decimal('20.00')
        assert res.total_amount == Decimal('120.00')
        assert res.components.vat_amount == Decimal('20.00')

    def test_uk_unregistered_supplier_issues_commercial_invoice(self):
        """Unregistered UK supplier below £90k threshold issues Commercial Invoice with 0% VAT under Schedule 1."""
        ctx = TaxTransactionContext(
            country_code='GB',
            supplier_jurisdiction='GB-ENG',
            supplier_tax_id=None,
            supplier_registration_state=SupplierRegistrationState.NOT_LIABLE_TO_REGISTER,
            can_collect_tax=False,
            currency='GBP',
            transaction_date='2026-11-03',
            delivery_jurisdiction='GB-ENG',
        )
        line = TaxLineInput(
            line_id='item-1',
            item_type='PART',
            description='Alternator',
            taxable_amount=Decimal('100.00'),
        )
        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.document_type == DocumentType.COMMERCIAL_INVOICE
        assert res.requires_tax_review is False
        assert res.tax_amount == Decimal('0.00')
        assert res.effective_tax_rate == Decimal('0.00')
        assert res.total_amount == Decimal('100.00')
        assert "Schedule 1" in res.lines[0].legal_citation

    def test_uk_unverified_registration_preserves_vat_and_blocks_invoice(self):
        """Unverified UK VAT registration preserves underlying 20% VAT but blocks VAT invoice."""
        ctx = TaxTransactionContext(
            country_code='GB',
            supplier_jurisdiction='GB-ENG',
            supplier_tax_id='UNVERIFIED_VAT_999',
            supplier_registration_state=SupplierRegistrationState.UNVERIFIED_REGISTRATION,
            can_collect_tax=False,
            currency='GBP',
            transaction_date='2026-11-03',
            delivery_jurisdiction='GB-ENG',
        )
        line = TaxLineInput(
            line_id='item-1',
            item_type='PART',
            description='Alternator',
            taxable_amount=Decimal('100.00'),
        )
        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.document_type == DocumentType.BLOCKED
        assert res.requires_tax_review is True
        # Underlying 20% VAT must be preserved rather than silently zeroed
        assert res.tax_amount == Decimal('20.00')
        assert res.effective_tax_rate == Decimal('20.00')
        assert res.total_amount == Decimal('120.00')
        assert "UNVERIFIED_REGISTRATION" in res.review_reason

    def test_uk_registered_without_authorization_preserves_vat_and_blocks_invoice(self):
        """Registered UK supplier without administrative authorization has underlying VAT preserved and invoice blocked."""
        ctx = TaxTransactionContext(
            country_code='GB',
            supplier_jurisdiction='GB-ENG',
            supplier_tax_id='GB123456789',
            supplier_registration_state=SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION,
            can_collect_tax=False,  # Platform authorization withheld
            currency='GBP',
            transaction_date='2026-11-03',
            delivery_jurisdiction='GB-ENG',
        )
        line = TaxLineInput(
            line_id='item-1',
            item_type='PART',
            description='Alternator',
            taxable_amount=Decimal('100.00'),
        )
        res = TaxEngineService.calculate_transaction_tax(context=ctx, lines=[line])

        assert res.document_type == DocumentType.BLOCKED
        assert res.requires_tax_review is True
        assert res.tax_amount == Decimal('20.00')
        assert res.effective_tax_rate == Decimal('20.00')
        assert res.total_amount == Decimal('120.00')
        assert "can_collect_tax=False" in res.review_reason

    def test_supplier_resolver_from_workshop_profile(self):
        """Resolver correctly derives state and collection authorization from WorkshopProfile."""
        from platform_core.tax.supplier_resolver import resolve_marketplace_supplier_tax_context
        from apps.organisations.models import Organisation
        from apps.workshops.models import WorkshopProfile

        org = Organisation.objects.create(name="Authorized Workshop Org", type="WORKSHOP", country="IN", jurisdiction="IN-TG")
        profile = WorkshopProfile.objects.create(
            organisation=org,
            is_tax_registered=True,
            can_collect_tax=True,
            default_tax_rate_percent=Decimal('18.00'),
        )

        class MockListing:
            seller = None
            organisation = org
            is_tax_verified = True
            gst_rate = Decimal('18.00')

        ctx = resolve_marketplace_supplier_tax_context(MockListing(), country_code="IN")
        assert ctx.supplier_registration_state == SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION
        assert ctx.can_collect_tax is True
        assert ctx.supplier_jurisdiction == "IN-TG"

        # Now test unauthorized workshop
        profile.can_collect_tax = False
        profile.save()
        ctx_unauth = resolve_marketplace_supplier_tax_context(MockListing(), country_code="IN")
        assert ctx_unauth.supplier_registration_state == SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION
        assert ctx_unauth.can_collect_tax is False

        # Now test unregistered workshop
        profile.is_tax_registered = False
        profile.can_collect_tax = False
        profile.save()
        ctx_unreg = resolve_marketplace_supplier_tax_context(MockListing(), country_code="IN")
        assert ctx_unreg.supplier_registration_state == SupplierRegistrationState.NOT_LIABLE_TO_REGISTER
        assert ctx_unreg.can_collect_tax is False

    def test_supplier_resolver_from_seller_application(self):
        """Resolver correctly evaluates SellerApplication status, tax ID format, and authorization."""
        from platform_core.tax.supplier_resolver import resolve_marketplace_supplier_tax_context
        from apps.identity.models import User
        from apps.onboarding.models import SellerApplication, SellerApplicationStatusChoices

        user = User.objects.create_user(email="applicant@example.com")
        app = SellerApplication.objects.create(
            user=user,
            business_name="Valid Tax Business",
            status=SellerApplicationStatusChoices.APPROVED,
            tax_id="27AAAAA0000A1Z5",  # Valid GSTIN
            country="India",
            jurisdiction="IN-MH",
        )

        class MockListing:
            seller = user
            organisation = None
            is_tax_verified = True
            gst_rate = Decimal('18.00')

        # 1. Syntactically valid tax ID entered on application, but government verification not completed:
        # Format validation confirms structure only and is NEVER treated as government registration verification.
        ctx = resolve_marketplace_supplier_tax_context(MockListing(), country_code="IN")
        assert ctx.supplier_registration_state == SupplierRegistrationState.UNVERIFIED_REGISTRATION
        assert ctx.can_collect_tax is False

        # 2. With explicit staff verification and administrative authorization:
        user.is_tax_registered = True
        user.can_collect_tax = True
        ctx_auth = resolve_marketplace_supplier_tax_context(MockListing(), country_code="IN")
        assert ctx_auth.can_collect_tax is True
        assert ctx_auth.supplier_registration_state == SupplierRegistrationState.ACTIVE_MANDATORY_REGISTRATION

        # 3. Voluntary registration:
        user.is_voluntarily_registered = True
        ctx_vol = resolve_marketplace_supplier_tax_context(MockListing(), country_code="IN")
        assert ctx_vol.supplier_registration_state == SupplierRegistrationState.VOLUNTARILY_REGISTERED
        assert ctx_vol.can_collect_tax is True

        # 4. Inactive or suspended accounts:
        user.is_active = False
        ctx_susp = resolve_marketplace_supplier_tax_context(MockListing(), country_code="IN")
        assert ctx_susp.supplier_registration_state == SupplierRegistrationState.SUSPENDED_OR_CANCELLED
        assert ctx_susp.can_collect_tax is False
        user.is_active = True
        user.is_voluntarily_registered = False

        # 5. Invalid tax ID format produces UNVERIFIED_REGISTRATION:
        app.tax_id = "INVALID_GST"
        app.save()
        user.can_collect_tax = False
        user.is_tax_registered = False
        ctx_invalid = resolve_marketplace_supplier_tax_context(MockListing(), country_code="IN")
        assert ctx_invalid.supplier_registration_state == SupplierRegistrationState.UNVERIFIED_REGISTRATION
        assert ctx_invalid.can_collect_tax is False

    def test_multi_seller_marketplace_order_calculation_parity_and_snapshot(self):
        """Multi-seller marketplace order maintains line-level seller tax attribution and calculation parity."""
        from apps.identity.models import User
        from apps.catalogue.models import PartCategory
        from apps.marketplace.models import SparePartListing, ListingStatusChoices, Order
        from apps.marketplace.pricing import calculate_item_tax_breakdown
        from rest_framework.test import APIClient
        from rest_framework import status

        from apps.organisations.models import Organisation
        from apps.workshops.models import WorkshopProfile

        cat = PartCategory.objects.create(name="Multi Seller Test Cat", slug="multi-seller-test-cat")
        seller1 = User.objects.create_user(email="seller1@example.com")
        seller2 = User.objects.create_user(email="seller2@example.com")
        buyer = User.objects.create_user(email="buyer_multi@example.com")

        # Seller 1: Registered & Authorized Workshop Merchant (18% GST)
        org1 = Organisation.objects.create(name="Seller 1 Org", type="WORKSHOP", country="IN", jurisdiction="IN-MH")
        WorkshopProfile.objects.create(
            organisation=org1,
            is_tax_registered=True,
            can_collect_tax=True,
            default_tax_rate_percent=Decimal("18.00"),
        )
        part1 = SparePartListing.objects.create(
            seller=seller1,
            organisation=org1,
            name="Seller 1 Part (Authorized)",
            brand="BrandA",
            mpn="MPN-1",
            category=cat,
            price=Decimal("1000.00"),
            currency="INR",
            hsn_code="8708",
            gst_rate=Decimal("18.00"),
            status=ListingStatusChoices.APPROVED,
            is_active=True,
            stock_quantity=10,
        )

        # Seller 2: Unregistered below threshold (0% GST)
        part2 = SparePartListing.objects.create(
            seller=seller2,
            name="Seller 2 Part (Unregistered)",
            brand="BrandB",
            mpn="MPN-2",
            category=cat,
            price=Decimal("500.00"),
            currency="INR",
            hsn_code="8708",
            gst_rate=Decimal("0.00"),
            status=ListingStatusChoices.APPROVED,
            is_active=True,
            stock_quantity=10,
        )

        client = APIClient()
        client.force_authenticate(user=buyer)

        # 1. Preview calculation (/orders/calculate/)
        calc_payload = {
            "items": [
                {"listing_id": str(part1.id), "quantity": 1},
                {"listing_id": str(part2.id), "quantity": 1},
            ],
            "shipping_country": "India",
            "place_of_supply": "MH",
            "currency": "INR",
        }
        res_calc = client.post("/api/v1/marketplace/orders/calculate/", calc_payload, format="json")
        assert res_calc.status_code == status.HTTP_200_OK
        data_calc = res_calc.data

        # Subtotal: 1000 + 500 = 1500.00
        # Tax: Part1 18% of 1000 = 180.00, Part2 0% of 500 = 0.00 => Total tax = 180.00
        # Grand total: 1680.00
        assert Decimal(data_calc["subtotal_taxable_amount"]) == Decimal("1500.00")
        assert Decimal(data_calc["total_tax_amount"]) == Decimal("180.00")
        assert Decimal(data_calc["total_amount"]) == Decimal("1680.00")
        assert data_calc["tax_breakdown"]["is_multi_seller"] is True

        # Check line breakdowns in snapshot
        lines = data_calc["tax_breakdown"]["lines"]
        assert len(lines) == 2
        assert lines[0]["tax_amount"] == "180.00"
        assert lines[0]["can_collect_tax"] is True
        assert lines[1]["tax_amount"] == "0.00"
        assert lines[1]["can_collect_tax"] is False

        # 2. Checkout execution (/orders/checkout/)
        checkout_payload = {
            "items": [
                {"listing_id": str(part1.id), "quantity": 1},
                {"listing_id": str(part2.id), "quantity": 1},
            ],
            "shipping_name": "Test Multi Buyer",
            "shipping_phone": "+919876543210",
            "shipping_address_line1": "456 Market Road",
            "shipping_city": "Mumbai",
            "shipping_state": "MH",
            "shipping_postal_code": "400001",
            "shipping_country": "India",
            "currency": "INR",
            "payment_method": "ONLINE",
            "expected_total_amount": "1680.00",
            "idempotency_key": "multi-seller-test-key-1",
        }
        res_checkout = client.post("/api/v1/marketplace/orders/checkout/", checkout_payload, format="json")
        assert res_checkout.status_code == status.HTTP_201_CREATED
        order_dict = res_checkout.data["order"]

        # Calculation parity between preview and persisted checkout
        assert Decimal(order_dict["subtotal_taxable_amount"]) == Decimal(data_calc["subtotal_taxable_amount"])
        assert Decimal(order_dict["total_tax_amount"]) == Decimal(data_calc["total_tax_amount"])
        assert Decimal(order_dict["total_amount"]) == Decimal(data_calc["total_amount"])

        # Persisted order in DB
        order = Order.objects.get(id=order_dict["id"])
        assert order.tax_breakdown["is_multi_seller"] is True
        assert order.tax_breakdown["tax_amount"] == "180.00"
        assert order.items.count() == 2

        item1 = order.items.get(listing=part1)
        assert item1.tax_amount == Decimal("180.00")
        assert item1.total_amount == Decimal("1180.00")

        item2 = order.items.get(listing=part2)
        assert item2.tax_amount == Decimal("0.00")
        assert item2.total_amount == Decimal("500.00")

