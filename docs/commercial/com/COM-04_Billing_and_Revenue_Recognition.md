# Doc COM-04 — Billing and Revenue Recognition

| Field | Value |
|---|---|
| Document ID | DX-COMM-COM-04 (proposed; map to canonical engineering register per M§25) |
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Parent | DX-COMM-MASTER-001 v1.0 (23 Oct 2026); v1.1 PROPOSED revision |
| Status | DRAFT — not approved. No content is a live tariff, executed contract, legal/tax opinion or regulatory permission. |
| Proposed owner | CFO (price/economics/accounting sign-off) with the Controller for accounting policy [M§00, M§11, M App B caveat] |
| Required approvers | CFO [M§00]; Controller via signed accounting memorandum [M§11]; Global Tax + CFO for tax/invoicing schedule (D09) [M§25]; Finance + Product for subscription/renewal/dunning policy [M App D] |
| Related decisions | D08 OPEN; D09 BLOCKED (needs D01, D02, D04); D03 OPEN; D02 BLOCKED (needs D01 corridor) |
| Related tests | test COM-007, test COM-015, test COM-016 [M§24] |

ID-namespace note: "Doc COM-0X" = this deliverable series; "revenue code COM-0X" = M§04 codes; "test COM-0XX" = M§24 tests. They are unrelated identifiers.

Accounting status: every ASC 606 / IFRS 15 treatment below is **for the Controller's signed accounting memo** and is not concluded here [M§11].

> **Decision update (19 November 2026, rev. B).** Confirmed direction from Lennox Zoiko: contracting company **Zoiko Mobility Inc.**; initial target markets **USA and UK** (no pilot city or corridor chosen); preferred payment provider **Stripe** (Stripe Connect capabilities, merchant onboarding, settlement and payouts per country still to be verified); finance and insurance handled as a **separate workstream owned by Rithika** (stays OFF here). These are recorded as CONFIRMED DIRECTION, not formal legal or regulatory approvals. Where this document's header or text gives older statuses for D01, D02, D04, D07 or D09, the current register in [../02_Commercial_Decision_Register.md](../02_Commercial_Decision_Register.md) prevails.

## 1. Purpose and scope

Defines how earned platform fees, subscriptions and metered usage become invoices, credits and ledger postings, and how platform revenue is kept separate from GMV and third-party funds. It is the deliverable "COM-04 Billing & Revenue Recognition" [M§25]. Sources: accounting policy matrix, finance fields and tax scope [M§11]; metric definitions [M§17]; account codes [M App B]; entities `earning_event`, `invoice_credit`, `usage_meter_event` and the subscription state machine [M§21]. Tax determination and seller reporting belong to Doc COM-06; PSP settlement to Doc COM-05 [M§25].

## 2. Requirements carried from the master

| Req ID | Requirement | Source |
|---|---|---|
| R04-01 | Recognize reported GMV, attributed partner value, booking value and GAAP/IFRS platform revenue separately. | [M§04] |
| R04-02 | Controller MUST assess ASC 606 / IFRS 15 for performance obligations, variable-consideration constraint, principal vs agent, contract modifications, loyalty credits. | [M§11] |
| R04-03 | Neither checkout gross sales volume nor PSP-held third-party funds are automatically DriverXtra revenue. | [M§11] |
| R04-04 | US GAAP/IFRS policy selection follows the reporting entity and signed accounting memorandum. | [M§11] |
| R04-05 | A fee is earned only on a defined earning event with proof; reversals link to the original. | [M§21 earning_event, M App C] |
| R04-06 | Refund/credit applies to the same original financial obligation, with original tax/rate/FX evidence. | [M§07 Refunds] |
| R04-07 | Invoices: local tax invoice/legal identity; sequential numbers by authorized legal issuer; e-invoicing only where validated. | [M§07 Invoices] |
| R04-08 | Trials may not auto-convert without compliant consent; billing cycles, taxes, notice, prorations, refunds and renewal dates shown before acceptance. | [M§05] |
| R04-09 | Idempotency for money and subscriptions; at-least-once event deduplication. | [M§20] |
| R04-10 | Never calculate all tax from a single "seller country" field; apply country-specific professional advice. | [M§11] |
| R04-11 | GMV is not revenue; lead-influenced downstream value is not GMV. | [M§19] |
| R04-12 | General ledger only posts earned platform revenue vs third-party pass-through. | [M§24 test COM-016] |

