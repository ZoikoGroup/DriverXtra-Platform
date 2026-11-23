# Doc COM-10 — Finance Admin Wireframes

| Field | Value |
|---|---|
| Document ID | DX-COMM-COM-10 (proposed; map to canonical engineering register per M§25) |
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Parent | DX-COMM-MASTER-001 v1.0 (23 Oct 2026); v1.1 PROPOSED revision |
| Status | DRAFT — not approved. No content is a live tariff, executed contract, legal/tax opinion or regulatory permission. |
| Proposed owner | CFO (price/economics/accounting sign-off) with CPO (UX & journeys) [M§00 Cross-functional sign-off]; master owner is Global Commercial Director & CFO [M cover] |
| Required approvers | CFO, CPO, CTO (technical controls), Security/Privacy (trust) [M§00]; issue under founder approval [M§25 Dependency-controlled estate] |
| Related decisions | D08 controlled rollout — OPEN; D09 tax/settlement — BLOCKED (needs D01, D02, D04); D04 payment PSP — BLOCKED (needs D01, D02); D10 UX/app parity — OPEN. Master §25 lists these as OPEN; statuses above are set by the document owner. |
| Related tests | test COM-002, test COM-006, test COM-007, test COM-010, test COM-011, test COM-016 [M§24] |

ID-namespace note: "Doc COM-0X" = deliverable; "revenue code COM-0X" = M§04 stream; "test COM-0XX" = M§24 acceptance test.

> **Decision update (19 November 2026, rev. B).** Confirmed direction from Lennox Zoiko: contracting company **Zoiko Mobility Inc.**; initial target markets **USA and UK** (no pilot city or corridor chosen); preferred payment provider **Stripe** (Stripe Connect capabilities, merchant onboarding, settlement and payouts per country still to be verified); finance and insurance handled as a **separate workstream owned by Rithika** (stays OFF here). These are recorded as CONFIRMED DIRECTION, not formal legal or regulatory approvals. Where this document's header or text gives older statuses for D01, D02, D04, D07 or D09, the current register in [../02_Commercial_Decision_Register.md](../02_Commercial_Decision_Register.md) prevails.

## 1. Purpose and scope

Low-fidelity screen inventory for the internal **Finance Admin**, **Commercial Admin** and **Executive / Board** consoles named in M§15, with the finance fields of M§11 and the treasury controls of M§10. This is the "COM-10 Finance Admin Wireframes" deliverable [M§25]. Out of scope: Seller/Dealer, Workshop, Supplier, Fleet, Trust & Compliance and Growth/RevOps consoles [M§15], visual design, and any screen for GATED products (REG-01, REG-02, FIN-01, revenue code COM-04, payment modes E/F) [M§04, M§10]. Screens list only fields the master defines; layout is indicative.

## 2. Requirements carried from the master

