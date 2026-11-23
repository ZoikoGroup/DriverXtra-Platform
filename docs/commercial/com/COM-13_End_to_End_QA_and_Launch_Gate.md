# Doc COM-13 — End-to-End QA and Launch Gate

| Field | Value |
|---|---|
| Document ID | DX-COMM-COM-13 (proposed; map to canonical engineering register per M§25) |
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Parent | DX-COMM-MASTER-001 v1.0 (23 Oct 2026); v1.1 PROPOSED revision |
| Status | DRAFT — not approved. No content is a live tariff, executed contract, legal/tax opinion or regulatory permission. |
| Proposed owner | CTO (technical controls) [M§00]; Days 61–90 "gate review" owned by CTO/CFO/Commercial/Compliance [M§22 90-day sequence] |
| Required approvers | CEO/Founder, CFO, GC/Compliance, CTO, CPO, Security/Privacy [M§00 Cross-functional sign-off]; Founder + CFO for D08 [M§25]; "executive approval ticket" per go-live SKU [M§24]; issue under founder approval [M§25] |
| Related decisions | D08 controlled rollout — OPEN; D01 first market — OPEN; D04 payment PSP — BLOCKED (needs D01, D02); D06 regulated products — RECOMMENDED (hold; switch stays OFF); D09 tax/settlement — BLOCKED (needs D01, D02, D04). Master §25 lists these as OPEN / RECOMMENDED HOLD; statuses above are set by the document owner. |
| Related tests | test COM-001 … test COM-016 [M§24] |

ID-namespace note: "Doc COM-0X" = deliverable; "revenue code COM-0X" = M§04 stream; "test COM-0XX" = M§24 acceptance test.

**Naming collision (flag):** "R0–R4" has three meanings across sources — E release rings (R0 CI … R4 multi-cell) [E 2.10]; E admin action risk classes R0–R4 [E 2.9]; and repository release labels ("R1 commercial control plane", "R0 — Payment test-mode defaults" proposal) [Repo: backend/apps/commercial/README.md, docs/proposals/R0-payment-safeguards.md]. In this document: release rings are written **"ring R0–R4"**, risk classes **"risk class R0–R4"**, repository labels **"repo release R0/R1"**. Repo "R1" is not ring R1 and not a gate.

> **Decision update (19 November 2026, rev. B).** Confirmed direction from Lennox Zoiko: contracting company **Zoiko Mobility Inc.**; initial target markets **USA and UK** (no pilot city or corridor chosen); preferred payment provider **Stripe** (Stripe Connect capabilities, merchant onboarding, settlement and payouts per country still to be verified); finance and insurance handled as a **separate workstream owned by Rithika** (stays OFF here). These are recorded as CONFIRMED DIRECTION, not formal legal or regulatory approvals. Where this document's header or text gives older statuses for D01, D02, D04, D07 or D09, the current register in [../02_Commercial_Decision_Register.md](../02_Commercial_Decision_Register.md) prevails.

## 1. Purpose and scope

Defines the QA catalogue and per-gate launch checklist that tie M§24 acceptance tests and the minimum evidence pack to the M§22 gates. This is the "COM-13 End-to-End QA + Launch Gate" deliverable [M§25]. In scope: gates G0–G3; G4 "Regulated/global expansion" is **GATED and out of current scope** [M§22, M§00 GATED, D06]. "Feature complete" is insufficient without commercial proof [M§24]. Pass/fail results are not recorded here; they will be added by the document owner.

## 2. Requirements carried from the master