## 3. Specification draft

### 3.1 Accounting policy matrix (subject to audited memo) [M§11]

| Revenue class | Potential performance obligation | Primary recognition risk | Memo status |
|---|---|---|---|
| Listing / advertising | Publish/deliver ad placement over term or specified exposure | Upfront cash may be deferred | For Controller's memo |
| Marketplace transaction fee | Successful facilitation service after material obligations/cancellation | Gross vs net, variable consideration, refunds/chargebacks | For Controller's memo |
| SaaS subscription | Time-based access delivered ratably as appropriate | Prepaid → deferred revenue; trial/credits/proration | For Controller's memo |
| Qualified lead fee | Validated lead transmitted/accepted by agreed criteria | Fake/duplicate leads; rejection windows, clawback | For Controller's memo |
| Partner referral | Qualifying attributable event with enforceable consideration | Regulated activity, clawbacks, attribution | For Controller's memo; regulated classes GATED |
| API/data license | Right-to-access/use or delivered units | Rights, minimum commits, usage reversals | For Controller's memo |
| Campaign sponsorship | Delivered placements, leads or milestones | Guaranteed outcomes, makegoods | For Controller's memo |

### 3.2 Finance fields [M§11]

| Record | Minimum finance fields |
|---|---|
| Commercial contract | legal issuer/customer, customer class, rate version, term, jurisdiction, renewal, tax flags, SLA, clawback |
| Order / quote | order ID, accepted terms hash, amount/currency, seller-of-record, buyer role, local tax evidence, fee snapshot |
| Invoice/credit | number/series, entity, tax registration, service period, FX, due date, line-level tax, linked adjustment |
| Payout/settlement | PSP balance account, settlement currency, reserve, charges, exchange spread, external reconciliation key |
| General ledger | entity/segment/vertical/revenue code, gross/net indicator, deferral period, contra-revenue, AR, bad debt |
| Close evidence | daily matched totals, aging, trial-to-ledger bridge, manual journal approvals, exception log, month-end cutoffs |

### 3.3 Canonical entities and states [M§21]

| Entity | Minimum fields |
|---|---|
| `earning_event` | SKU obligation, proof, due date, amount, reversal lineage, journal state, evidence hash |
| `invoice_credit` | issuer, counterparty, tax, invoice number, links to earning event, originals and adjustment |
| `usage_meter_event` | resource, quantity, actor, dimension, dedup key, time, contract quota, snapshot |

Linking fields: `earning_event_reference` (final event and evidence key causing a fee to be earned) and `reversal_of_earning_id` (link to original fee/credit) [M App C].

| Flow | States [M§21] |
|---|---|
| Subscription | trial/requested → approved/active → past_due/grace → suspended → cancelled/expired, with historic entitlement ledger |
| Lead (billing tail) | … → fee_pending → earned/voided → invoiced/credited |

Events: `fee.earned`, `invoice.issued`, `refund.initiated`, `chargeback.opened` — versioned, with business ID, correlation ID, actor/source, UTC timestamp, event ID and idempotency key [M§21].

Billing flow (assembled from cited sources): accepted snapshot [M§07] → earning event with proof [M§21] → invoice or self-bill as lawful [M§08 A] → collections/credit note [M§08 A] → GL posting by revenue code with gross/net indicator [M§11]. Self-billing legality per corridor is for counsel/tax adviser (open input).

### 3.4 Earning rules by stream (from master)

| Stream | Earning trigger | No-fee conditions | Source |
|---|---|---|---|
| Leads (ADV-04, REF-01) | Partner acceptance of qualified lead | Unconfirmed, rejected, duplicate, out-of-territory leads | [M§04, M§24 test COM-004] |
| Marketplace fees (revenue codes COM-01, COM-02, COM-03) | Completed order / booking / fulfilled procurement | Failed payment, reversed transaction | [M§04] |
| Subscriptions (SUB-01..SUB-05) | Time-based entitlement | Trial without compliant consent | [M§04, M§05] |
| Metered (API-01, SUB-04 consumption) | Usage above allowance under license | Duplicate meter events (dedup key) | [M§04, M§21] |
| Gated (REG-01, REG-02, FIN-01, revenue code COM-04) | None — disabled | All | [M§04] |

