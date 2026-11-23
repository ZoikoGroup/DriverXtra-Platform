# Doc COM-09 — Partner Contract Pack

| Field | Value |
|---|---|
| Document ID | DX-COMM-COM-09 (proposed; map to canonical engineering register per M§25) |
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Parent | DX-COMM-MASTER-001 v1.0 (23 Oct 2026); v1.1 PROPOSED revision |
| Status | DRAFT — not approved. No content is a live tariff, executed contract, legal/tax opinion or regulatory permission. |
| Proposed owner | GC + Commercial + CFO — controlled owner of "Seller/dealer/master services agreements and pricing schedules" [M App D]; each other App D item keeps its own controlled owner (§3.1) |
| Required approvers | GC + CFO (D02 role profiles) [M§25]; commercial owner proposes, CFO approves, legal/tax approves roles/territory [M§07 Approval]; GC/Compliance sign-off [M§00] |
| Related decisions | D02 legal transaction roles — BLOCKED (needs D01); D01 first market — OPEN; D04 payment PSP — BLOCKED (needs D01, D02); D06 regulated products — RECOMMENDED (hold; switch stays OFF); D07 data rights — BLOCKED (country scope needs D01); D09 tax/settlement — BLOCKED (needs D01, D02, D04) |
| Related tests | test COM-001, test COM-002, test COM-004, test COM-008, test COM-015 [M§24] |

ID-namespace note: "Doc COM-0X" = deliverable; "revenue code COM-0X" = M§04 stream; "test COM-0XX" = M§24 acceptance test.

**This document contains no contract clauses or legal text.** It defines the pack's structure, required schedules, the data each schedule must carry, and owners. All legal drafting is for counsel.

> **Decision update (19 November 2026, rev. B).** Confirmed direction from Lennox Zoiko: contracting company **Zoiko Mobility Inc.**; initial target markets **USA and UK** (no pilot city or corridor chosen); preferred payment provider **Stripe** (Stripe Connect capabilities, merchant onboarding, settlement and payouts per country still to be verified); finance and insurance handled as a **separate workstream owned by Rithika** (stays OFF here). These are recorded as CONFIRMED DIRECTION, not formal legal or regulatory approvals. Where this document's header or text gives older statuses for D01, D02, D04, D07 or D09, the current register in [../02_Commercial_Decision_Register.md](../02_Commercial_Decision_Register.md) prevails.

## 1. Purpose and scope

Defines the partner contract pack required by the master's contract lifecycle ("Standard MSA/DPA/schedule; plan or rate addenda; authority and expiry; renewals, notice and price-change audit") [M§18] and the policy/contract library checklist [M App D]. It is the "COM-09 Partner Contract Pack" deliverable in M§25. The pack is the source of the `source_contract` dimension every revenue stream must carry [M§04] and of the `commercial_agreement` entity [M§21]. Every launch SKU requires a jurisdiction/version-scoped signed commercial schedule [M§00 Change policy].

Excluded: regulated introducer, cross-border orchestrator and principal-seller arrangements are GATED / OUT OF SCOPE [M§09]; only their placeholder rows appear.

## 2. Requirements carried from the master

