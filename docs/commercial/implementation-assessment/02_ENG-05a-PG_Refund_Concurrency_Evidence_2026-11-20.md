# ENG-05a-PG — PostgreSQL refund concurrency evidence

| Field | Value |
|---|---|
| Date | 20 November 2026 |
| Scope | Verify, on PostgreSQL, that ENG-05a (shared multi-seller order protection) holds under genuinely concurrent refund requests. |
| Result | **PASSED.** 11 of 11 concurrency tests passed on PostgreSQL 17.11, with row-lock contention observed in every test. 286 of 286 tests passed in the PostgreSQL refund regression run. |
| Production code changed | **None.** No defect was found. |
| Verification status | Concurrency tests pass on PostgreSQL. Formal status (gap-closure plan §3.3): **IMPLEMENTED – NOT VERIFIED** until the runs are bound to a commit SHA (DX-CONS CD-06). The tested code is uncommitted on top of `HEAD` `4107076f41b5dba269c490cbbdc8bfb059580f5d` (see `03_G17a_…` §7.4). Git commands were not permitted in this work. |
| Related record | [01_Gap_Closure_Plan_Update_2026-11-19.md §7](01_Gap_Closure_Plan_Update_2026-11-19.md#7-implementation-evidence-log) |

## 0. Underlying ENG-05a implementation evidence (SQLite, 19 Nov 2026)

*Added 20 Nov 2026, so that ENG-05a's own test evidence is recorded alongside its PostgreSQL verification. Results come from the session's run log.*

**IDs:** ENG-05a is an implementation ID. It is **not** gap-closure plan §4.1 ENG-05 (quote → checkout), and no master-register gap ID is assigned to it.

**Files:**
- `backend/apps/marketplace/returns/service.py` (seller-share enforcement);
- `backend/apps/marketplace/views.py` (409 `MULTI_SELLER_ORDER_STATUS_LOCKED`; error `code` in the seller refund views);
- `backend/tests/test_shared_order_seller_isolation.py` (new, 17 tests).

| # | When (UTC, 19 Nov) | Command (from `backend/`) | Result |
|---|---|---|---|
| E5-1 | 10:35 | `.venv/Scripts/python.exe -m pytest tests/test_shared_order_seller_isolation.py -q -p no:cacheprovider -rfE` | **17 passed** (303.00 s) |
| E5-2 | 11:17 | `.venv/Scripts/python.exe -m pytest tests/test_payment_gateway_and_cod.py tests/test_country_currency_checkout.py tests/test_marketplace_checkout.py tests/test_order_management.py tests/test_platform_core_tax_engine.py tests/test_razorpay_actual_integration.py tests/test_spare_part_gst.py tests/test_stage_e_payment_integration.py tests/test_maker_checker_engine.py tests/test_marketplace_payment_refunds.py tests/test_refund_gateway_timeout_reconciliation.py tests/test_workshop_quotation_deposits.py tests/test_admin_account_management.py tests/test_admin_disputes_and_refunds_workflow.py tests/test_authorization_matrix.py tests/test_customer_support_ticketing.py tests/test_marketplace_responsibilities.py tests/test_returns_refunds_and_disputes.py tests/test_shipping_and_logistics.py tests/test_staff_permission_fallback_removal.py tests/test_staff_role_dashboard_integration.py tests/test_staff_security_remediation.py -q -p no:cacheprovider -rfE` | **637 passed** (2,431.12 s); 22 files. **This regression did not include `test_shared_order_seller_isolation.py`**, which was run separately (E5-1). |

The ENG-05a tests also passed on PostgreSQL:
- in the 286-test regression (§7);
- in G17a run P1, whose failures were in other files (`03_G17a_…` §7.2).

They have **not** been re-run on PostgreSQL against G17a's final code (`03_G17a_…` §7.3).

## 1. What was verified

ENG-05a limits a seller to their own items' share of a shared order. It does this inside the existing refund transaction, after the order row is locked:

- `RefundService.record_seller_direct_refund`, used by `POST seller/orders/<id>/record-refund/`, calls `RefundService.enforce_seller_refund_share` for non-staff actors.
- `RefundService.create_refund(enforce_seller_share=True)`, used by `POST seller/orders/<id>/request-platform-refund/`, calls the same check.
- Admin and dispute refunds (`POST admin/orders/<id>/refund/`) keep only the existing order-level balance check.

Both services run their checks in the same order:

1. Open `transaction.atomic()`.
2. Lock the order row with `Order.objects.select_for_update()`.
3. Read active refunds and check the order-level balance (`get_order_refund_summary`).
4. Run the seller-share check (ENG-05a).
5. Create the `Refund` row and its audit entry.

PostgreSQL runs at its default READ COMMITTED isolation. Each statement after the lock reads a new snapshot, so a request that waited for the lock sees the competing refund that has already been committed.

## 2. Environment

| Item | Value |
|---|---|
| PostgreSQL | 17.11 (Docker, Alpine build), `localhost:5432`. Default isolation is `read committed`; `max_connections` is 100. |
| Application | Django 5.1.15, DRF 3.17.2, pytest 9.1.1, pytest-django 4.14.0, psycopg2-binary 2.9.13, Python 3.13.15 |
| Test settings | `TEST_USE_SQLITE=False`, so `DATABASES` comes from `backend/.env` (PostgreSQL). |
| Test database | `test_driverxtra_db`. pytest-django creates it and drops it on every run. |

## 3. Test database safety

- Before **each** PostgreSQL run, a read-only probe connected to the `postgres` maintenance database and listed databases. Each time the list was only `driverxtra_db` and `postgres`, so `test_driverxtra_db` did not exist before any run.
- No `--reuse-db` / `--create-db` flags were used. pytest-django created, migrated and dropped `test_driverxtra_db` ("Destroying test database for alias 'default'"). After the final run the database list was again only `driverxtra_db` and `postgres`.
- `driverxtra_db` was never targeted by tests, migrations or writes. The probe only read `pg_database`, `pg_roles` and server settings through the `postgres` database.
- **Operating caveat:** pytest-django runs non-interactively, so an *existing* `test_driverxtra_db` would be dropped and recreated without a prompt. Check that it does not exist before running these commands against a shared server.

## 4. Test design (`backend/tests/test_refund_concurrency_postgresql.py`)

### 4.1 Running the requests in parallel

- Every request runs in its own thread with its own PostgreSQL connection, through the real HTTP endpoints.
- Each thread closes its connection when it finishes.
- Tests use `@pytest.mark.django_db(transaction=True, serialized_rollback=True)`. That way the data each thread needs is committed, and data seeded by migrations is restored for later tests.
- The module is skipped unless `connection.vendor == "postgresql"`. On SQLite all 11 tests report **skipped**, so SQLite is never counted as evidence.

### 4.2 How overlap is forced

- `LockContentionGate` wraps `RefundService.get_order_refund_summary` as a pass-through (test-only `mock.patch`). It does not change any results.
- Both refund services call that function only after `select_for_update()`, so the first request to reach it holds the order row lock.
- The lock holder keeps its transaction open. It polls PostgreSQL until it sees the competing backend blocked **by the holder's own PID**, using `pg_blocking_pids()` on `pg_stat_activity` with `pg_stat_clear_snapshot()` before each poll. Only then does it continue.

### 4.3 How contention is proven

Every test asserts all of the following:

- The waiter's query is a `SELECT` on `marketplace_order`.
- The waiter holds `RowShareLock` on `marketplace_order`, the lock taken by `SELECT ... FOR UPDATE`.
- The waiter has an ungranted lock, observed as `transactionid ShareLock`, meaning it is waiting on the holder's transaction.
- The wait event is `Lock/transactionid`.
- If no blocked competitor is seen within 15 s, the test fails.

### 4.4 Ordering modes

- **Simultaneous:** both threads are released by a `threading.Barrier`, and the winner is not chosen.
- **Ordered:** one request starts first, and the other starts only after the first holds the lock. This gives a deterministic winner and is used to test both orderings.

### 4.5 Checks after each run

- HTTP status and error `code` for every request.
- Number of active `Refund` rows and their sum.
- Unique refund numbers.
- Refund attribution, via `created_by` / `dispute`.
- `AuditLog` counts, to show the losing request left nothing behind.
- Order payment status unchanged.
- No ungranted locks and no `idle in transaction` sessions left afterwards.

**Harness update (G17a, 20 Nov 2026):**
- **Snapshot-lag fix:** the poll now also requires `wait_event_type = 'Lock'`. Without it, a single run flagged a correct outcome as "no contention", because `pg_stat_activity` lagged the live lock graph. Hold points and contention assertions can now be configured for the G17a webhook tests.
- **Re-run:** all 11 ENG-05a-PG tests passed again with this change (see `03_G17a_…` §7.2).

## 5. Concurrency results (PostgreSQL 17.11)

Shares in the multi-seller order fixture:
- Seller A: 2,832.00
- Seller B: 2,360.00
- Order total: INR 5,192.00

Every row below passed. In every row the second request was seen blocked on the first one's row lock (`Lock/transactionid`, `RowShareLock` on `marketplace_order`).

### 5.1 Seller refunds on a shared order

**Seller A refunds 2,832.00 and Seller B refunds 2,360.00 at the same moment** (`test_pg_two_sellers_refund_full_shares_simultaneously`)
- Mode: simultaneous.
- Outcome: both 201.
- Records: 2 refunds, each attributed to its seller. Sum is 5,192.00, equal to the order total; remaining balance is 0.

**Seller A asks for 2,832.01 (1p over share) while Seller B refunds 2,360.00, A first** (`test_pg_seller_overreach_while_other_seller_refunds[seller_a]`)
- Mode: ordered, A first.
- Outcome: A gets 400 `SELLER_REFUND_LIMIT_EXCEEDED`. B gets 201.
- Records: 1 refund (B).

**Same as above, B first** (`test_pg_seller_overreach_while_other_seller_refunds[seller_b]`)
- Mode: ordered, B first.
- Outcome: B gets 201. A gets 400 with the order-level balance error, because 2,832.00 is left and A asked for 2,832.01.
- Records: 1 refund (B).

**Seller A sends two direct refunds of 2,000.00 at once** (`test_pg_same_seller_concurrent_direct_refunds_cannot_exceed_share`)
- Mode: simultaneous.
- Outcome: one 201. One 400 `SELLER_REFUND_LIMIT_EXCEEDED` whose message says "remaining … INR 832.00".
- Records: 1 refund and 1 evidence audit entry. Order still PAID.
- Follow-up: 832.01 is refused and 832.00 is accepted. The remaining share is exact, with no lost update.

**Seller A sends two platform refund requests of 2,000.00 at once** (`test_pg_same_seller_concurrent_platform_refund_requests_cannot_exceed_share`)
- Mode: simultaneous.
- Outcome: one 201 (PENDING). One 400 `SELLER_REFUND_LIMIT_EXCEEDED`.
- Records: 1 refund and 1 `refund.created` audit entry.

### 5.2 Order balance, admin and dispute refunds

**Two admin refunds of 3,000.00 each** (`test_pg_two_admin_refunds_cannot_exceed_order_balance`)
- Mode: simultaneous.
- Outcome: one 201. One 400 with the order-level balance error naming INR 2,192.00 remaining.
- Records: 1 refund of 3,000.00. The admin is not share-limited.

**Admin refunds the full 5,192.00 while Seller B refunds 2,360.00, admin first** (`test_pg_admin_full_refund_and_seller_refund_cannot_exceed_order_balance[admin]`)
- Mode: ordered, admin first.
- Outcome: admin gets 201. Seller B gets 400 with the order-level balance error and no `code`.
- Records: 1 refund.

**Same as above, Seller B first** (`test_pg_admin_full_refund_and_seller_refund_cannot_exceed_order_balance[seller_b]`)
- Mode: ordered, B first.
- Outcome: B gets 201. Admin gets 400 with the order-level balance error.
- Records: 1 refund.

**Dispute refund of 2,360.00 (dispute against Seller B) while Seller B refunds 2,360.00, dispute first** (`test_pg_dispute_refund_racing_seller_refund[dispute_admin]`)
- Mode: ordered, dispute first.
- Outcome: dispute refund gets 201. Seller B gets 400 `SELLER_REFUND_LIMIT_EXCEEDED`, because the dispute refund is attributed to B.
- Records: 1 refund, linked to the dispute.

**Same as above, Seller B first** (`test_pg_dispute_refund_racing_seller_refund[seller_b]`)
- Mode: ordered, B first.
- Outcome: both 201. Admin and dispute refunds keep their existing behaviour and are limited only by the order balance.
- Records: 2 refunds totalling 4,720.00, within 5,192.00. See limitation L5.

### 5.3 Single-seller order

**Two refunds of 60% each on a single-seller order** (`test_pg_single_seller_concurrent_refunds_cannot_exceed_order_balance`)
- Mode: simultaneous.
- Outcome: one 201. One 400 with the order-level balance error and no `code`, so the share check is not involved.
- Records: 1 refund.

### 5.4 Observed lock waits

From the test output:
- Holder and waiter were always different backend PIDs (for example, holder 9815 and waiter 9816).
- The waiter's ungranted lock was always `('transactionid', None, 'ShareLock', False)`.
- In simultaneous mode, contention was observed 0.04–0.09 s after the holder took the lock.
- In ordered mode, it was observed 2.2–2.6 s after, which includes the second request's startup.

## 6. Negative control (detecting a missing lock)

- **Setup:** a plugin outside the repository, at `<scratchpad>/negctl/eng05a_no_row_lock.py` and loaded with `-p eng05a_no_row_lock`, turned `QuerySet.select_for_update()` into a no-op for one run only. No project file was changed.
- **Test run:** `test_pg_same_seller_concurrent_direct_refunds_cannot_exceed_share`.
- **Result: FAILED, as expected:**
  ```
  AssertionError: No competing transaction was observed blocked on the order row lock; the requests did not overlap.
  ```
  The request output was `second: HTTP 201 in 3.863s; first: HTTP 400 SELLER_REFUND_LIMIT_EXCEEDED in 18.586s`.
- **Conclusion:** the suite cannot pass when row locking is absent.
- **Scope of the control:** because the gate pauses the first request *before* it reads balances, the unlocked second request committed first. The paused request then saw that refund. So the control proves that a missing lock is **detected**. It does **not** reproduce an actual over-refund without the lock (limitation L1).

## 7. Regression on PostgreSQL

One run, 8 files, **286 passed, 0 failed, 0 skipped, 0 errors**, in 2,253 s (37 min 33 s):

| File | Tests | Passed | Failed | Skipped | Errors |
|---|---|---|---|---|---|
| `tests/test_refund_concurrency_postgresql.py` (new) | 11 | 11 | 0 | 0 | 0 |
| `tests/test_shared_order_seller_isolation.py` (ENG-05a) | 17 | 17 | 0 | 0 | 0 |
| `tests/test_returns_refunds_and_disputes.py` | 39 | 39 | 0 | 0 | 0 |
| `tests/test_marketplace_payment_refunds.py` | 19 | 19 | 0 | 0 | 0 |
| `tests/test_admin_disputes_and_refunds_workflow.py` | 8 | 8 | 0 | 0 | 0 |
| `tests/test_refund_gateway_timeout_reconciliation.py` | 36 | 36 | 0 | 0 | 0 |
| `tests/test_shipping_and_logistics.py` | 16 | 16 | 0 | 0 | 0 |
| `tests/test_authorization_matrix.py` | 140 | 140 | 0 | 0 | 0 |
| **Total** | **286** | **286** | **0** | **0** | **0** |

The run order is pytest-django's: non-transactional tests first. Per-file counts come from `--collect-only` and match the 286 collected.

The 11 concurrency tests also passed in an earlier standalone run: 11 passed in 414 s. The first standalone run failed all 11 on a **harness** assertion. It looked for `FOR UPDATE` in `pg_stat_activity.query`, which PostgreSQL cuts off at `track_activity_query_size` (1024 bytes). The proof was moved to `pg_locks` (§4.3). No assertion about refund behaviour was weakened.

## 8. Commands

Run from `backend/` with the project virtualenv:

```bash
# 1. SQLite (default): the module must report 11 skipped
.venv/Scripts/python.exe -m pytest tests/test_refund_concurrency_postgresql.py -q -p no:cacheprovider

# 2. PostgreSQL: concurrency tests (prints [ENG-05a-PG] contention lines with -rA)
TEST_USE_SQLITE=False .venv/Scripts/python.exe -m pytest tests/test_refund_concurrency_postgresql.py -p no:cacheprovider -rA

# 3. PostgreSQL: negative control (expected to FAIL); plugin kept outside the repo
PYTHONPATH=<scratchpad>/negctl TEST_USE_SQLITE=False .venv/Scripts/python.exe -m pytest \
  "tests/test_refund_concurrency_postgresql.py::test_pg_same_seller_concurrent_direct_refunds_cannot_exceed_share" \
  -p eng05a_no_row_lock -p no:cacheprovider -rA

# 4. PostgreSQL: refund regression
TEST_USE_SQLITE=False .venv/Scripts/python.exe -m pytest tests/test_refund_concurrency_postgresql.py \
  tests/test_shared_order_seller_isolation.py tests/test_returns_refunds_and_disputes.py \
  tests/test_marketplace_payment_refunds.py tests/test_admin_disputes_and_refunds_workflow.py \
  tests/test_refund_gateway_timeout_reconciliation.py tests/test_shipping_and_logistics.py \
  tests/test_authorization_matrix.py -p no:cacheprovider -q
```

Before every PostgreSQL run, confirm that `test_driverxtra_db` does not exist (§3).

## 9. Limitations

| # | Limitation |
|---|---|
| L1 | The negative control proves that a missing lock is detected, not that an over-refund happens without it (§6). |
| L2 | Only two competing requests per test. There is no N-way or sustained load test. |
| L3 | Only PostgreSQL's default READ COMMITTED isolation is exercised. The code relies on it (or stricter); under REPEATABLE READ or SERIALIZABLE, waiters would get serialization errors rather than a recomputed balance. |
| L4 | The guarantee covers refunds created through `create_refund` and `record_seller_direct_refund`, which are the only creation paths found in `apps/`. Rows written directly through the ORM or admin bypass the lock and the checks. |
| L5 | **Policy observation, not a defect, and unchanged:** when a seller refunds first, a dispute or admin refund for the same seller's item is still allowed up to the order balance. In the test, Seller B's 2,360.00 item was refunded twice (4,720.00 in total). ENG-05a deliberately left admin and dispute refunds without a share limit. Whether admin and dispute refunds should respect the seller share is a business decision for the refunds policy (Appendix D item 9), not an engineering fix. |
| L6 | There is no idempotency key on refund requests. Two identical requests that both fit within the share both succeed by design. ENG-05a prevents over-refund, not duplicate submission. |
| L7 | The full backend suite has **not** been run on PostgreSQL; the refund-related subset above has. The last broad run was on SQLite (ENG-05a regression: 637 passed across 22 files, 19–20 Nov 2026). |
| L8 | The overlap gate is a test-only patch on `get_order_refund_summary`. It passes calls through unchanged, but it is an instrumented path, not an unmodified production process. |
| L9 | No commit SHA is bound to this evidence (CD-06), because Git commands were not permitted. |

## 10. Files

| File | Change |
|---|---|
| `backend/tests/test_refund_concurrency_postgresql.py` | **New.** 11 PostgreSQL concurrency tests and the contention harness. |
| `docs/commercial/implementation-assessment/02_ENG-05a-PG_Refund_Concurrency_Evidence_2026-11-20.md` | **New.** This record. |
| `docs/commercial/implementation-assessment/01_Gap_Closure_Plan_Update_2026-11-19.md` | Header note and new §7 evidence log, referencing ENG-05a only. |
| Production code | **No change.** |
