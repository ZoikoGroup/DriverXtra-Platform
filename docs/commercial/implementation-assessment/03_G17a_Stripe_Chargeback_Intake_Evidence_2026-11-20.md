# G17a — Stripe chargeback intake and refund guard: evidence record

| Field | Value |
|---|---|
| Date | 20 November 2026 |
| Master-register gap | **G17** (P0, evidence class V, lead document DX-GC-05): "Refunds, reversals, chargebacks and platform fault". |
| Plan item | Gap-closure plan §4.1 **ENG-03** (chargeback event intake as a recorded exception, with no automatic money movement). This is **not** the implementation-sequence "ENG-03" (delivery-country check). |
| Package | **G17a**, a partial closure. **G17 remains PARTIALLY IMPLEMENTED.** This is not G17 certification. |
| Mode | Stripe test mode only. |
| Excluded | No money movement, evidence submission, seller deductions, payout holds, ledger journals, loss allocation, Razorpay chargebacks, new models, migrations, consoles, queues or tickets. |
| Test results | **G17a tests pass on the final code.** SQLite: 515 passed (focused regression) plus 44 passed (re-run on final code). PostgreSQL 17.11: 59 of 59 on the final code, including 4 G17a real-concurrency tests (§7.2). |
| Not re-run | **The broader PostgreSQL refund/payment regression was NOT re-run after the final fixes** (§7.3). Its only PostgreSQL run (236 passed, 5 failed) predates both the test-only fixes **and** one production-code change (the `confirm_refund_receipt` lock-order swap). |
| Formal status | Baseline terms (gap-closure plan §3.3; DX-CONS CD-06/CD-07): **IMPLEMENTED – NOT VERIFIED** until the runs are bound to a commit SHA and environment. The tested code is not yet committed (§7.4). **G17 remains PARTIALLY IMPLEMENTED.** No G17 closure and no market certification (EV-08 / B-G5) is claimed. |

## 1. Approved decisions implemented

| # | Decision (approved 20 Nov 2026) | Implementation |
|---|---|---|
| D1 | Record `warning_*` inquiries; do not block refunds | Inquiries are recorded with `is_inquiry: true`, state `INQUIRY`. They do not block refunds until Stripe escalates them to a chargeback status. |
| D2 | While a chargeback is open, prevent new approval or dispatch of existing pending refunds. Preserve their state and records. Reconciliation and failure recording stay available. | `approve_refund`, `dispatch_gateway_refund` (which also covers maker-checker execution) and `process_refund` (manual settlement) are refused **before** any change. Existing refunds are never modified by dispute events. `fail_refund`, `reject_refund`, reconciliation, manual FAILED/CANCELLED resolution and refund webhooks are unchanged. |
| D3 | Keep refunds blocked after a lost chargeback; lift the block after a won one | `lost` → `CHARGEBACK_LOST`, which keeps blocking. `won` → the block is lifted. A lost chargeback does not restore refundable balance; resolving it is an authorised **financial policy dependency** (§8). |
| D4 | Allow recording an already-completed seller direct refund; never initiate a payment through it; keep share and balance protections | See §3. |
| — | HTTP 400 with an explicit code | `CHARGEBACK_OPEN`. `CHARGEBACK_LOST` is used for the lost state (D3), so the reason stays explicit. |
| — | Guard applies to admin and seller creation paths | Applies to admin refund creation (including `auto_process`) and seller platform-refund requests. |
| — | Unmatched events stay visible; REF-03 tickets deferred; no external notifications | See §2 and §5. |

## 2. Webhook lifecycle (Stripe)

**Unchanged existing behaviour:**
- Signature check (HMAC).
- Deduplication by unique `event_id`: checked before the transaction, and again inside it under lock.
- The order row is locked inside the webhook transaction.