### 3.5 Metric definitions [M§17, M§19]

| Metric | Definition (master) |
|---|---|
| Attributed GMV | Third-party orders paid through supported flows; exclude lead-implied retail value and duplicates |
| Platform net revenue | Earned recognized advertising + SaaS + commission + eligible referrals + API; exclude seller pass-through and unearned balances |
| Gross profit | Net revenue – direct infrastructure, platform-borne PSP, fulfilment/support, fraud/returns loss, other COGS |
| Net take rate | Transaction platform net revenue / eligible settled marketplace GMV; not applied to off-platform vehicles and SaaS |
| Payments loss ratio | Confirmed fraud loss + platform-borne chargebacks + concessions / relevant settled GMV |

Dashboard semantics: "GMV is not revenue; lead-influenced downstream purchase value is not GMV; 'active' requires a contractual and event definition" [M§19]. The §17 worked examples and scenario table are ILLUSTRATIVE, "not forecasts" [M§17], and are not reproduced as targets here.

### 3.6 Management account codes [M App B] (ILLUSTRATIVE mapping)

| Code | Management account / observation |
|---|---|
| 4000–4099 | Advertising / listing recognized revenue; distinct deferred obligation |
| 4100–4199 | Dealer / workshop / supplier / FleetOps subscriptions and related deferred revenue |
| 4200–4299 | Parts, services and authorized transaction facilitation fees (net) |
| 4300–4399 | Eligible partner referrals and sponsorship; regulated partner class separately tracked |
| 4400–4499 | Enterprise API, software and privacy-safe licensed analytics |
| 4900–4999 | Contra-revenue: refunds, approved credits, incentives, performance shortfalls |
| 2100–2199 | Deferred revenue, refunds payable, other customer liabilities as applicable |
| 2300–2399 | Seller payable / PSP settlement clearing where recognized by actual role model |
| 5000–5999 | Direct COGS: PSP-borne fees, hosting, verification, variable support, fraud, fulfilment |
| 7100–7199 | Acquisition/marketing spend; separate from pricing incentives unless policy dictates |
| Z dimension | Entity, region, market, corridor, vertical, sku, channel, seller class, cohort, subscription/transaction, currency |

ACCOUNTING CAVEAT (verbatim): "The illustrative account numbers are a suggested management mapping, not a statutory chart of accounts; the financial controller must align them with Zoiko Mobility Inc.'s actual consolidated GL and accounting policy." [M App B]

The "(net)" label on 4200–4299 is the master's management observation; principal-vs-agent treatment remains for the Controller's memo.

### 3.7 Tax scope (requirements for tax adviser to determine) [M§11]

Indirect-tax marketplace facilitator/deemed supplier exposure; tax on SaaS, advertising, services and digital supplies; cross-border B2B reverse charges; invoice format/e-invoicing; withholding; platform reporting rules; transfer pricing between Zoiko entities. No determination is made here; D09 is BLOCKED.

### 3.8 Golden vectors relevant to billing [M App A] (ILLUSTRATIVE test data)

| Case | Expected behavior |
|---|---|
| Partial return | Fee credit $2.40 at original 8% if contract mandates proportional reversal; keep original invoice/FX trace |
| Subscription proration | Prorate/credit per executed policy; no hard-coded assumption until rate plan configured |
| Parts basket | Platform fee $7.20 on base $90.00; PSP fees and tax party modeled separately |

## 4. Engineering reconciliation notes

| Topic | Engineering text | Master position | Handling |
|---|---|---|---|
| Ownership | Double-entry ledger in CTX-07 Payments and Ledger [E 2.4, E 1.5]; no billing/subscription context listed [E 2.4] | Separate Billing & Tax and Finance Subledger domains [M§20] | Whether subscriptions, invoicing and earning events sit in CTX-07 or a new context is an open input (CTO). |
| Revenue model | Commissions and advertising only; "no prices or rates" [E 1.8] | 22 revenue codes incl. SaaS, API, data [M§04] | Master governs; engineering scope narrower. |
| Events | Transactional outbox; at-least-once; idempotent consumers; DLQ [E 2.2, E 2.5] | Versioned events with idempotency key [M§21] | Compatible. |
| Recovery | Tier 0 includes payments and ledger: RTO ≤ 30 min, RPO ≤ 5 min [E 2.10] | Not stated in master | Engineering figure; applicability to billing/subledger is an open input (CTO). |

