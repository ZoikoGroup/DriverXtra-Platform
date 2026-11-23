# Doc COM-11 — Quote and Checkout UX

| Field | Value |
|---|---|
| Document ID | DX-COMM-COM-11 (proposed; map to canonical engineering register per M§25) |
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Parent | DX-COMM-MASTER-001 v1.0 (23 Oct 2026); v1.1 PROPOSED revision |
| Status | DRAFT — not approved. No content is a live tariff, executed contract, legal/tax opinion or regulatory permission. |
| Proposed owner | CPO (UX & journeys) [M§00 Cross-functional sign-off]; Days 31–60 "onboarding, disclosure, pricing UX" owned by CTO/Engineering/Design [M§22 90-day sequence] |
| Required approvers | CPO (UX), CFO (price/economics), GC/Compliance (role/tax disclosures), CTO (technical controls) [M§00]; Product + CTO for D10 [M§25]; issue under founder approval [M§25] |
| Related decisions | D10 UX/app parity — OPEN; D02 legal transaction roles — BLOCKED (needs D01 corridor); D04 payment PSP — BLOCKED (needs D01, D02); D05 product safety/fitment — OPEN; D09 tax/settlement — BLOCKED (needs D01, D02, D04). Master §25 lists these as OPEN; statuses above are set by the document owner. |
| Related tests | test COM-001, test COM-002, test COM-009, test COM-013, test COM-014 [M§24] |

ID-namespace note: "Doc COM-0X" = deliverable; "revenue code COM-0X" = M§04 stream; "test COM-0XX" = M§24 acceptance test.

> **Decision update (19 November 2026, rev. B).** Confirmed direction from Lennox Zoiko: contracting company **Zoiko Mobility Inc.**; initial target markets **USA and UK** (no pilot city or corridor chosen); preferred payment provider **Stripe** (Stripe Connect capabilities, merchant onboarding, settlement and payouts per country still to be verified); finance and insurance handled as a **separate workstream owned by Rithika** (stays OFF here). These are recorded as CONFIRMED DIRECTION, not formal legal or regulatory approvals. Where this document's header or text gives older statuses for D01, D02, D04, D07 or D09, the current register in [../02_Commercial_Decision_Register.md](../02_Commercial_Decision_Register.md) prevails.

## 1. Purpose and scope

UX requirements for forming, presenting, accepting and checking out a commercial quote, for the parts order (journey B) and workshop/installer booking (journey C) [M§08], within the public information architecture of M§14. This is the "COM-11 Quote/Checkout UX" deliverable [M§25]. Out of scope: journey F finance/insurance (GATED) [M§08 F]; payment modes E and F (GATED) [M§10]; vehicle closing service (revenue code COM-04, GATED/future) [M§04]; visual design beyond the master's design-system rules [M§14].

## 2. Requirements carried from the master