**What changed:**
1. **Linking.** Order linking applies to any Stripe `charge.dispute.*` event *or* any object with `object: "dispute"` (`payments/service.py`, dispute branch). **Recording** (step 2) applies only to `charge.dispute.*` event types. Disputes carry no order metadata, so they are linked through `payment_intent` → `Order.payment_reference`, falling back to `PaymentTransaction.provider_order_id`.
   - If no order matches, it is recorded as **unmatched** with reason `NOT_FOUND`.
   - If more than one order matches, it is recorded as **unmatched** with reason `AMBIGUOUS`.
   - If the event has no PaymentIntent, it is recorded as **unmatched** with reason `NO_PAYMENT_INTENT`.
   - The generic lookup fallback is disabled for disputes, so it can no longer misuse the `dp_…` ID as a PaymentIntent.
2. **Recording.** Recording happens inside the webhook transaction, under the order row lock when an order was linked. Unmatched events have no order to lock and are recorded in the same transaction. Audit event types:
   - `marketplace.payment.chargeback_opened`
   - `_updated`
   - `_funds_withdrawn`
   - `_funds_reinstated`
   - `_closed`
   - `_unmatched`

   Each entry records, in its metadata:
   - dispute ID, PaymentIntent and charge;
   - amount in minor units, and currency;
   - reason, status, state and outcome;
   - evidence deadline (`due_by`, as UTC ISO-8601) and `past_due`;
   - `livemode` and the event time;
   - order currency and a `currency_mismatch` flag;
   - each reported balance transaction, with **amount and fee kept separate** and fee details listed. The platform never computes or stores a net figure.
   - **Actor kind:** `SYSTEM`.
3. **Ordering.** Stripe doesn't guarantee delivery order.
   - `won` and `lost` are final: a late, older event cannot reopen a closed dispute.
   - Otherwise the event with the latest Stripe `created` time decides.
   - On a tie, the more restrictive state wins (fail closed).
   - Unknown statuses count as `OPEN` (fail closed).
4. **Duplicates.** The existing `event_id` deduplication applies. Verified both sequentially and with concurrent delivery (§7.2).
5. **No side effects:**
   - no change to order `status` or `payment_status`;
   - no `Refund` or `PaymentTransaction` rows;
   - no notifications (no notification resolver exists for these event types);
   - no automatic Stripe calls.

## 3. Seller direct refunds: recording vs initiating (D4)

`record_seller_direct_refund` (`POST seller/orders/<id>/record-refund/`) cannot initiate a payment:
- It never calls a payment provider or any dispatch path.
- It always records a payment the seller attests is already completed. A transaction reference is mandatory.
- The refund it creates is `SELLER_DIRECT` / `PROCESSING`, a state that `approve_refund` and `dispatch_gateway_refund` both refuse.

So there is no initiation path to block, and recording stays available during an open or lost chargeback:
- ENG-05a seller-share and order-balance checks still apply.
- The evidence audit entry adds `chargebacks_at_recording` and `recorded_while_chargeback_blocks`.
- Completing such a record (buyer receipt confirmation, or `process_refund` on a `SELLER_DIRECT` refund) is also allowed, because it records a completed payment rather than dispatching one.

**Limitation:** completion is seller-attested and the platform cannot verify it. This is unchanged existing behaviour.

## 4. Refund guard: entry-point matrix

"Blocking" means a formal chargeback that is open, or one that was lost. The guard runs with the **order row locked**, using the same order → refund lock sequence as the webhook.

| Entry point | Behaviour while blocking |
|---|---|
| `create_refund`: admin `admin/orders/<id>/refund/` (including `auto_process`) and seller `request-platform-refund/` | 400 `CHARGEBACK_OPEN` / `CHARGEBACK_LOST`. Takes precedence over balance and share errors. No refund is created. |
| `approve_refund`: `admin/refunds/<id>/approve/` | Refused before `approved_by`, notes or status change. |
| `dispatch_gateway_refund`: `admin/refunds/<id>/dispatch/`, approval execution, `auto_process` | Pre-check before any maker-checker request is created, then an authoritative check under lock before any state change or provider call. An already-SUCCEEDED refund keeps its idempotent return. |
| `process_refund`: `admin/refunds/<id>/process/` | Refused, except for `SELLER_DIRECT` (recording a completed payment). |
| `record_seller_direct_refund` | Allowed (D4), with evidence flags. |
| `confirm_refund_receipt` (buyer) | Available. The only change is its lock order (order → refund). Tested during an open chargeback. |
| `fail_refund`, `reject_refund` | Unchanged and available. Tested during an open chargeback. |
| `reconcile_refund`, `manual_resolve_unknown_refund` (FAILED/CANCELLED only), `reconcile_all_pending_unknown`, refund webhooks | Unchanged and not guarded (code inspection: none of them calls `issue_refund`, `approve_refund` or `process_refund`). **Not separately exercised during an open chargeback.** |

