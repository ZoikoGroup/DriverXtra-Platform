# Doc COM-12 — KPI and FP&A Driver Book

| Field | Value |
|---|---|
| Document ID | DX-COMM-COM-12 (proposed; map to canonical engineering register per M§25) |
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Parent | DX-COMM-MASTER-001 v1.0 (23 Oct 2026); v1.1 PROPOSED revision |
| Status | DRAFT — not approved. No content is a live tariff, executed contract, legal/tax opinion or regulatory permission. |
| Proposed owner | CFO (price/economics/accounting) [M§00]; account mapping aligned by the financial controller [M App B caveat] |
| Required approvers | CFO; financial controller for App B mapping [M App B]; Founder + CFO for D08 [M§25]; issue under founder approval [M§25] |
| Related decisions | D08 controlled rollout — OPEN; D03 first 8 SKUs — OPEN; D01 first market — OPEN; D09 tax/settlement — BLOCKED (needs D01, D02, D04). Master §25 lists these as OPEN; statuses above are set by the document owner. |
| Related tests | test COM-016, test COM-015, test COM-004 [M§24] |

ID-namespace note: "Doc COM-0X" = deliverable; "revenue code COM-0X" = M§04 stream; "test COM-0XX" = M§24 acceptance test.

> **Decision update (19 November 2026, rev. B).** Confirmed direction from Lennox Zoiko: contracting company **Zoiko Mobility Inc.**; initial target markets **USA and UK** (no pilot city or corridor chosen); preferred payment provider **Stripe** (Stripe Connect capabilities, merchant onboarding, settlement and payouts per country still to be verified); finance and insurance handled as a **separate workstream owned by Rithika** (stays OFF here). These are recorded as CONFIRMED DIRECTION, not formal legal or regulatory approvals. Where this document's header or text gives older statuses for D01, D02, D04, D07 or D09, the current register in [../02_Commercial_Decision_Register.md](../02_Commercial_Decision_Register.md) prevails.

## 1. Purpose and scope

Single reference for commercial metric definitions, illustrative planning drivers and KPI dashboard semantics used by Finance, Commercial and the Executive console (Doc COM-10). This is the "COM-12 KPI & FP&A Driver Book" deliverable [M§25]. All numbers are ILLUSTRATIVE: "Planning only ... not market-validated pricing" [M§00 Decision labels]; "scenario endpoints, not forecasts" [M§17]. No forecast, budget or price is set here. D08 requires G0/G1 funding to rest on "documented unit economics hypotheses and weekly gate evidence" [M§25]; this document supplies the hypothesis register, not the evidence.

## 2. Requirements carried from the master

| Req ID | Requirement | Source |
|---|---|---|
| KP-01 | Use the metric formulas of M§17 (GMV, net revenue, gross profit, contribution, net take rate, lead yield, CAC payback, fleet unit economics, retention, payments loss ratio) | [M§17] |
| KP-02 | Report GMV, attributed partner value, booking value and platform revenue separately | [M§04] |
| KP-03 | Board KPI pillars and guardrails per M§19 | [M§19] |
| KP-04 | Dashboard semantics: GMV ≠ revenue; lead-influenced value ≠ GMV; "active" needs contractual and event definition; negative margin can hide in PSP/disputes/returns/support; forecasts need cohort and effective-date segmentation | [M§19] |
| KP-05 | Pricing experiments record segment, geography, currency, attribution horizon, randomization/holdout, quoted price, conversion, gross margin, churn, complaint rate, counterfactual | [M§06] |
| KP-06 | Pricing governance: quarterly rate hypothesis review; annual contracted renewals subject to local notice and signed schedules | [M§18] |
| KP-07 | Renewals: usage/lead-quality review, ROI pack, supported downgrade, 90/60/30-day enterprise renewal cycle as internal practice | [M§18] |
| KP-08 | Management account codes are a suggested mapping, not a statutory chart of accounts | [M App B caveat] |
| KP-09 | Neither checkout gross sales volume nor PSP-held third-party funds are automatically revenue; ASC 606 / IFRS 15 assessment by controller | [M§11] |

## 3. Specification draft

### 3.1 Metric definitions (verbatim intent of M§17)

