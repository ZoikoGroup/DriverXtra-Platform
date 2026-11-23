# Doc COM-08 — Business Plans and Entitlements

| Field | Value |
|---|---|
| Document ID | DX-COMM-COM-08 (proposed; map to canonical engineering register per M§25) |
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Parent | DX-COMM-MASTER-001 v1.0 (23 Oct 2026); v1.1 PROPOSED revision |
| Status | DRAFT — not approved. No content is a live tariff, executed contract, legal/tax opinion or regulatory permission. |
| Proposed owner | Finance + Product — controlled owner of "Subscription/plan renewal, upgrades, dunning, overage and SLA credits" [M App D] |
| Required approvers | CFO + Commercial (D03) [M§25]; Product + CTO (D10) [M§25]; CFO approves price/economics [M§00], [M§07 Approval] |
| Related decisions | D03 first 8 SKUs — OPEN; D10 UX/app parity — OPEN; D08 controlled rollout — OPEN; D09 tax/settlement — BLOCKED (needs D01, D02, D04) |
| Related tests | test COM-015; also test COM-002, test COM-005, test COM-010 [M§24] |

ID-namespace note: "Doc COM-0X" = deliverable; "revenue code COM-0X" = M§04 stream; "test COM-0XX" = M§24 acceptance test.

> **Decision update (19 November 2026, rev. B).** Confirmed direction from Lennox Zoiko: contracting company **Zoiko Mobility Inc.**; initial target markets **USA and UK** (no pilot city or corridor chosen); preferred payment provider **Stripe** (Stripe Connect capabilities, merchant onboarding, settlement and payouts per country still to be verified); finance and insurance handled as a **separate workstream owned by Rithika** (stays OFF here). These are recorded as CONFIRMED DIRECTION, not formal legal or regulatory approvals. Where this document's header or text gives older statuses for D01, D02, D04, D07 or D09, the current register in [../02_Commercial_Decision_Register.md](../02_Commercial_Decision_Register.md) prevails.

## 1. Purpose and scope

Specifies business plan packaging, entitlement rules, subscription lifecycle and usage metering for the subscription revenue codes SUB-01 … SUB-05 and API-01 [M§04], the plans in M§05 and the subscription SKUs in M§06. It is the "COM-08 Business Plans & Entitlements" deliverable in M§25. Billing mode is reference mode D "Subscription billing" (RECOMMENDED early recurring revenue) [M§10]. Revenue recognition (deferral, proration accounting) belongs to Doc COM-04; tax on SaaS to Doc COM-06.

All prices are ILLUSTRATIVE: "hypotheses for structured willingness-to-pay tests … not … board-approved rates, checkout prices" [M§06].

## 2. Requirements carried from the master