Every refused attempt writes a **denied audit entry**: reason code, attempted amount, refund number and dispute IDs.
- On PostgreSQL this entry is committed on an independent connection, so it survives the rollback.
- On SQLite it is rolled back with the request. That is the existing behaviour of `record_denied_audit_entry`.

**Messages** that sellers may see carry no dispute identifiers or card-network details. In the refund summary, `chargebacks` and `chargeback_refund_block_code` are returned only to users holding `order.refund` or `finance.payout`. Visibility is permission-based, not role-based: a seller account that also holds one of those permissions (as in the ENG-05a test setup) would see them. Buyers and ordinary sellers do not.

## 5. REF-03 (owner and deadline): deferred

The existing support `Ticket` confidentiality does **not** protect the buyer the ticket would be attached to:
- `is_confidential` hides tickets from agents only (`apps/support/views.py` agent views).
- The customer ticket list filters only by customer (`views.py:78`).
- The customer detail view allows the owner regardless of the flag (`views.py:126`).
- Ticket creation and status changes notify `ticket.customer` (`apps/notifications/handlers.py:1317-1324`, `1381-1388`).

No tickets are created. The evidence deadline **is** recorded (`evidence_due_by`). **Owner assignment is not implemented.**

## 6. Files

| File | Change |
|---|---|
| `backend/apps/marketplace/payments/chargebacks.py` | **New.** Parsing, order linking, recording, state derivation, and the guard (`ChargebackRefundBlocked`). |
| `backend/apps/marketplace/payments/service.py` | `process_webhook`: Stripe dispute linking branch, and dispute recording inside the existing locked transaction. |
| `backend/apps/marketplace/returns/service.py` | `_guard_chargeback` helper. Guards in `create_refund`, `approve_refund`, `dispatch_gateway_refund` and `process_refund`. Evidence flags in `record_seller_direct_refund`. Order → refund lock order in `approve_refund`, `dispatch_gateway_refund` and `process_refund`, and also in `confirm_refund_receipt` (swap of two lock lines, no behaviour change) to avoid a refund/order deadlock with approve and dispatch. |
| `backend/apps/marketplace/views.py` | `_refund_error_body`: admin create, approve, process and dispatch 400 bodies gain `code` (additive). Refund summary gains staff-only `chargebacks` and `chargeback_refund_block_code`. |
| `backend/apps/identity/views.py` | Approval execute view 400 body gains `code` (additive). |
| `backend/tests/test_stripe_chargeback_intake.py` | **New.** 25 tests. |
| `backend/tests/test_refund_concurrency_postgresql.py` | Gate generalised (`install_on_function`, configurable contention assertion). The poll now waits until `wait_event_type = 'Lock'` and the live lock graph agree. 4 new G17a PostgreSQL tests. |
| Docs | This record; §7 of `01_Gap_Closure_Plan_Update_2026-11-19.md`; note on finding line 127 of `com/COM-05_Marketplace_Settlement_and_PSP.md`; harness-update note in `02_ENG-05a-PG_Refund_Concurrency_Evidence_2026-11-20.md`. |

No migrations. No frontend change, so the UI doesn't display chargebacks yet.

## 7. Test evidence

### 7.1 Complete run log (in order)

Every command was run from `backend/` with the project virtualenv. Where output was piped through `grep`/`tail` for display, the filter didn't affect the test result.

