# R0 — Payment test-mode defaults and production safeguards

**Status:** Proposal for review. No code has been changed.
**Owner of affected code:** Rithika (marketplace payments, PRs #9/#10).
**Prepared:** 30 Oct 2026, against `indra` @ `56f7a1c`.
**Architecture references:** Master Architecture v1.0 §10 (money-movement prohibition, treasury invariants),
§23 P0 "Checkout/ledger divergence", §24 COM-005 / COM-016.

## 1. Problem

The payment layer is built for sandbox use, but several sandbox behaviours are **on by default** and are not tied to a
non-production environment. If the backend were deployed without every payment environment variable set correctly,
orders could be marked paid and refunds marked processed without any money moving.

## 2. Findings (verified in code)

| # | Finding | Location | Severity |
|---|---|---|---|
| F1 | Webhook secrets default to **public placeholder values** (`rzp_test_webhook_secret`, `whsec_test_placeholder_secret`). The HMAC check uses them whenever the env var is missing, **even with test mode off**, so anyone can forge a valid webhook. The webhook endpoint is `AllowAny` (correct for webhooks) | `config/settings.py:375,380`; `payments/stripe_provider.py` `verify_webhook`; `payments/razorpay_provider.py` `verify_webhook` | **Critical** |
| F2 | `PAYMENT_TEST_MODE` defaults to `True` | `config/settings.py:370` | High |
| F3 | In test mode, webhook verification accepts fixed **magic signatures** (`test_stripe_sig_valid`, `mock_valid_sig`, `test_webhook_sig_valid`) | `stripe_provider.py:170`, `razorpay_provider.py:134` | High (when F2 applies) |
| F4 | In test mode, payment confirmation accepts magic signatures (`test_sig_valid`, `mock_valid_signature`), and Stripe returns "succeeded" for any `pi_…` that matches the order's session ID, with no `DEBUG` check | `razorpay_provider.py:97`, `stripe_provider.py:98–133` | High (when F2 applies) |
| F5 | `create_payment_session` always fabricates provider IDs (`pi_test_…`, `order_rzp_…`) and never calls the provider, even when test mode is off. Live mode therefore cannot work, and it does not fail clearly | `stripe_provider.py:29–59`, `razorpay_provider.py:29–61` | Medium (fails open as "sandbox") |
| F6 | The test payment simulation endpoint is gated by `PAYMENT_TEST_MODE and (DEBUG or IS_TESTING)`, but `DEBUG` also defaults to `True` | `views.py` `OrderPaymentSimulateTestView`; `settings.py:37` | High (when defaults apply) |
| F7 | Admin refunds accept `auto_process` from the request and mark the refund processed with a simulated reference (`sim_rfnd_…`), with no sandbox check | `views.py:3875`, `returns/service.py:674–677` | Medium (admin-only) |
| F8 | Cash on delivery is enabled by default for `IN,GB` (`COD_ENABLED=True`) | `settings.py:383–386` | Medium (market decision D01/D04, Architecture §10 does not list COD as a supported mode) |

## 3. Proposed changes (small and reviewable; behaviour under the test runner unchanged)

1. **Fail-closed defaults (settings).**
   - `PAYMENT_TEST_MODE` defaults to `IS_TESTING`: on under pytest, off everywhere else unless set explicitly.
   - `COD_ENABLED` defaults to `False`. `COD_ALLOWED_COUNTRIES` defaults to an empty list.
   - The six provider key/secret settings default to `""`, with no placeholder values.
   - Proposed separately (it affects the whole project): `DEBUG` defaults to `False`. Local `.env` files already set `DEBUG=True`.
2. **One sandbox predicate.** Add `payments_sandbox_allowed()`, which returns `PAYMENT_TEST_MODE and (DEBUG or IS_TESTING)`. Use it for:
   - the magic-signature fallbacks (F3, F4)
   - the Stripe deterministic success path (F4)
   - the simulate endpoint (F6)
   - refund `auto_process` (F7); outside the sandbox this returns 409
3. **Webhook verification fails closed (F1).** Reject any webhook when the configured secret is empty or one of the known placeholder values, whatever the test mode.
4. **No fabricated sessions outside the sandbox (F5).** If the sandbox isn't allowed and no real provider integration exists, `create_payment_session` raises "Payment provider not configured" (HTTP 503). It no longer returns fake IDs. The real provider integration stays out of scope until decision D04.
5. **Startup system check.** Register a Django check that refuses to start (`checks.Error`) when any of these hold:
   - `PAYMENT_TEST_MODE` is on and neither `DEBUG` nor `IS_TESTING` is set.
   - A live key (`sk_live_`, `rzp_live_`) is configured while test mode is on.
   - `DEBUG` is off and any payment secret is empty or a placeholder, while online payments are offered.
6. **Cash on delivery (F8).** R0 only flips the default to off. Later (R4), each market's cash-on-delivery availability moves behind the R1 country gates.

## 4. Tests to add (in the existing payment test modules)

- With production-like settings (`PAYMENT_TEST_MODE=False`, `DEBUG=False`):
  - magic signatures are rejected for both payment verification and webhooks
  - the simulate endpoint returns 403
  - refund `auto_process` returns 409
  - creating a payment session returns 503
- Webhooks signed with a placeholder secret are rejected even when test mode is off.
- The system check reports errors for each unsafe combination in §3.5 and stays silent for a correct local `.env`.
- All existing payment tests keep passing unchanged, because pytest still runs in sandbox mode (`IS_TESTING`).

## 5. Rollout and effort

- **Effort:** about half a day to one day, including tests.
- **Rollout:** one PR by the payment code owner, reviewed by a second engineer.
- **Local development:** add `PAYMENT_TEST_MODE=True` (and `COD_ENABLED=True` if you want it) to local `.env` files.
- **Risk:** low. Behaviour changes only where configuration is missing or unsafe.

## 6. Decisions needed

1. Approve fail-closed defaults (§3.1–3.5).
2. Approve `DEBUG` defaulting to `False` (project-wide).
3. Confirm cash on delivery is off by default until a market decision (D01/D04) enables it per gate.
