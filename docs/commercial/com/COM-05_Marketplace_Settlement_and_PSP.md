# Doc COM-05 — Marketplace Settlement and PSP

| Field | Value |
|---|---|
| Document ID | DX-COMM-COM-05 (proposed; map to canonical engineering register per M§25) |
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Parent | DX-COMM-MASTER-001 v1.0 (23 Oct 2026); v1.1 PROPOSED revision |
| Status | DRAFT — not approved. No content is a live tariff, executed contract, legal/tax opinion or regulatory permission. |
| Proposed owner | Finance / CTO (gate owner, "P0: Checkout/ledger divergence") with GC / Payments ("P0: Escrow misuse / custody") [M§23]; PSP arrangements owned by Payments + CFO + GC [M App D] |
| Required approvers | CTO + CFO + GC (D04) [M§25]; Global Tax + CFO for PSP funds schedule (D09) [M§25] |
| Related decisions | D04 BLOCKED (needs D01, D02); D01 OPEN; D02 BLOCKED (needs D01 corridor); D09 BLOCKED (needs D01, D02, D04) |
| Related tests | test COM-005, test COM-006, test COM-011 (cross-reference test COM-007, test COM-016) [M§24] |

ID-namespace note: "Doc COM-0X" = this deliverable series; "revenue code COM-0X" = M§04 codes; "test COM-0XX" = M§24 tests. They are unrelated identifiers.

**D04 is BLOCKED.** No PSP is selected. Any PSP named in this document is either a master benchmark candidate [M§12, M§25] or existing repo implementation; neither is a decision.

> **Decision update (19 November 2026, rev. B).** Confirmed direction from Lennox Zoiko: contracting company **Zoiko Mobility Inc.**; initial target markets **USA and UK** (no pilot city or corridor chosen); preferred payment provider **Stripe** (Stripe Connect capabilities, merchant onboarding, settlement and payouts per country still to be verified); finance and insurance handled as a **separate workstream owned by Rithika** (stays OFF here). These are recorded as CONFIRMED DIRECTION, not formal legal or regulatory approvals. Where this document's header or text gives older statuses for D01, D02, D04, D07 or D09, the current register in [../02_Commercial_Decision_Register.md](../02_Commercial_Decision_Register.md) prevails.

## 1. Purpose and scope

Defines treasury and settlement invariants, the PSP payment reference and settlement ledger, the settlement state machine, and the controls against checkout/ledger divergence and escrow misuse. It is the deliverable "COM-05 Marketplace Settlement / PSP" [M§25]. Sources: [M§10], [M§21], [M§23], tests [M§24]; engineering ledger/idempotency/outbox [E 1.5, E 2.2]. Funds-flow mode selection per role is in Doc COM-02; journals in Doc COM-04.

## 2. Requirements carried from the master

| Req ID | Requirement | Source |
|---|---|---|
| R05-01 | No self-operated escrow, wallet balances, customer safeguarding or payment custody without counsel-confirmed permissions and documented PSP role; PSP delayed payout ≠ licensed legal escrow. | [M§10] |
| R05-02 | Do not market funds as "escrow" without independently confirmed licensed/legal structure. | [M§01] |
| R05-03 | No platform transfer or fee against failed/unsettled charges; idempotency keys, replay-safe webhooks, PSP event reconciliation. | [M§10] |
| R05-04 | Track separately: gross payer charge, seller payable, platform receivable, taxes, PSP fee, reserves, dispute balance, refund liabilities, payout reference. | [M§10] |
| R05-05 | Daily reconciliation: PSP ledger vs order subledger vs invoices vs bank settlement; suspense items need owner, reason, aged action. | [M§10] |
| R05-06 | Defined precedence for refunds, chargebacks, partial fulfilment, split shipments, manual offsets, goodwill credits, seller negative balances. | [M§10] |
| R05-07 | Prohibit cross-seller negative netting, use of held customer funds for operating cash, payout acceleration without reserve-risk approval. | [M§10] |
| R05-08 | Dual-control treasury administration, bank-verification change hold, payee-name matching, PCI scope minimization, payout anomaly controls, immutable adjustment trails. | [M§10] |
| R05-09 | Order & Payments owns PSP orchestration and payment reference; "no internal uncontrolled wallet". | [M§20] |
| R05-10 | PSP is an integration; "buy compliant payment rails and build domain ledger/exception controls on top". | [M§20, M§12] |
| R05-11 | Loyalty: no cashback funded from customer funds held for sellers. | [M§13.8] |
| R05-12 | Modes E and F GATED; mode B only after role, chargeback and negative-balance allocation approval. | [M§10] |

## 3. Specification draft

