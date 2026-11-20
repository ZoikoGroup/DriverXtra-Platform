# Gap-Closure Plan Update — D02 / D04 / D09 reconciliation and next safe P0 task

| Field | Value |
|---|---|
| Date / status | **Assessment:** 19 November 2026, PROPOSED FOR APPROVAL. §1–§6 are the assessment as written that day; at that point nothing had been implemented.<br>**Implementation since (19–20 Nov 2026):** ENG-01, ENG-02, ENG-03 (implementation ID), ENG-04a, ENG-05a, ENG-05a-PG, G17a and the ENG-01/03 frontend correction.<br>**§7 is the authoritative implementation and evidence log**, including the ID mapping. All of this work is **IMPLEMENTED – NOT VERIFIED**: nothing is VERIFIED IN TEST until the runs are bound to a commit SHA.<br>**Corrections above §7:** only this row and two dated notes in §6. Evidence index: [README.md](README.md). |
| Supersedes | Nothing. Adds to `../` trackers (master v1.1 rev. B, decision register, Appendix D, gate and blocker lists), which remain authoritative for the commercial estate. |
| Inputs | (1) D02/D04/D09 findings relayed by the project owner from recent Codex investigations; (2) Consolidated Engineering Baseline DX-CONS-001 v2.0 (read in full); (3) targeted sections of DX-GC-04, DX-GC-05, DX-GC-07, DX-GC-08 and EV-03; (4) spot checks of the repository (listed in §1). |
| Status vocabulary | IMPLEMENTED AND VERIFIED · IMPLEMENTED – NOT VERIFIED · PARTIALLY IMPLEMENTED · NOT IMPLEMENTED · BLOCKED · NOT APPLICABLE (project owner's definitions). Mapping to the baseline's states is in §3.3. |

## 1. Evidence basis

| Finding | Basis in this update |
|---|---|
| D02 role-profile findings | Relayed; not re-scanned (instruction not to repeat the investigation). Consistent with `backend/apps/commercial/README.md`, read 19 Nov. |
| D04: Stripe is GBP-only | **Re-verified**: `backend/apps/marketplace/payments/stripe_provider.py` lines 68–69 and 170–175 reject any currency other than GBP. |
| D04: payment-method paths may advertise unsupported options | **Re-verified, and confirmed.** `PaymentService.get_available_payment_methods` (`backend/apps/marketplace/payments/service.py` ~262–310) returns a Stripe "Card Payment" method labelled `currency: "GBP"` for **every** non-INR request, including US/USD. Its `is_available` depends only on configuration or test mode, not on currency support. `PaymentMethodsView` (`apps/marketplace/views.py` ~3020–3047) also defaults `country` to "India" when the parameter is missing. |
| D04: other items (no Connect, no payouts, no chargebacks or settlement reconciliation, quote not in checkout) | Relayed; consistent with the 19 Nov inspection (no Connect code found; commercial README lists these as "Not in R1"). |
| D09 | Relayed; consistent with `platform_core/tax/regimes` (only `india_gst.py` and `uk_vat.py`). |

**Not available:** Codex's own output files (none are in the repository); the original DOC 01–25 (also absent per DX-CONS-001 §0); commit SHAs. DX-CONS CD-06 requires SHA-bound evidence, and Git commands were not permitted, so the repository owner must attach SHAs when evidence is formally recorded.

## 2. Do the findings conflict with the architecture specifications?

| # | Finding | Specification position | Conflict? | Resolution (no new system) |
|---|---|---|---|---|
| 1 | Approval and legal-memo references are only checked for non-empty strings | DX-CONS §2: EV-03 holds signed evidence; DX-GC-08 WF-05 is the single approval experience; CD-06 requires evidence fingerprints | **Gap, not a conflict.** The design is right; the implementation stops short. | Do **not** build an evidence store inside `apps/commercial`. The reference must resolve to an EV-03 / DX-GC-08 evidence record once that model exists. Until then, keep as PARTIALLY IMPLEMENTED and BLOCKED on a CTO decision about the evidence record owner. |
| 2 | No contracting legal-entity binding | DX-CONS §2: DX-GC-04 owns identity, organization and legal identity (DOC 04); DX-GC-05: "named legal entities … rendered in each step" | **Ownership risk.** Adding an entity table to `apps/commercial` would duplicate the DX-GC-04 identity domain. | Model Zoiko Mobility Inc. (and any per-market entity) in the identity/organisation domain (`apps/organisations` is the nearest existing owner). The role profile holds only a reference. Needs a CTO ADR (extends PD-12). |
| 3 | Seven role-profile types with approval workflow | DX-GC-04 G04 "partner capability and market eligibility registry" | **Possible overlap.** A transaction-role profile (seller of record, payment role, tax party) is not the same as a partner capability. | Keep both, but link by ID. Do not create a second registry. Record the boundary in the ADR for PD-12. |
| 4 | Stripe GBP-only; US unsupported; methods advertised for unsupported currency | DX-GC-05 §15: "country-specific licensed PSP capabilities … **no unsupported market flags**"; PAY-06 (preserve PSP currency and minor units); DX-GC-07: fail closed for writes | **Implementation conflicts with the spec** (the advertising defect). | Fix at the existing endpoint (see §6). No new service. |
| 5 | No Stripe Connect, payouts, chargebacks or settlement reconciliation | DX-GC-05 G15/G16/G17 (P0); DX-CONS G3 needs EV-06 reconciliation proof | Consistent: these are open P0 gaps. | Remain NOT IMPLEMENTED. Connect and payouts are BLOCKED by D04 country verification; chargeback and reconciliation design can start (see §4). |
| 6 | Commercial quote not in marketplace checkout | Master §07; DX-GC-01 owns the journey; DX-GC-05 owns money | Consistent gap. | Remains a P1 engineering item behind closed country gates (it cannot transact until D02 profiles are approved). |
| 7 | UK VAT exists; no US tax | Master §11; DX-GC-07 / DOC 18 jurisdiction packs | Consistent. | BLOCKED on D09 tax determinations. No US tax logic before them (PD-16). |
| 8 | Market policy has three code locations: commercial `CountryGate`, `platform_core/regional` (IN/GB only), and payment country normalisation in `PaymentService` | DX-CONS CD-05: **DX-GC-07 owns global market policy**; no second market-policy engine | **Conflict with CD-05** (duplication already exists in code). | No new engine. A CTO ADR designates one canonical market-capability record, and the other two consume it. The recommended task in §6 must not add a fourth source of market truth. |

## 3. Conflicts inside the specification set (logged, not silently resolved)

### 3.1 Two gate schemes use the same labels
| Master §22 (commercial) | DX-CONS §5 (engineering evidence) |
|---|---|
| G0 Board design freeze | G0 EV-01 signed as-built inventory |
| G1 Controlled pilot | G1 DX-GC-01/04/07 + EV-04 |
| G2 Transactional commerce | G2 DX-GC-02 valuation + EV-03/05 |
| G3 Enterprise marketplace | G3 DX-GC-03/05 + EV-06 |
| G4 Regulated / global expansion | G4 DX-GC-06/09 + EV-05/07 |
| — | G5 DX-GC-08 + EV-08 certificate |

**Proposal:** refer to them as **M-G0..M-G4** (master) and **B-G0..B-G5** (baseline) in all trackers. A market launch needs both: the commercial gate (M-Gx) and the evidence certificate (B-G5 / EV-08). Decision owner: CTO + document owner.

### 3.2 First market
DX-CONS §10 lists "First target market and capability set — TBD, not assumed" (13 Nov). It is superseded **in direction** by the 19 Nov confirmation (USA and UK). The formal decision record is still to be filed (D01 remains CONFIRMED DIRECTION, not APPROVED).

### 3.3 Status vocabularies
| Project status | DX-CONS state | Master/tracker usage |
|---|---|---|
| IMPLEMENTED AND VERIFIED | VERIFIED IN TEST (needs SHA + environment) | — |
| IMPLEMENTED – NOT VERIFIED | IMPLEMENTED—UNVERIFIED | "implementation evidence" |
| PARTIALLY IMPLEMENTED | (no equivalent; treated as IMPLEMENTED—UNVERIFIED plus a gap) | — |
| NOT IMPLEMENTED | DESIGN SPECIFIED | "not implemented" |
| BLOCKED | EXCEPTION / BLOCKED | BLOCKED |
| NOT APPLICABLE | — | GATED / OUT OF SCOPE |

Note: under CD-06 nothing in this repository can reach VERIFIED IN TEST until runs are bound to a commit SHA and environment. The 61 passing commercial tests (19 Nov) therefore count as IMPLEMENTED – NOT VERIFIED in baseline terms.

### 3.4 Finance and insurance
DX-GC-05 assigns G28 and G29 (P0) to the same document as payments. These are handled by the **separate finance and insurance workstream (Rithika)**: excluded from this plan's scope, not NOT APPLICABLE, and not blocking payments work.

## 4. Updated gap-closure plan: D02 / D04 / D09, split by type of dependency

### 4.1 Engineering work with no external dependency (can start after approval)
| ID | Work | Existing code to extend | Gap / spec | Priority |
|---|---|---|---|---|
| ENG-01 | Fail-closed payment-method and currency availability (§6) | `apps/marketplace/payments/service.py`, `apps/marketplace/views.py` (PaymentMethodsView), checkout validation | DX-GC-05 §15, PAY-06; G15 (part) | **P0** |
| ENG-02 | API-level tests for role-profile approval: separation of duties, missing approval reference, gated types blocked, prospective-only rules | `backend/tests/test_commercial_api.py` | D02 finding; master test COM-008; EV-04 (authorisation) | P0 (tests only) |
| ENG-03 | Chargeback (Stripe dispute) event intake as a recorded exception linked to the order, with no automatic money movement | Existing webhook path `payments/webhook/{provider}/`, `PaymentWebhookEvent`, `Dispute` model | G17 (P0) | P0. Design can start now; implement against Stripe test mode only. |
| ENG-04 | Settlement reconciliation design: PSP balance and payout report vs order subledger, with an exceptions queue | Reuse the existing admin refunds/approvals screens; no new console | G16/G17; master §10; DX-GC-05 WF-05 | P0 (design); build after D04 verification |
| ENG-05 | Commercial quote → checkout integration behind closed gates | `apps/commercial` quotes, `orders/checkout/` | Master §07; D10 | P1 |

### 4.2 Engineering blocked by an external dependency
| ID | Work | Blocked by |
|---|---|---|
| BLK-01 | Stripe Connect connected-account onboarding and seller payouts (USA, UK) | D04: Stripe Connect country capability and terms verification (CTO + CFO + GC) |
| BLK-02 | USD checkout and US provider path | D04 verification; PD-16 decision on US enablement |
| BLK-03 | US tax calculation and display | D09 USA tax determinations (Global Tax) |
| BLK-04 | Approval-evidence resolver for role profiles and gates | CTO decision on the evidence record owner (EV-03 / DX-GC-08), per §2 row 1 |
| BLK-05 | Contracting legal-entity binding | ADR placing it in the DX-GC-04 identity domain (PD-11 / PD-12) |
| BLK-06 | Approved USA and UK role profiles (data, not code) | D02 legal role memos (GC + CFO) |

### 4.3 Legal, finance and commercial dependencies (not engineering)
| Owner | Dependency |
|---|---|
| GC + CFO | D02 role-profile legal determinations, USA and UK |
| CTO + CFO + GC | D04 Stripe Connect verification and agreement; PD-14 disposition of COD and Razorpay |
| Global Tax + CFO | D09 USA and UK tax determinations and invoicing schedule |
| GC | PD-11 per-market contracting-entity verification for Zoiko Mobility Inc. |
| Founder + Commercial | Formal D01 record; whether a pilot city or corridor is required |
| Legal / Partnerships | EV-03 provider-rights evidence (valuation and other data providers) |
| Rithika (separate workstream) | Finance and insurance (G28–G31, G64) |

## 5. Outstanding items from the Commercial Estate Master (preserved, not repeated)
All remain open. Sources of record are in `docs/commercial/`.

| Area | Open count | Record |
|---|---|---|
| Decisions D01–D10 | D01 and D04 CONFIRMED DIRECTION (open parts remain); D02, D03, D05, D07, D08, D10 OPEN; D06 RECOMMENDED (separate workstream); D09 BLOCKED; **none APPROVED** | `02_Commercial_Decision_Register.md` |
| Proposed decisions | PD-11 to PD-16, all open | same |
| Doc COM-02..COM-13 | 12 of 12 at 0.1 DRAFT, not approved | `03_COM_Document_Tracker.md` |
| Appendix D policies and contracts | 15 of 15 NOT STARTED (item 4 is in the separate workstream) | `04_Appendix_D_Policy_Tracker.md` |
| Gates M-G0..M-G3 | 4 of 4 NOT MET | `05_G0-G3_Launch_Readiness_Tracker.md` |
| External approvals and blockers | 18 open | `06_External_Approvals_and_Blockers.md` |
| Engineering reconciliation | 5 inconsistencies and 14 gaps open (8 aligned, 27 rows; the corporate-identity row moved from inconsistency to gap in rev. B); the 25-document series is still unavailable | `01_Engineering_Reconciliation_Matrix.md` |
| Wireframe unresolved requirements | 14 open | `wireframes/03_Unresolved_Requirements.md` |
| Master v1.1 tracked changes | Awaiting owner review | the v1.1 PROPOSED .docx |

New items from this update to add to those records **after approval** (not added now, to avoid editing existing documents): the gate-label disambiguation (§3.1), the market-policy consolidation ADR (§2 row 8), the evidence-record owner decision (BLK-04), and ENG-01..ENG-05.

## 6. Recommendation: next safe P0 engineering task

### ENG-01 — Fail-closed payment-method and currency availability

> **Status note (20 Nov 2026):** approved and implemented on 19 Nov 2026. The frontend step in "Files" below was completed on 20 Nov: `CartDrawer.tsx` did **not** honour the rule fully, because it defaulted the country to India. Evidence: [04](04_ENG-01_Payment_Availability_Evidence_2026-11-20.md) and [08](08_ENG-01-03_Frontend_Delivery_Country_Evidence_2026-11-20.md). The text below is the original 19 Nov recommendation, unchanged.

**Why this task first**
- It is the only confirmed **live correctness defect** in the D04 findings. The API tells a US/USD (or any non-INR, non-GBP) customer that card payment is available, but the Stripe provider then rejects the order. That conflicts with DX-GC-05 ("no unsupported market flags") and with master §10 and §14 (no misleading payment or price representations).
- It needs **no** legal, tax or commercial approval. It enables nothing new; it only stops the API from advertising what the code cannot do.
- It is small, contained in existing code, and reversible.

**Scope (behaviour)**
1. A method is reported `is_available: true` only when its provider actually supports the requested currency: Stripe = GBP today (read from the provider, not hard-coded twice); Razorpay = INR.
2. An unsupported currency or country gets `is_available: false` with a machine-readable `reason_code` (for example `CURRENCY_NOT_SUPPORTED`, `MARKET_NOT_ENABLED`). The same response shape is kept, so the existing CartDrawer contract holds.
3. Remove the silent default `country = "India"` in PaymentMethodsView. A missing country uses the order's or user's country if one exists; otherwise every method is unavailable with `MARKET_NOT_SPECIFIED`.
4. Server-side guard at checkout and payment-session creation: reject a method/currency/country combination that step 1 reports unavailable, **before** an order or provider session is created (fail closed).

**Explicitly out of scope** (each still needs its own decision)
- No change to the COD policy or its defaults, and no removal of Razorpay (PD-14).
- No US or USD enablement (D04 verification, PD-16).
- No Stripe Connect or payouts (BLK-01).
- No new market-policy store (§2 row 8: reuse what exists; the ADR comes later).

**Files** (existing only): `backend/apps/marketplace/payments/service.py`, `backend/apps/marketplace/payments/stripe_provider.py` (expose supported currencies), `backend/apps/marketplace/views.py` (PaymentMethodsView; checkout path). Frontend: confirm that `frontend/src/components/platform/CartDrawer.tsx` already honours `is_available: false`; change it only if it does not. No migrations.

**Tests** (added to existing suites, e.g. `tests/test_payment_gateway_and_cod.py`)
- US/USD → no available online method; reason `CURRENCY_NOT_SUPPORTED`.
- GB/GBP → Stripe available when configured or in test mode (unchanged).
- IN/INR → Razorpay unchanged.
- Missing country → no implicit India.
- Checkout with an unavailable combination → 4xx, with no order and no provider session created.
- All existing payment, COD and Razorpay tests still pass.

**Acceptance criteria**
- No API response marks a method available when the provider would reject the currency.
- No order is created for a method/currency combination that cannot be paid.
- Existing GB and IN behaviour is unchanged.
- Test run recorded. SHA binding is to be added by the repository owner (CD-06).

**Alternative if you prefer zero production-code change first:** ENG-02 (API-level role-profile approval tests). It is tests only, with no runtime risk, and closes the D02 verification gap.

---
**Decision requested:** approve ENG-01 (or ENG-02) as the next implementation task, and confirm that the §3.1 gate labels and the §2 row 8 / BLK-04 / BLK-05 ADR topics should be added to the existing trackers.

> **Outcome (20 Nov 2026):** ENG-01 and ENG-02 were approved and implemented (§7). The second half of the request is **still open**: adding the §3.1 gate labels and the §2 row 8 / BLK-04 / BLK-05 ADR topics, and listing these ENG items, to the existing trackers (§5, last paragraph).

## 7. Implementation evidence log

*Added 20 November 2026 and finalised the same day. This section records implementation evidence only. It does not change the priorities, approvals or status of any item in §4–§6. Index of evidence records: [README.md](README.md).*

### 7.1 Status terms used in this log

| Term | Meaning here |
|---|---|
| **IMPLEMENTED** | The code (or, for test-only packages, the tests) exists in the working tree. |
| **TESTED** | Named tests were executed and passed, with the command, count and database recorded in the evidence record. |
| **IMPLEMENTED – NOT VERIFIED** | Baseline status (§3.3) for work that is implemented and tested but whose runs are **not bound to a commit SHA** and environment (DX-CONS CD-06/CD-07). |
| **VERIFIED IN TEST** | Tests pass on the **exact committed SHA**, with the environment recorded. This is the project's "IMPLEMENTED AND VERIFIED" (§3.3). **No package has reached it yet.** |

All work below sits **uncommitted** on top of `HEAD` `4107076f41b5dba269c490cbbdc8bfb059580f5d` (branch `indra`), so every package is at most IMPLEMENTED – NOT VERIFIED.

### 7.2 ID mapping (traceable correction)

Later implementation instructions reused the ENG numbers of §4.1 with different scopes. The §4.1 table is left unchanged; this mapping governs.

| Implementation ID | §4.1 plan ID | Master-register gap | Relationship |
|---|---|---|---|
| ENG-01 | **ENG-01** (same) | G15 (part), as cited in §4.1 | Same scope |
| ENG-02 | **ENG-02** (same) | None assigned. §4.1 cites D02, master test COM-008 and EV-04. | Same scope (tests only) |
| ENG-03 | — **NOT §4.1 ENG-03** | None assigned | Explicit delivery country at checkout. §4.1 has no row for it. |
| ENG-04a | — **NOT §4.1 ENG-04** | None assigned | Preparatory library proof for §4.1 **ENG-05**. §4.1 ENG-04 (settlement reconciliation) is untouched. |
| ENG-05a | — **NOT §4.1 ENG-05** | None assigned | Shared multi-seller order protection. §4.1 has no row for it. |
| ENG-05a-PG | — | None (verifies ENG-05a) | PostgreSQL concurrency verification |
| G17a | **ENG-03** | **G17** (partial) | Stripe chargeback intake |
| Frontend correction | — | As ENG-01 / ENG-03 | Client-side completion of ENG-01 (§6 "Files") and implementation ENG-03 |

**§4.1 items with no implementation:**
- **ENG-04** (settlement reconciliation design): NOT IMPLEMENTED. Its build waits on D04 verification.
- **ENG-05** (quote → checkout): NOT IMPLEMENTED. ENG-04a is preparatory only.

### 7.3 Log

| ID | Scope | Evidence | IMPLEMENTED / TESTED | Formal status | Open points |
|---|---|---|---|---|---|
| ENG-01 | Fail-closed payment-method and currency availability. Providers declare their supported currencies. Every method reports `is_available` with a `reason_code`. No implicit country. The checkout guard returns `PAYMENT_METHOD_UNAVAILABLE` before any order or session is created. | [04](04_ENG-01_Payment_Availability_Evidence_2026-11-20.md): 16 ENG-01 tests passed; 12-file regression **295 passed** (SQLite). The test file also passed on PostgreSQL in G17a P1 (pre-final code). | Implemented; tested (SQLite). Frontend completion in [08](08_ENG-01-03_Frontend_Delivery_Country_Evidence_2026-11-20.md). | **IMPLEMENTED – NOT VERIFIED** | Not re-run on final code. No SHA. US/USD unavailable until D04 and PD-16. |
| ENG-02 | D02 role-profile approval rules tested through the admin API. Tests only. | [05](05_ENG-02_Role_Profile_Approval_API_Tests_Evidence_2026-11-20.md): 17 cases; filtered run 18 passed, 16 deselected; commercial suites **78 passed** (SQLite). | Implemented (tests); tested (SQLite only) | **IMPLEMENTED – NOT VERIFIED** | Never run on PostgreSQL. BLK-04 (reference resolution) and BLK-06 (approved profiles) open. |
| ENG-03 | `DELIVERY_COUNTRY_REQUIRED` on checkout preview and order creation; no implicit country | [06](06_ENG-03_Explicit_Delivery_Country_Evidence_2026-11-20.md): 23 ENG-03 cases + 1 updated test = **24 passed**; regression **318 passed** (SQLite) | Implemented (backend and frontend); tested (SQLite; frontend static checks only) | **IMPLEMENTED – NOT VERIFIED** | Never run on PostgreSQL. Browser test outstanding. Only India and the UK are offered in the UI. |
| ENG-04a | Non-binding commercial quote adapter. **Library-level proof only; NOT integrated into application checkout.** | [07](07_ENG-04a_Commercial_Quote_Adapter_Evidence_2026-11-20.md): **25 passed**; 14-file regression **396 passed** (SQLite) | Implemented (library); tested (SQLite) | **IMPLEMENTED – NOT VERIFIED** | Not re-run since later `views.py` changes. Never run on PostgreSQL. Integration (§4.1 ENG-05) not authorised. |
| ENG-05a | Shared (multi-seller) orders: sellers cannot change order-level status (409 `MULTI_SELLER_ORDER_STATUS_LOCKED`). Seller refunds are limited to the seller's own items' share (`SELLER_REFUND_LIMIT_EXCEEDED`, `REFUND_NOT_SELLER_ITEM`, `REFUND_ATTRIBUTION_AMBIGUOUS`). Admin and dispute refunds are unchanged. | [02](02_ENG-05a-PG_Refund_Concurrency_Evidence_2026-11-20.md) §0: `test_shared_order_seller_isolation.py` **17 passed** (SQLite); 22-file regression **637 passed** (it did not include the isolation file). The 17 tests also passed on PostgreSQL 17.11 (the 286-test run and G17a P1). | Implemented; tested (SQLite and PostgreSQL) | **IMPLEMENTED – NOT VERIFIED** | Policy question: should admin and dispute refunds respect seller shares? (L5 in [02](02_ENG-05a-PG_Refund_Concurrency_Evidence_2026-11-20.md), for the Appendix D item 9 owner.) Not re-run on PostgreSQL against G17a's final code. |
| ENG-05a-PG | Concurrency verification of ENG-05a refund limits on PostgreSQL, using real parallel transactions | [02](02_ENG-05a-PG_Refund_Concurrency_Evidence_2026-11-20.md): 11 of 11 concurrency tests passed with row-lock contention proven in each; the negative control failed as expected; the PostgreSQL refund regression passed 286 of 286 across 8 files. All 11 passed again in G17a P2 after the harness fix. | Tests implemented; tested (PostgreSQL). No production code changed. | **IMPLEMENTED – NOT VERIFIED** | L1–L9 in [02](02_ENG-05a-PG_Refund_Concurrency_Evidence_2026-11-20.md) |
| **G17a** | Stripe chargeback intake as a recorded exception.<br>- `charge.dispute.*` events are linked to orders by PaymentIntent.<br>- The lifecycle is recorded in the audit trail: dispute ID, amount, currency, reason, status, evidence deadline, outcome, and fees kept separate.<br>- Unmatched events stay visible.<br>- **Refund guard** while a chargeback is open or lost (`CHARGEBACK_OPEN` / `CHARGEBACK_LOST`, HTTP 400): it blocks new refunds and the approval, dispatch and settlement of existing refunds, which are preserved unchanged.<br>- Inquiries are recorded but don't block. Recording seller direct refunds stays allowed.<br>- No money movement. | [03](03_G17a_Stripe_Chargeback_Intake_Evidence_2026-11-20.md): SQLite **515 + 44 passed**; PostgreSQL 17.11 **59 of 59** on final code, including 4 G17a real-concurrency tests (§7.2 of that record) | Implemented; tested (SQLite and PostgreSQL) | **G17 stays PARTIALLY IMPLEMENTED.** G17a: **IMPLEMENTED – NOT VERIFIED** (record §7.4). No G17 closure or market certification is claimed. | - **REF-03:** owner assignment **deferred** (ticket confidentiality doesn't protect the buyer).<br>- **REF-04:** **partial**.<br>- **REF-05 and REF-07:** **blocked** (BLK-01 / D04).<br>- **REF-08:** **deferred** (Appendix D item 9).<br>- **Lost chargebacks:** resolving them is an authorised **financial policy dependency** (CFO + Payments; R05-06, COM-02 R02-08).<br>- **Manual payout recording limitation (L5):** while a chargeback blocks, finance cannot record a bank-transfer refund it has already paid.<br>- **The broader PostgreSQL refund/payment regression was not re-run after the final fixes** (record §7.3).<br>- Out of scope: evidence submission, payout holds, loss allocation and ledger; Razorpay disputes (PD-14). |
| Frontend correction (ENG-01/ENG-03) | Removes the implicit India default and its fallbacks from the cart checkout. The buyer must select a delivery country explicitly; it is passed consistently. Backend codes `DELIVERY_COUNTRY_REQUIRED` and `PAYMENT_METHOD_UNAVAILABLE` (with reason codes) are handled. | [08](08_ENG-01-03_Frontend_Delivery_Country_Evidence_2026-11-20.md): `tsc --noEmit`, ESLint and `next build` all exit 0 | Implemented. **Static checks and build only; no frontend test framework exists.** | **IMPLEMENTED – NOT VERIFIED** | **Browser-level testing outstanding.** Region default after country choice is a product question. |