| Req ID | Requirement | Source |
|---|---|---|
| FA-01 | Finance Admin minimum screens: billing and collections, tax determinations, PSP reconciliation, payout exceptions, GL posting, credits, deferred revenue, dispute reserves, close pack | [M§15] |
| FA-02 | Commercial Admin minimum screens: revenue scorecard, SKU catalog, rate book, contract terms, promotions, campaigns, sales approvals, forecast drivers | [M§15] |
| FA-03 | Executive / Board minimum screens: GMV vs net revenue, revenue by cohort/vertical/territory, active supply, margin bridge, liquidity, fraud, unit economics, launch-readiness | [M§15] |
| FA-04 | Reuse role-scoped services and design components; no separate application per revenue stream | [M§15 Prioritization constraint] |
| FA-05 | Public pricing and internal finance consoles read the same effective-dated SKU catalog; private negotiated terms not exposed | [M§15 Prioritization constraint] |
| FA-06 | Sensitive payout/tax and individual contact data permission- and purpose-scoped; support access time-bound and logged | [M§15 Prioritization constraint] |
| FA-07 | Minimum finance fields per record type (contract, order/quote, invoice/credit, payout/settlement, GL, close evidence) | [M§11 Financial dimensions] |
| FA-08 | Track gross payer charge, seller payable, platform receivable, taxes, PSP fee, reserves, dispute balance, refund liabilities, payout reference separately | [M§10 Treasury invariants] |
| FA-09 | Daily reconciliation PSP ledger vs order subledger vs invoices vs bank settlement; suspense items need owner, reason and aged action | [M§10] |
| FA-10 | Dual-control treasury administration, bank verification change hold, payee-name matching, payout anomaly controls, immutable adjustment trails | [M§10] |
| FA-11 | No cross-seller negative netting; no payout acceleration without reserve-risk approval | [M§10] |
| FA-12 | Approval chain: Commercial owner proposes; CFO approves; legal/tax approves roles/territory; technical release separates duties | [M§07 Approval] |
| FA-13 | Discount permissions: thresholds, exception expiry and margin floor enforced | [M§07 Discount permissions] |
| FA-14 | Staff actions are commands via an Operations Command Gateway; no direct production SQL; actions risk-classed R0–R4; maker-checker for R3 and above | [E 2.9] |
| FA-15 | Dashboard semantics: GMV is not revenue; lead-influenced value is not GMV; "active" needs contractual and event definition | [M§19] |

## 3. Specification draft

### 3.1 Screen inventory

Permission column: master permission/role named where available; "R-class: TBD (CTO/Security)" where the master and E are silent on the class [E 2.9]. "Dual control" is stated only where M§10 or M§07 requires it.