### 3.1 Canonical entities [M§21]

| Entity | Minimum fields / invariant |
|---|---|
| `payment_intent_ref` | PSP token/id, authorized/captured/refunded/charged-back status, idempotency, currency; no raw PAN |
| `settlement_ledger` | PSP statement key, matched order, seller/platform liability, payout, reserve, suspense reason |
| `order_booking` | listing/provider, accepted quote id, buyer, service window, lifecycle, cancellation, fulfilment |

Payout/settlement finance fields: PSP balance account, settlement currency, reserve, charges, exchange spread, external reconciliation key [M§11].

### 3.2 State machines [M§21]

| Flow | States |
|---|---|
| Settlement | pending → PSP_confirmed → matched → seller_payable → paid → reconciled; exception / chargeback hold branches |
| Order | draft → quoted → accepted → authorized → fulfilled/completed → closed; cancelled/failed/disputed/refunded branches |

Events: `payment.captured`, `refund.initiated`, `chargeback.opened`, `seller.payout_settled`, `settlement.reconciled` — each versioned with business ID, correlation ID, actor/source, UTC timestamp, event ID and idempotency key [M§21]. The master example API `GET /v1/finance/reconciliations` is "examples only" and must be reconciled with the controlled API master [M§21].

### 3.3 Treasury and settlement invariants → control design

| Invariant [M§10] | Control expressed against §21 entities | Evidence |
|---|---|---|
| No transfer/fee on failed/unsettled charges | `fee.earned` and `seller.payout_settled` only after settlement state ≥ PSP_confirmed | test COM-005, test COM-007 |
| Idempotency, replay-safe webhooks | Each PSP event stored once by provider event ID; downstream effects keyed by idempotency key | test COM-005 |
| Separate balances | `settlement_ledger` carries seller/platform liability, reserve, suspense; App B 2300–2399 clearing "where recognized by actual role model" [M App B] | test COM-007, test COM-016 |
| Daily four-way reconciliation | PSP statement key ↔ order ↔ `invoice_credit` ↔ bank settlement | test COM-011 |
| Suspense ownership | Every exception has owner, reason, age | test COM-011 |
| No cross-seller netting; no operating use of held funds | Negative balance is a per-seller exception, not offset | test COM-011 |
| Account-change hold, payee matching | Payout freeze on suspected account takeover | test COM-006 |

The "≥ PSP_confirmed" ordering is a drafting reading of the §21 settlement sequence combined with the §10 invariant; confirm with Finance / CTO.

### 3.4 Mode-specific posture [M§10]

| Mode | Settlement scope here |
|---|---|
| A PSP direct settlement | In scope once D04 selects a PSP; platform fee via application fee/billing |
| B PSP facilitated split | In scope only after role, chargeback, negative-balance allocation approval |
| C Off-platform dealer sale | No settlement through DriverXtra; label "transaction completed off DriverXtra" without representing controlled funds [M§08 D] |
| D Subscription billing | Platform's own receivable; see Doc COM-04 |
| E PSP conditional payout | **GATED — disabled**; never labeled legal escrow |
| F Financing/insurance partner | **GATED — disabled** |

### 3.5 P0 risks [M§23]

| Risk | Design correction | Gate owner |
|---|---|---|
| P0: Checkout/ledger divergence | Idempotent financial state, PSP webhook reconciliation, exceptions ownership | Finance / CTO |
| P0: "Escrow" misuse / custody | PSP-supported modeled transfers; no self-held buyer funds; legal name of assurance product | GC / Payments |

### 3.6 Monitoring [M§19, M§20]

KPIs: daily reconciled value %, unapplied suspense age, webhook recovery, idempotency violations, chargeback rate [M§19]. SLOs and synthetic monitoring for checkout, order transitions, PSP feed timeliness and dispute queues [M§20]. Thresholds are not given in the master (open input).

## 4. Engineering reconciliation notes