### 7.4 Consolidated outstanding items (blocking VERIFIED IN TEST and sign-off)

1. **Commit SHA:** none of the tested code is committed. The repository owner must commit the full working tree and record the SHA ([03](03_G17a_Stripe_Chargeback_Intake_Evidence_2026-11-20.md) §7.4 lists what it must contain, plus the three frontend files in [08](08_ENG-01-03_Frontend_Delivery_Country_Evidence_2026-11-20.md)).
2. **Full backend regression:** never run on the final code, on SQLite or PostgreSQL. The largest runs were subsets (637 tests / 22 files on 19 Nov; 515 / 17 on 20 Nov).
3. **Broader PostgreSQL regression:**
   - 7 refund and payment files have not been re-run after G17a's final fixes;
   - 8 further files have never run on PostgreSQL during G17a (record 03 §7.3);
   - the ENG-02, ENG-03 and ENG-04a suites have never run on PostgreSQL.
4. **Migration check:** `manage.py makemigrations --check --dry-run` has never been run. The "no migrations" claims rest on code inspection.
5. **Frontend:** browser-level testing is outstanding. No automated frontend tests exist.
6. **G17 remainder:**
   - REF-03 (owner) deferred;
   - REF-04 partial;
   - REF-05 and REF-07 blocked on Stripe Connect (BLK-01, D04);
   - REF-08 deferred;
   - lost-chargeback financial policy (CFO + Payments);
   - manual payout recording limitation (G17a L5).
7. **External approvals** (§4.2, §4.3, §5): D02 role memos, D04 Stripe Connect verification, D09 tax, PD-11 to PD-16, BLK-04 to BLK-06, Appendix D item 9. **None is approved.**
8. **Tracker additions** pending approval (§5, last paragraph; §6 outcome note).

No gap in this document, or in `../01_Engineering_Reconciliation_Matrix.md`, `../05_G0-G3_Launch_Readiness_Tracker.md` or the other trackers, is marked verified by this log.
