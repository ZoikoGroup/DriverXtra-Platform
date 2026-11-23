# Doc COM-03 — SKU and Pricing Rules

| Field | Value |
|---|---|
| Document ID | DX-COMM-COM-03 (proposed; map to canonical engineering register per M§25) |
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Parent | DX-COMM-MASTER-001 v1.0 (23 Oct 2026); v1.1 PROPOSED revision |
| Status | DRAFT — not approved. No content is a live tariff, executed contract, legal/tax opinion or regulatory permission. |
| Proposed owner | Global Commercial Director (master owner; "Commercial owner proposes") [M cover, M§07 Approval] |
| Required approvers | CFO approves rates; legal/tax approves roles/territory; technical release separates duties [M§07 Approval]; CFO + Commercial for D03 [M§25]; Product + CTO for D10 [M§25] |
| Related decisions | D03 OPEN; D10 OPEN; D02 BLOCKED (needs D01 corridor); D06 RECOMMENDED (hold; switch stays OFF); D09 BLOCKED (needs D01, D02, D04) |
| Related tests | test COM-001, test COM-002, test COM-003, test COM-013 [M§24] |

ID-namespace note: "Doc COM-0X" = this deliverable series; "revenue code COM-0X" = M§04 codes; "test COM-0XX" = M§24 tests. They are unrelated identifiers.

> **Decision update (19 November 2026, rev. B).** Confirmed direction from Lennox Zoiko: contracting company **Zoiko Mobility Inc.**; initial target markets **USA and UK** (no pilot city or corridor chosen); preferred payment provider **Stripe** (Stripe Connect capabilities, merchant onboarding, settlement and payouts per country still to be verified); finance and insurance handled as a **separate workstream owned by Rithika** (stays OFF here). These are recorded as CONFIRMED DIRECTION, not formal legal or regulatory approvals. Where this document's header or text gives older statuses for D01, D02, D04, D07 or D09, the current register in [../02_Commercial_Decision_Register.md](../02_Commercial_Decision_Register.md) prevails.

## 1. Purpose and scope

Defines the commercial SKU taxonomy, the revenue-code ledger each SKU belongs to, the precedence and control rules for forming a quote, and the golden vectors that prove calculations. It is the deliverable "COM-03 SKU / Pricing Rules" [M§25]. Sources: revenue codes [M§04], price book [M§06], rate engine [M§07], golden vectors [M App A], data dictionary [M App C], entity `commercial_sku`/`rate_schedule`/`quote_snapshot` [M§21]. Plan entitlements belong to Doc COM-08; quote/checkout UX to Doc COM-11 [M§25].

## 2. Requirements carried from the master

| Req ID | Requirement | Source |
|---|---|---|
| R03-01 | Each stream carries revenue_code, commercial_product, payer_role, rate_basis, performance_obligation, earning_event, reversal_policy, tax_profile, jurisdiction, source_contract. | [M§04] |
| R03-02 | Never charge a fee on an unconfirmed lead, nonbillable lead rejection, failed payment, reversed transaction or out-of-scope activity. | [M§04] |
| R03-03 | Mixed streams: contracts define non-duplication or affirmative stackable charges. | [M§04, M§07 Stacking] |
| R03-04 | All §06 figures are hypotheses for willingness-to-pay tests; not checkout prices; localized price books need Finance/Tax sign-off. | [M§06 PRICING STATUS] |
| R03-05 | Pricing experiments record segment, geography, currency, attribution horizon, randomization/holdout, quoted price, conversion, gross margin, churn, complaint rate, counterfactual. | [M§06] |
| R03-06 | Quote formation follows the six-step precedence in §3.3. | [M§07] |
| R03-07 | Accepted snapshot is immutable; retroactive amendments never rewrite accepted orders or earned fees. | [M§07] |
| R03-08 | Money as ISO 4217 integer minor units with explicit exponent; no floating-point. | [M§07 Currency, M App C] |
| R03-09 | No front-end-only pricing calculations or unapproved hardcoded local fees. | [M§20] |
| R03-10 | Public pricing and finance consoles read the same effective-dated SKU catalog without exposing negotiated terms. | [M§15] |
| R03-11 | Every launch SKU needs a jurisdiction/version-scoped signed schedule and regression-tested controls. | [M§00 Change policy] |
| R03-12 | Revenue codes REG-01, REG-02, FIN-01 and revenue code COM-04 stay OFF/GATED. | [M§04] |