| Req ID | Requirement | Source |
|---|---|---|
| QA-01 | Gates G0–G4 with scope/must-pass criteria and business decision | [M§22] |
| QA-02 | "Global-first" ≠ simultaneous activation; activate only markets with validated payment/compliance/vendor density | [M§22] |
| QA-03 | 90-day G0→G1 sequence (relative, not a promised launch date) | [M§22] |
| QA-04 | Must-pass release tests COM-001..COM-016 | [M§24] |
| QA-05 | Minimum evidence pack per go-live SKU | [M§24] |
| QA-06 | Appendix A golden vectors | [M App A] |
| QA-07 | Country gate: designed → legally_reviewed → partner_verified → finance_signed → technical_rehearsed → enabled; suspended/withdrawn | [M§21] |
| QA-08 | Every launch SKU needs jurisdiction/version-scoped signed schedule and regression-tested quote, invoice, refund, tax, payout and ledger controls | [M§00 Change policy] |
| QA-09 | SLOs and synthetic monitoring for quote availability, checkout, order transitions, PSP feed timeliness, invoicing, dispute queues | [M§20] |
| QA-10 | SLOs and error budgets govern releases; trace_id, correlation_id, request_id on every request | [E 2.9] |
| QA-11 | Release rings: ring R0 CI, ring R1 non-production, ring R2 production canary, ring R3 cell rollout, ring R4 multi-cell, with rollback | [E 2.10] |
| QA-12 | Recovery tiers (RTO/RPO): Tier 0 orders/payments/ledger/IAM/jurisdiction control ≤30 min/≤5 min; Tier 1 listings/search/checkout/bookings/messaging/B2B ≤2 h/≤15 min; Tier 2 notifications/admin read models ≤4 h/≤1 h; Tier 3 warehouse/BI ≤24 h/≤24 h | [E 2.10] |
| QA-13 | No production data in lower environments | [E 2.10] |

## 3. Specification draft

### 3.1 Gates [M§22]

| Gate | Scope / must-pass criteria | Business decision | Status in this doc |
|---|---|---|---|
| G0 Board design freeze | Legal role matrix, vertical scope, target pilot market, contracting legal entity, tax map, PSP viability, source architecture, data-rights inventory | Authorize detailed build and pilot envelope; not market launch | In scope |
| G1 Controlled pilot | EV services and verified workshops/dealers: accurate listings, consented lead capture, subscriptions/lead billing, risk controls, reconciliation | Activate market only after contracts, support desk and measurement readiness | In scope |
| G2 Transactional commerce | Parts/booking payments, seller KYB, fitment, returns, PSP settlement, tax and dispute resilience; vendor coverage | Enable per vertical + payment corridor after operational rehearsals | In scope |
| G3 Enterprise marketplace | Dealer inventory integrations, fleet subscriptions, group accounts, B2B procurement, enterprise APIs and SLAs | Expand to proven profitable cohorts and suppliers | In scope |
| G4 Regulated/global expansion | Finance/insurance referrals, controlled vehicle settlement, cross-border, additional countries/data regions | Separate signed legal licenses and economics per corridor | **GATED — out of current scope** |

90-day G0→G1 sequence (relative) [M§22]: Days 1–30 — pilot geography/corridor, preliminary role/PSP/consumer memo, SKU schema, EV/workshop partner criteria, target economics (CEO/CFO/GC/Product). Days 31–60 — quote/contract/lead domain, onboarding, disclosure, pricing UX, seller admin, webhooks/CRM, billing/reconciliation design (CTO/Engineering/Design). Days 61–90 — sandbox rehearsal, revenue and fraud dashboards, support incidents, partner training, price experiments, controlled customer evidence, gate review (CTO/CFO/Commercial/Compliance).

### 3.2 Test catalogue

Gate column = **proposed mapping** derived from M§22 gate scope (first gate at which the test must pass; tests stay in regression afterwards). Repo column cites test names verified in the files. Run record: on 19 November 2026, `pytest tests/test_commercial_control_plane.py tests/test_commercial_api.py` (backend venv, in-memory SQLite test database) returned **61 passed, 0 failed**. This is evidence for tests COM-001, COM-002, COM-003 (fee-base vectors only) and COM-008 at the R1 control-plane level. It is not a gate pass.

