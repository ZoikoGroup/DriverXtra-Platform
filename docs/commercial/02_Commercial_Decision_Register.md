# Commercial Decision Register (D01–D10)

| Field | Value |
|---|---|
| Parent | DX-COMM-MASTER-001 — DriverXtra Global Commercial Estate Master Architecture v1.0 (23 Oct 2026); revision 1.1 PROPOSED DRAFT, rev. B |
| Version / date | 1.1 PROPOSED DRAFT, rev. B — 19 November 2026 |
| Status | Working tracker. Not approved. No decision, price, contract, legal permission or launch is approved by this file. |
| Sources | M = master v1.0; E = engineering reference DriverXtra.docx (Project Concept and Architecture); Repo = implementation evidence in this repository (not approval) |

| Status | Meaning |
|---|---|
| OPEN | Can be worked and closed now. |
| CONFIRMED DIRECTION | Business direction confirmed (source and date recorded). Not a formal legal, regulatory or board approval record. The approvers named in M§25 still record formal closure. |
| RECOMMENDED | Recommendation stands and awaits approver sign-off. |
| BLOCKED | Cannot close until the listed predecessor closes. |
| APPROVED | Only with documented approval evidence. Not used: no such evidence is on file. |

The master's recommendation and approver are preserved verbatim. **No decision is APPROVED:** no signed approval record is in the project files. The 19 November 2026 confirmations are recorded as CONFIRMED DIRECTION, with their source.

| ID | Decision | Recommendation (M§25, preserved) | Approver (M§25) | Status in v1.0 | Status v1.1 | Information required to close | Depends on | Evidence / notes | Formal approval record |
|---|---|---|---|---|---|---|---|---|---|
| D01 | First market | Select one EV/workshop-dense pilot city/corridor after supply, laws, PSP and operational diligence. | Founder + Commercial | OPEN | CONFIRMED DIRECTION: initial target markets USA and UK. Pilot city/corridor: OPEN | Whether a single pilot city/corridor within the USA and/or UK is still required (M§25 recommendation); if so, selection after supply-density diligence (M§18, M§23 P1). Formal decision record by Founder + Commercial. | None. | Confirmation from Lennox Zoiko, 19 Nov 2026, relayed in the project owner's instructions. No signed decision record is in the project files. Code supports IN and GB regional/tax configuration only; there is no US country, USD regional setting or US sales-tax regime [Repo: platform_core/regional/choices.py, platform_core/tax/regimes]. IN is outside the confirmed markets. | None on file |
| D02 | Legal transaction roles | Approve advertising, SaaS, lead and facilitated-commerce role profiles separately. | GC + CFO | OPEN | OPEN (market dependency cleared) | Per-market preliminary role/PSP/consumer-rule memos for the USA and the UK (M§22 days 1–30); merchant-of-record analysis per M§09 profile; agency opinion if the disclosed-agent profile is used. | None (D01 markets confirmed). D09 depends on this. | Role-profile records and approval guards exist with no approved profiles [Repo: backend/apps/commercial]. Draft: Doc COM-02. | None on file |
| D03 | First 8 SKUs | Select listing, workshop, dealer, lead, fleet and EV introductory SKUs for customer tests. | CFO + Commercial | OPEN | OPEN | Willingness-to-pay test design with the M§06 experiment fields; target segments; USD and GBP price books (M§06 requires Finance/Tax sign-off); clarification of 'eight SKUs' against the six families named. | None. | M§06 bands remain ILLUSTRATIVE. Seed loads M§06 SKUs as ILLUSTRATIVE/DRAFT with no rates. Draft: Doc COM-03, Doc COM-08. | None on file |
| D04 | Payment PSP | Evaluate Stripe Connect vs Adyen vs local qualified PSP on corridor/legal roles/chargebacks. | CTO + CFO + GC | OPEN | CONFIRMED DIRECTION: Stripe preferred. Country capability verification OPEN | Verification for the USA and the UK of Stripe Connect capabilities, connected-account (merchant) onboarding, settlement, payout, chargeback, negative-balance and reserve terms against the M§10 modes and the D02 role profiles; Stripe agreement terms. | D02 (role profiles) for the mode mapping. | Confirmation from Lennox Zoiko, 19 Nov 2026, relayed in the project owner's instructions. No signed decision record is in the project files. Existing code has a Stripe provider in test mode and no Stripe Connect connected-account integration; it also has Razorpay (India) [Repo: backend/apps/marketplace/payments]. The R0 safeguards proposal remains open. | None on file |
| D05 | Product safety/fitment | Select verified fitment reference and recall/parts policy partner. | Product + Trust | OPEN | OPEN | Candidate fitment reference datasets and recall sources with licensing terms and USA/UK coverage; parts policy (Appendix D item 7). | None. | Catalogue and part-compatibility models exist [Repo: backend/apps/catalogue]. No reference-data provider recorded. | None on file |
| D06 | Regulated products | Keep finance/insurance referral switch OFF until licensed partnership and perimeter memo. | GC | RECOMMENDED HOLD | RECOMMENDED (hold; switch stays OFF). Separate workstream owned by Rithika | Delivered by the separate finance and insurance workstream (owner: Rithika). GC sign-off of the hold. Activation needs a perimeter memo and licensed-partner agreements (M§13.7, G4). | None. Does not block current work. | Regulated SKUs and gates cannot be approved or enabled in code [Repo: backend/apps/commercial/README.md]. | None on file |
| D07 | Data rights | Approve OEM/partner licensing, analytics and retention uses by country. | GC + Privacy | OPEN | OPEN (country scope: USA, UK) | Data-rights inventory (G0); OEM and partner licence terms; USA and UK retention schedule; AI feature classification (E 2.7 classes A–D). | None (D01 markets confirmed). | No data-licensing implementation found. | None on file |
| D08 | Controlled rollout | Fund G0/G1 only on documented unit economics hypotheses and weekly gate evidence. | Founder + CFO | OPEN | OPEN | Documented unit-economics hypotheses (M§17, ILLUSTRATIVE); weekly gate evidence format (Doc COM-13); funding envelope (not in sources). | D03 informs the hypotheses. | Draft driver book: Doc COM-12. | None on file |
| D09 | Tax/settlement | Sign first country tax, PSP funds and platform invoicing schedule. | Global Tax + CFO | OPEN | BLOCKED | USA and UK tax adviser determinations (marketplace facilitator / deemed supplier, invoicing, seller reporting); Stripe funds flow per market; platform invoicing schedule. | D02; D04 Stripe country verification. | UK VAT engine exists; no US sales-tax implementation [Repo: platform_core/tax/regimes]. Not a tax sign-off. Draft: Doc COM-06, Doc COM-05. | None on file |
| D10 | UX/app parity | Approve single shared public pricing catalog across web, mobile and admin. | Product + CTO | OPEN | OPEN | Confirmation that every channel reads one effective-dated catalog (M§15 prioritization constraint); mobile channel scope. | None. | One catalog serves the public plans endpoint and the admin endpoints [Repo: backend/apps/commercial/urls.py]. No mobile client found in the repository. | None on file |