| Req ID | Requirement | Source |
|---|---|---|
| QX-01 | Quote formation step 1: resolve jurisdiction/fulfilment location and buyer/seller legal roles; check vertical feature permissions and eligible currencies | [M§07] |
| QX-02 | Step 2: resolve executed partner agreement and effective-dated customer rate card; apply eligibility, entitlement and negotiated overrides in approved priority order | [M§07] |
| QX-03 | Step 3: face value, taxes, item discounts, delivery, partner charges, processing costs and fee-bearing base as separate lines | [M§07] |
| QX-04 | Step 4: min/max fee, currency rounding, price freshness, inventory/availability, promotion budget and caps; generate signed quote snapshot | [M§07] |
| QX-05 | Step 5: present full customer payable total, payer and seller identities, taxes, optional services and refund conditions BEFORE acceptance | [M§07] |
| QX-06 | Step 6: immutable accepted snapshot; retroactive amendments never rewrite accepted orders or earned fees | [M§07] |
| QX-07 | Before order creation, re-check offer status, price, stock, seller eligibility, fitment and country rules | [E 1.5, E 2.4 "Checkout revalidates against the real source"] |
| QX-08 | Journey B: VIN/YMM → compatibility & safety → cart → seller-of-record + shipping estimate → tax/fee quote → licensed PSP charge/authorization → reservation → fulfilment → return/warranty → settlement → net fee accrual → payout/reconciliation/chargeback; uncertain fitment visibly flagged | [M§08 B] |
| QX-09 | Journey C: service/location → credentials/availability → scoped estimate vs fixed price → buyer accepts terms → booking/deposit via permitted PSP configuration → change-order authorization → completion evidence → invoice/receipt → settlement/refund/dispute; quote revisions need affirmative buyer approval | [M§08 C] |
| QX-10 | Plans & Pricing: segment switcher, currency/territory, rate units, inclusion matrix, all fees, tax/terms; no hardcoded globally universal prices | [M§14] |
| QX-11 | Parts: fitment confidence separate from certified fitment. Book a Service: fixed total vs estimate visually distinguished | [M§14] |
| QX-12 | Design system: amber/titanium; large typography; neutral backgrounds; 8-point grid; WCAG 2.2 AA target | [M§14] |
| QX-13 | One primary CTA per conversion surface; progressive disclosure for high-risk terms; mobile-first sticky price/CTA; responsive breakdowns | [M§14] |
| QX-14 | Every price card states billing interval, renewal, taxes, mandatory charges, included inventory/seats, territory | [M§14] |
| QX-15 | Sponsored rank, verification, eco-impact evidence and commission/funding disclosures are separate badges with proper semantics | [M§14] |
| QX-16 | All-in price prominent where required incl. dealer mandatory charges; no financing-dependent misleading "cash" prices | [M§14] |
| QX-17 | Accessible quote detail, review and confirmation; plain-language errors; alternate checkout; keyboard focus; localization; screen-reader error announcements | [M§14] |
| QX-18 | Trials: no auto-convert without compliant consent; billing cycle, taxes, notice, prorations, refunds, renewal dates appear before acceptance | [M§05 Entitlement rules] |
| QX-19 | No front-end-only pricing calculations or unapproved hardcoded local fees; web and mobile use the same state models | [M§20] |

## 3. Specification draft

### 3.1 Quote → checkout screen sequence (journeys B and C)

| Step | Screen | Content (master fields) | Blocking behavior | Source |
|---|---|---|---|---|
| S1 | Context | market/territory, currency, buyer role; vehicle (VIN/YMM) for B; service + location for C | No binding quote if country gate or role missing; discovery may still display (App A "Tax rule missing") | [M§07, M§08, M App A] |
| S2 | Eligibility | fitment state (B: confidence vs certified); provider credentials/availability (C) | Uncertain fitment flagged, not hidden | [M§08 B, M§14, E 1.5 fitment states CONFIRMED_FIT / CONDITIONAL_FIT / DOES_NOT_FIT / UNKNOWN] |
| S3 | Quote detail | separate lines: face value, discount, delivery, taxes, partner charges, processing costs; seller of record; payer; optional services; refund conditions; estimate vs fixed price (C) | All mandatory charges in customer total | [M§07 steps 3–5, M§14, M App C customer_total_in_minor_units] |
| S4 | Review & consent | terms version; consent notice; quote expiry | One primary CTA "Accept"; progressive disclosure for high-risk terms | [M§14, M App C consent_provenance_id, quote_terms_hash] |
| S5 | Revalidation | re-check offer, price, stock, seller eligibility, fitment, country rules | If any changed: show plain-language reason and require a fresh quote | [E 1.5, M§14 error resolution] |
| S6 | Payment / booking | PSP authorization (B) or booking/deposit (C) via approved PSP | PSP not selected (D04 BLOCKED): no live payment step | [M§08, M§10, M§25] |
| S7 | Confirmation / receipt | seller of record, sponsored labels (if any), totals as accepted | Receipt values come from the accepted snapshot only | [M§24 test COM-009, M§07 step 6] |
| S8 | Change order (C) | original authorized amount; proposed increment | Increment blocked until affirmative buyer approval | [M§08 C, M App A Workshop change order] |

### 3.2 Appendix A vectors used as UX acceptance examples (ILLUSTRATIVE)