| Metric | Formula / definition | Source | Data owner | Event / data source (named in master) |
|---|---|---|---|---|
| Attributed GMV | Value of third-party orders paid through supported flows; excludes lead-implied retail value and duplicate line allocations | [M§17] | Open | Candidate: `payment_intent_ref`, `order_booking` [M§21] |
| Platform net revenue | Earned recognized advertising + SaaS + commission + eligible referrals + API; excludes seller pass-through and unearned balances | [M§17] | Open | Candidate: `earning_event`, `fee.earned` [M§21] |
| Gross profit | Net revenue − direct infrastructure, platform-borne PSP amounts, direct fulfilment/support, fraud/returns loss, other attributable COGS | [M§17] | Open | Not named |
| Contribution margin | Gross profit − variable acquisition, incentives, onboard/verification, claims and support attributable to cohort | [M§17] | Open | Not named |
| Net take rate | Transaction-related net revenue / eligible settled marketplace GMV; not applied to off-platform vehicles and SaaS | [M§17] | Open | Candidate: `settlement_ledger`, `settlement.reconciled` [M§21] |
| Lead yield | Accepted billable leads / verified inbound leads; revenue per accepted lead and invalid-lead rejection tracked | [M§17] | Open | Candidate: `qualified_lead` (billable flag, invalid reason), `lead.accepted` [M§21] |
| Dealer CAC payback | Dealer CAC / monthly dealer contribution profit (not gross MRR) | [M§17] | Open | Not named |
| Fleet unit economics | Monthly recognized fleet revenue per active billed asset less incremental platform, support, data/partner costs | [M§17] | Open | Candidate: `usage_meter_event` [M§21] |
| Retention | Logo churn, GRR, NRR by subscribed cohort; 12-month cohorts | [M§17] | Open | Not named |
| Payments loss ratio | (Confirmed fraud loss + platform-borne chargebacks + concessions) / relevant settled GMV | [M§17] | Open | Candidate: `chargeback.opened` [M§21] |

"Candidate" = the master names the entity/event in M§21 but does not itself link it to the metric; linkage is a proposal for CFO/CTO confirmation.

### 3.2 Worked unit examples — ILLUSTRATIVE, not forecasts [M§17] (arithmetic rechecked)

| Scenario | Master calculation | Recheck | Result |
|---|---|---|---|
| Parts order | $100 × 8% = $8; − $1.80 PSP/direct − $1.20 support/risk → $5 contribution; 62.5% of $8 | 100 × 0.08 = 8.00; 8.00 − 1.80 − 1.20 = 5.00; 5 / 8 = 0.625 | Consistent |
| Workshop booking | $150 × 10% = $15; − $3.50 → $11.50 | 150 × 0.10 = 15.00; 15.00 − 3.50 = 11.50 | Consistent |
| Dealer Growth | $249 − $65 = $184; $1,100 / $184 = 6.0 months | 249 − 65 = 184; 1,100 / 184 = 5.978 → 6.0 (rounded) | Consistent (rounded) |
| Fleet SaaS | 150 × $8 = $1,200; − $350 → $850 | 150 × 8 = 1,200; 1,200 − 350 = 850 | Consistent |

### 3.3 24-month scenario drivers — ILLUSTRATIVE [M§17]

| Driver | Downside | Base | Upside |
|---|---|---|---|
| Dealer paying accounts at month 24 | 100 | 350 | 900 |
| Average dealer MRR, modeled USD | $149 | $249 | $349 |
| Workshops paying at month 24 | 75 | 250 | 650 |
| Average workshop MRR, modeled USD | $39 | $79 | $119 |
| Fleet active paid assets, month 24 | 1,500 | 7,500 | 25,000 |
| Fleet revenue/asset/mo, modeled USD | $5 | $8 | $12 |
| Monthly eligible settled parts GMV at month 24 | $100,000 | $500,000 | $2,000,000 |
| Parts fee rate (net platform) modeled | 6% | 8% | 10% |

Recomputed month-24 monthly run-rate (four streams only) [M§17]:

| Component | Downside | Base | Upside |
|---|---|---|---|
| Dealers (accounts × MRR) | 100 × $149 = $14,900 | 350 × $249 = $87,150 | 900 × $349 = $314,100 |
| Workshops (accounts × MRR) | 75 × $39 = $2,925 | 250 × $79 = $19,750 | 650 × $119 = $77,350 |
| Fleet (assets × $/asset) | 1,500 × $5 = $7,500 | 7,500 × $8 = $60,000 | 25,000 × $12 = $300,000 |
| Parts (rate × GMV) | 6% × $100,000 = $6,000 | 8% × $500,000 = $40,000 | 10% × $2,000,000 = $200,000 |
| **Total (recomputed)** | **$31,325** | **$206,900** | **$891,450** |
| Master stated total | $31,325 | $206,900 | $891,450 |

