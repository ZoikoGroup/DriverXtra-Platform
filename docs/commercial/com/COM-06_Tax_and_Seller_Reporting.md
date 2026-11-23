# Doc COM-06 — Tax and Seller Reporting

| Field | Value |
|---|---|
| Document ID | DX-COMM-COM-06 (proposed; map to canonical engineering register per M§25) |
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Parent | DX-COMM-MASTER-001 v1.0 (23 Oct 2026); v1.1 PROPOSED revision |
| Status | DRAFT — not approved. No content is a live tariff, executed contract, legal/tax opinion or regulatory permission. |
| Proposed owner | Global Tax — controlled owner of "Marketplace tax/deemed-supplier, seller reporting and invoice issuance" [M App D]; gate owner for "P0: Tax/deemed supplier exposure" [M§23] |
| Required approvers | Global Tax + CFO (D09) [M§25]; GC/Compliance for role/tax/permissions sign-off [M§00]; legal/tax approves roles/territory [M§07 Approval] |
| Related decisions | D09 tax/settlement — BLOCKED (needs D01, D02, D04); D01 first market — OPEN; D02 legal transaction roles — BLOCKED (needs D01); D04 payment PSP — BLOCKED (needs D01, D02). Master §25 lists all four as OPEN; statuses above are set by the document owner. |
| Related tests | test COM-001, test COM-003, test COM-007, test COM-016 [M§24] |

ID-namespace note: "Doc COM-0X" = deliverable; "revenue code COM-0X" = M§04 stream; "test COM-0XX" = M§24 acceptance test.

> **Decision update (19 November 2026, rev. B).** Confirmed direction from Lennox Zoiko: contracting company **Zoiko Mobility Inc.**; initial target markets **USA and UK** (no pilot city or corridor chosen); preferred payment provider **Stripe** (Stripe Connect capabilities, merchant onboarding, settlement and payouts per country still to be verified); finance and insurance handled as a **separate workstream owned by Rithika** (stays OFF here). These are recorded as CONFIRMED DIRECTION, not formal legal or regulatory approvals. Where this document's header or text gives older statuses for D01, D02, D04, D07 or D09, the current register in [../02_Commercial_Decision_Register.md](../02_Commercial_Decision_Register.md) prevails.

## 1. Purpose and scope

This document collects the tax, invoice and seller-reporting requirements the master assigns to Global Tax, so that a qualified tax adviser can determine them per country/corridor. It is the "COM-06 Tax / Seller Reporting" deliverable listed in M§25. It contains **no tax conclusions**: every item is a requirement for Global Tax / a qualified adviser to determine [M§11: "Apply country-specific professional advice"; M App E: "legal analysis requires qualified local counsel"].

In scope: indirect-tax marketplace facilitator/deemed-supplier exposure; tax on SaaS, advertising, services and digital supplies; cross-border B2B reverse charge; invoice format/e-invoicing; withholding; platform reporting rules; transfer pricing between Zoiko entities [M§11]; trader traceability and seller reporting regimes cited in M§09 and M App E; invoice issuance controls [M§07]; the "Tax rule missing" control vector [M App A].

Out of scope: revenue-recognition policy (Doc COM-04), PSP funds flow (Doc COM-05), country role mapping (Doc COM-02) — referenced only where tax depends on them [M§25].

## 2. Requirements carried from the master