| Case | Golden input | Expected displayed/controlled outcome | Source |
|---|---|---|---|
| Parts basket | Goods $100.00; discount $10.00; shipping $6.00; sales tax $7.20; fee 8% of goods net of seller discount | Buyer payable $103.20 (check: 100.00 − 10.00 + 6.00 + 7.20 = 103.20); fee base $90.00; platform fee $7.20 (8% × 90.00) — fee not added to buyer total in this case | [M App A] |
| Partial return | Fee-bearing goods $90.00; accepted return $30.00 | Fee credit $2.40 (8% × 30.00) if contract mandates proportional reversal; original invoice/FX trace kept | [M App A] |
| Workshop change order | Approved $150; technician proposes +$90 without consent | Only $150 authorized; increment prohibited until approval | [M App A] |
| Subscription proration | Dealer month $249; mid-cycle change | Per executed policy; no hard-coded assumption | [M App A] |
| Tax rule missing | Buyer country in UI but no tax/role schedule | Discovery as appropriate; binding checkout blocked; policy reason recorded | [M App A] |

The "Duplicate lead" vector [M App A] belongs to the lead journey (Doc COM-07), not this document.

### 3.3 Appendix C field → UX element

| Field [M App C] | UX element | Required at |
|---|---|---|
| commercial_role_id | (hidden) gate for binding order | S1, S5 |
| seller_of_record_id | "Sold by" identity | S3, S7 |
| price_in_minor_units | line amounts, formatted by currency exponent | S3 |
| commissionable_base_in_minor_units | not shown to buyer (internal); rule version retained | — |
| customer_total_in_minor_units | sticky total incl. mandatory charges | S3–S7 |
| tax_determination_id | tax line + evidence reference | S3 |
| fx_rate_quote_id | locked/indicative FX disclosure with expiry (only if FX enabled) | S3 |
| consent_provenance_id | consent notice version + user action + time | S4 |
| partner_credential_evidence | provider credential badge (never purchasable) | S2 (C) |
| quote_terms_hash | echoed on acceptance | S4 |
| country_activation_version | rechecked at acceptance | S5 |
| earning_event_reference, reversal_of_earning_id | not buyer-facing; used for refunds/receipts lineage | — |

## 4. Engineering reconciliation notes

| Topic | Note | Source |
|---|---|---|
| Context ownership | Cart→order: CTX-06; payment: CTX-07; fitment: CTX-03; bookings: CTX-08; country rules: CTX-17. Master "Contract & Pricing" quote engine [M§20] has no named CTX in E 2.4 — open. | [E 2.4, M§20] |
| Order snapshot | E pins price, tax, terms, fitment and policy on the order; master pins SKU, rate, fee base, tax, consent, FX, contracting identity, policy decision. Fitment is in E's snapshot but not listed in M§20 — flagged, not resolved. | [E 2.2, M§20] |
| Payment timeout | E: timed-out payment marked "unknown" and reconciled, never charged twice. Master has no equivalent UX state; needs a buyer-facing message. | [E 1.5] |
| Multi-seller cart | E splits a multi-seller cart into one order per seller; master quote formation is per quote. Quote-per-seller vs per-cart is open. | [E 1.5, M§07] |

## 5. Implementation evidence (repo)

Implementation evidence only; not approval.

