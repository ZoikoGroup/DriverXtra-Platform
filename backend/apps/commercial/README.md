# Commercial Control Plane (R1)

Implements the R1 foundation of *DriverXtra Global Commercial Estate – Master Architecture v1.0* (23 Oct 2026):
the SKU catalogue, country/market gates, party role profiles, effective-dated rate schedules, immutable quote
snapshots and (in `platform_core/events`) the transactional event outbox.

R1 decides **what may be sold, where, by whom and at what approved rate**, and freezes accepted terms.
It does **not** move money: no payment processing, payouts, escrow, finance or insurance features.

## Safety defaults

| Control | Default |
|---|---|
| New SKU | `DRAFT`. The illustrative price band is a text note only and never used in calculations |
| New country gate | `DESIGNED` (closed). A missing gate is also closed; there is no default market |
| New rate / role profile | `DRAFT` |
| Regulated SKUs (`REG-01`, `REG-02`, `FIN-01`, `COM-04`, `REGULATED`/`PAYMENT` families, `FINANCE_INSURANCE` vertical) | Cannot be approved (COM-008) |
| Regulated gates (`FINANCE_INSURANCE` vertical, `REGULATED_REFERRAL` capability) | Cannot be enabled |
| Gated role profiles (regulated introducer, principal seller, cross-border, payment modes E/F) | Cannot be approved |
| Approvals | Need `commercial.approve`, a different person from the author, and an approval reference |
| Gate enablement | Needs every evidenced step, a tax schedule reference, currencies, an approved role profile, and a different person from the finance sign-off |
| Rate approval | Prospective only (`effective_from` ≥ now), approved SKU, no overlapping approved rate |
| Money | Integer minor units + ISO 4217 code; unknown currencies rejected; no floats; no FX (cross-currency quotes are rejected) |

## Quote formation (§7)

A **binding** quote (`POST /api/v1/commercial/quotes/`) is issued only when every control passes:

1. The `BINDING_QUOTE` gate for country × vertical is `ENABLED` and allows the currency.
2. The named party role profile is `APPROVED` and effective; required parties (seller of record) are present.
3. Every SKU is `APPROVED` and not regulated; duplicate SKUs (fee stacking) are rejected.
4. An `APPROVED`, effective rate resolves (highest priority, then exact plan match; ties are errors).
5. `tax_determination_reference` and `terms_version` are supplied.

Fee base rule `GOODS_NET_OF_DISCOUNT_EXCL_TAX_DELIVERY_V1`: commissionable base = face value − discount.
Customer total = face − discount + delivery + tax + fees whose payer role is the customer's role
(Appendix A: goods 10000, discount 1000, delivery 600, tax 720, 8% seller fee → total 10320, fee 720).

The snapshot stores lines, totals, the role snapshot, gate activation version, tax evidence and a SHA-256
`terms_hash`. Acceptance must echo the same `terms_hash`, record a consent notice version, happen before expiry
(`COMMERCIAL_QUOTE_TTL_SECONDS`, default 1800), and the gate must still be open at the same activation version.
Snapshots, lines, role snapshots and gate transitions are append-only (model and queryset guards).

`POST /api/v1/commercial/admin/quote-preview/` runs the same calculation over draft/illustrative data and returns
`blocking_reasons`. It is labelled `NON_BINDING_PREVIEW` and never persisted.

## API

| Method | Path | Access |
|---|---|---|
| GET | `/api/v1/commercial/plans/?market=XX[&vertical=]` | Public; empty unless the market's `DISCOVERY` gate is enabled |
| GET/POST | `/api/v1/commercial/quotes/` | Authenticated (own quotes / issue binding quote) |
| GET | `/api/v1/commercial/quotes/{id}/` | Owner or commercial staff |
| POST | `/api/v1/commercial/quotes/{id}/accept/` | Owner |
| GET/POST, GET/PATCH, POST `status/`, POST `new-version/` | `/api/v1/commercial/admin/skus/` | Staff with a commercial permission; writes `commercial.manage`; APPROVED/RETIRED need `commercial.approve` |
| same shape | `/api/v1/commercial/admin/rate-schedules/` (no new-version) | as above |
| same shape | `/api/v1/commercial/admin/role-profiles/` | as above |
| GET/POST, GET/PATCH, POST `transition/` | `/api/v1/commercial/admin/country-gates/` | Writes need `country_gate.manage` |
| POST | `/api/v1/commercial/admin/quote-preview/` | `commercial.manage` |
| GET | `/api/v1/commercial/admin/quotes/`, `/api/v1/commercial/admin/outbox/` | Commercial staff |

Rule violations return `409` (or `400` for invalid input) in the project error format with
`details.rule` (e.g. `COUNTRY_GATE_CLOSED`, `SEPARATION_OF_DUTIES`, `REGULATED_SKU_BLOCKED`).

## Events (transactional outbox)

Emitted in the same transaction as the change: `commercial.sku.published`, `commercial.sku.retired`,
`commercial.rate_schedule.approved`, `commercial.rate_schedule.retired`, `compliance.policy_changed`,
`eligibility.suspended`, `quote.issued`, `quote.accepted`. Deliver with
`python manage.py publish_outbox_events` (at-least-once; consumers registered with
`platform_core.events.outbox.register_consumer` are de-duplicated per consumer).

## Commands

```bash
python manage.py seed_illustrative_commercial_catalogue [--created-by staff@example.com]
    # Optional. Loads the §6 SKU list as ILLUSTRATIVE/DRAFT with no rates, gates or approvals. Idempotent.
python manage.py publish_outbox_events [--limit 100]
```

## Permissions

`commercial.manage`, `commercial.approve` and `country_gate.manage` are added by migration
`0002_seed_commercial_permissions`. They are not assigned to any staff sub-role; platform ADMIN users hold all
permissions. Assign them to a staff role only after an access decision.

## Not in R1

Commercial agreements/contracts, leads, subscriptions/entitlements, invoicing, earning events, ledger,
settlement/reconciliation, payouts, FX quotes, tax engine integration, and any integration with the existing
marketplace checkout. Existing marketplace orders are unaffected.

## Tests

```bash
pytest tests/test_commercial_control_plane.py tests/test_commercial_api.py tests/platform_core/test_outbox.py
```
