# ENG-04a (implementation ID) — Non-binding commercial quote adapter: evidence record

| Field | Value |
|---|---|
| Record date | 20 November 2026. The work was implemented and tested on 19 November 2026. |
| IDs | **Implementation ID ENG-04a is NOT gap-closure plan §4.1 ENG-04.** §4.1 ENG-04 is the settlement reconciliation design: **NOT IMPLEMENTED**, and its build waits on D04 verification. ENG-04a is a **preparatory proof** for §4.1 **ENG-05** (commercial quote → checkout integration; master §07; D10). **§4.1 ENG-05 remains NOT IMPLEMENTED.** No master-register gap ID is assigned to ENG-04a. |
| **Scope statement** | **ENG-04a is a library-level proof only. It is NOT integrated into application checkout, payment or order flows.** No application module imports it (enforced by `test_adapter_is_not_wired_into_runtime_code`; re-confirmed by a source search of `apps/`, `config/` and `platform_core/` on 20 Nov 2026). |
| IMPLEMENTED | **Yes**, as a library module plus tests |
| TESTED | **Yes**, on SQLite (§3) |
| Formal status | **IMPLEMENTED – NOT VERIFIED.** No SHA binding (CD-06). The changes are uncommitted on top of `HEAD` `4107076f41b5dba269c490cbbdc8bfb059580f5d`. |
| VERIFIED IN TEST | **No** |

## 1. What it is

`backend/apps/marketplace/commercial_quote_adapter.py` (new) maps a **single-seller** marketplace checkout calculation onto the existing commercial `QuoteRequest` / `compute_quote` model.

**Functions:**
- `to_minor_units`
- `build_quote_request`
- `preview_quote`
- `preview_checkout_quote`

**Hard limits, by design:**
- It always calls `compute_quote(..., binding=False)`, so it persists nothing: no quote snapshot, lines, role snapshot or outbox event.
- It never activates a price, role, SKU, payment mode or market.
- Money is converted to minor units exactly. Anything that isn't a whole number of minor units is rejected; nothing is rounded.
- Unsupported shapes are rejected with reason codes rather than approximated:
  - `FX_CONVERTED_PRICE_NOT_SUPPORTED`
  - `MULTI_SELLER_NOT_SUPPORTED`
  - `FRACTIONAL_MINOR_UNIT`
  - `INVALID_AMOUNT`
  - `UNSUPPORTED_CURRENCY`
  - `CHECKOUT_TOTALS_INCONSISTENT`
  - `LISTING_NOT_FOUND`
  - `UNIT_PRICE_MISMATCH`
  - `EMPTY_CALCULATION`

No migrations. Checkout behaviour is unchanged.

## 2. Tests

`backend/tests/test_commercial_quote_adapter.py` (new) contains **25** test cases, including:
- exact minor-unit conversion, and rejection instead of rounding;
- the Appendix A golden vector through the adapter;
- India and UK single-seller checkout parity;
- rejection of FX-converted and multi-seller checkouts, and of unrepresentable calculations;
- the engine's refusal being reported rather than raised;
- the adapter only ever calling the non-binding preview;
- the adapter not being wired into runtime code.

## 3. Test evidence

From `backend/`, SQLite in-memory; environment as in [04](04_ENG-01_Payment_Availability_Evidence_2026-11-20.md) §3.

| # | When (UTC, 19 Nov) | Command | Result |
|---|---|---|---|
| E4-1 | 09:56 | `.venv/Scripts/python.exe -m pytest tests/test_commercial_quote_adapter.py -q -p no:cacheprovider -rfE` | **25 passed** (166.81 s) |
| E4-2 | 10:14 | ENG-01 E1-3's 12 files plus `tests/test_commercial_api.py tests/test_commercial_control_plane.py`, with `-q -p no:cacheprovider -rfE` | **396 passed** (1,070.48 s); 14 files |

## 4. Outstanding

1. **Not re-run since 19 Nov.** The parity tests call the checkout endpoint, and `marketplace/views.py` changed afterwards (ENG-05a and G17a). Re-run on the final committed code.
2. **PostgreSQL:** never run on PostgreSQL.
3. **No SHA binding.**
4. **Integration into checkout (§4.1 ENG-05)** is **not** authorised. It is gated on D02 role profiles, D10 and the closed country gates.