| Topic | Engineering text | Master position | Handling |
|---|---|---|---|
| Ownership | CTX-07 Payments and Ledger owns the double-entry ledger; CTX-06 cart to order; CTX-12 disputes [E 2.4]; "Disputes authorise a remedy, and Payments executes it" [E 1.6, E 2.4] | Order & Payments; Settlement Reconciliation; Finance Subledger as separate domains [M§20] | CTX-07 maps to Order & Payments; whether settlement reconciliation and subledger also sit in CTX-07 is an open input (CTO). |
| Seller funds held | "The seller's money is held until it is eligible for payout." [E 1.5] | Holding only via a documented PSP role; mode E GATED; no self-held buyer funds [M§10, M§23] | **Conflict flagged, not resolved.** Must be restated as PSP-held delayed payout pending D04 and counsel. |
| Ledger | Payment recorded in "an immutable double-entry ledger" [E 1.5]; append-only ledger [E 2.7] | `settlement_ledger` with immutable adjustment trails [M§10, M§21] | Compatible. |
| Timeouts | Timed-out payment marked "unknown" and reconciled; "never charges twice and never cancels automatically" [E 1.5] | No transfer on unsettled charges [M§10] | Repo auto-cancels unpaid PENDING online orders after `PAYMENT_EXPIRY_MINUTES` (§5); whether this conflicts with "never cancels automatically" is for CTO review. |
| Idempotency/outbox | Idempotency on mutating calls; transactional outbox [E 2.2]; at-least-once, idempotent consumers, DLQ [E 2.5]; signed, timestamped, replay-protected webhooks [E 2.8] | Same intent [M§10, M§20] | Compatible; marketplace payments do not use the outbox (§5). |
| Money | Integer minor units + ISO currency [E 2.2] | Same [M§07] | Marketplace uses decimal amounts (§5); flagged. |
| Recovery | Tier 0 (orders, payments, ledger): RTO ≤ 30 min, RPO ≤ 5 min [E 2.10] | Not stated | Engineering figure, not a master SLA. |
| Buyer protection | Listed as a protection feature [E 1.2] | No guaranteed buyer protection represented for off-platform sales; assurance product needs legal name [M§08 D, M§23] | Flagged for counsel. |

## 5. Implementation evidence (repo)

The marketplace payment code below is **existing implementation that predates any D04 PSP decision**. It is evidence of current behavior, not a PSP selection, funds-flow approval or §10 mode assignment. It is separate from commercial R1, which "does not move money" [Repo: backend/apps/commercial/README.md].

| Fact (verified) | Path |
|---|---|
| Providers: `StripePaymentProvider` (UK / GBP, international cards) and `RazorpayPaymentProvider` (India / INR) behind `BasePaymentProvider` (create session, verify payment, verify webhook, issue/inquire refund). | [Repo: backend/apps/marketplace/payments/base.py], [Repo: backend/apps/marketplace/payments/stripe_provider.py], [Repo: backend/apps/marketplace/payments/razorpay_provider.py], [Repo: backend/config/settings.py] |
| Test mode applies only when `PAYMENT_TEST_MODE` is set and `DEBUG` or `IS_TESTING` is true; `PAYMENT_TEST_MODE` defaults on only when `DEBUG` or `IS_TESTING`; `DEBUG` defaults to False. | [Repo: backend/apps/marketplace/payments/stripe_provider.py], [Repo: backend/config/settings.py] |
| Provider key and webhook-secret settings still default to placeholder values (e.g. `whsec_test_placeholder_secret`, `rzp_test_webhook_secret`); webhook HMAC verification uses the configured secret; magic signatures accepted only in test mode. | [Repo: backend/config/settings.py], [Repo: backend/apps/marketplace/payments/stripe_provider.py], [Repo: backend/apps/marketplace/payments/razorpay_provider.py] |
| Stripe webhook check verifies HMAC over `t.payload`; no timestamp-tolerance check was observed in `verify_webhook`. | [Repo: backend/apps/marketplace/payments/stripe_provider.py] |
| `PaymentWebhookEvent`: provider, unique `event_id`, event_type, processed flag, order, payload. `process_webhook` returns "already_processed" for processed events and re-checks under `select_for_update` inside a transaction; order row is locked; success events on cancelled orders are rejected. | [Repo: backend/apps/marketplace/models.py], [Repo: backend/apps/marketplace/payments/service.py] |
| `PaymentTransaction` (PAYMENT, REFUND, COD_COLLECTION) with provider IDs and `idempotency_key`; docstring calls it an "immutable ledger record", but no append-only guard was observed on the model. It is not a double-entry ledger. | [Repo: backend/apps/marketplace/models.py] |
| Marketplace money fields (`Order`, `PaymentTransaction`, `Refund`) are `DecimalField` with `currency` default `INR`, not integer minor units. | [Repo: backend/apps/marketplace/models.py] |
| Unpaid PENDING online orders are auto-cancelled after `PAYMENT_EXPIRY_MINUTES` (default 30, repo configuration). | [Repo: backend/apps/marketplace/payments/service.py], [Repo: backend/config/settings.py] |
| `Refund` with `PROCESSING_UNKNOWN` status and a `reconcile_refunds` command that inquires the gateway; refund methods include BANK_TRANSFER and MANUAL_PAYOUT; seller-direct refunds can be recorded. | [Repo: backend/apps/marketplace/models.py], [Repo: backend/apps/marketplace/management/commands/reconcile_refunds.py], [Repo: backend/apps/marketplace/returns/service.py] |
| COD enabled by default for `IN,GB` with per-currency caps; COD is not a §10 mode. | [Repo: backend/config/settings.py] |
| Not found in marketplace code: chargeback handling, seller payable/payout records, PSP statement reconciliation, suspense ledger, use of the `platform_core/events` outbox. **Update 20 Nov 2026 (G17a):** Stripe chargeback *intake* now exists. `charge.dispute.*` events are linked to orders, recorded as internal audit entries (amount, fees and outcome kept separate, with no netting), and new refunds plus approval, dispatch and settlement of existing refunds are blocked while a chargeback is open or lost. Chargeback *handling* is still absent: no evidence submission, loss allocation, payout hold or ledger journal, and R05-06 precedence is unresolved. The other items in this row are unchanged. | none found (searched `apps/marketplace`); G17a: [Repo: backend/apps/marketplace/payments/chargebacks.py], [../implementation-assessment/03_G17a_Stripe_Chargeback_Intake_Evidence_2026-11-20.md] |
| Workshops: separate `WorkshopDepositWebhookEvent` for booking deposits. | [Repo: backend/apps/workshops/models.py] |
| `docs/proposals/R0-payment-safeguards.md` — status "Proposal for review", prepared 30 Oct 2026 — lists findings F1–F8 (placeholder webhook secrets, test-mode defaults, magic signatures, fabricated sessions, simulate endpoint, refund `auto_process`, COD default) and proposes fail-closed defaults, a sandbox predicate, placeholder-secret rejection and a startup check; it defers real provider integration to D04 and per-market COD to country gates. Current code already differs from some findings (e.g. `DEBUG` and `PAYMENT_TEST_MODE` defaults; provider session code now refers to live API calls when credentials are configured) while others remain (placeholder secret defaults, COD default). The proposal is not approved. | [Repo: docs/proposals/R0-payment-safeguards.md], [Repo: backend/config/settings.py], [Repo: backend/apps/marketplace/payments/razorpay_provider.py] |