| Req ID | Requirement | Source |
|---|---|---|
| PLAN-R01 | Each plan has explicit seat/asset/site/inventory quotas, usage dimensions, soft and hard limits, upgrade/downgrade policy and suspension behavior. | [M§05] |
| PLAN-R02 | No unearned badge, verification, ranking or safety guarantee is purchased through a higher tier; paid placement separately labeled. | [M§05], [M§16 Service quality] |
| PLAN-R03 | Introductory/free trials may not auto-convert without compliant consent; billing cycles, taxes, notice, prorations, refunds and renewal dates appear before acceptance. | [M§05] |
| PLAN-R04 | Parent/group contracting requires location-level entitlements and affiliate authorization, not cross-tenant data access by default. | [M§05] |
| PLAN-R05 | Subscription states: trial/requested → approved/active → past_due/grace → suspended → cancelled/expired, with historic entitlement ledger. | [M§21] |
| PLAN-R06 | `usage_meter_event`: resource, quantity, actor, dimension, dedup key, time, contract quota, snapshot. | [M§21] |
| PLAN-R07 | `commercial_sku` carries `entitlement_type`. | [M§21] |
| PLAN-R08 | Subscription proration: prorate/credit according to actual executed policy; no hard-coded assumption until rate plan configured. | [M App A] |
| PLAN-R09 | Idempotency for money and subscriptions. | [M§20] |
| PLAN-R10 | Every price card states billing interval, renewal, taxes, mandatory charges, included inventory/seats and applicable territory; no hardcoded globally universal prices. | [M§14] |
| PLAN-R11 | Public pricing and internal consoles read the same effective-dated SKU catalog without exposing private negotiated terms. | [M§15], [M§25 D10] |
| PLAN-R12 | No front-end-only pricing calculations or unapproved hardcoded local fees. | [M§20] |
| PLAN-R13 | Retroactive plan or rate amendments never silently rewrite accepted orders or earned fees; rate changes prospective. | [M§07] |
| PLAN-R14 | SaaS recognition risk: prepaid → deferred revenue; trial/credits/proration. | [M§11] |
| PLAN-R15 | "Active" requires a contractual and event definition; fleet SKU subject to monthly active asset definition, minimum commitment and caps. | [M§19], [M§06 DX-FLEET-ASSET] |
| PLAN-R16 | Renewals: usage/lead-quality review, ROI pack, supported downgrade, 90/60/30-day enterprise renewal cycle as internal practice. | [M§18 Renewals] |
| PLAN-R17 | Pricing governance: quarterly rate hypothesis review; annual contracted renewals subject to local notice and signed schedules. | [M§18] |
| PLAN-R18 | Pricing experiments record segment, geography, currency, attribution horizon, randomization/holdout, quoted price, conversion, gross margin, churn, complaint rate, counterfactual. | [M§06] |
| PLAN-R19 | SaaS and paid advertising are distinct obligations; explicit combinability rules. | [M§07 Stacking] |
| PLAN-R20 | Fleet journey E: corporate KYB → sites/vehicles/seats → subscription order → contracted monthly entitlement → monthly usage/overage invoice. | [M§08 E] |

## 3. Specification draft

### 3.1 Plan catalog (M§05, RECOMMENDED entitlements)

| Plan | Customer | Recommended entitlements (master text) | Candidate SKU (inferred — confirm) |
|---|---|---|---|
| Driver / Buyer | Consumers | Free account, saved garage, browse/compare, verified providers, secure messaging | None (free) |
| Private Seller | Individuals | A-la-carte listing; optional inspection, premium placement; transparent term/renewal | DX-LST-PRIVATE |
| Dealer Launch | Small dealers | Basic storefront, validated profile, inventory limits, lead inbox, standard analytics | DX-DEAL-LAUNCH |
| Dealer Growth | Active dealers | Higher stock cap, feed/API import, lead routing, staff seats, sponsored add-on | DX-DEAL-GROWTH |
| Dealer Enterprise | Groups / OEM dealers | Multi-location stock, SLA, integrations, account management, contract-priced controls | DX-DEAL-ENT |
| Parts Seller | Supplier small/mid | Catalog tools, fitment validation, shipping/returns, paid add-on integrations | DX-SUPPLIER-PRO (to confirm) |
| Workshop Pro | Garages | Bookings, calendar, fixed service menus, enquiry inbox, staff permissions, service metrics | DX-WORKSHOP-SUB |
| FleetOps Business | SMEs / fleets | Vehicle allowance, vendor rules, approvals, reporting, spend tracking | DX-FLEET-ASSET (to confirm) |
| FleetOps Enterprise | Fleet groups | SSO, regional data controls, API, budget owners, audit extracts, committed SLA | DX-FLEET-ASSET or contract (to confirm) |
| Infrastructure API | OEM / B2B | API entitlements, scoped keys, quotas, webhook reliability, usage billing, DPA, SLA | DX-API-BASE |

### 3.2 Subscription SKUs — ILLUSTRATIVE test bands (USD reference only) [M§06]

| SKU | ILLUSTRATIVE base rate | Basis (master) | Revenue code |
|---|---|---|---|
| DX-DEAL-LAUNCH | $49–$149 / mo | Small dealer account; fixed active stock cap | SUB-01 |
| DX-DEAL-GROWTH | $149–$499 / mo | Expanded stock, feed, lead queue, analytics; usage beyond cap priced separately | SUB-01 |
| DX-DEAL-ENT | Custom $1,000+ / mo | Group, integration, SLA, multi-site; no universal minimum implied | SUB-01 |
| DX-WORKSHOP-SUB | $39–$199 / mo | Workspace, calendar, lead analytics, local staff seats | SUB-02 |
| DX-SUPPLIER-PRO | $79–$299 / mo | Catalog tools, feeds, order ops; commerce fees separate | SUB-03 |
| DX-FLEET-ASSET | $5–$20 / active asset / mo | Active asset definition, minimum commitment, caps | SUB-04 |
| DX-API-BASE | $500–$2,500 / mo | API tier plus contracted usage | API-01 |

