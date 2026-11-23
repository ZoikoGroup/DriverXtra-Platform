# ENG-01 — Fail-closed payment-method and currency availability: evidence record

| Field | Value |
|---|---|
| Record date | 20 November 2026. The work was implemented and tested on 19 November 2026. |
| IDs | Implementation **ENG-01** = gap-closure plan §4.1 **ENG-01** (same scope). Master register: **G15 (part)**, as cited in §4.1 (DX-GC-05 §15, PAY-06). |
| IMPLEMENTED | **Yes** (backend). The client-side completion is in [08](08_ENG-01-03_Frontend_Delivery_Country_Evidence_2026-11-20.md). |
| TESTED | **Yes**, on SQLite (§3). The ENG-01 test file also passed on PostgreSQL inside G17a run P1, on pre-final code (§3). |
| Formal status | **IMPLEMENTED – NOT VERIFIED.** The runs are not bound to a commit SHA (CD-06). The tested code is uncommitted on top of `HEAD` `4107076f41b5dba269c490cbbdc8bfb059580f5d`. |
| VERIFIED IN TEST | **No.** It requires a re-run on the committed SHA. |

## 1. Defect addressed

The payment-methods API advertised Stripe card payment as available for every non-INR request, including US/USD. Stripe here supports GBP only, so it would then reject the order. The view also silently defaulted a missing country to India (gap-closure plan §1, D04 finding; §6).

## 2. Implementation (backend)

| File | Change |
|---|---|
| `backend/apps/marketplace/payments/base.py` | `supported_currencies`, `supports_currency()`, `is_ready()` on the provider base class |
| `backend/apps/marketplace/payments/stripe_provider.py` | `supported_currencies = {'GBP'}` |
| `backend/apps/marketplace/payments/razorpay_provider.py` | `supported_currencies = {'INR'}` |
| `backend/apps/marketplace/payments/service.py` | `get_online_payment_availability()` and `_market_unavailability()`. Each method reports `is_available` with `reason_code`/`reason`, using one of these codes:<br>- `MARKET_NOT_SPECIFIED`<br>- `MARKET_NOT_ENABLED`<br>- `CURRENCY_NOT_SUPPORTED`<br>- `PROVIDER_NOT_CONFIGURED`<br>- `COD_NOT_ELIGIBLE` |
| `backend/apps/marketplace/views.py` | The payment-methods view has no implicit country: without one, every method is unavailable (`MARKET_NOT_SPECIFIED`). The checkout guard returns 400 `PAYMENT_METHOD_UNAVAILABLE` (with `reason_code` and `available_payment_methods`) before any order, stock change or provider session is created. |

Out of scope, unchanged:
- COD policy and Razorpay (PD-14);
- US/USD enablement (D04, PD-16);
- Stripe Connect (BLK-01);
- a market-policy store (§2 row 8).

No migrations.

## 3. Test evidence

**Tests added:** `backend/tests/test_payment_gateway_and_cod.py::TestEng01FailClosedPaymentAvailability`, 16 tests:
- `test_providers_declare_supported_currencies`
- `test_us_usd_reports_no_available_method`
- `test_us_destination_with_gbp_reports_market_not_enabled`
- `test_uk_with_non_gbp_currency_is_not_available`
- `test_uk_gbp_and_india_inr_unchanged`
- `test_country_defaults_currency_from_destination_rules`
- `test_missing_country_has_no_implicit_india`
- `test_unconfigured_provider_reported_unavailable_in_production`
- `test_cod_threshold_reason_code`
- `test_uk_online_checkout_rejected_when_stripe_unavailable`
- `test_india_online_checkout_rejected_when_razorpay_unavailable`
- `test_us_destination_checkout_rejected_without_order`
- `test_cod_checkout_unaffected_when_online_unavailable`
- `test_checkout_preview_reports_unavailable_without_blocking`
- `test_test_mode_online_checkout_still_succeeds`
- `test_payment_session_creation_fails_closed_for_unready_provider`