| # | Console / screen | Purpose | Data shown (master-defined fields only) | Actions | Permission / risk class | Source |
|---|---|---|---|---|---|---|
| F1 | Finance / Billing & collections | Invoices, credits, AR | invoice number/series, entity, tax registration, service period, FX, due date, line-level tax, linked adjustment; AR aging | view; open linked adjustment | R-class: TBD (CTO/Security) | [M§15, M§11] |
| F2 | Finance / Tax determinations | Inspect tax evidence per order/invoice | local tax evidence; `tax_determination_id` (engine evidence + maker/collector role) | view; flag tax exception | Purpose-scoped [M§15]; R-class: TBD | [M§15, M§11, M App C] |
| F3 | Finance / PSP reconciliation | Daily 4-way match | PSP ledger, order subledger, invoices, bank settlement; `settlement_ledger` fields (PSP statement key, matched order, seller/platform liability, payout, reserve, suspense reason) | match; assign suspense owner/reason/action | R-class: TBD | [M§15, M§10, M§21] |
| F4 | Finance / Payout exceptions | Hold/release anomalous payouts | payout/settlement fields: PSP balance account, settlement currency, reserve, charges, exchange spread, external reconciliation key | hold; release (reserve-risk approval) ; escalate | Dual control [M§10]; proposed ≥R3 (CTO/Security to confirm) | [M§15, M§10, M§11] |
| F5 | Finance / Treasury & payee changes | Bank-detail change control | payee name match result; verification hold status; immutable adjustment trail | request change; approve (second person) | Dual control [M§10]; test COM-006; proposed ≥R3 (to confirm) | [M§10, M§24] |
| F6 | Finance / GL posting | Review journals before export | entity/segment/vertical/revenue code, gross/net indicator, deferral period, contra-revenue, AR, bad debt | review; approve manual journal | Manual journal approvals listed as close evidence [M§11]; R-class: TBD | [M§15, M§11, M App B] |
| F7 | Finance / Credits | Credit notes and reversals | `invoice_credit` (issuer, counterparty, tax, invoice number, earning-event link, originals, adjustment); `reversal_of_earning_id` | issue credit against original obligation | R-class: TBD | [M§15, M§07 Refunds, M§21, M App C] |
| F8 | Finance / Deferred revenue | Deferral schedule | deferral period; deferred revenue (account range 2100–2199, ILLUSTRATIVE mapping) | view | R-class: TBD | [M§15, M§11, M App B] |
| F9 | Finance / Dispute reserves | Dispute balance and reserves | dispute balance, reserves, refund liabilities | view; adjust reserve | R-class: TBD | [M§15, M§10] |
| F10 | Finance / Close pack | Month-end evidence | daily matched totals, aging, trial-to-ledger bridge, manual journal approvals, exception log, month-end cutoffs | assemble; sign-off | R-class: TBD | [M§15, M§11] |
| C1 | Commercial / Revenue scorecard | Revenue by line | recognized revenue by line, ARR/MRR, eligible GMV, effective take rate | view | R-class: TBD | [M§15, M§19] |
| C2 | Commercial / SKU catalog | Effective-dated catalog | `commercial_sku`: sku_id, family, fee_basis, entitlement_type, refund_policy_id, scope/status, tax_class, version | propose; approve (CFO) | Separation of duties [M§07]; R-class: TBD | [M§15, M§21, M§07] |
| C3 | Commercial / Rate book | Rate schedules | `rate_schedule`: validity interval, currency, payer, source rank, commissionable base, cap/floor, override approvals | propose; approve (CFO) | Separation of duties [M§07]; R-class: TBD | [M§15, M§21, M§07] |
| C4 | Commercial / Contract terms | Agreements | `commercial_agreement`: parties, role_profile, rate_schedule_id, signature/effective dates, territory, termination, required evidence | view; link schedule | Private negotiated terms not exposed publicly [M§15]; R-class: TBD | [M§15, M§21] |
| C5 | Commercial / Promotions & campaigns | Budgeted promotions | budget owner, redemption cap, fraud velocity, expiry, customer eligibility | create; expire | R-class: TBD | [M§15, M§07 Promotions] |
| C6 | Commercial / Sales approvals | Discount exceptions | discount threshold, exception expiry, margin floor | request; approve | Thresholds: open input (CFO); R-class: TBD | [M§15, M§07 Discount permissions] |
| C7 | Commercial / Forecast drivers | Planning drivers | drivers in Doc COM-12 (ILLUSTRATIVE) | view; edit scenario | R-class: TBD | [M§15, M§17] |
| X1 | Executive / GMV vs net revenue | Separate GMV from revenue | attributed GMV; platform net revenue | view | R-class: TBD | [M§15, M§17, M§19] |
| X2 | Executive / Revenue mix | By cohort/vertical/territory | recognized revenue by cohort, vertical, territory | view | R-class: TBD | [M§15] |
| X3 | Executive / Margin & unit economics | Margin bridge | gross profit, contribution margin, net take rate, dealer CAC payback, fleet unit economics | view | R-class: TBD | [M§15, M§17] |
| X4 | Executive / Supply, liquidity, fraud | Health | active supply; "liquidity" (meaning open: M§19 marketplace-liquidity pillar or financial liquidity); fraud bps of GMV; chargeback rate | view | R-class: TBD | [M§15, M§19] |
| X5 | Executive / Launch-readiness | Gate status | country-gate state per market/vertical; G0–G4 gate evidence (Doc COM-13) | view | R-class: TBD | [M§15, M§21, M§22] |

### 3.2 Key wireframes (low fidelity; at most four)