| Test [M§24] | Gate (proposed mapping) | Required evidence | Current repo evidence |
|---|---|---|---|
| COM-001 Quote from correct effective-dated market/contract SKU; expired/absent role rejects checkout | G1 (subscriptions/lead billing) | Test run; blocked-checkout screenshots (Doc COM-11) | Mapped in file header. `test_com_001_closed_or_absent_gate_rejects_binding_quote`, `test_com_001_absent_or_expired_commercial_role_rejects`, `test_com_001_unapproved_sku_or_no_effective_rate_rejects`, `test_com_001_currency_and_evidence_requirements`, `test_binding_quote_issued_from_approved_effective_terms` [Repo: backend/tests/test_commercial_control_plane.py]; `test_quote_api_rejects_when_gate_closed` [Repo: backend/tests/test_commercial_api.py]. Covers binding quote only; marketplace checkout not integrated [Repo: backend/apps/commercial/README.md] |
| COM-002 Accepted quote immutable after pricing/rate/promotion/plan change | G1 | Test run; snapshot hash evidence | Mapped in header. `test_com_002_accepted_quote_is_immutable_after_pricing_changes`, `test_com_002_snapshot_cannot_be_mutated_or_deleted`, `test_issued_quote_keeps_price_until_expiry_after_rate_change`, `test_accept_rejects_wrong_terms_other_users_and_double_acceptance`, `test_accept_rejects_expired_quotes_and_records_expiry`, `test_accept_rejects_when_gate_changed_since_issue` [Repo: test_commercial_control_plane.py]; `test_quote_issue_accept_flow_and_owner_isolation` [Repo: test_commercial_api.py]. Promotions not implemented |
| COM-003 Fee on contract-defined basis; partial refund/discount/tax match golden case | G2 (parts/booking payments) | Golden vector outputs | Mapped in header. `test_appendix_a_parts_basket_golden_vector` (asserts base 9000, fee 720, total 10320 minor units); `test_money_rounding_is_integer_half_up` asserts 8% of 3000 = 240 (partial-return arithmetic only; no refund/reversal flow exists) [Repo: test_commercial_control_plane.py] |
| COM-004 Lead accepted once within SLA; invalid leads never generate fees | G1 (consented lead capture) | Test run; dedupe vector | None found (leads "Not in R1") |
| COM-005 Duplicate PSP webhooks do not duplicate orders/fees/invoices/payouts | G2 (PSP settlement); G1 if subscription billing uses a PSP | Webhook/reconciliation test [M§24 pack] | None in commercial. Outbox consumer dedupe tests exist [Repo: backend/tests/platform_core/test_outbox.py] (internal events, not PSP). Marketplace refund idempotency/reconciliation tests exist, not mapped to COM IDs [Repo: backend/tests/test_refund_gateway_timeout_reconciliation.py] |
| COM-006 Payment account change needs verification/approval; payout freeze on suspected takeover | G2 | Test run; dual-control evidence (Doc COM-10 W3) | None found. Generic maker-checker for refunds exists, not payout accounts [Repo: backend/tests/test_maker_checker_engine.py] |
| COM-007 Partial capture/shipment/completion/cancellation/credit/chargeback → balanced journals | G2 | Journal trial balance per scenario | None found (ledger "Not in R1") |
| COM-008 No regulated SKU, warranty insurance or high-value settlement without signed country gate | G1 and every later gate (regulated activation itself is G4, GATED) | Test run; gate register | Mapped in header. `test_com_008_regulated_skus_cannot_be_approved`, `test_com_008_regulated_gates_cannot_be_enabled`, `test_gated_role_profiles_cannot_be_approved` [Repo: test_commercial_control_plane.py]; `test_gate_api_creates_closed_gates_and_blocks_regulated_activation` [Repo: test_commercial_api.py]. Repo blocks outright (stricter than master) |
| COM-009 Seller-of-record and sponsored labels consistent across search, price, listing, checkout, receipts | G1 (accurate listings) | Disclosure screenshots [M§24 pack] | Partial: quote role snapshot carries seller of record (`test_facilitated_order_requires_named_seller_of_record`) [Repo: test_commercial_control_plane.py]; no UI label tests found |
| COM-010 Sensitive data tenant-/role-scoped; logs redact tokens | G1 | Access test; log sample | Not mapped by header; possibly relevant: `test_admin_endpoints_require_commercial_staff`, `test_quote_for_organisation_requires_owner_or_admin` [Repo: test_commercial_api.py] |
| COM-011 Negative balance, unmatched PSP item, drift, aged AR → owned exceptions | G1 (reconciliation) / G2 | Exception queue evidence (Doc COM-10 F3) | None found |
| COM-012 Recall/counterfeit disables listings and triggers outreach | G2 (fitment, parts) | Incident drill | None found in commercial; not reviewed elsewhere |
| COM-013 US total consumer price includes mandatory non-government seller fees where applicable | G1, only if US displays are in scope (depends on D01) | Screenshots; test run | None found |
| COM-014 WCAG 2.2 AA automated + manual; locale/RTL, taxes, keyboard | G1 | Accessibility test [M§24 pack] | None found |
| COM-015 Renewal/downgrade/trial cancellation: no silent double bill or notice breach | G1 (subscriptions) | Test run | None found (subscriptions "Not in R1") |
| COM-016 GL posts only earned platform revenue vs pass-through (GMV ≠ revenue) | G1 (reconciliation) | Ledger evidence | None found (ledger "Not in R1") |