## 6. Open inputs required to complete

| Input | Needed from | Blocks |
|---|---|---|
| PSP selection per corridor (Stripe Connect vs Adyen vs local qualified PSP) | CTO + CFO + GC (D04) | §3.4 modes A/B, all settlement design |
| First corridor | Founder + Commercial (D01) | D04 |
| Counsel confirmation of PSP role and naming of any assurance/delayed-payout product | GC / Payments | Mode E (stays GATED), E 1.5 wording |
| Precedence order for refunds, chargebacks, partial fulfilment, split shipments, offsets, goodwill, negative balances | CFO + Payments | R05-06, test COM-007 |
| Reserve policy and payout schedule | Payments + CFO + GC [M App D] | settlement_ledger reserve |
| Suspense aging thresholds and exception owners | CFO | test COM-011 |
| Reconciliation and webhook SLO thresholds | CTO + CFO | §3.6 |
| Decision on existing marketplace payment code (adopt, adapt or replace after D04); R0 proposal disposition | CTO + payment code owner | §5 |
| COD treatment (not a §10 mode) | CFO + GC (with D01/D04) | Marketplace checkout |
| Context ownership for settlement reconciliation and subledger | CTO | §4 |
| Ruling on auto-expiry of unpaid orders vs E 1.5 | CTO | §4 |

## 7. Acceptance / evidence mapping

| Test / evidence | What this document must supply | Source |
|---|---|---|
| test COM-005 | Webhook dedup rule; no duplicate orders, fees, invoices or payouts | [M§24] |
| test COM-006 | Account-change verification/approval; payout freeze on suspected takeover | [M§24, M§10] |
| test COM-011 | Exception classes (negative balance, PSP unmatched, settlement drift, aged AR) with owners | [M§24] |
| test COM-007 / test COM-016 | Balance separation feeding journals (with Doc COM-04) | [M§24] |
| Evidence pack: successful webhook/reconciliation test; refund and chargeback test; incident/rollback switch | Per go-live SKU | [M§24] |

## 8. Completion status

| Section | Status |
|---|---|
| 1–2 Purpose, requirements | Drafted |
| 3.1–3.3 Entities, states, invariants | Drafted |
| 3.4 Mode posture | Pending external input (D04) |
| 3.5–3.6 Risks, monitoring | Drafted; thresholds pending |
| 4 Engineering reconciliation | Drafted (flagged, not resolved) |
| 5 Implementation evidence | Drafted |
| 6–7 Open inputs, acceptance | Drafted |

Overall: DRAFT — structurally complete; 11 open inputs; D04 BLOCKED.
