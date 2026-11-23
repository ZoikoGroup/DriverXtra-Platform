# Unresolved Requirements (wireframe-blocking or wireframe-shaping)

| Field | Value |
|---|---|
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Requirements sources | Master DX-COMM-MASTER-001 (v1.0; v1.1 rev. B proposed), `../01_Engineering_Reconciliation_Matrix.md`, Doc COM-02..COM-13 drafts in `../com/` |
| Confirmed decisions used | Zoiko Mobility Inc.; markets USA and UK; Stripe preferred (verification pending); finance and insurance out of scope here (separate workstream, Rithika) |
| API status legend | **CONFIRMED** = the route and method exist in the repository today (verified against the Django URL configuration on 19 November 2026; existing does not mean production-ready). **PROPOSED** = not in the repository; no contract implied. **DISABLED** = the route exists but the capability is closed by a gate, decision or test mode. |

| # | Requirement | Impact on the wireframes | Owner / decision |
|---|---|---|---|
| 1 | US market support in code | No US country, USD regional setting or sales-tax regime in the regional/tax modules; US tax display is a placeholder on every price screen. | CTO + Global Tax (PD-16, D09) |
| 2 | Stripe Connect per country | Seller payout onboarding (SEL-04) and live checkout (ORD-01) depend on verified US/UK Connect capabilities, settlement and payout terms. | CTO + CFO + GC (D04) |
| 3 | All-in vehicle price | The USA needs mandatory dealer fee fields for test COM-013; UK display rules are pending counsel. No fee fields exist in the listing API. | Legal + Dealer Ops; CTO |
| 4 | Business identifiers for KYB | Market-specific registration and tax identifiers for seller onboarding (SEL-02) are not defined. | Compliance + Global Tax |
| 5 | Vehicle identifier lookups | VIN (USA) / registration (UK) lookup and history/inspection provider not selected. | Product + Trust (D05) |
| 6 | Fitment reference data | Source for CONFIRMED_FIT vs CONDITIONAL_FIT labels not selected. | Product + Trust (D05) |
| 7 | Checkout vs commercial quote | Marketplace checkout does not use the commercial binding quote; the target flow (one quote per seller vs per cart) is undecided. | CTO + CPO (D10, Doc COM-11) |
| 8 | Plans and prices | No approved SKU, rate or gate; plan pages (SEL-09, CMA-06) can only show empty or pending states. | CFO + Commercial (D03) |
| 9 | Lead billing | Qualified-lead definition, acceptance window and billing (LEAD-03) undefined and not implemented. | Commercial + Product (Doc COM-07) |
| 10 | Legal and consent copy | Terms, privacy, consent, returns and cancellation texts for the USA and UK are not drafted. | Qualified counsel (Appendix D) |
| 11 | Staff roles for commercial and finance consoles | Role-to-screen permissions and risk classes for commercial/finance admin actions are undefined. | CTO + Security (PD-15, Doc COM-10) |
| 12 | Payment defaults outside the confirmed markets | The cash-on-delivery default (IN,GB) and Razorpay (India) need a decision; the wireframes hide COD for the USA/UK. | CTO + CFO + GC (PD-14) |
| 13 | Pilot scope | Whether a single pilot city/corridor is still required within the USA/UK affects geo-search defaults and supply-density thresholds. | Founder + Commercial (D01) |
| 14 | Design system | No DriverXtra design system or component library is attached; the wireframes use the master's amber/titanium direction (M§14) as placeholder tokens. | CPO / Design |