| Req ID | Requirement | Source |
|---|---|---|
| CON-R01 | Contract lifecycle: standard MSA/DPA/schedule; plan or rate addenda; authority and expiry; renewals, notice and price-change audit. | [M§18] |
| CON-R02 | Partner pipeline: lead → diligence → economics → technical integration → legal approval → training → launch cohort → quality score. | [M§18] |
| CON-R03 | Each revenue stream carries revenue_code, commercial_product, payer_role, rate_basis, performance_obligation, earning_event, reversal_policy, tax_profile, jurisdiction, source_contract. | [M§04] |
| CON-R04 | Mixed revenue streams: contract must explicitly define non-duplication or affirmative stackable charges. | [M§04], [M§07 Stacking] |
| CON-R05 | `commercial_agreement`: parties, role_profile, rate_schedule_id, signature/effective dates, territory, termination, required evidence. | [M§21] |
| CON-R06 | Event `agreement.executed` (versioned; business ID, correlation ID, actor/source, UTC timestamp, event ID, idempotency key). | [M§21] |
| CON-R07 | Commercial contract finance fields: legal issuer/customer, customer class, rate version, term, jurisdiction, renewal, tax flags, SLA, clawback. | [M§11] |
| CON-R08 | Role profiles: advertising-only, software-only, facilitated order, disclosed commercial agent, regulated introducer, cross-border orchestrator, principal seller (OUT OF SCOPE), each with its mandatory decision. | [M§09] |
| CON-R09 | Quote formation resolves executed partner agreement and effective-dated customer rate card. | [M§07] |
| CON-R10 | Approval: commercial owner proposes; CFO approves; legal/tax approves roles/territory; technical release separates duties. | [M§07 Approval] |
| CON-R11 | Discount permissions: sales cannot create unlimited discretionary terms; thresholds, exception expiry and margin floor enforced. | [M§07 Discount permissions] |
| CON-R12 | Price protection: rate changes prospective, published or individually notified as required. | [M§07] |
| CON-R13 | Partner management: scorecards, performance thresholds, suspension, remediation, reserves, safety incidents. | [M§18] |
| CON-R14 | Pricing governance: quarterly rate hypothesis review; annual contracted renewals subject to local notice and signed schedules. | [M§18] |
| CON-R15 | Private negotiated terms not exposed on public surfaces. | [M§15] |
| CON-R16 | Go-live evidence pack includes a versioned contract and role/legal memo. | [M§24] |
| CON-R17 | Policy precedence (engineering): law, then transaction contract, then DriverXtra policy, then goodwill. | [E 1.6] |

## 3. Specification draft

### 3.1 Pack inventory — Appendix D (all 15 items)

Status for every row: **template required / counsel drafting required. Not drafted.**

| # | Document / policy [M App D] | Controlled owner [M App D] | Pack role |
|---|---|---|---|
| 1 | Public marketplace terms (buyer, private seller, trade seller, workshops, fleets) | General Counsel + Product | Customer-facing terms |
| 2 | Seller/dealer/master services agreements and pricing schedules | GC + Commercial + CFO | Core MSA + schedules (3.2) |
| 3 | Supplier/installer/chargepoint/roadside SLAs and credential warranties | Commercial + Risk | SLA schedule |
| 4 | Licensing/AR/regulated partner contract, remuneration and promotions | Regulatory Counsel | GATED (D06 hold) |
| 5 | Payment PSP platform/seller arrangements, dispute and reserves schedule | Payments + CFO + GC | Payment schedule (D04) |
| 6 | Privacy notices, consent capture, DPA, sub-processor and retention schedule | Privacy + CTO | DPA schedule |
| 7 | Product safety/recall, counterfeit, VIN/fitment and restricted goods policy | Trust + Legal | Incorporated policy |
| 8 | Vehicle advertising all-in price policy and seller/title verification | Legal + Dealer Ops | Incorporated policy |
| 9 | Cancellation/refund/no-show, returns, warranties and credit notes policy | Consumer Legal + CFO | Incorporated policy |
| 10 | Subscription/plan renewal, upgrades, dunning, overage and SLA credits | Finance + Product | Plan addendum (Doc COM-08) |
| 11 | Marketplace tax/deemed-supplier, seller reporting and invoice issuance | Global Tax | Tax schedule (Doc COM-06) |
| 12 | Ads/sponsorship labeling, rankings and lead attribution/dispute rules | Product + Commercial | Lead/ad schedule (Doc COM-07) |
| 13 | Data licensing, AI claims, OEM data, fleet telemetry and aggregate analytics | Privacy + Data Governance | Data-rights schedule (D07) |
| 14 | Incident management, customer care, financial exception and regulatory escalations | Trust + Operations | Operations schedule |
| 15 | AML/sanctions/KYB, complaints, whistleblowing and records retention | Compliance + Security | Compliance schedule |

### 3.2 Pack structure and required schedules (data carried, no text)