## 3. Specification draft

### 3.1 Revenue-code ledger [M§04]

| Code | Stream | Earning event / restriction | Status |
|---|---|---|---|
| ADV-01 | Vehicle listing fee / private seller | Published listing activation; duration, cancellation/renewal terms | RECOMMENDED |
| ADV-02 | Promoted listing / sponsored placement | Impressions/duration delivered; visible labels | RECOMMENDED |
| ADV-03 | Dealer advertising plan | Recurring access/stock slot entitlement | RECOMMENDED |
| ADV-04 | Qualified dealer lead | Unique, consented, valid lead accepted against objective SLA | RECOMMENDED |
| revenue code COM-01 | Parts/accessories platform fee | Completed attributable on-platform order, subject to reversals | RECOMMENDED |
| revenue code COM-02 | Workshop booking facilitation | Completed or contract-defined billable booking; cancellations adjust | RECOMMENDED |
| revenue code COM-03 | B2B procurement/wholesale | Fulfilled procurement order or licensed software facilitation charge | RECOMMENDED |
| revenue code COM-04 | Vehicle closing service (future) | Only under signed jurisdiction role | **GATED — disabled** |
| SUB-01..SUB-05 | Dealer, WorkshopHub, Supplier, FleetOps, OEM/enterprise software | Time-based / contract entitlement | RECOMMENDED |
| REF-01 | EV installer/charging lead | Verified partner acceptance, disclosure, dedupe | RECOMMENDED |
| REF-02 | Roadside, logistics, inspection | Contract-defined referral or completed job where permitted | RECOMMENDED |
| REG-01 | Consumer finance introduction | OFF until approved permissions/partner contract | **GATED — disabled** |
| REG-02 | Insurance introduction | OFF until approved distribution/AR structure or exemption | **GATED — disabled** |
| API-01, DAT-01, MKT-01, LOY-01 | API usage, insights, campaigns, benefit administration | Per §04 row | RECOMMENDED |
| FIN-01 | Payment service-related margin | OFF until PSP agreement, disclosure, local approval | **GATED — disabled** |

### 3.2 Price book — ILLUSTRATIVE launch test bands [M§06]

PRICING STATUS (verbatim): "ALL figures below are hypotheses for structured willingness-to-pay tests and finance sensitivity analysis. They are not verified market averages, board-approved rates, checkout prices, margin commitments or globally harmonized tariffs. USD used for reference only; localized price books require Finance/Tax sign-off." [M§06]

| SKU | ILLUSTRATIVE base rate (verbatim) | Basis / inclusions / exclusions (verbatim) |
|---|---|---|
| DX-LST-PRIVATE | $15–$49 | Per vehicle/30-day listing; buyer sees no platform checkout unless separately supported. |
| DX-SPONSORED | $10–$150 | Campaign duration/impressions by segment; clearly labeled sponsorship. |
| DX-DEAL-LAUNCH | $49–$149 / mo | Small dealer account and fixed active stock cap; verify limits via pricing experiments. |
| DX-DEAL-GROWTH | $149–$499 / mo | Expanded active stock, feed, lead queue, analytics; usage beyond cap priced separately. |
| DX-DEAL-ENT | Custom $1,000+ / mo | Group, integration, SLA and multi-site contract; do not imply universal minimum. |
| DX-LEAD-DEALER | $5–$35 | Only accepted qualified lead under dedupe, consent and definition controls. |
| DX-PARTS-TAKE | 5%–12% | On defined commissionable net order value; exclude seller tax/pass-through items per policy. |
| DX-WORKSHOP-SUB | $39–$199 / mo | Workshop workspace, calendar, lead analytics, local staff seats. |
| DX-SERVICE-BOOK | 5%–12% or $5–$25 | One published basis per SKU, on completed booking/value; no undisclosed stacking. |
| DX-SUPPLIER-PRO | $79–$299 / mo | Supplier catalog tools, feeds, order operations; separate fees for commerce. |
| DX-FLEET-ASSET | $5–$20 / active asset/mo | Subject to monthly active asset definition, minimum commitment and caps. |
| DX-API-BASE | $500–$2,500 / mo | API tier plus contracted usage; data rights and SLA per contract. |
| DX-REF-EV | $5–$40 | Accepted, nonduplicate eligible EV services lead; contractor paid by contract. |
| DX-REG-REF | No rate proposed | Legal/compliance gated; negotiated only after regulated perimeter and consumer outcomes approved. **GATED** |
| DX-PAYMENT-FEE | No rate proposed | Third-party PSP economics passed through only as expressly contracted and lawful. **GATED** |