**Existing test changed (disclosed on 19 Nov):** `TestBug2PaymentVerificationAndIsolation::test_server_simulated_payment_blocked_in_production` had switched to production settings *before* creating its order. The new fail-closed guard then correctly refused that order. The test now creates the order first and then switches to production; what it asserts is unchanged.

**Runs** (from `backend/`, SQLite in-memory default test settings; Windows, Python 3.13.15, Django 5.1.15, pytest 9.1.1, pytest-django 4.14.0):

| # | When (UTC, 19 Nov) | Command | Result |
|---|---|---|---|
| E1-0 | 07:02 | `.venv/Scripts/python.exe -m pytest tests/test_payment_gateway_and_cod.py … tests/test_stage_e_payment_integration.py -q -p no:cacheprovider -x --timeout=0` | **Not run:** pytest usage error (`--timeout` is not an available option). 0 tests. |
| E1-1 | 07:09 | `.venv/Scripts/python.exe -m pytest "tests/test_payment_gateway_and_cod.py::TestEng01FailClosedPaymentAvailability" -q -p no:cacheprovider -rfE` | **16 passed** (148.50 s) |
| E1-2 | 07:13 | `.venv/Scripts/python.exe -m pytest tests/test_payment_gateway_and_cod.py tests/test_country_currency_checkout.py tests/test_marketplace_checkout.py tests/test_order_management.py tests/test_platform_core_tax_engine.py tests/test_razorpay_actual_integration.py tests/test_spare_part_gst.py tests/test_stage_e_payment_integration.py -q -p no:cacheprovider -rfE` | **1 failed, 180 passed** (586.35 s). The failure was the test above, fixed by the reorder. |
| E1-3 | 07:32 | `.venv/Scripts/python.exe -m pytest tests/test_payment_gateway_and_cod.py tests/test_country_currency_checkout.py tests/test_marketplace_checkout.py tests/test_order_management.py tests/test_platform_core_tax_engine.py tests/test_razorpay_actual_integration.py tests/test_spare_part_gst.py tests/test_stage_e_payment_integration.py tests/test_maker_checker_engine.py tests/test_marketplace_payment_refunds.py tests/test_refund_gateway_timeout_reconciliation.py tests/test_workshop_quotation_deposits.py -q -p no:cacheprovider -rfE` | **295 passed** (1,127.57 s); 12 files |

**Later runs that include the ENG-01 tests:**

| Run | Database | Result |
|---|---|---|
| ENG-03 regression | SQLite | 318 passed ([06](06_ENG-03_Explicit_Delivery_Country_Evidence_2026-11-20.md)) |
| ENG-04a regression | SQLite | 396 passed ([07](07_ENG-04a_Commercial_Quote_Adapter_Evidence_2026-11-20.md)) |
| ENG-05a regression | SQLite | 637 passed (19 Nov 11:17) |
| G17a S3 | SQLite | 515 passed, 15 skipped ([03](03_G17a_Stripe_Chargeback_Intake_Evidence_2026-11-20.md) §7.1) |
| G17a P1 | **PostgreSQL 17.11** | 236 passed, 5 failed. All 5 failures were in other files, so every test in `test_payment_gateway_and_cod.py` passed on PostgreSQL in that run. P1 predates G17a's final code. |

**Earlier baseline (19 Nov):** a pre-change baseline run overlapped with the edits, because Django loads views lazily. That was disclosed at the time, and the run is **not** used as evidence.

## 4. Outstanding

1. **No SHA binding.** Re-run on the committed SHA (CD-06).
2. **No re-run on final code.** The ENG-01 tests have not run on the final code of the whole package set, on SQLite or PostgreSQL (`test_payment_gateway_and_cod.py` was last run before G17a's final changes).
3. **Browser behaviour** of the frontend completion is untested ([08](08_ENG-01-03_Frontend_Delivery_Country_Evidence_2026-11-20.md)).
4. **External decisions:** US/USD online payment remains unavailable by design until D04 Stripe capability verification and the PD-16 decision.