| Req ID | Requirement | Source |
|---|---|---|
| TAX-R01 | Country/corridor activation bundle includes country-specific entity authority, tax nexus and marketplace deemed-supplier classification. | [M§09] |
| TAX-R02 | Activation bundle includes seller verification / trader traceability. | [M§09] |
| TAX-R03 | EU DSA Article 30 sets trader-traceability duties for relevant online marketplaces; applicability to DriverXtra is for counsel to determine. | [M§09], [M App E] |
| TAX-R04 | DAC7 and UK digital-platform rules can create seller reporting obligations independently of subscription contracts; applicability is for Global Tax to determine. | [M§09], [M App E] |
| TAX-R05 | Tax scope covers: marketplace facilitator/deemed supplier exposure; tax on SaaS, advertising, services and digital supplies; cross-border B2B reverse charges; invoice format/e-invoicing; withholding; reporting platform rules; transfer pricing between Zoiko entities. | [M§11] |
| TAX-R06 | Never calculate all tax from a single "seller country" field. | [M§11] |
| TAX-R07 | Invoices: local tax invoice/legal identity and issuer; sequential numbers by authorized legal issuer; e-invoicing only where validated. | [M§07 Invoices] |
| TAX-R08 | Invoice/credit minimum finance fields: number/series, entity, tax registration, service period, FX, due date, line-level tax and linked adjustment. | [M§11] |
| TAX-R09 | Commercial contract record carries tax flags; order/quote carries local tax evidence. | [M§11] |
| TAX-R10 | Quote formation calculates taxes as separate lines; full payable total including taxes shown before acceptance. | [M§07] |
| TAX-R11 | Refunds retain original tax/rate/FX evidence and apply to the original financial obligation. | [M§07 Refunds] |
| TAX-R12 | "Tax rule missing": a buyer country supported by the UI but lacking a tax and role schedule may display discovery as appropriate but must block binding transaction/checkout and record the policy reason. | [M App A] |
| TAX-R13 | Independent tax decision on indirect tax, invoices, exemptions and reporting (P0 risk). | [M§23] |
| TAX-R14 | Every launch SKU requires regression-tested tax controls and a jurisdiction/version-scoped signed schedule. | [M§00 Change policy] |
| TAX-R15 | `commercial_sku` carries `tax_class`; `party_role_snapshot` carries `tax_party` and `issuer`; `invoice_credit` carries issuer, counterparty, tax, invoice number, links to earning event. | [M§21] |
| TAX-R16 | `tax_determination_id`: external/local tax engine evidence and maker/collector role. | [M App C] |
| TAX-R17 | Tax engines are integrations, not a mandate to reinvent regulated/commodity capabilities. | [M§20] |
| TAX-R18 | Finance Admin console includes tax determinations; Supplier console includes tax docs; sensitive payout/tax data is permission- and purpose-scoped. | [M§15] |
| TAX-R19 | Finance-control KPI includes tax exception backlog and invoice-error rate. | [M§19] |
| TAX-R20 | Localized price books require Finance/Tax sign-off. | [M§06] |
| TAX-R21 | Accounting codes and GL mapping are illustrative; financial controller must align with Zoiko Mobility Inc.'s actual GL. | [M App B] |

## 3. Specification draft

### 3.1 Determination register (all items: "for Global Tax / qualified adviser to determine")

One register row per activated country/corridor × vertical × role profile [M§07 Rate scope; M§09]. No row is pre-filled.

| Determination item | What must be determined (no conclusion given here) | Source |
|---|---|---|
| Tax nexus and entity authority | Which Zoiko entity contracts and is registered, per country | [M§09], [M§11] |
| Deemed-supplier / marketplace facilitator | Whether the platform is treated as supplier/collector for third-party sales, per role profile (facilitated order, disclosed agent, etc.) | [M§09], [M§11], [M§23] |
| Platform's own supplies | Tax treatment of SaaS, advertising, services and digital supplies sold by DriverXtra | [M§11] |
| Cross-border B2B | Reverse-charge applicability and evidence | [M§11] |
| Withholding | Whether withholding applies to any flow | [M§11] |
| Invoice issuer and format | Legal issuer, numbering series, invoice/self-bill format, e-invoicing validation | [M§07 Invoices], [M§08 A: "invoice or self-bill as lawful"] |
| Seller reporting | Whether DAC7, UK HMRC digital-platform reporting or any other platform rule applies; data to collect and verify; filing owner | [M§09], [M App E] |
| Trader traceability | Whether EU DSA Art. 30 applies; trader data to collect | [M§09], [M App E] |
| Transfer pricing | Intercompany arrangement between Zoiko entities | [M§11] |
| Regulated introductions | GATED; no tax determination requested until D06 changes (revenue codes REG-01, REG-02; FIN-01; revenue code COM-04 also GATED) | [M§04], [M§25 D06] |

### 3.2 Seller-reporting and traceability data requirements (structure only)

The master names the regimes but not their data fields. This document therefore defines only the *containers*; field lists come from Global Tax/counsel.

| Container | Required content | Source / status |
|---|---|---|
| Seller identity evidence | Individuals vs traders, KYB/KYC where needed, beneficial ownership, bank confirmation, licensing, re-verification cadence | [M§16 Seller verification] |
| Regime applicability record | Per country: regime name, applicability decision, adviser reference, effective date | Open input (Global Tax) |
| Reportable-seller dataset | Fields required by each applicable regime | Open input (Global Tax); [M App E] DAC7 / HMRC sources |
| Reporting run evidence | Period, entity, submission reference | Open input (Global Tax) |