The master does not map §06 SKUs to §04 revenue codes. The SKU → revenue-code mapping is an open input (§6); the repo's mapping (§5) is implementation evidence only.

### 3.3 Versioned precedence and quote formation [M§07]

1. Resolve jurisdiction/fulfilment location and buyer/seller legal roles; check vertical feature permissions and eligible currencies.
2. Resolve executed partner agreement and effective-dated customer rate card; apply eligibility, entitlement and negotiated overrides in approved priority order.
3. Calculate face value, taxes, item discounts, delivery, partner charges, processing costs and fee-bearing base as separate lines.
4. Check minimum/maximum fee, currency rounding, price freshness, inventory/availability, promotion budget and caps; generate signed quote snapshot.
5. Present full customer payable total, payer and seller identities, taxes, optional services and refund conditions BEFORE acceptance.
6. Create immutable accepted commercial snapshot.

Blocking rule: a buyer country supported in the UI without tax and role schedule may show discovery but must block binding transaction/checkout and record the policy reason [M App A "Tax rule missing"].

### 3.4 Control table [M§07] (RECOMMENDED rules, carried verbatim in substance)

| Control | Rule | Open element |
|---|---|---|
| Currency | ISO 4217 integer minor units + exponent; zero-/three-decimal safe; exact FX quote/version, source, expiry, consent. | Rounding method not specified (open input) |
| Rate scope | market × vertical × category × payer/role × plan × contract × date; explicit priority; no wildcard to regulated territory. | Contract dimension depends on Doc COM-09 |
| Fee basis | Net-of-discount commissionable amount defined by contract; taxes/shipping/returns modeled separately. | Inclusion/exclusion list per SKU (open input) |
| Stacking | Explicit combinability; advertising and SaaS are distinct obligations; no double fee absent disclosure. | Combinability matrix (open input) |
| Price protection | Changes prospective, published or notified; accepted quote signed and frozen. | Notice periods not given (open input, counsel) |
| Promotions | Budget owner, redemption cap, fraud velocity, expiry, eligibility, independent audit. | All parameters open |
| Refunds | Original tax/rate/FX evidence retained; credit to original obligation, not current catalog. | — |
| Approval | Commercial proposes; CFO approves; legal/tax approves roles/territory; technical release separates duties. | — |
| Discount permissions | Thresholds, exception expiry, margin floor enforced. | Thresholds and floor (open input, CFO) |
| Invoices | Local tax invoice/legal identity; sequential numbers by authorized issuer; e-invoicing only where validated. | See Doc COM-04 |

### 3.5 Golden vectors [M App A] (ILLUSTRATIVE test data)

| Case | Golden input | Expected control behavior |
|---|---|---|
| Parts basket | Goods $100.00; discount $10.00; shipping $6.00; sales tax $7.20; fee 8% of goods net of seller discount. | Buyer payable $103.20; fee base $90.00; platform fee $7.20; PSP fees and tax party modeled separately. |
| Partial return | Fee-bearing goods $90.00; accepted eligible return $30.00. | Fee credit $2.40 at original 8% if contract mandates proportional reversal; keep original invoice/FX trace. |
| Duplicate lead | Two submissions, same customer/provider/vehicle within dedupe window. | One potential billable lead maximum; partner acceptance required. |
| Workshop change order | Approved job $150; technician proposes +$90 without consent. | Original authorized amount only; incremental fee/payment prohibited until affirmative approval. |
| Subscription proration | Dealer month billed $249; mid-cycle plan change. | Prorate/credit per executed policy; no hard-coded assumption. |
| Tax rule missing | UI-supported buyer country, no tax/role schedule. | Discovery only; block binding checkout; record policy reason. |