## 5. Implementation evidence (repo)

| Fact (verified) | Path |
|---|---|
| Commercial R1 explicitly excludes subscriptions/entitlements, invoicing, earning events, ledger, settlement/reconciliation, payouts, FX quotes and tax-engine integration. | [Repo: backend/apps/commercial/README.md] |
| `QuoteSnapshot` stores face, discount, delivery, tax, commissionable base, `platform_fee_minor` and `customer_total_minor` separately; face/discount/delivery/tax lines are commented as "seller/customer amounts, not platform revenue". Supports test COM-016 at quote level only. | [Repo: backend/apps/commercial/models.py], [Repo: backend/apps/commercial/services/quotes.py] |
| `CommercialSku.billing_interval` (ONE_TIME, PER_EVENT, MONTHLY, ANNUAL) and fee bases incl. RECURRING_FLAT, PER_ACTIVE_ASSET, USAGE_METERED (not quotable in R1). | [Repo: backend/apps/commercial/choices.py] |
| Transactional outbox with per-consumer de-duplication. | [Repo: backend/platform_core/events/outbox.py] |
| Statutory tax engine (India GST, UK VAT) with document types TAX_INVOICE, BILL_OF_SUPPLY, COMMERCIAL_INVOICE, DISBURSEMENT_NOTE, BLOCKED. Implementation only; not a D09 sign-off and not wired to commercial R1. | [Repo: backend/platform_core/tax/choices.py], [Repo: backend/platform_core/tax/engine.py] |
| No `earning_event`, `invoice_credit`, `usage_meter_event` or subscription model for platform fees found in `apps/commercial` or `apps/marketplace` models. | none found |

## 6. Open inputs required to complete

| Input | Needed from | Blocks |
|---|---|---|
| Signed accounting memorandum (ASC 606 / IFRS 15 policy, principal vs agent, variable consideration, modifications) | Controller | §3.1, all recognition rules |
| Reporting entity and GAAP/IFRS selection | CFO + Controller | §3.1 |
| Alignment of App B codes to Zoiko Mobility Inc. consolidated GL | Controller | §3.6 |
| Revenue code → account code mapping | Controller | GL posting |
| First-country tax and platform invoicing schedule; invoice issuer per role profile | Global Tax + CFO (D09) | §3.7, invoice_credit |
| Self-billing legality per corridor | Tax adviser / counsel | Lead and referral invoicing |
| Proration, credit, dunning and grace policy (durations) | Finance + Product [M App D] | Subscription state machine, test COM-015 |
| Trial consent and notice rules per country | Consumer Legal + counsel | test COM-015 |
| Definition of "active" asset/account for billing | CFO + Commercial | SUB-04, DX-FLEET-ASSET |
| Context ownership for billing/subledger; recovery tier | CTO | §4 |

## 7. Acceptance / evidence mapping

| Test / evidence | What this document must supply | Source |
|---|---|---|
| test COM-007 | Journal rules for partial capture, shipment, completion, cancellation, credit, chargeback (balanced) | [M§24] |
| test COM-015 | Renewal/downgrade/trial-cancel rules; no silent double billing | [M§24, M§05] |
| test COM-016 | Posting rule: only earned platform revenue to revenue accounts; pass-through to liability/clearing | [M§24, M§11] |
| Evidence pack: finance/tax configuration; refund and chargeback test; KPI baseline | Per go-live SKU | [M§24] |
| Close evidence | Items in §3.2 "Close evidence" row | [M§11] |

## 8. Completion status

| Section | Status |
|---|---|
| 1–2 Purpose, requirements | Drafted |
| 3.1 Policy matrix | Pending external input (Controller memo) |
| 3.2–3.5 Fields, entities, earning rules, metrics | Drafted |
| 3.6 Account codes | Drafted (ILLUSTRATIVE); GL alignment pending |
| 3.7 Tax scope | Pending external input (D09) |
| 4 Engineering reconciliation | Drafted (flagged, not resolved) |
| 5 Implementation evidence | Drafted (no billing implementation found) |
| 6–7 Open inputs, acceptance | Drafted |

Overall: DRAFT — structurally complete; 10 open inputs.