| # | DB | Command | Result | Code state |
|---|---|---|---|---|
| S0 | SQLite | `.venv/Scripts/python.exe -m pytest tests/test_stripe_chargeback_intake.py -q -p no:cacheprovider -o addopts="" --tb=short` | **1 failed, 23 errors.** **Test-fixture fault:** `Order.currency` is an immutable financial snapshot, so the helper could not switch an existing order to GBP. Fixed by creating GBP orders at creation time. | Pre-final |
| S1 | SQLite | same as S0 | **24 passed** | Pre-final |
| S2 | SQLite | `.venv/Scripts/python.exe -m pytest tests/test_refund_concurrency_postgresql.py -q -p no:cacheprovider -o addopts=""` | **15 skipped**: PostgreSQL-only module is never counted on SQLite | Final |
| S3 | SQLite | `.venv/Scripts/python.exe -m pytest tests/test_stripe_chargeback_intake.py tests/test_refund_concurrency_postgresql.py tests/test_payment_gateway_and_cod.py tests/test_stage_e_payment_integration.py tests/test_razorpay_actual_integration.py tests/test_returns_refunds_and_disputes.py tests/test_marketplace_payment_refunds.py tests/test_admin_disputes_and_refunds_workflow.py tests/test_refund_gateway_timeout_reconciliation.py tests/test_shared_order_seller_isolation.py tests/test_shipping_and_logistics.py tests/test_authorization_matrix.py tests/test_notifications_workflow_integration.py tests/test_maker_checker_engine.py tests/test_staff_security_remediation.py tests/test_marketplace_checkout.py tests/test_country_currency_checkout.py -p no:cacheprovider -q -rfE` | **515 passed, 15 skipped, 0 failed** (4,107.78 s). 17 files; the intake file had 24 tests at that point. | Before the `confirm_refund_receipt` lock swap and the test-scoping fixes |
| P1 | PostgreSQL | `TEST_USE_SQLITE=False .venv/Scripts/python.exe -m pytest tests/test_stripe_chargeback_intake.py tests/test_refund_concurrency_postgresql.py tests/test_refund_gateway_timeout_reconciliation.py tests/test_marketplace_payment_refunds.py tests/test_returns_refunds_and_disputes.py tests/test_admin_disputes_and_refunds_workflow.py tests/test_shared_order_seller_isolation.py tests/test_maker_checker_engine.py tests/test_payment_gateway_and_cod.py -p no:cacheprovider -q -rfE` | **236 passed, 5 failed** (2,340.92 s). 9 files. Only the last 60 lines of output were retained (the failures and the summary), so a per-file breakdown is not available. | Same as S3 |
| P- | PostgreSQL | P2's command, preceded by a database probe | **Not run (0 tests).** PostgreSQL refused connections and the `&&` chain stopped before pytest started. | — |
| S4 | SQLite | `.venv/Scripts/python.exe -m pytest tests/test_stripe_chargeback_intake.py tests/test_marketplace_responsibilities.py tests/test_refund_concurrency_postgresql.py -p no:cacheprovider -q -rfE` | **44 passed, 15 skipped, 0 failed** (506.18 s): intake 25 + responsibilities 19 (includes buyer receipt confirmation) | **Final** |
| P2 | PostgreSQL | `TEST_USE_SQLITE=False .venv/Scripts/python.exe -m pytest tests/test_stripe_chargeback_intake.py tests/test_refund_concurrency_postgresql.py tests/test_marketplace_responsibilities.py -p no:cacheprovider -q -rA` | **59 passed, 0 failed** (924.85 s): intake 25 + concurrency 15 (11 ENG-05a-PG + 4 G17a) + responsibilities 19 | **Final** |

"Final" means the code and tests as they stand now, with no change after S4 and P2. SQLite is never counted as concurrency evidence.

### 7.2 PostgreSQL 17.11 (Docker), disposable `test_driverxtra_db`

**Test database safety:** before each run a read-only probe listed only `driverxtra_db` and `postgres`, so `test_driverxtra_db` was absent. pytest-django created and dropped it on each run, and the same list was confirmed afterwards. `driverxtra_db` was never touched.

Run P1 (236 passed, 5 failed) and run P2 (59 passed, 0 failed) are detailed in §7.1.

**P1 failures, exactly, and why they are test faults, not product faults:**