The 8% rate and dollar amounts are test inputs, not proposed rates.

### 3.6 Data dictionary fields used [M App C, M§21]

`commercial_role_id`, `seller_of_record_id`, `price_in_minor_units`, `commissionable_base_in_minor_units`, `customer_total_in_minor_units`, `tax_determination_id`, `fx_rate_quote_id`, `consent_provenance_id`, `quote_terms_hash`, `country_activation_version` [M App C]. Entities: `commercial_sku` (sku_id, family, fee_basis, entitlement_type, refund_policy_id, scope/status, tax_class, version); `rate_schedule` (validity interval, currency, payer, source rank, commissionable base, cap/floor, override approvals); `quote_snapshot` (gross/discount/tax/shipping/fees, FX/rounding, role+policy hash, expiration, consent) [M§21].

## 4. Engineering reconciliation notes

| Topic | Engineering text | Master position | Handling |
|---|---|---|---|
| Ownership | No catalog/pricing context among CTX-01..CTX-18; offers in CTX-04, orders in CTX-06, ads in CTX-16 [E 2.4] | Commercial Catalog and Contract & Pricing domains [M§20] | Context assignment is an open input (CTO). |
| Revenue routes | "Commissions on sales (and on finance or insurance referrals...)" [E 1.8] | REG-01/REG-02 OFF; vehicle-sale percentage not taken until attribution/role/title controls exist [M§04, M§13.1] | Flagged; master governs. |
| Snapshots | Orders pin price, tax, terms, fitment, policy [E 2.2] | Immutable accepted snapshot [M§07] | Compatible. |
| Cross-context keys | "No cross-context foreign keys" [E 2.2] | Not addressed | Repo `QuoteSnapshot` has FKs to user and `organisations.Organisation` (§5); flag for CTO. |
| Money | Integer minor units + ISO currency [E 2.2] | Same [M§07] | Compatible; marketplace uses decimals (see Doc COM-05). |

## 5. Implementation evidence (repo)

| Fact (verified) | Path |
|---|---|
| `CommercialSku` (sku_code, version, family, revenue_code, vertical, fee_basis, entitlement_type, billing_interval, tax_class, refund_policy_id, `illustrative_band_note` "never used in calculations", computed `is_regulated`, status default DRAFT). | [Repo: backend/apps/commercial/models.py] |
| `RevenueCodeChoices` lists all 22 §04 codes; `GATED_REVENUE_CODES` = REG-01, REG-02, FIN-01, COM-04; regulated SKUs cannot be approved; author cannot approve own SKU. | [Repo: backend/apps/commercial/choices.py], [Repo: backend/apps/commercial/services/catalogue.py] |
| `RateSchedule`: SKU × country × vertical × currency × payer_role × optional plan_code, `priority`, effective dates, `flat_amount_minor` or `percentage_bps`, `min_fee_minor`/`max_fee_minor`; default DRAFT. | [Repo: backend/apps/commercial/models.py] |
| Resolution: APPROVED and effective only; highest priority, then plan-specific over blank plan; ties raise `RATE_AMBIGUOUS`. No contract or category dimension observed. | [Repo: backend/apps/commercial/services/rates.py] |
| Fee: percentage = base × bps / 10,000 rounded half-up to minor unit; flat × quantity; clamp to min/max; USAGE_METERED and CUSTOM_CONTRACT not quotable. | [Repo: backend/apps/commercial/services/rates.py], [Repo: backend/apps/commercial/money.py] |
| Fee-base rule `GOODS_NET_OF_DISCOUNT_EXCL_TAX_DELIVERY_V1`: commissionable base = face − discount; customer total = face − discount + delivery + tax + fees payable by the customer's role. README states App A parts basket reproduces 10320 total / 720 fee (minor units). | [Repo: backend/apps/commercial/services/quotes.py], [Repo: backend/apps/commercial/README.md] |
| Binding quote requires open BINDING_QUOTE gate with allowed currency, approved role profile, approved non-regulated SKUs, approved rate, `tax_determination_reference`, `terms_version`; snapshot stores SHA-256 `terms_hash`; acceptance must echo hash before expiry at the same gate version. | [Repo: backend/apps/commercial/README.md], [Repo: backend/apps/commercial/services/quotes.py] |
| `QuoteSnapshot` allows only ISSUED → ACCEPTED/EXPIRED/VOID; other fields immutable; `QuoteLine` append-only. Quote TTL setting `COMMERCIAL_QUOTE_TTL_SECONDS` default 1800 (repo configuration, not a master value). | [Repo: backend/apps/commercial/models.py], [Repo: backend/apps/commercial/README.md] |
| Supported currency list with 0/2/3-decimal exponents; unknown currency rejected; cross-currency quotes rejected (no FX). | [Repo: backend/apps/commercial/money.py], [Repo: backend/apps/commercial/README.md] |
| Seed command loads the 15 §06 SKUs, mapping each to a revenue code and vertical (e.g. dealer plans → SUB-01, DX-LEAD-DEALER → ADV-04, DX-PAYMENT-FEE → vertical PARTS); bands stored as text; DX-SERVICE-BOOK stays DRAFT with "UNDECIDED basis" note while its `fee_basis` field is set to PERCENT_OF_BASE; no rates, gates or approvals. | [Repo: backend/apps/commercial/management/commands/seed_illustrative_commercial_catalogue.py] |
| Not in R1: price freshness, inventory, promotion budget/caps, discount thresholds, contract dimension, FX quotes. | [Repo: backend/apps/commercial/README.md] (by omission; verified against services read) |

