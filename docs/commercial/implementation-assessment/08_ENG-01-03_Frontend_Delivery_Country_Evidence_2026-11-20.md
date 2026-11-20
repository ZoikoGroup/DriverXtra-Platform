# ENG-01 / ENG-03 frontend correction — Explicit delivery country in the cart checkout: evidence record

| Field | Value |
|---|---|
| Record date | 20 November 2026 (implemented and checked the same day) |
| IDs | Client-side completion of **ENG-01** ([04](04_ENG-01_Payment_Availability_Evidence_2026-11-20.md); gap-closure plan §6 "Files: Frontend…") and implementation **ENG-03** ([06](06_ENG-03_Explicit_Delivery_Country_Evidence_2026-11-20.md)). No separate plan or master-register ID. |
| Why | The 20 Nov audit found that `CartDrawer.tsx` always sent `shipping_country`, defaulting to "India". That defeated ENG-03's `DELIVERY_COUNTRY_REQUIRED` and ENG-01's "no implicit India" rule for real users. |
| IMPLEMENTED | **Yes** |
| TESTED | **Static checks and build only** (§3). **No automated frontend test framework exists** in the project, and **browser-level testing has not been done.** |
| Formal status | **IMPLEMENTED – NOT VERIFIED.** No SHA binding. The changes are uncommitted. |
| VERIFIED IN TEST | **No** |

## 1. Defaults and fallbacks removed

| Location | Before | After |
|---|---|---|
| `CartDrawer.tsx`, initial form state | `shipping_country: "India"`, `shipping_state: "MH"` | Both empty |
| `CartDrawer.tsx`, tax-calculation payload | `shipping_country.trim() \|\| "India"` | Trimmed value; validated beforehand |
| `CartDrawer.tsx`, order-submission payload | `shipping_country.trim() \|\| "India"` | Trimmed value; guarded beforehand |
| `CartContext.tsx`, `validateInventory` | `options?.country \|\| "India"` (plus INR/MH derived from it) | No country means local stock check only and the issue "Select a delivery country…". The backend calculation is not called. |
| `CartDrawer.tsx`, display (banner, labels, region field, subtotal) | Any non-UK value, **including empty**, rendered as India / INR / GST, because `getCurrencyForCountry("")` returns INR | Shows "Select a country". The region field is disabled until a country is chosen. The subtotal shows the cart's own listing currency. |

**The only remaining "India" strings** are the explicit user choices: the India quick-switch button and the dropdown option.

## 2. Behaviour

- **Explicit selection:**
  - the dropdown has a disabled "Select delivery country…" placeholder, and nothing is pre-selected;
  - the India and UK buttons remain as explicit choices;
  - no country is chosen automatically.
- **Validation:** "Proceed to Delivery & Taxes", "Verify Stock", "Review" and "Place order" each stop with "Please select a delivery country to continue." The message appears as a field error and in the checkout banner.
- **Consistent propagation:** the same selected value goes to stock validation, tax calculation and order submission. Payment availability comes back in the calculation response.
- **Backend error codes:** the shared API client had shown raw response fields; the cart now handles both codes, reading them from `ApiError.details`, without changing the shared client.
  - `DELIVERY_COUNTRY_REQUIRED`: country message, return to the delivery step.
  - `PAYMENT_METHOD_UNAVAILABLE`: plain-language message for the reason code; payment options refreshed from `available_payment_methods`; cart kept.
- **Unavailable methods:** shown with fixed messages for `MARKET_NOT_SPECIFIED`, `MARKET_NOT_ENABLED`, `CURRENCY_NOT_SUPPORTED` and `PROVIDER_NOT_CONFIGURED`. `COD_NOT_ELIGIBLE` also appends the backend's own detail. Unknown codes fall back to the backend text. No message implies that a method or country is available.
- **Unchanged:**
  - cart, pricing and the 409 price-change handling;
  - Razorpay, Stripe and COD flows;
  - the country-to-currency and region logic once a country is chosen.

**Files:**
- `frontend/src/components/platform/CartDrawer.tsx`
- `frontend/src/context/CartContext.tsx`
- `frontend/src/lib/api/client.ts`: optional `reason_code` on `PaymentMethodOption`, type only

No backend change. No new country registry, service or pricing rule.

## 3. Checks (from `frontend/`; Next.js 16.4.6, React 19.3.0, TypeScript)

| Check | Command | Before change | After change |
|---|---|---|---|
| Type-check | `npx tsc --noEmit -p .` | exit 0 | **exit 0** |
| Lint (the 3 files) | `npx eslint src/components/platform/CartDrawer.tsx src/context/CartContext.tsx src/lib/api/client.ts` | exit 0 | **exit 0** |
| Production build | `npm run build` (`next build`) | not run | **exit 0**: compiled; TypeScript passed; 11 routes generated |
| Automated frontend tests | none | **No test framework present.** `package.json` scripts are `dev`, `build`, `start`, `lint`; there is no Jest, Vitest or Playwright and no test files. None was added. | — |

The checks rewrote `tsconfig.tsbuildinfo` and `.next/`, both ignored by the root `.gitignore`.

## 4. Limitations and outstanding

1. **Browser-level testing:** outstanding. Manually exercise each of these with a running backend:
   - no-country validation;
   - India checkout;
   - UK checkout;
   - payment-unavailable messages.
2. **Countries offered:** only India and the UK. USA support depends on backend market enablement (D04, PD-16, D09).
3. **Region default:** after a country is chosen, its default region (London or Maharashtra) is still pre-filled (existing behaviour). Whether to leave it blank instead is a product decision.
4. **Validation issues not rendered:** `CartContext` validation `issues` aren't shown by the drawer. The country prompt reaches the buyer through the drawer's banner and field error.
5. **Other error codes:** refund and seller codes (`CHARGEBACK_*`, `SELLER_REFUND_LIMIT_EXCEEDED`, `MULTI_SELLER_ORDER_STATUS_LOCKED`) still display the backend message only. They were out of scope.
6. **No SHA binding;** the changes are uncommitted.