**W1 — Commercial Admin / Rate book: approval (C3)** [M§07 Approval, M§21 rate_schedule]
```
+-- Rate book ------------------------------------------- [Market v][Vertical v][Status v] --+
| SKU      | Validity     | Currency | Payer | Rank | Base | Cap/Floor | Status   | Author  |
| <sku_id> | from..to     | <ISO>    | <role>| <n>  | <rule>| <min/max>| PROPOSED | <maker> |
+--------------------------------------------------------------------------------------------+
| Detail: override approvals | change is prospective only (price protection)                 |
| [Approve] (enabled only for a CFO-role user who is not the author)  [Reject + reason]      |
+--------------------------------------------------------------------------------------------+
```
**W2 — Finance Admin / PSP reconciliation (F3)** [M§10, M§11, M§21 settlement_ledger]
```
+-- Daily reconciliation  <date> -------------------------------------------------------------+
| Source:   PSP ledger | Order subledger | Invoices | Bank settlement                         |
| Matched:  <total>    | <total>         | <total>  | <total>      Unmatched: <count/value> |
| Suspense items: PSP statement key | matched order | suspense reason | owner | age | action     |
| [Assign owner] [Record reason] [Mark matched]   -- every action written to adjustment trail  |
+---------------------------------------------------------------------------------------------+
```
**W3 — Finance Admin / Payout exception & payee change (F4/F5)** [M§10, test COM-006]
```
+-- Payout exception  <external reconciliation key> ------------------------------------------+
| PSP balance account | settlement currency | reserve | charges | exchange spread               |
| Anomaly: <payout anomaly flag>  | Payee-name match: <result> | Bank change hold: <ON/OFF>    |
| Maker: [Request release]   Checker (different person): [Approve] [Reject]                    |
| Release before reserve-risk approval: BLOCKED                                                |
+---------------------------------------------------------------------------------------------+
```
**W4 — Executive / GMV vs net revenue (X1)** [M§17, M§19 semantics]
```
+-- Executive scorecard  [Territory v][Vertical v][Cohort v][Effective date v] ---------------+
| Attributed GMV (paid via supported flows)   | Platform net revenue (earned, recognized)     |
| Banner: "GMV is not revenue. Lead-influenced value is not GMV."                            |
| Margin bridge: net revenue -> gross profit -> contribution margin                           |
+---------------------------------------------------------------------------------------------+
```
No numeric values appear in wireframes; all figures come from the reporting data owner once defined (§6).

## 4. Engineering reconciliation notes

| Topic | Note | Source |
|---|---|---|
| Context ownership | Staff tools: CTX-18 Admin Ops; payments/ledger: CTX-07; disputes: CTX-12; country rules: CTX-17. Master domains "Settlement Reconciliation", "Finance Subledger", "Billing & Tax" [M§20] have no one-to-one CTX in E 2.4 — mapping open. | [E 2.4, M§20] |
| Admin actions | E requires an Operations Command Gateway and R0–R4 risk classes with maker-checker at R3+, but defines no class per action. Master requires dual control for treasury [M§10] and separation of duties for approvals [M§07]. Mapping proposed in §3.1; not resolved. | [E 2.9, M§07, M§10] |
| Roles | E lists FINANCE_MANAGER, FINANCE_OPS, AUDITOR, MARKETPLACE_ADMIN and "no permanent super-admin"; master names roles by function (CFO, Commercial owner). Role-to-screen mapping open. | [E 2.6, M§07] |
| ID collision | "R0–R4" in E denotes both admin risk classes [E 2.9] and release rings [E 2.10]; the repo uses "R1" for the commercial control plane release. Flagged in Doc COM-13. | [E 2.9, E 2.10, Repo: backend/apps/commercial/README.md] |

## 5. Implementation evidence (repo)

Implementation evidence only; not approval.