The header of `backend/tests/test_commercial_control_plane.py` states it maps COM-001, COM-002, COM-003, COM-008; `test_commercial_api.py` carries no COM-ID mapping in its header and describes "permissions, response contracts, closed-by-default behaviour".

### 3.3 Golden vectors [M App A] — ILLUSTRATIVE

| Case | Expected control behavior | Repo evidence |
|---|---|---|
| Parts basket | Buyer payable $103.20; fee base $90.00; fee $7.20 | `test_appendix_a_parts_basket_golden_vector` |
| Partial return | Fee credit $2.40 at original 8% if contract mandates proportional reversal | Arithmetic only (`test_money_rounding_is_integer_half_up`) |
| Duplicate lead | One potential billable lead maximum; partner acceptance required | None |
| Workshop change order | Original authorized amount only until affirmative approval | None in commercial; workshops `ChangeOrder` model exists [Repo: backend/apps/workshops/models.py] — not reviewed against this vector |
| Subscription proration | Per executed policy; no hard-coded assumption | None |
| Tax rule missing | Discovery as appropriate; block binding checkout; record policy reason | Partial: binding quote rejects missing `tax_determination_reference` (`TAX_DETERMINATION_REQUIRED`); gate cannot be enabled without `tax_schedule_reference` [Repo: backend/apps/commercial/services/gates.py] |

QA note: in the Parts basket vector the sales tax ($7.20) equals the platform fee ($7.20); a test that confuses the tax and fee lines would still pass on totals. Recommend asserting by line type; the repo test looks up the `PLATFORM_FEE` line by type and checks it is not customer-payable, in addition to asserting amounts by position [Repo: backend/tests/test_commercial_control_plane.py].

### 3.4 Country-gate state machine [M§21] vs repo

Master: designed → legally_reviewed → partner_verified → finance_signed → technical_rehearsed → enabled; suspended/withdrawn. Repo implements the same forward sequence one step at a time, evidence reference required for the four middle steps, a reason on every transition, ENABLED ↔ SUSPENDED, any → WITHDRAWN, WITHDRAWN → DESIGNED; enabling needs tax schedule reference, currencies, an approved role profile (non-DISCOVERY) and a person other than the FINANCE_SIGNED actor; regulated gates cannot be enabled [Repo: backend/apps/commercial/services/gates.py]. The return paths (SUSPENDED → ENABLED, WITHDRAWN → DESIGNED) are not specified in M§21 — implementation choices to confirm.

### 3.5 Per-gate launch checklist (evidence slots intentionally empty)

| Gate | Checklist item | Source | Evidence ref | Owner sign |
|---|---|---|---|---|
| G0 | Legal role matrix (D02) | [M§22] | | |
| G0 | Vertical scope; target pilot market (D01) | [M§22] | | |
| G0 | Contracting legal entity; tax map (D09) | [M§22] | | |
| G0 | PSP viability (D04) | [M§22] | | |
| G0 | Source architecture; data-rights inventory (D07) | [M§22] | | |
| G1 | Tests (proposed): COM-001, 002, 004, 008, 009, 010, 011, 013*, 014, 015, 016 | §3.2 | | |
| G1 | Contracts, support desk, measurement readiness | [M§22] | | |
| G1 | Country gate ENABLED per capability with transition evidence | [M§21] | | |
| G2 | Tests (proposed): COM-003, 005, 006, 007, 012 + G1 regression | §3.2 | | |
| G2 | Operational rehearsal per vertical + payment corridor | [M§22] | | |
| G3 | Enterprise API/SLA evidence; G1–G2 regression | [M§22] | | |
| G4 | **GATED — not assessed** | [M§22] | n/a | n/a |
| Each go-live SKU | Approved fee specification; role/legal memo; finance/tax configuration; versioned contract; end-user disclosure screenshots; golden calculation vectors; webhook/reconciliation test; refund and chargeback test; accessibility test; escalation owner; incident/rollback switch; KPI baseline; executive approval ticket | [M§24] | | |
| Each release | Ring R0→R4 progression with rollback; SLO/error-budget check | [E 2.9, E 2.10] | | |
| Each release | Recovery tier assigned and RTO/RPO rehearsed for affected components | [E 2.10] | | |