Recheck findings:
- All three totals reproduce exactly.
- Notation discrepancy: the M§17 text writes the downside terms as "$100×149" and "$75×39". The table defines 100 and 75 as account counts and $149 / $39 as the dollar amounts, so the terms should read "100 × $149" and "75 × $39" (as the base and upside terms do). The totals are unaffected. Proposed for the v1.1 PROPOSED revision.
- Master exclusions apply: ramp curves, churn, refunds, revenue timing, other streams, tax and cost structure [M§17].
- The illustrative driver values sit inside the M§06 ILLUSTRATIVE bands where a band exists (DX-DEAL-LAUNCH/GROWTH, DX-WORKSHOP-SUB $39–$199, DX-FLEET-ASSET $5–$20, DX-PARTS-TAKE 5%–12%) [M§06]. Mapping of the four streams to revenue codes SUB-01, SUB-02, SUB-04 and revenue code COM-01 is a proposed reading of M§04, not stated in M§17.

### 3.4 KPI pillars and dashboard semantics [M§19]

| Pillar | Board metrics / guardrails | Formula defined in master? |
|---|---|---|
| Marketplace liquidity | Eligible active sellers, verified inventory, EV service coverage, search-to-qualified-response, fill rate | No — open |
| Conversion | Quote-to-booking, lead accepted %, listing response time, service completion %, parts return/fitment accuracy | Lead accepted % relates to lead yield [M§17]; others open |
| Revenue | ARR/MRR, recognized revenue by line, eligible GMV, effective take rate, AR aging, deferred revenue | GMV, take rate [M§17]; others open |
| Profitability | Gross margin, variable contribution, CAC, payback, 12-month LTV, churn/NRR by segment | Partly [M§17]; LTV open |
| Consumer outcomes | Cancellation/refund lead time, complaint volume, booking failures, verified review mix, all-in pricing exceptions | No — open |
| Trust & risk | Fraud bps of GMV, counterfeit takedown latency, safety-recall removal, KYB/KYC refresh, chargeback rate | No — open |
| Finance controls | Daily reconciled value %, unapplied suspense age, invoice-error rate, close timeline, tax exception backlog | No — open (inputs in M§10, M§11) |
| Reliability | Checkout/quote availability, webhook recovery, job completion consistency, idempotency violations, audit completeness | No — SLO targets open (Doc COM-13) |
| Growth sustainability | Revenue mix recurring vs transaction, supplier retention, geographic density, partner concentration, compliance gate aging | No — open |

Semantics to enforce on every dashboard [M§19]: GMV is not revenue; lead-influenced downstream purchase value is not GMV; "active" requires a contractual and event definition; negative gross margin can be concealed by ignoring PSP, disputes, returns and support; forecast metrics require cohort and effective-date segmentation.

### 3.5 Management account mapping — ILLUSTRATIVE [M App B]

| Code | Management account / observation |
|---|---|
| 4000–4099 | Advertising / listing recognized revenue; distinct deferred obligation |
| 4100–4199 | Dealer / workshop / supplier / FleetOps subscriptions and related deferred revenue |
| 4200–4299 | Parts, services and authorized transaction facilitation fees (net) |
| 4300–4399 | Eligible partner referrals and sponsorship; regulated partner class separately tracked |
| 4400–4499 | Enterprise API, software and privacy-safe licensed analytics |
| 4900–4999 | Contra-revenue: refunds, approved credits, incentives and performance shortfalls |
| 2100–2199 | Deferred revenue, refunds payable and other customer liabilities as applicable |
| 2300–2399 | Seller payable / PSP settlement clearing where recognized by actual role model |
| 5000–5999 | Direct COGS: PSP borne fees, hosting, verification, variable support, fraud, service fulfilment |
| 7100–7199 | Acquisition/marketing spend; separate from pricing incentives unless policy dictates |
| Z dimension | Entity, region, market, corridor, vertical, sku, channel, seller class, cohort, subscription/transaction, currency |

Caveat (verbatim intent): suggested management mapping, not a statutory chart of accounts; the financial controller must align it with Zoiko Mobility Inc.'s actual consolidated GL and accounting policy [M App B]. Regulated referral revenue (revenue codes REG-01, REG-02) stays OFF/GATED [M§04]; 4300–4399 "regulated partner class" must carry no activity until D06 changes.

### 3.6 Renewals and pricing governance [M§18]