| Fact | Path |
|---|---|
| `POST /api/v1/commercial/quotes/` issues a binding quote only when the BINDING_QUOTE gate is ENABLED with the currency, the role profile is APPROVED/effective, every SKU APPROVED and non-regulated, a rate resolves, and `tax_determination_reference` and `terms_version` are supplied. | [Repo: backend/apps/commercial/README.md, backend/apps/commercial/services/quotes.py] |
| Snapshot stores lines, totals, role snapshot (seller_of_record_party, payment_role, tax_party, invoice_issuer, jurisdiction, snapshot_hash), `gate_version`, tax reference and a SHA-256 `terms_hash` of canonical JSON; snapshot and lines are guarded as immutable/append-only. | [Repo: backend/apps/commercial/models.py, backend/apps/commercial/services/common.py] |
| `POST .../quotes/{id}/accept/` requires owner, ISSUED status, before expiry (`COMMERCIAL_QUOTE_TTL_SECONDS`, default 1800 — an implementation default, not a master value), matching `terms_hash`, a `consent_notice_version`, and the gate still ENABLED at the same version; emits `quote.accepted` via outbox and writes an audit entry. | [Repo: backend/apps/commercial/services/quotes.py] |
| Acceptance stores `consent_notice_version`, `accepted_at`, `accepted_by`; no lawful channel basis field found (App C consent_provenance_id is therefore partial). | [Repo: backend/apps/commercial/models.py] |
| No FX: cross-currency quotes rejected; integer minor units + ISO 4217. `fx_rate_quote_id` has no implementation. | [Repo: backend/apps/commercial/README.md] |
| `GET /api/v1/commercial/plans/?market=` requires a market (no default), returns plans only where the DISCOVERY gate is ENABLED, and carries a disclosure that taxes, terms and final total are confirmed in a quote. | [Repo: backend/apps/commercial/views.py] |
| Frontend API client defines `getPlans`, `createQuote`, `getQuote`, `acceptQuote`; no customer-facing component calling them was found (only the admin console uses commercial endpoints). | [Repo: frontend/src/lib/api/client.ts, frontend/src/components/platform/CommercialAdminView.tsx] |
| Marketplace checkout (`POST /api/v1/marketplace/orders/checkout/`) recalculates GST on the backend and creates an order; it does not import the commercial app. README "Not in R1" lists integration with marketplace checkout. | [Repo: backend/apps/marketplace/views.py, backend/apps/commercial/README.md] |
| Workshops app has bookings, quotations, work orders, change orders and deposit webhook events (journey C building blocks), not linked to commercial quotes. | [Repo: backend/apps/workshops/models.py] |

## 6. Open inputs required to complete

| Input | Needed from | Blocks |
|---|---|---|
| First market/corridor (drives currency, locale, RTL need, US all-in rule applicability) | Founder + Commercial (D01) | S1, test COM-013, test COM-014 scope |
| Legal role profiles per journey (seller of record, merchant of record) | GC + CFO (D02) | S3, S7 copy |
| PSP and payment mode for B and C | CTO + CFO + GC (D04) | S6 |
| Consumer disclosure copy: refund conditions, cancellation/no-show, estimate vs fixed price wording | Consumer Legal + CFO [M App D] | S3, S4, S8 |
| Quote validity period (UX expiry) | CFO + Product | S4, S5 |
| Tax display rules (inclusive/exclusive) per market | Global Tax (D09) | S3 |
| Fitment reference and labels | Product + Trust (D05) | S2 |
| Design tokens (amber/titanium values) and component library | CPO / Design | QX-12 |
| Alternate checkout method definition | CPO + Payments | QX-17 |
| Quote-per-seller vs per-cart decision | CTO + CPO | §4 |

## 7. Acceptance / evidence mapping

| Test / evidence | What this doc must supply |
|---|---|
| test COM-001 | S1/S5 blocking states and copy for expired/absent role |
| test COM-002 | S7 receipt from accepted snapshot after rate change |
| test COM-009 | S3/S7 seller-of-record and sponsored labels across search, price, listing, checkout, receipts |
| test COM-013 | S3 all-in total incl. mandatory non-government seller fees (US displays where applicable) |
| test COM-014 | WCAG 2.2 AA automated + manual run of S1–S8; locale/currency/RTL; keyboard |
| Evidence pack: end-user disclosure screenshots; golden calculation vectors; accessibility test [M§24] | Screenshots of S3, S4, S7; §3.2 vectors rendered |

## 8. Completion status

| Section | Status |
|---|---|
| 1–2 Purpose, requirements | Drafted |
| 3 Screen sequence, vectors, fields | Drafted; copy and market specifics Pending external input |
| 4 Engineering reconciliation | Drafted (flagged, not resolved) |
| 5 Implementation evidence | Drafted |
| 6 Open inputs | Drafted |
| 7 Acceptance mapping | Drafted |

Overall: DRAFT — structurally complete; 10 open inputs.