Revenue-code mapping for DX-WORKSHOP-SUB, DX-SUPPLIER-PRO, DX-FLEET-ASSET, DX-API-BASE is by name correspondence to M§04; confirm (open input). SUB-05 (OEM/enterprise software) has no M§06 SKU.

### 3.3 Entitlement model (structure; values are open inputs)

| Element | Required per plan | Source |
|---|---|---|
| Quota dimensions | seat / asset / site / inventory | [M§05] |
| Usage dimensions | per plan (e.g., API usage, overage) | [M§05], [M§06] |
| Soft and hard limits | per dimension | [M§05] |
| Upgrade / downgrade policy | per plan | [M§05], [M§24 test COM-015] |
| Suspension behavior | per plan, linked to past_due/grace/suspended | [M§05], [M§21] |
| Group scope | location-level entitlements + affiliate authorization | [M§05] |
| Entitlement ledger | historic, retained through cancellation/expiry | [M§21] |
| Metering | `usage_meter_event` with dedup key and contract quota snapshot | [M§21] |

### 3.4 Lifecycle and billing controls

| Transition | Control | Source |
|---|---|---|
| trial → active | Requires compliant consent; no silent auto-conversion | [M§05], [M§24 test COM-015] |
| active (plan change) | Prorate/credit per executed policy only; no hard-coded proration | [M App A] |
| renewal | Notice per local rules and signed schedule | [M§18], [M§24 test COM-015] |
| past_due → grace → suspended | Dunning policy required (App D item) | [M§21], [M App D] |
| cancelled / expired | No double billing; entitlement history kept | [M§21], [M§24 test COM-015] |
| any billing call | Idempotent | [M§20], [M§24 test COM-005] |

Proration example (ILLUSTRATIVE): "Dealer month billed $249; plan change mid-cycle" → behavior per executed policy [M App A]. Dealer Growth $249 MRR worked example is ILLUSTRATIVE, not a forecast [M§17].

## 4. Engineering reconciliation notes

| Topic | Note (flagged, not resolved) | Source |
|---|---|---|
| Ownership | E 2.4 has no billing/subscription context. Master §20 "Billing & Tax" owns subscriptions and usage meters. Adjacent: CTX-07 Payments and Ledger; CTX-15 B2B ("enterprise capabilities"); CTX-01 Identity and Orgs (organizations/sites). CTO decision. | [E 2.4], [M§20] |
| Enforcement point | Entitlement checks would need to integrate with the PEP/PDP authorization model (deny by default); approach not specified in either source. | [E 2.6] |
| Seats vs roles | Engineering org roles (e.g., ORG_ADMIN, FLEET_MANAGER) are authorization roles, not billed seats; mapping is open. | [E 2.6], [M§05] |
| Money and IDs | Integer minor units + ISO currency, idempotency, outbox — consistent with master. | [E 2.2], [M§07], [M§20] |
| Corporate identity | Engineering doc says "Zoiko Tech Inc."; master: Zoiko Mobility Inc. | [E 1.1], [M§00] |

## 5. Implementation evidence (repo)

