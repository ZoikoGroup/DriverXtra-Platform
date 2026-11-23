# G0–G3 Launch Readiness Tracker

| Field | Value |
|---|---|
| Parent | DX-COMM-MASTER-001 — DriverXtra Global Commercial Estate Master Architecture v1.0 (23 Oct 2026); revision 1.1 PROPOSED DRAFT, rev. B |
| Version / date | 1.1 PROPOSED DRAFT, rev. B — 19 November 2026 |
| Status | Working tracker. Not approved. No decision, price, contract, legal permission or launch is approved by this file. |
| Sources | M = master v1.0; E = engineering reference DriverXtra.docx (Project Concept and Architecture); Repo = implementation evidence in this repository (not approval) |

Gate scope and business decisions are quoted from M§22. Everything GATED stays disabled: G4 (finance/insurance, controlled vehicle settlement, cross-border), regulated SKUs REG-01, REG-02, FIN-01 and revenue code COM-04, and payment modes E and F.
**Every gate is NOT MET.**

| Gate | Scope / must-pass criteria (M§22) | Business decision (M§22) | Required deliverables | Dependencies | Evidence required | Responsible owner | Outstanding blockers | Status |
|---|---|---|---|---|---|---|---|---|
| G0 — Board design freeze | Legal role matrix, vertical scope, target pilot market, contracting legal entity, tax map, PSP viability, source architecture and data-rights inventory. | Authorize detailed build and pilot envelope; not market launch. | Legal role matrix for the USA and the UK (Doc COM-02); vertical scope frozen (M§03); target markets USA and UK (D01 direction confirmed; pilot city/corridor open); contracting entity Zoiko Mobility Inc. (direction confirmed; per-market verification by GC); tax map for the USA and the UK (Doc COM-06); PSP viability: Stripe preferred, country capability verification (D04); source architecture (M§20.3; 25-document series outstanding); data-rights inventory (D07). | D02, D04 verification, D07, D09, PD-12. | Signed preliminary role/PSP/consumer memo (M§22 days 1–30); decision records for D01–D09; reconciliation sign-off by CTO. | CEO/CFO/GC/Product (M§22 days 1–30) | D02 role memos (USA, UK) not started; Stripe Connect verification open; D07 open; D09 blocked; 25-document series unavailable; formal decision records for the 19 Nov confirmations not yet filed. | NOT MET |
| G1 — Controlled pilot | EV services and verified workshops/dealers: accurate listings, consented lead capture, subscriptions/lead billing, risk controls and reconciliation. | Activate market only after contracts, support desk and measurement readiness. | Approved SKUs and rates for the pilot (D03); lead model and billing (Doc COM-07); plans and subscriptions (Doc COM-08); contracts (Doc COM-09); quote UX (Doc COM-11); KPI baseline (Doc COM-12); gate evidence (Doc COM-13); enabled country gate per M§21. | G0; D03, D08, D10; Appendix D items 1, 2, 3, 6, 10 and 12. | M§24 minimum evidence pack for each go-live SKU; tests mapped to G1 below. | CTO/Engineering/Design (days 31–60); CTO/CFO/Commercial/Compliance (days 61–90) | G0 not met; leads, subscriptions, invoicing, earning events and reconciliation are not implemented (commercial README 'Not in R1'); no Appendix D documents. | NOT MET |
| G2 — Transactional commerce | Parts/booking payments, seller KYB, fitment, returns, PSP settlement, tax and dispute resilience; vendor coverage. | Enable per vertical + payment corridor after operational rehearsals. | PSP selection and settlement design (Doc COM-05); tax determinations (Doc COM-06); revenue recognition memo (Doc COM-04); fitment reference (D05); refund/returns policy (Appendix D item 9); R0 payment safeguards resolved (PD-14). | G1; D04, D05, D09; Appendix D items 5, 7, 9 and 11. | M§24 evidence pack, including the webhook/reconciliation and refund/chargeback tests and golden vectors (M App A). | Finance / CTO (M§23 checkout/ledger); Trust / Engineering (fitment) | D09 blocked; Stripe Connect not integrated (provider in test mode only); no US regional or tax support (PD-16); R0 proposal open. | NOT MET |
| G3 — Enterprise marketplace | Dealer inventory integrations, fleet subscriptions, group accounts, B2B procurement, enterprise APIs and SLAs. | Expand to proven profitable cohorts and high-quality suppliers. | Enterprise plans and entitlements (Doc COM-08); API terms and quotas; data rights (D07); enterprise contract schedules (Doc COM-09). | G2 evidence of profitable cohorts (Doc COM-12); D07. | Cohort economics (M§17), SLA evidence, API contract tests. | CEO / CTO; CFO / RevOps | Dependent on G1 and G2; D07 blocked. | NOT MET |

## Engineering acceptance tests (M§24): proposed gate mapping

"First gate" is the earliest gate whose scope needs the test. This mapping is proposed for the CTO and gate owners. Repository evidence shows only whether a test exists, not that a gate passed.

| Test | First gate (proposed) | What must be shown | Repository evidence |
|---|---|---|---|
| COM-001 | G1 | Quote rejection matrix for gate, role, SKU and rate absence | Covered by backend/tests/test_commercial_control_plane.py (header maps COM-001). Commercial test files: 61 passed, 19 Nov 2026 |
| COM-002 | G1 | Immutability after rate, plan and promotion changes | Covered by test_commercial_control_plane.py (COM-002); passed 19 Nov 2026 |
| COM-003 | G2 | Golden fee vectors incl. partial refund | Fee-base golden vectors covered (COM-003), passed 19 Nov 2026; partial-refund handling not implemented |
| COM-004 | G1 | Lead single acceptance, dedupe, fraud and territory | None; leads not implemented |
| COM-005 | G1 | Duplicate PSP webhooks create no duplicate effects (subscription billing in G1; orders in G2) | Not verified for the commercial domain; marketplace PaymentWebhookEvent exists |
| COM-006 | G2 | Payout account change verification and freeze | None in the commercial domain |
| COM-007 | G2 | Balanced subledger journals across lifecycle | None; ledger not implemented |
| COM-008 | G1 | Regulated SKU/gate cannot be enabled | Covered by test_commercial_control_plane.py (COM-008); passed 19 Nov 2026 |
| COM-009 | G1 | Seller-of-record and sponsored labels consistent across surfaces | None |
| COM-010 | G1 | Tenant/role scoping; token redaction in logs | Not verified |
| COM-011 | G1 | Owned exceptions for unmatched items, drift and aged AR | None; reconciliation not implemented |
| COM-012 | G2 | Recall/counterfeit disables listings with outreach evidence | None |
| COM-013 | G1 (USA is a confirmed market) | All-in consumer price incl. mandatory dealer fees | None |
| COM-014 | G1 | WCAG 2.2 AA automated and manual critical journeys | None |
| COM-015 | G1 | Renewal/downgrade/trial cancellation without double billing | None; subscriptions not implemented |
| COM-016 | G1 | GL posts only earned platform revenue | None; GL export not implemented |

## M§24 minimum evidence pack (required for each go-live SKU)

Approved fee specification · role/legal memo · finance/tax configuration · versioned contract · end-user disclosure screenshots · golden calculation vectors · webhook/reconciliation test · refund and chargeback test · accessibility test · escalation owner · incident/rollback switch · KPI baseline · executive approval ticket. **No SKU currently has a complete pack.**
