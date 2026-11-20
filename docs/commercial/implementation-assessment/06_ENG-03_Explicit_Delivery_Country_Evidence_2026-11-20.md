# ENG-03 (implementation ID) — Explicit delivery country at checkout: evidence record

| Field | Value |
|---|---|
| Record date | 20 November 2026. The backend was implemented and tested on 19 November 2026; the frontend on 20 November 2026. |
| IDs | **Implementation ID ENG-03 is NOT gap-closure plan §4.1 ENG-03.** §4.1 ENG-03 is Stripe chargeback intake, implemented as **G17a** ([03](03_G17a_Stripe_Chargeback_Intake_Evidence_2026-11-20.md)). §4.1 has no row for this work, and no master-register gap ID is assigned to it in the current records. It enforces the fail-closed market rule behind ENG-01 (D04 finding; DX-GC-05 "no unsupported market flags"). |
| IMPLEMENTED | **Yes** (backend). Frontend correction: **yes** ([08](08_ENG-01-03_Frontend_Delivery_Country_Evidence_2026-11-20.md)). |
| TESTED | Backend: **yes**, on SQLite (§3). Frontend: type-check, lint and build only; **no browser test**. |
| Formal status | **IMPLEMENTED – NOT VERIFIED.** No SHA binding (CD-06). The changes are uncommitted on top of `HEAD` `4107076f41b5dba269c490cbbdc8bfb059580f5d`. |
| VERIFIED IN TEST | **No** |

## 1. Change

`OrderCheckoutView` serves both `orders/calculate/` and `orders/checkout/`. It now returns **400 `DELIVERY_COUNTRY_REQUIRED`**, with `field_errors.shipping_country`, when no delivery country is supplied. The check runs before any order, payment record or stock change. There is no implicit India or UK fallback (`backend/apps/marketplace/views.py`).

No migrations. No pricing, tax or market rules were changed.

## 2. Investigation

- **Probe run** (19 Nov 08:13): `-p probe_country`, a plugin kept outside the repository that logs checkout calls made without a country. It ran across 8 payment and checkout files: **197 passed**. It recorded **4** checkout calls made without a country in existing tests.
- **Existing test changed:** `tests/test_marketplace_checkout.py::TestMarketplaceCheckout::test_rollback_on_partial_failure` now sends `shipping_country` "India" explicitly. The 318-test regression then passed (§3).

## 3. Test evidence

**Tests added:** `backend/tests/test_country_currency_checkout.py::TestEng03DeliveryCountryRequired`, 4 test functions that become **23 cases** after parametrisation:
- `test_missing_country_rejected_without_side_effects`
- `test_missing_country_rejected_for_cash_on_delivery`
- `test_explicit_india_checkout_unchanged`
- `test_explicit_uk_checkout_unchanged`

The file uses CRLF line endings, which were preserved.

From `backend/`, SQLite in-memory; environment as in [04](04_ENG-01_Payment_Availability_Evidence_2026-11-20.md) §3.

| # | When (UTC, 19 Nov) | Command | Result |
|---|---|---|---|
| E3-1 | 08:41 | `.venv/Scripts/python.exe -m pytest "tests/test_country_currency_checkout.py::TestEng03DeliveryCountryRequired" "tests/test_marketplace_checkout.py::TestMarketplaceCheckout::test_rollback_on_partial_failure" -q -p no:cacheprovider -rfE` | **24 passed** (344.22 s) |
| E3-2 | 08:56 | Same 12-file command as ENG-01 E1-3 ([04](04_ENG-01_Payment_Availability_Evidence_2026-11-20.md) §3) | **318 passed** (863.92 s) |

**Later SQLite runs that include these files:**
- ENG-04a regression: 396 passed.
- ENG-05a regression: 637 passed.
- G17a S3: 515 passed, 15 skipped. It included `test_country_currency_checkout.py` and `test_marketplace_checkout.py`.

**Never run on PostgreSQL.**

## 4. Outstanding

1. **No re-run on final code.** Re-run on the final committed code, on SQLite **and** PostgreSQL; these files have never run on PostgreSQL.
2. **Browser-level testing of the frontend flow** ([08](08_ENG-01-03_Frontend_Delivery_Country_Evidence_2026-11-20.md)).
3. **No SHA binding.**
4. **Product scope:** the UI offers only India and the United Kingdom. Adding the USA (D01 direction) depends on backend market enablement (D04, PD-16, D09) and is not part of ENG-03.
