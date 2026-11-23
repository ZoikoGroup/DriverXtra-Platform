# Supporting Documents Tracker (Doc COM-02 to COM-13)

| Field | Value |
|---|---|
| Parent | DX-COMM-MASTER-001 — DriverXtra Global Commercial Estate Master Architecture v1.0 (23 Oct 2026); revision 1.1 PROPOSED DRAFT, rev. B |
| Version / date | 1.1 PROPOSED DRAFT, rev. B — 19 November 2026 |
| Status | Working tracker. Not approved. No decision, price, contract, legal permission or launch is approved by this file. |
| Sources | M = master v1.0; E = engineering reference DriverXtra.docx (Project Concept and Architecture); Repo = implementation evidence in this repository (not approval) |

**Pre-check:** before drafting, the repository was searched for existing deliverables. No COM-02..COM-13 documents existed. Related existing material is referenced, not duplicated: `backend/apps/commercial/README.md` (R1 control plane), `docs/proposals/R0-payment-safeguards.md`, `docs/auth-design.md`.

**Identifier note (PD-13):** "Doc COM-xx" are deliverables (M§25). Revenue codes COM-01..COM-04 (M§04) and tests COM-001..COM-016 (M§24) are different things.

Owners are proposed from M§00, §22, §23 and Appendix D and must be mapped to the canonical engineering register (M§25). Each document's own "Completion status" section lists its open inputs.

| Deliverable | Title | File | Proposed owner | Required approvers | Master sources | Decisions | Status |
|---|---|---|---|---|---|---|---|
| Doc COM-02 | Country Role & Funds Flow | [com/COM-02_Country_Role_and_Funds_Flow.md](com/COM-02_Country_Role_and_Funds_Flow.md) | GC / Compliance + CFO | GC, CFO, Payments | M§02, §09, §10, §21, §22 | D01, D02, D04, D09 | 0.1 DRAFT — not approved |
| Doc COM-03 | SKU / Pricing Rules | [com/COM-03_SKU_and_Pricing_Rules.md](com/COM-03_SKU_and_Pricing_Rules.md) | CFO + Commercial | CFO; GC/Tax for roles and territory (M§07 Approval) | M§04, §06, §07, App A, App C | D03, D10 | 0.1 DRAFT — not approved |
| Doc COM-04 | Billing & Revenue Recognition | [com/COM-04_Billing_and_Revenue_Recognition.md](com/COM-04_Billing_and_Revenue_Recognition.md) | CFO / Controller | CFO; signed accounting memo (M§11) | M§11, §17, §21, App B | D08, D09 | 0.1 DRAFT — not approved |
| Doc COM-05 | Marketplace Settlement / PSP | [com/COM-05_Marketplace_Settlement_and_PSP.md](com/COM-05_Marketplace_Settlement_and_PSP.md) | Payments + CFO | CTO, CFO, GC (D04) | M§10, §21, §23, §24 | D04, D09 | 0.1 DRAFT — not approved |
| Doc COM-06 | Tax / Seller Reporting | [com/COM-06_Tax_and_Seller_Reporting.md](com/COM-06_Tax_and_Seller_Reporting.md) | Global Tax | Global Tax, CFO (D09) | M§09, §11, §07, App A, App E | D01, D09 | 0.1 DRAFT — not approved |
| Doc COM-07 | Lead / Referral Attribution | [com/COM-07_Lead_and_Referral_Attribution.md](com/COM-07_Lead_and_Referral_Attribution.md) | Commercial + Product | Product + Commercial (App D item 12); Regulatory Counsel for REG-xx | M§04, §08A, §18, §21, App A | D03, D06 | 0.1 DRAFT — not approved |
| Doc COM-08 | Business Plans & Entitlements | [com/COM-08_Business_Plans_and_Entitlements.md](com/COM-08_Business_Plans_and_Entitlements.md) | Finance + Product | CFO, Product | M§05, §06, §21, App A | D03, D10 | 0.1 DRAFT — not approved |
| Doc COM-09 | Partner Contract Pack | [com/COM-09_Partner_Contract_Pack.md](com/COM-09_Partner_Contract_Pack.md) | GC + Commercial + CFO | GC, CFO; qualified local counsel | M§09, §18, §21, App D | D02, D06, D07 | 0.1 DRAFT — not approved |
| Doc COM-10 | Finance Admin Wireframes | [com/COM-10_Finance_Admin_Wireframes.md](com/COM-10_Finance_Admin_Wireframes.md) | CPO + CFO | CPO, CFO, CTO/Security (risk classes) | M§15, §10, §11; E 2.9 | D10 | 0.1 DRAFT — not approved |
| Doc COM-11 | Quote / Checkout UX | [com/COM-11_Quote_and_Checkout_UX.md](com/COM-11_Quote_and_Checkout_UX.md) | CPO + CTO | CPO, CTO, Legal (disclosures) | M§07, §08, §14, App A, App C | D03, D10 | 0.1 DRAFT — not approved |
| Doc COM-12 | KPI & FP&A Driver Book | [com/COM-12_KPI_and_FPA_Driver_Book.md](com/COM-12_KPI_and_FPA_Driver_Book.md) | CFO | CFO, Founder (D08) | M§17, §18, §19, App B | D03, D08 | 0.1 DRAFT — not approved |
| Doc COM-13 | End-to-End QA + Launch Gate | [com/COM-13_End_to_End_QA_and_Launch_Gate.md](com/COM-13_End_to_End_QA_and_Launch_Gate.md) | CTO + CFO + GC | Gate owners per M§22/§23 | M§21, §22, §24, App A; E 2.9, 2.10 | D01–D10 | 0.1 DRAFT — not approved |