## 6. Open inputs required to complete

| Input | Needed from | Blocks |
|---|---|---|
| D03 SKU list: master says "first 8 SKUs" but lists six families (listing, workshop, dealer, lead, fleet, EV) — which 8 SKUs | CFO + Commercial (D03) | §3.2 launch set, test design |
| SKU → revenue-code mapping (e.g. dealer plans: ADV-03 vs SUB-01) | CFO + Commercial | §3.1/§3.2 linkage, Doc COM-04 |
| DX-SERVICE-BOOK single published basis (percentage or flat) | CFO + Commercial | Rate configuration |
| Localized rates per corridor (any figure) | CFO with Finance/Tax sign-off | All rate schedules |
| Rounding method per currency | CFO | §3.4 Currency |
| Fee inclusion/exclusion list per SKU; pass-through items | CFO + Global Tax | Fee basis, test COM-003 |
| Stacking/combinability matrix | Commercial + CFO | §3.4 Stacking |
| Discount thresholds, exception expiry, margin floor | CFO | §3.4 |
| Promotion parameters | Commercial (budget owner) + CFO | §3.4 |
| Price-change notice periods | GC / counsel | §3.4 Price protection |
| Quote expiry duration | CFO + Product | Quote TTL |
| Contract dimension in rate scope | GC + CFO (Doc COM-09) | Rate resolution |
| Context ownership for catalog/pricing | CTO | §4 |
| Shared public catalog across web/mobile/admin | Product + CTO (D10) | Public pricing surface |

## 7. Acceptance / evidence mapping

| Test / evidence | What this document must supply | Source |
|---|---|---|
| test COM-001 | Effective-dated SKU/rate resolution rules | [M§24] |
| test COM-002 | Snapshot immutability rule | [M§24, M§07] |
| test COM-003 | Fee-base rule and App A golden vectors | [M§24, M App A] |
| test COM-013 | Customer total composition incl. mandatory seller fees (US displays) | [M§24, M App C] |
| Evidence pack: approved fee specification; golden calculation vectors; versioned contract | Per go-live SKU | [M§24] |

## 8. Completion status

| Section | Status |
|---|---|
| 1 Purpose and scope | Drafted |
| 2 Requirements | Drafted |
| 3.1 Revenue codes | Drafted |
| 3.2 Price book | Drafted (ILLUSTRATIVE only); launch set pending D03 |
| 3.3–3.4 Precedence and controls | Drafted; parameters pending external input |
| 3.5 Golden vectors | Drafted |
| 4 Engineering reconciliation | Drafted (flagged, not resolved) |
| 5 Implementation evidence | Drafted |
| 6–7 Open inputs, acceptance | Drafted |

Overall: DRAFT — structurally complete; 14 open inputs.