## Decision history

| Date | Revision | Change | Source |
|---|---|---|---|
| 23 Oct 2026 | v1.0 | D01–D05 and D07–D10 OPEN; D06 RECOMMENDED HOLD. | Master §25 |
| 19 Nov 2026 | v1.1 rev. A | D02, D04, D07 and D09 set to BLOCKED pending D01. No decision approved. | Reconciliation dependency analysis |
| 19 Nov 2026 | v1.1 rev. B | D01 CONFIRMED DIRECTION (USA and UK; pilot city/corridor still OPEN). D04 CONFIRMED DIRECTION (Stripe preferred; country verification OPEN). D02 and D07 back to OPEN. D09 BLOCKED on D02 and the Stripe verification. D06 handled by a separate workstream (Rithika). PD-11 CONFIRMED DIRECTION (Zoiko Mobility Inc.). | Confirmation from Lennox Zoiko, 19 Nov 2026, relayed in the project owner's instructions. No signed decision record is in the project files. |

## Proposed additional decisions (not part of D01–D10)

Raised by the reconciliation. The document owner accepts or rejects them; none is added to the approved register here.

| ID | Topic | Issue / proposal | Proposed approver |
|---|---|---|---|
| PD-11 | Contracting legal entity and corporate identity | CONFIRMED DIRECTION: Zoiko Mobility Inc. (Confirmation from Lennox Zoiko, 19 Nov 2026, relayed in the project owner's instructions. No signed decision record is in the project files.) Open: GC verifies the contracting and invoicing identity for each market (USA, UK). The engineering reference owner corrects E 1.1 'Zoiko Tech Inc.'. | GC |
| PD-12 | Bounded-context ownership of commercial domains | Assign the M§20 domains Commercial Catalog, Contract & Pricing, Lead, Billing & Tax, Settlement Reconciliation, Finance Subledger and evidence_record to existing CTX-01..18 owners or new contexts, keeping single-writer-per-fact (E 2.2). | CTO + CFO |
| PD-13 | Identifier namespace | Deliverable IDs COM-02..COM-13 collide with revenue codes COM-01..COM-04 (M§04) and tests COM-001..COM-016 (M§24). Proposed: prefix deliverables as 'Doc COM-xx' until the canonical register assigns IDs. | Document owner (Global Commercial Director & CFO) |
| PD-14 | Existing payment defaults | The cash-on-delivery default (IN,GB), the Razorpay (India) provider and the test-mode behaviors (R0 proposal) fall outside the confirmed markets (USA, UK) and the preferred PSP (Stripe). Their disposition needs a decision. | CTO + CFO + GC |
| PD-15 | Identity architecture | E 2.6 external IdP and 'no permanent super-admin' against implemented local authentication and an all-permission ADMIN role. | CTO + Security |
| PD-16 | US market enablement in code | The confirmed USA market has no country, regional, currency or sales-tax support in the regional and tax modules (IN/GB only). Scope and sequencing of US support need a decision; no US tax logic may be built before D09 determinations. | CTO + Global Tax |