### 3.3 Invoice and credit controls

| Control | Requirement | Source |
|---|---|---|
| Issuer | Authorized legal issuer per role profile; recorded in `party_role_snapshot.issuer` | [M§07], [M§21] |
| Numbering | Sequential by authorized legal issuer | [M§07] |
| Fields | number/series, entity, tax registration, service period, FX, due date, line-level tax, linked adjustment | [M§11] |
| Linkage | `invoice_credit` links to `earning_event`, originals and adjustment | [M§21] |
| Credits/refunds | Original tax/rate/FX evidence retained; reverse against the original obligation | [M§07], [M App A Partial return] |
| E-invoicing | Only where validated | [M§07] |
| Event | `invoice.issued` | [M§21] |

### 3.4 "Tax rule missing" control (M App A)

1. Discovery may display where appropriate [M App A].
2. Binding quote/checkout is blocked when no tax and role schedule exists for the buyer country [M App A].
3. The block records a policy reason [M App A]; `country_activation_version` has no default permissive state [M App C].
4. Tax determination evidence (`tax_determination_id`) is stored on the quote snapshot [M App C], [M§20 immutable snapshots].

## 4. Engineering reconciliation notes

| Topic | Note (flagged, not resolved) | Source |
|---|---|---|
| Ownership — country rules | CTX-17 Global Policy owns "country rules"; country rules live in versioned jurisdiction packs, no country forks. | [E 2.4], [E 2.2] |
| Ownership — invoicing/tax service | Master domain "Billing & Tax" (invoices, credits, local tax service integration) has no direct CTX in E 2.4. CTX-07 Payments and Ledger is adjacent. CTO decision required. | [M§20], [E 2.4] |
| Ownership — trader traceability | CTX-09 Trust and Verification owns verification; seller-reporting extraction has no named owner. | [E 2.4] |
| Tax as external provider | Engineering lists tax among external providers via adapters, consistent with M§20. | [E 2.3], [M§20] |
| Corporate identity | Engineering doc states "Zoiko Tech Inc."; master is authoritative: Zoiko Mobility Inc. Logged inconsistency. | [E 1.1], [M§00] |
| Money precision | Master requires integer minor units, zero-/three-decimal safe. Repo tax engine quantizes Decimal to 0.01 (adequate for INR/GBP only). Flag for engineering review before any further currency. | [M§07 Currency], [Repo: backend/platform_core/tax/regimes/base.py] |

## 5. Implementation evidence (repo)

Implementation evidence only. **None of it is a D09 sign-off, a D01 market decision, or a tax opinion.**