| Item | Rule | Source |
|---|---|---|
| Rate hypothesis review | Quarterly | [M§18] |
| Contracted renewals | Annual, subject to local notice and signed schedules | [M§18] |
| Enterprise renewal cycle | 90/60/30-day, internal practice | [M§18] |
| Renewal inputs | Usage/lead-quality review, ROI pack, supported downgrade | [M§18] |
| Rate changes | Prospective; published or individually notified as required | [M§07 Price protection] |
| No silent double billing on renewal/downgrade/trial cancellation | test COM-015 | [M§24] |

## 4. Engineering reconciliation notes

| Topic | Note | Source |
|---|---|---|
| Analytics boundary | Warehouse fed by events and CDC; analytics may derive but not rewrite orders, payments or trust outcomes. | [E 2.7] |
| Ownership | No CTX in E 2.4 owns "commercial KPI warehouse"; master places it in Operations & Analytics [M§20]. Open. | [E 2.4, M§20] |
| Revenue routes | E 1.8 says source documents "give no prices or rates" and names commissions and advertising only; master adds SaaS, leads, API, data. Master wins; E gap noted. | [E 1.8, M§04] |
| Recovery tier | Warehouse/BI is Tier 3 (RTO/RPO 24 h or less): KPI dashboards are not real-time control evidence. | [E 2.10] |

## 5. Implementation evidence (repo)

Implementation evidence only; not approval.

| Fact | Path |
|---|---|
| Commercial events emitted to the outbox: `commercial.sku.published`, `commercial.sku.retired`, `commercial.rate_schedule.approved`, `commercial.rate_schedule.retired`, `compliance.policy_changed`, `eligibility.suspended`, `quote.issued`, `quote.accepted`. `quote.accepted` payload carries `customer_total_minor` and `platform_fee_minor`. | [Repo: backend/apps/commercial/README.md, backend/apps/commercial/services/quotes.py] |
| None found: earning events, `fee.earned`, ledger, invoicing, subscriptions, leads, settlement, KPI warehouse or dashboards for M§17/M§19 metrics. README "Not in R1" lists earning events, ledger, invoicing, subscriptions, leads, settlement. | [Repo: backend/apps/commercial/README.md] |
| Seed command loads §6 SKUs as ILLUSTRATIVE/DRAFT with no rates, gates or approvals; the illustrative band is a text note never used in calculations. | [Repo: backend/apps/commercial/README.md] |

## 6. Open inputs required to complete

| Input | Needed from | Blocks |
|---|---|---|
| Data owner for each M§17 metric | CFO | §3.1 |
| Event/source linkage for each metric (confirm "candidate" rows) | CFO + CTO | §3.1 |
| Definition of "active" (seller, asset, account, supply) | CFO + Commercial | §3.1, §3.4 [M§19] |
| Formulas for M§19 pillar metrics not defined in M§17 | CFO + owning functions | §3.4 |
| Pilot-market drivers replacing USD illustrative values | CFO + Commercial (after D01, D03) | §3.3 |
| Ramp curves, churn, refunds, timing, cost structure | CFO | Any forecast use of §3.3 |
| Consolidated GL alignment of App B codes | Financial controller | §3.5 |
| Accounting memo (ASC 606 / IFRS 15, principal vs agent) | Controller | Net revenue, take rate |
| Weekly gate-evidence KPI set for D08 | Founder + CFO | G0/G1 funding |
| Correction of "$100×149" / "$75×39" notation | Master document owner | v1.1 PROPOSED revision |

## 7. Acceptance / evidence mapping

| Test / evidence | What this doc must supply |
|---|---|
| test COM-016 | Definitions separating GMV from earned revenue (§3.1, §3.4) |
| test COM-015 | Renewal/notice rules (§3.6) |
| test COM-004 | Lead yield definition and billable-lead rule (§3.1) |
| Evidence pack: defined KPI baseline [M§24] | Baseline metric list and definitions per go-live SKU |

## 8. Completion status

| Section | Status |
|---|---|
| 1–2 Purpose, requirements | Drafted |
| 3 Metrics, examples, scenarios, pillars, codes, governance | Drafted (ILLUSTRATIVE); owners and sources Pending external input |
| 4 Engineering reconciliation | Drafted |
| 5 Implementation evidence | Drafted |
| 6 Open inputs | Drafted |
| 7 Acceptance mapping | Drafted |

Overall: DRAFT — structurally complete; 10 open inputs; 1 master notation discrepancy logged (totals verified).