| Test | Error | Cause | Fix (test only) |
|---|---|---|---|
| `test_admin_refund_creation_blocked_while_open[False]` | `AuditLog.MultipleObjectsReturned` (`get()` returned 3) | Unscoped audit query. On PostgreSQL, denied entries are committed on an independent connection and persist across tests. | Scoped to `metadata__order_number` |
| `test_admin_refund_creation_blocked_while_open[True]` | `AuditLog.MultipleObjectsReturned` (`get()` returned 4) | Same | Same |
| `test_pg_refund_waiting_on_chargeback_intake_is_refused` | `assert 9 == 1` (denied-audit count) | Same. The behaviour was correct: `refund: HTTP 400 CHARGEBACK_OPEN` with contention observed. | Same |
| `test_pg_concurrent_duplicate_dispute_delivery_is_recorded_once` | `assert 4 == 1` (`chargeback_opened` count) | Rows from earlier transactional tests remained. The behaviour was correct: both HTTP 200, and the preceding `already_processed` assertion passed. | Scoped to `resource_id` = the order |
| `test_pg_dispute_refund_racing_seller_refund[seller_b]` (existing ENG-05a-PG test) | `assert None == 'Lock'` (`wait_event_type`) | Harness timing: the `pg_stat_activity` snapshot lagged the live `pg_blocking_pids()`. Refund outcomes were correct (`seller_b: 201; dispute_admin: 201`). | Poll now also requires `wait_event_type = 'Lock'` |

No refund-behaviour assertion was weakened. P1 also predates the `confirm_refund_receipt` lock swap. P2 covers that through `test_marketplace_responsibilities.py` and `test_buyer_can_confirm_receipt_of_seller_direct_refund_during_chargeback`.

**P2 G17a contention proof.** Every test asserted that:
- the competitor was blocked by the holder's own PID;
- its wait event was `Lock`;
- it held the expected lock on the expected table;
- it had an ungranted lock.

In every case the observed ungranted lock was `transactionid ShareLock`:

| Test | Hold point → blocked competitor | Outcome |
|---|---|---|
| `test_pg_refund_commits_before_concurrent_chargeback_intake` | Refund (order lock) → dispute webhook `SELECT … FOR UPDATE` on `marketplace_order` | `refund: HTTP 201; webhook: HTTP 200`. Chargeback recorded after; the next refund returns `CHARGEBACK_OPEN`. |
| `test_pg_refund_waiting_on_chargeback_intake_is_refused` | Webhook (order lock) → refund `SELECT … FOR UPDATE` | `webhook: HTTP 200; refund: HTTP 400 CHARGEBACK_OPEN`. No refund row; one denied audit entry survived the rollback. |
| `test_pg_pending_refund_approval_waiting_on_chargeback_intake_is_refused` | Webhook (order lock) → approval `SELECT … FOR UPDATE` | `approve: HTTP 400 CHARGEBACK_OPEN`. The pending refund's status, approver and notes are unchanged. |
| `test_pg_concurrent_duplicate_dispute_delivery_is_recorded_once` | First delivery → second delivery's `INSERT` blocked on the unique `event_id` (`RowExclusiveLock` on `marketplace_paymentwebhookevent`) | Both HTTP 200; the second returns `already_processed`. One webhook row and one audit entry. |

All 11 ENG-05a-PG tests passed again in P2, with contention observed, under the code changed by G17a.

**Environment note:** during the session PostgreSQL briefly refused connections while `docker ps` was unresponsive (run P-). It recovered by itself: container `driverxtra_db`, `postgres:17-alpine`, reported "Up 5 hours (healthy)". Nothing was started, stopped or modified.

### 7.3 Not re-run on PostgreSQL after the final fixes (explicit)

The final code differs from P1's in one **production** change (the `confirm_refund_receipt` lock swap) and in test-only fixes. **The following were NOT re-run on PostgreSQL against the final code.** Their last PostgreSQL results come from P1; their final-code coverage is SQLite run S3 (which itself predates the lock swap):
- `test_refund_gateway_timeout_reconciliation.py`
- `test_marketplace_payment_refunds.py`
- `test_returns_refunds_and_disputes.py`
- `test_admin_disputes_and_refunds_workflow.py`
- `test_shared_order_seller_isolation.py`
- `test_maker_checker_engine.py`
- `test_payment_gateway_and_cod.py`