| Finding | Path |
|---|---|
| Tax engine facade `TaxEngineService` routes `IN` → India GST regime and `GB` → UK VAT regime; any other country raises `TaxEngineError`. | [Repo: backend/platform_core/tax/engine.py] |
| Engine downgrades a TAX_INVOICE to `BLOCKED` when any line classification is PROVISIONAL or UNRESOLVED_LEGAL_QUESTION. | [Repo: backend/platform_core/tax/engine.py] |
| Enums: `DocumentType` (TAX_INVOICE, BILL_OF_SUPPLY, COMMERCIAL_INVOICE, DISBURSEMENT_NOTE, BLOCKED); `SupplierRegistrationState` (5 states); `ClassificationGovernanceStatus`. | [Repo: backend/platform_core/tax/choices.py] |
| Registries: India HSN, India SAC, UK VAT schedules. Code embeds statutory rates and legal citations; this document does not adopt them — they require Global Tax validation. | [Repo: backend/platform_core/tax/registry/] |
| Supplier resolver: tax-ID format check is explicitly not treated as registration verification; seller onboarding approval is not treated as tax registration. When jurisdiction is blank it falls back to `GB-ENG` / `IN-MH`, while `regional/specs.py` default for IN is `IN-TG` — inconsistency flagged for engineering/Global Tax review against TAX-R06. | [Repo: backend/platform_core/tax/supplier_resolver.py], [Repo: backend/platform_core/regional/specs.py] |
| Tax engine is called by marketplace pricing and workshop quotation/change-order calculations (seller-side supplies). | [Repo: backend/apps/marketplace/pricing.py], [Repo: backend/apps/workshops/models.py] |
| Regional module: country codes IN, GB; currencies INR, GBP; GST/VAT config interfaces with candidate rates. | [Repo: backend/platform_core/regional/choices.py], [Repo: backend/platform_core/regional/tax_interface.py] |
| Commercial R1: `CommercialSku.tax_class`; `CountryGate.tax_schedule_reference` required to enable a gate (`TAX_SCHEDULE_MISSING`); `QuoteSnapshot.tax_determination_reference`; `PartyRoleProfile.tax_party` (SELLER, PLATFORM, BUYER_REVERSE_CHARGE, DEEMED_SUPPLIER_PLATFORM) and `invoice_issuer` (SELLER, PLATFORM, PSP, PARTNER). Implements TAX-R12 blocking at gate level. | [Repo: backend/apps/commercial/models.py], [Repo: backend/apps/commercial/choices.py], [Repo: backend/apps/commercial/services/gates.py] |
| Commercial R1 does not include invoicing or tax engine integration. | [Repo: backend/apps/commercial/README.md "Not in R1"] |
| **Seller reporting (DAC7 / UK HMRC platform reporting) and DSA Art. 30 trader traceability: none found.** Search of `backend/` for DAC7, platform reporting, trader traceability, DSA returned no implementation; "HMRC" appears only in VAT-schedule citations and a comment that HMRC/GST portal verification is out of scope. | [Repo: backend/apps/onboarding/services.py], [Repo: backend/platform_core/tax/registry/uk_vat_schedules.py] |
| Platform invoice/credit-note issuance (`invoice_credit`): none found. | — |

## 6. Open inputs required to complete

| Input | Needed from | Blocks |
|---|---|---|
| First country/corridor | Founder + Commercial (D01) | All determinations in 3.1 |
| Approved role profiles per corridor | GC + CFO (D02) | Deemed-supplier and issuer determinations |
| PSP selection and funds-flow mode | CTO + CFO + GC (D04) | Withholding, settlement-tax treatment, D09 |
| First-country tax, PSP funds and platform invoicing schedule | Global Tax + CFO (D09) | Gate enablement (`tax_schedule_reference`), test COM-016 |
| Applicability of DSA Art. 30, DAC7, UK HMRC platform reporting | Global Tax / qualified counsel | 3.2 containers |
| Reportable-seller field lists and filing owner | Global Tax | Seller-reporting build |
| Contracting/invoicing entity per country and intercompany (transfer pricing) arrangement | Global Tax + CFO | Invoice issuer, TAX-R05 |
| External tax engine / provider selection | CTO + Global Tax | TAX-R16, TAX-R17 |
| E-invoicing validation per country | Global Tax | Invoice format |
| Validation of repo-embedded rates/registries (IN, GB) | Global Tax | Any use of `platform_core/tax` for production invoices |
| Engineering owner of invoicing/tax context | CTO | Build allocation |
| Statutory chart-of-accounts alignment | Financial controller | App B mapping |

## 7. Acceptance / evidence mapping

| Test / evidence | What this document must supply | Source |
|---|---|---|
| test COM-001 | Missing commercial role / tax schedule rejects checkout (App A "Tax rule missing") | [M§24], [M App A] |
| test COM-003 | Golden cases with tax handling separate from fee base (App A Parts basket: sales tax $7.20 modeled separately) | [M§24], [M App A] |
| test COM-007 | Balanced journals including tax lines on capture/credit/chargeback | [M§24] |
| test COM-016 | GL posts earned platform revenue vs third-party pass-through (incl. seller tax) | [M§24] |
| Evidence pack | "finance/tax configuration" and "role/legal memo" per go-live SKU | [M§24] |

## 8. Completion status

| Section | Status |
|---|---|
| 1 Purpose and scope | Drafted |
| 2 Requirements | Drafted |
| 3.1 Determination register | Pending external input (Global Tax) |
| 3.2 Seller-reporting containers | Drafted (structure); field lists pending external input |
| 3.3 Invoice controls | Drafted |
| 3.4 Tax rule missing | Drafted |
| 4 Engineering reconciliation | Drafted |
| 5 Implementation evidence | Drafted |
| 6 Open inputs | Drafted |
| 7 Acceptance mapping | Drafted |

Overall: DRAFT — structurally complete; 12 open inputs; D09 BLOCKED.