| Component | Data the schedule must carry | Source |
|---|---|---|
| A. Master agreement (MSA) | parties (legal issuer/customer), customer class, term, jurisdiction, termination, renewal, notice | [M§18], [M§11], [M§21] |
| B. Role-profile schedule | role_profile; seller_of_record, performer, platform_role, payment_role, tax_party, licensed_partner, issuer, jurisdiction | [M§09], [M§21 party_role_snapshot] |
| C. Pricing / rate schedule | rate_schedule_id, validity interval, currency, payer, source rank, commissionable base, cap/floor, override approvals, rate version | [M§21 rate_schedule], [M§11] |
| D. Revenue-stream schedule | per stream: revenue_code, commercial_product, payer_role, rate_basis, performance_obligation, earning_event, reversal_policy, tax_profile, jurisdiction | [M§04] |
| E. Stacking / non-duplication schedule | explicit combinability per mixed stream | [M§04], [M§07] |
| F. Plan / rate addenda | plan, entitlements, renewal, price-change notice | [M§18], [M§05] |
| G. SLA schedule | SLA, partner acceptance deadline (leads), credentials | [M§11], [M§04 ADV-04], [M App D #3] |
| H. Clawback / reversal schedule | clawback terms; reversal policy | [M§11], [M§04] |
| I. Territory schedule | territory; country activation version | [M§21], [M App C] |
| J. Evidence schedule | required evidence (signature, authority, memo references) | [M§21], [M§18 "authority and expiry"] |
| K. DPA | per App D #6 | [M App D] |
| L. Tax flags | tax flags; invoice issuer | [M§11], [M§07 Invoices] |
| M. Payment schedule | payment mode (A–D only; E and F GATED), disputes, reserves | [M§10], [M App D #5] |

### 3.3 Role-profile templates required

| Role profile [M§09] | Mandatory decision before template use | Status |
|---|---|---|
| Advertising-only | Truthful claims and ad transparency | Template required (D02) |
| Software-only | SaaS supply and data-processing roles mapped | Template required (D02) |
| Facilitated order | Merchant-of-record, checkout liability, tax, returns per corridor | Template required (D02, D04, D09) |
| Disclosed commercial agent | Signed mandate; conflicts, disclosure, local agency law opinion | Template required (D02) |
| Regulated introducer | FCA/US state/EU perimeter, remuneration, marketing, oversight | GATED |
| Cross-border orchestrator | Importer/exporter, customs, title allocation | GATED (G4 scope) |
| Principal seller / owner | Board approval etc. | OUT OF SCOPE |

### 3.4 Lifecycle and controls

| Stage | Control | Source |
|---|---|---|
| Pipeline: lead → diligence → economics | Economics proposed by commercial owner; CFO approves | [M§18], [M§07] |
| Technical integration | Technical release separates duties | [M§07] |
| Legal approval | Legal/tax approves roles/territory | [M§07], [M§18] |
| Execution | `commercial_agreement` record created; `agreement.executed` emitted | [M§21] |
| Training → launch cohort → quality score | Partner scorecards, thresholds, suspension, remediation | [M§18] |
| Discounts / overrides | Thresholds, exception expiry, margin floor; no unlimited discretionary terms | [M§07] |
| Amendment | Prospective only; accepted orders/earned fees never silently rewritten | [M§07] |
| Renewal | Notice, price-change audit; 90/60/30-day enterprise cycle is internal practice | [M§18] |

## 4. Engineering reconciliation notes

| Topic | Note (flagged, not resolved) | Source |
|---|---|---|
| Ownership | E 2.4 has no contract/agreement context. Master §20 "Contract & Pricing" owns agreements, rate books, overrides, quote engine. Adjacent: CTX-17 Global Policy, CTX-15 B2B, CTX-10 Messaging and Documents (document storage). CTO decision; not chosen here. | [E 2.4], [M§20] |
| Maker-checker | Engineering requires maker-checker for R3+ admin actions; consistent with CON-R10 separation of duties. Risk class of contract approval not defined. | [E 2.9] |
| Policy precedence | E 1.6 ranks contract below law and above DriverXtra policy; pack must reflect this ordering — for counsel. | [E 1.6] |
| Corporate identity | Engineering doc says "Zoiko Tech Inc."; master contracting identity is Zoiko Mobility Inc. Contracting entity per country remains open. | [E 1.1], [M§00] |

## 5. Implementation evidence (repo)

| Finding | Path |
|---|---|
| Commercial agreements/contracts are "Not in R1". | [Repo: backend/apps/commercial/README.md] |
| `PartyRoleProfile` carries profile_type, country, vertical, seller_of_record, service_performer, platform_role, payment_role, tax_party, invoice_issuer, licensed_partner_required, legal_memo_reference, effective dates, status; gated types (regulated introducer, cross-border, principal seller, payment modes E/F) cannot be approved. | [Repo: backend/apps/commercial/models.py], [Repo: backend/apps/commercial/choices.py], [Repo: backend/apps/commercial/README.md] |
| `RateSchedule` carries SKU, country, vertical, currency, payer_role, plan_code, priority, effective dates, flat/percentage, min/max fee; approval prospective only. | [Repo: backend/apps/commercial/models.py], [Repo: backend/apps/commercial/README.md] |
| Approvals use `approval_reference` and separation of duties (author ≠ approver) for SKUs and rates. | [Repo: backend/apps/commercial/services/catalogue.py], [Repo: backend/apps/commercial/services/rates.py] |
| No `commercial_agreement` model, no `agreement.executed` event (outbox events list excludes it), no discount-authority thresholds or margin-floor control found. | [Repo: backend/apps/commercial/README.md "Events"], [Repo: backend/apps/commercial/services/quotes.py] |

## 6. Open inputs required to complete

| Input | Needed from | Blocks |
|---|---|---|
| Approved role profiles per corridor | GC + CFO (D02) | 3.3 templates |
| First market / governing law and contracting entity | Founder + Commercial (D01); GC | Component A |
| Templates for all 15 App D items | Each App D controlled owner; counsel drafting | 3.1 |
| PSP and payment schedule | CTO + CFO + GC (D04) | Component M |
| Tax schedule | Global Tax + CFO (D09) | Component L |
| Data-rights schedule | GC + Privacy (D07) | Component K, App D #13 |
| Discount thresholds, exception expiry, margin floor | CFO + Commercial | CON-R11 |
| SLA metrics and lead acceptance deadlines | Commercial + Risk | Component G |
| Clawback terms | CFO + GC | Component H |
| Partner quality-score definition and suspension thresholds | Commercial + Risk | Lifecycle |
| Engineering owner for agreements | CTO | Build allocation |
| Maker-checker risk class for agreement execution | CTO + GC | CON-R10 |

## 7. Acceptance / evidence mapping

| Test / evidence | What this document must supply | Source |
|---|---|---|
| test COM-001 | Executed role/contract required; absent role rejects checkout | [M§24] |
| test COM-002 | Contract amendment does not rewrite accepted quote | [M§24] |
| test COM-004 | Partner SLA definition for lead acceptance | [M§24] |
| test COM-008 | Regulated templates stay GATED; no regulated SKU without signed country gate | [M§24] |
| test COM-015 | Renewal/notice terms in plan addenda | [M§24] |
| Evidence pack | Versioned contract; role/legal memo; executive approval ticket | [M§24] |

## 8. Completion status

| Section | Status |
|---|---|
| 1 Purpose and scope | Drafted |
| 2 Requirements | Drafted |
| 3.1 Pack inventory | Drafted (inventory); all 15 templates Not started (counsel) |
| 3.2 Schedules | Drafted (structure) |
| 3.3 Role-profile templates | Pending external input (D02) |
| 3.4 Lifecycle | Drafted; thresholds pending external input |
| 4 Engineering reconciliation | Drafted; ownership open |
| 5 Implementation evidence | Drafted |
| 6 Open inputs | Drafted |
| 7 Acceptance mapping | Drafted |

Overall: DRAFT — structurally complete; 12 open inputs; no legal text drafted.