| Fact | Path |
|---|---|
| A Commercial Admin console exists with seven panels: SKU Catalogue, Rate Schedules, Role Profiles, Country Gates, Quote Preview (non-binding), Quotes (latest 20, shows terms hash prefix and gate version), Event Outbox. Its on-screen safety banner states "No payments, payouts or settlement happen here." | [Repo: frontend/src/components/platform/CommercialAdminView.tsx] |
| The console is rendered for `activeRole` ADMIN or STAFF on tab `commercial_admin`; backend enforces permissions. | [Repo: frontend/src/app/platform/page.tsx] |
| Admin endpoints under `/api/v1/commercial/admin/` (skus, rate-schedules, role-profiles, country-gates, quote-preview, quotes, outbox). Read access requires platform staff holding any of `commercial.manage`, `commercial.approve`, `country_gate.manage`; APPROVED/RETIRED transitions require `commercial.approve`; gate transitions require `country_gate.manage`. | [Repo: backend/apps/commercial/urls.py, views.py, permissions.py] |
| Maker-checker: SKU and rate authors cannot approve their own record; approval needs an approval reference; the person who recorded FINANCE_SIGNED cannot enable the gate. | [Repo: backend/apps/commercial/services/catalogue.py, rates.py, gates.py] |
| Permissions are seeded by migration and not assigned to any staff sub-role. | [Repo: backend/apps/commercial/README.md] |
| A separate generic maker-checker `ApprovalRequest` (PENDING/APPROVED/REJECTED/CANCELLED/EXECUTED) exists, used for high-value refunds, with an admin approvals view. Its thresholds are environment-configured settings (`MAKER_CHECKER_THRESHOLDS`) and use decimal amounts, not integer minor units [M§07 Currency]. These are implementation defaults, not master-defined thresholds. | [Repo: backend/apps/identity/models.py, backend/apps/identity/approval_service.py, backend/config/settings.py, frontend/src/components/platform/AdminApprovalsView.tsx] |
| None found: Finance Admin screens F1–F10 (billing, tax determinations, PSP reconciliation, payout exceptions, GL, deferred revenue, close pack); Executive console; Operations Command Gateway or R0–R4 risk classes. README "Not in R1" excludes invoicing, ledger, settlement/reconciliation, payouts. | [Repo: backend/apps/commercial/README.md] |

## 6. Open inputs required to complete

| Input | Needed from | Blocks |
|---|---|---|
| R-class (R0–R4) per screen action, and the Operations Command Gateway command list | CTO + Security | §3.1 permission column; maker-checker scope |
| Role-to-screen access matrix (E roles vs master functions) | CTO + CFO + Security/Privacy | F1–F10, C1–C7, X1–X5 |
| Discount thresholds, exception expiry, margin floor | CFO | C6 |
| Reserve-risk approval policy and payout anomaly rules | CFO + Payments (PSP contract, D04) | F4, F5 |
| PSP statement format and settlement fields | Payments + CFO (after D04) | F3, F4 |
| Chart of accounts alignment (App B is ILLUSTRATIVE) | Financial controller | F6, F8 |
| Close calendar and month-end cutoff definition | CFO / financial controller | F10 |
| Definition of "active supply" and other "active" metrics; meaning of "liquidity" on the Executive console | CFO + Commercial | X4 [M§15, M§19] |
| Support-access time limit and logging policy | Security/Privacy | FA-06 |
| CTX owner for Settlement Reconciliation / Finance Subledger / Billing & Tax | CTO | §4 |

## 7. Acceptance / evidence mapping

| Test / evidence | What this doc must supply |
|---|---|
| test COM-002 | Quote screens show immutable accepted snapshot (Quotes panel evidence) |
| test COM-006 | W3 payee-change flow: verification/approval and payout freeze |
| test COM-007 | F6 journal review showing balanced journals |
| test COM-010 | Role/purpose scoping of F2, F4, F5 |
| test COM-011 | F3 suspense queue with owner/reason/age; F4 negative balance exceptions |
| test COM-016 | X1/W4 separation of GMV vs earned revenue |
| Evidence pack: escalation owner; incident/rollback switch; executive approval ticket [M§24] | Screen locations where these are recorded (F4, X5) |

## 8. Completion status

| Section | Status |
|---|---|
| 1–2 Purpose, requirements | Drafted |
| 3 Screen inventory and wireframes | Drafted; permission classes Pending external input |
| 4 Engineering reconciliation | Drafted (conflicts flagged, not resolved) |
| 5 Implementation evidence | Drafted |
| 6 Open inputs | Drafted |
| 7 Acceptance mapping | Drafted |

Overall: DRAFT — structurally complete; 10 open inputs.