\* COM-013 only where US displays apply.

## 4. Engineering reconciliation notes

| Topic | Note | Source |
|---|---|---|
| SLO values | E states SLOs govern releases but gives no targets; master lists SLO areas only. All targets are open inputs. | [E 2.9, M§20] |
| Recovery tiers | Quote/commercial control plane is not placed in a tier; "jurisdiction control" is Tier 0, "checkout" Tier 1. Placement of country gates/quotes open. | [E 2.10] |
| Environments | E lists developer, test, staging, pre-production, production, recovery; mapping of rings to environments open. | [E 2.10] |
| Gate vs ring | M§22 business gates and E release rings are different axes; a gate decision does not equal a ring promotion. | [M§22, E 2.10] |
| Context ownership | Country rules CTX-17; admin ops CTX-18; payments/ledger CTX-07. | [E 2.4] |

## 5. Implementation evidence (repo)

Implementation evidence only; not approval. See §3.2–§3.4 for test- and gate-level citations.

| Fact | Path |
|---|---|
| Commercial control plane test command lists `tests/test_commercial_control_plane.py`, `tests/test_commercial_api.py`, `tests/platform_core/test_outbox.py` | [Repo: backend/apps/commercial/README.md] |
| "Not in R1": agreements, leads, subscriptions/entitlements, invoicing, earning events, ledger, settlement/reconciliation, payouts, FX, tax engine integration, marketplace checkout integration | [Repo: backend/apps/commercial/README.md] |
| Payment sandbox defaults are the subject of a proposal with status "Proposal for review" | [Repo: docs/proposals/R0-payment-safeguards.md] |
| None found: ring definitions, SLO definitions, recovery-tier configuration | — |

## 6. Open inputs required to complete

| Input | Needed from | Blocks |
|---|---|---|
| Confirmation of proposed test→gate mapping | CTO + CFO + Compliance | §3.2, §3.5 |
| SLO targets and error budgets (quote availability, checkout, order transitions, PSP feed timeliness, invoicing, dispute queues) | CTO | QA-09, QA-10 |
| Recovery tier for commercial control plane components | CTO | QA-12 |
| Ring-to-environment mapping and rollback criteria | CTO | §3.5 |
| Resolution of R0–R4 naming collision (rings / risk classes / repo releases) | CTO + document owner | All docs |
| Approval of repo gate return paths (SUSPENDED→ENABLED, WITHDRAWN→DESIGNED) | GC + CFO | §3.4 |
| Gate approvers per gate (master names business decision, not approver) | Founder + CFO (D08) | §3.5 sign column |
| Pass/fail results and run records | Document owner | §3.2 |
| D01, D02, D04, D07, D09 outcomes | Per §25 approvers | G0 checklist |
| US-display applicability for test COM-013 | Founder + Commercial (D01) + Legal | §3.2 |

## 7. Acceptance / evidence mapping

This document is itself the mapping of tests COM-001..COM-016 and the M§24 minimum evidence pack to gates (§3.2, §3.5). It must supply: the completed test catalogue with run records; the per-gate checklist with evidence references; the golden-vector results (§3.3); gate transition records (§3.4).

## 8. Completion status

| Section | Status |
|---|---|
| 1–2 Purpose, requirements | Drafted |
| 3 Gates, catalogue, vectors, gate machine, checklist | Drafted; gate mapping proposed; evidence slots empty |
| 4 Engineering reconciliation | Drafted (flagged, not resolved) |
| 5 Implementation evidence | Drafted |
| 6 Open inputs | Drafted |
| 7 Acceptance mapping | Drafted; results Pending external input |

Overall: DRAFT — structurally complete; 10 open inputs; G4 GATED.