| Finding | Path |
|---|---|
| Subscriptions/entitlements are "Not in R1". | [Repo: backend/apps/commercial/README.md] |
| `EntitlementTypeChoices`: NONE, LISTING, INVENTORY_SLOT, SEAT, ASSET, SITE, API_QUOTA, CAMPAIGN. `BillingIntervalChoices`: ONE_TIME, PER_EVENT, MONTHLY, ANNUAL. | [Repo: backend/apps/commercial/choices.py] |
| `CommercialSku` has single `entitlement_type` and `billing_interval` fields (matches M§21 `entitlement_type`); no quota values, soft/hard limits, or upgrade/downgrade policy fields. | [Repo: backend/apps/commercial/models.py] |
| Fee bases `RECURRING_FLAT`, `PER_ACTIVE_ASSET` are quotable; `USAGE_METERED` and `CUSTOM_CONTRACT` are labeled "not quotable in R1". | [Repo: backend/apps/commercial/choices.py] |
| `RateSchedule.plan_code` (blank = any plan) used in rate resolution. | [Repo: backend/apps/commercial/models.py] |
| Gate capability `SUBSCRIPTION_BILLING` and payment role `SUBSCRIPTION_BILLING` (mode D) exist as choices; no subscription service consumes them. | [Repo: backend/apps/commercial/choices.py], [Repo: backend/apps/commercial/services/] |
| Seed maps subscription SKUs to entitlement types (e.g., DX-DEAL-LAUNCH/GROWTH → INVENTORY_SLOT; DX-DEAL-ENT → SITE; DX-WORKSHOP-SUB → SEAT; DX-FLEET-ASSET → ASSET; DX-API-BASE → API_QUOTA; DX-SUPPLIER-PRO → NONE), all MONTHLY, ILLUSTRATIVE, no rates. These mappings are implementation choices not stated in M§06; confirm under D03. | [Repo: backend/apps/commercial/management/commands/seed_illustrative_commercial_catalogue.py] |
| No subscription model, state machine, `usage_meter_event`, dunning, proration or `POST /v1/billing/subscriptions` endpoint found. | Search of `backend/apps`, `backend/platform_core` |

## 6. Open inputs required to complete

| Input | Needed from | Blocks |
|---|---|---|
| First 8 SKUs selection | CFO + Commercial (D03) | Plan catalog |
| Plan → SKU → revenue-code mapping confirmation | CFO + Commercial | 3.1, 3.2 |
| Quota values, usage dimensions, soft/hard limits per plan | Product + Finance | 3.3 |
| Upgrade/downgrade and proration policy | Finance + Product (App D) | App A vector, test COM-015 |
| Trial terms and consent mechanism per country | Product + GC | trial → active |
| Renewal notice rules per country | GC (D01 corridor) | test COM-015 |
| Dunning, grace length, suspension behavior | Finance + Product | past_due/suspended |
| "Monthly active asset" definition, minimum commitment, caps | CFO + Commercial | DX-FLEET-ASSET |
| SLA credits policy | Finance + Product (App D) | Enterprise plans |
| Billing PSP for mode D | CTO + CFO + GC (D04) | Subscription billing |
| Shared catalog across web/mobile/admin | Product + CTO (D10) | PLAN-R11 |
| Engineering owner context for billing/entitlements | CTO | Build allocation |
| SUB-05 SKU definition | CFO + Commercial | Enterprise software |

## 7. Acceptance / evidence mapping

| Test / evidence | What this document must supply | Source |
|---|---|---|
| test COM-015 | Renewal/downgrade and trial-cancellation golden cases; no silent double billing; notice rules | [M§24] |
| test COM-002 | Plan change does not rewrite accepted snapshot | [M§24] |
| test COM-005 | Duplicate webhooks do not duplicate invoices | [M§24] |
| test COM-010 | Fleet analytics and group entitlements stay tenant/role-scoped | [M§24], [M§05] |
| App A Subscription proration | Executed proration policy as golden vector | [M App A] |
| Evidence pack | Fee specification, versioned contract, disclosure screenshots (price cards per M§14), golden vectors, KPI baseline (MRR, churn, NRR) | [M§24], [M§19] |

## 8. Completion status

| Section | Status |
|---|---|
| 1 Purpose and scope | Drafted |
| 2 Requirements | Drafted |
| 3.1 Plan catalog | Drafted; SKU mapping pending external input |
| 3.2 SKUs | Drafted (ILLUSTRATIVE) |
| 3.3 Entitlement model | Drafted (structure); values pending external input |
| 3.4 Lifecycle controls | Drafted; policies pending external input |
| 4 Engineering reconciliation | Drafted; ownership open |
| 5 Implementation evidence | Drafted |
| 6 Open inputs | Drafted |
| 7 Acceptance mapping | Drafted |

Overall: DRAFT — structurally complete; 13 open inputs.