**Never run on PostgreSQL during G17a (SQLite S3 only):**
- `test_stage_e_payment_integration.py`
- `test_razorpay_actual_integration.py`
- `test_shipping_and_logistics.py`
- `test_authorization_matrix.py`
- `test_notifications_workflow_integration.py`
- `test_staff_security_remediation.py`
- `test_marketplace_checkout.py`
- `test_country_currency_checkout.py`

**Since S3:** the only production change is the `confirm_refund_receipt` lock swap. Of the SQLite suites, only `test_marketplace_responsibilities.py` (S4) exercises that function, and the S3 suites have not been re-run against it.

**Recommended to close this gap:** re-run P1's command and S3's command on the final code, and record the results here.

### 7.4 Commit SHA required (CD-06)

| Item | Value |
|---|---|
| Branch | `indra` |
| Current `HEAD` | `4107076f41b5dba269c490cbbdc8bfb059580f5d` (merge of PR #18). Read from `.git/HEAD` and `.git/refs/heads/indra` with a file reader; **no Git command was run.** It matches the session-start snapshot. |
| Is `HEAD` the evidence SHA? | **No.** Every run above tested `HEAD` **plus uncommitted working-tree changes**, so no existing commit contains the tested code. |
| SHA the evidence needs | The full SHA of the **future commit** whose tree equals the tested working tree. It doesn't exist yet. The repository owner must commit those changes (and push them if the evidence must be remotely reachable), then record that SHA here and in §7 of the gap-closure plan. |
| What that commit must contain | Per the session-start status snapshot plus files changed since in this session (not re-verified with Git):<br>**Modified:**<br>- `backend/apps/marketplace/payments/{base,razorpay_provider,service,stripe_provider}.py`<br>- `backend/apps/marketplace/returns/service.py`<br>- `backend/apps/marketplace/views.py`<br>- `backend/apps/identity/views.py`<br>- `backend/tests/{test_commercial_api,test_country_currency_checkout,test_marketplace_checkout,test_payment_gateway_and_cod}.py`<br>**New:**<br>- `backend/apps/marketplace/commercial_quote_adapter.py`<br>- `backend/apps/marketplace/payments/chargebacks.py`<br>- `backend/tests/{test_commercial_quote_adapter,test_shared_order_seller_isolation,test_refund_concurrency_postgresql,test_stripe_chargeback_intake}.py`<br>- `docs/commercial/`<br>**Why it can't be split:** G17a depends on the earlier ENG-01–ENG-05a changes in the same files, so G17a alone can't be committed separately without re-testing.<br>**Added 20 Nov (frontend correction, [08](08_ENG-01-03_Frontend_Delivery_Country_Evidence_2026-11-20.md)):** `frontend/src/components/platform/CartDrawer.tsx`, `frontend/src/context/CartContext.tsx`, `frontend/src/lib/api/client.ts`. |
| After committing | Re-run P2 (and ideally P1 and S3) on that exact commit, so the runs are bound to the SHA and environment (PostgreSQL 17.11, Python 3.13.15, Django 5.1.15, pytest 9.1.1, pytest-django 4.14.0). |

### 7.5 Acceptance-test mapping

| Plan test | Test(s) |
|---|---|
| AT-01 link and record, no state change | `test_dispute_created_is_linked_and_recorded_without_state_change` |
| AT-02 signature | `test_invalid_or_missing_signature_is_rejected_and_nothing_recorded` |
| AT-03 duplicate | `test_duplicate_delivery_is_recorded_once`; PostgreSQL: `test_pg_concurrent_duplicate_dispute_delivery_is_recorded_once` |
| AT-04/05 unmatched | `test_unmatched_dispute_stays_visible[...]`, `test_ambiguous_payment_reference_is_unmatched` |
| AT-06 lifecycle and fees (REF-06) | `test_lost_lifecycle_records_fees_separately_and_keeps_refunds_blocked` |
| AT-07/12 won and lost | `test_won_lifts_the_block`, the lost test above |
| AT-08 ordering | `test_out_of_order_delivery_cannot_reopen_a_closed_dispute`, `test_same_timestamp_conflict_fails_closed` |
| AT-09/10 creation guard | `test_admin_refund_creation_blocked_while_open[False/True]`, `test_seller_platform_refund_request_blocked_while_open`, `test_chargeback_reason_takes_precedence_over_balance_error` |
| AT-11 / D2 existing refunds | `test_pending_refund_preserved_and_approve_dispatch_process_blocked`, `test_high_value_dispatch_creates_no_maker_checker_request_while_blocked`; PostgreSQL: `test_pg_pending_refund_approval_waiting_on_chargeback_intake_is_refused` |
| AT-13 / D1 inquiries | `test_inquiry_is_recorded_but_does_not_block_until_escalated` |
| AT-14 multiple disputes | `test_one_open_dispute_among_several_still_blocks` |
| AT-15 currency | `test_currency_mismatch_is_flagged` |
| AT-16 other webhooks unchanged | Regression suites (payment/COD, Stripe stage E, Razorpay, refund reconciliation) |
| AT-17 no notifications | `test_chargeback_events_create_no_notifications` |
| AT-18 staff-only visibility | `test_refund_summary_exposes_chargebacks_to_staff_only` |
| D4 recording | `test_seller_direct_refund_recording_allowed_and_evidenced[needs_response/lost]`, `test_buyer_can_confirm_receipt_of_seller_direct_refund_during_chargeback`, `test_seller_direct_recording_keeps_share_and_balance_rules` |
| AT-PG1/PG2 races | `test_pg_refund_commits_before_concurrent_chargeback_intake`, `test_pg_refund_waiting_on_chargeback_intake_is_refused` |

## 8. Remaining G17 scope and dependencies (kept visible)

| Item | Status | Dependency |
|---|---|---|
| REF-01/REF-02 (no duplicate refund on replay) | Covered by existing refund tests; not re-certified here | — |
| REF-03 chargeback deadline **and assigned owner** | **Partial:** deadline recorded; owner **deferred** | A buyer-safe internal case mechanism (§5). No new ticketing system without approval (CD-01). |
| REF-04 disputed payment while refund pending | **Partial:** guard on creation, approval, dispatch and settlement | Lost-chargeback financial resolution (below) |
| REF-05 reversed transfer vs refunded charge | **Not implemented** | BLK-01 (Stripe Connect, D04) |
| REF-06 win/loss and fees without netting | **Recorded** (intake level) | Ledger journals are out of scope (COM-007; ledger not in R1) |
| REF-07 provider-mandated hold | **Not implemented** | BLK-01 |
| REF-08 buyer/seller notification | **Deferred** | Notice wording and liability policy (Appendix D item 9) |
| Lost-chargeback resolution | **Policy dependency:** refunds stay blocked (`CHARGEBACK_LOST`) and refundable balance is not restored | Authorised financial resolution: CFO + Payments (R05-06 refund/chargeback precedence; COM-02 R02-08 loss allocation) |
| Evidence submission to Stripe; payout holds; loss allocation; ledger | Out of scope | D04 / BLK-01 / COM-04 / COM-05 decisions |
| Razorpay disputes | Out of scope | PD-14 |

## 9. Limitations

| # | Limitation |
|---|---|
| L1 | No UI change. Chargeback state is API-visible to staff only (refund summary) and in the audit trail. |
| L2 | Unmatched and ambiguous disputes are visible in the audit trail but cannot block refunds on any order. |
| L3 | A refund whose dispatch committed `PROCESSING` before the chargeback was recorded proceeds to its provider call. The decision preceded knowledge of the chargeback; reconciliation still applies. |
| L4 | Denied-attempt audit entries survive rollback on PostgreSQL only (existing writer design). On SQLite they roll back. |
| L5 | Manual settlement of a platform bank-transfer refund that finance has **already** paid cannot be recorded while blocking, because `process_refund` doesn't distinguish "pay now" from "already paid". Blocked per D2; recordable after a `won` outcome or authorised resolution. |
| L6 | Seller direct completion is seller-attested (existing semantics). |
| L7 | `livemode` is recorded but not enforced. The package is exercised in Stripe test mode only. |
| L8 | Pre-existing, not changed: the Stripe signature check has no timestamp tolerance. Event-ID deduplication limits replay impact. |
| L9 | No commit SHA bound (CD-06). |
