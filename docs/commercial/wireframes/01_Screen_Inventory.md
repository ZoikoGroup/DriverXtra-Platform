# Screen Inventory

| Field | Value |
|---|---|
| Version / date | 0.1 DRAFT — 19 November 2026 |
| Requirements sources | Master DX-COMM-MASTER-001 (v1.0; v1.1 rev. B proposed), `../01_Engineering_Reconciliation_Matrix.md`, Doc COM-02..COM-13 drafts in `../com/` |
| Confirmed decisions used | Zoiko Mobility Inc.; markets USA and UK; Stripe preferred (verification pending); finance and insurance out of scope here (separate workstream, Rithika) |
| API status legend | **CONFIRMED** = the route and method exist in the repository today (verified against the Django URL configuration on 19 November 2026; existing does not mean production-ready). **PROPOSED** = not in the repository; no contract implied. **DISABLED** = the route exists but the capability is closed by a gate, decision or test mode. |

**Totals:** 51 P0 screens across 12 workflows (wireframed in `P0_Wireframes.html`), plus 26 P1/P2 backlog items (see `02_P1_P2_Backlog.md`).
P0 screens marked "Gated / pending" are wireframed in their disabled or approval-pending state: SEL-04, SEL-09, CMA-06, LEAD-03, ORD-01.

## P0 screens

| ID | Screen | Workflow | Role | Priority | Build state | APIs confirmed / proposed / disabled | Master | COM doc | Existing UI (repo) |
|---|---|---|---|---|---|---|---|---|---|
| CUS-01 | Sign up | Customer onboarding, login and profile | Visitor | P0 | Buildable | 1 / 2 / 0 | M§02, §05 (Driver/Buyer free account), §14, §16 Data and AI | Doc COM-11 | frontend/src/app/register |
| CUS-02 | Verify email | Customer onboarding, login and profile | Visitor | P0 | Buildable | 2 / 0 / 0 | M§16 Seller verification (account trust baseline) | Doc COM-11 | frontend/src/app/verify-email |
| CUS-03 | Log in (with MFA step for staff) | Customer onboarding, login and profile | All users | P0 | Buildable | 4 / 0 / 0 | M§20 qualities (zero trust); E 2.6 | Doc COM-10 (staff roles) | frontend/src/app/login |
| CUS-04 | Reset password | Customer onboarding, login and profile | Visitor | P0 | Buildable | 2 / 0 / 0 | M§20 qualities | — | frontend/src/app/forgot-password, reset-password |
| CUS-05 | Profile, preferences and security | Customer onboarding, login and profile | Customer | P0 | Buildable | 3 / 1 / 0 | M§05 entitlement rules; M§16 Data and AI | Doc COM-08 | Phase1ProfileView.tsx |
| CUS-06 | Customer home | Customer home and automotive discovery | Customer / visitor | P0 | Buildable | 4 / 2 / 0 | M§01, §03, §14 Public IA | Doc COM-11 | ConsumerDashboardView.tsx, MarketplaceBrowseView.tsx |
| CUS-07 | Search results (all categories) | Customer home and automotive discovery | Customer / visitor | P0 | Buildable | 3 / 1 / 0 | M§14; E 2.4 (search is a derived copy) | Doc COM-11 | GlobalSearch.tsx |
| CUS-08 | My Garage | Customer home and automotive discovery | Customer | P0 | Buildable | 4 / 1 / 0 | M§03 Digital infrastructure; M§13.8 data rights | Doc COM-11 | Phase2GarageView.tsx |
| VEH-01 | Vehicle search and listings | Vehicle listings and details | Customer / visitor | P0 | Buildable | 2 / 1 / 0 | M§13.1, §14 Buy a Vehicle, §16 listing integrity | Doc COM-11, Doc COM-07 | MarketplaceBrowseView.tsx |
| VEH-02 | Vehicle details | Vehicle listings and details | Customer / visitor | P0 | Buildable | 3 / 2 / 0 | M§08D, §13.1, §14, §16 | Doc COM-11, Doc COM-02 | MarketplaceBrowseView.tsx |
| VEH-03 | Enquiry or offer to seller | Vehicle listings and details | Customer | P0 | Buildable | 2 / 1 / 0 | M§08A, §08D, §18 Attribution | Doc COM-07 | BuyerEnquiriesView.tsx, BuyerVehicleOrdersOffersSection.tsx |
| PRT-01 | Parts catalogue | Parts catalogue, search and fitment | Customer / visitor | P0 | Buildable | 4 / 0 / 0 | M§13.2, §14 Parts & Accessories | Doc COM-11 | Phase2CatalogueView.tsx |
| PRT-02 | Parts search with fitment | Parts catalogue, search and fitment | Customer / visitor | P0 | Buildable | 3 / 0 / 0 | M§08B, §13.2, §14; E 1.5 fitment values | Doc COM-11, Doc COM-03 | MarketplaceBrowseView.tsx |
| PRT-03 | Part details and fitment | Parts catalogue, search and fitment | Customer / visitor | P0 | Buildable | 4 / 0 / 0 | M§08B, §13.2, §16 Fitment and safety | Doc COM-11 | MarketplaceBrowseView.tsx |
| PRT-04 | Cart | Parts catalogue, search and fitment | Customer | P0 | Buildable | 1 / 1 / 0 | M§07 quote formation, §08B | Doc COM-11, Doc COM-06 | CartDrawer.tsx |
| WRK-01 | Find a workshop or service | Workshop and service discovery | Customer / visitor | P0 | Buildable | 2 / 1 / 0 | M§13.3, §14 Book a Service | Doc COM-11 | BuyerWorkshopsView.tsx, WorkshopLandingView.tsx |
| WRK-02 | Workshop profile | Workshop and service discovery | Customer / visitor | P0 | Buildable | 3 / 0 / 0 | M§13.3, §14, §16 Service quality | Doc COM-11 | BuyerWorkshopsView.tsx |
| BKG-01 | Book a service | Service booking and quotation | Customer | P0 | Buildable | 2 / 0 / 0 | M§08C, §13.3 | Doc COM-11, Doc COM-03 (revenue code COM-02 earning event) | BuyerWorkshopsView.tsx |
| BKG-02 | My bookings and booking detail | Service booking and quotation | Customer | P0 | Buildable | 5 / 0 / 0 | M§08C, §21 order_booking | Doc COM-11 | BuyerWorkshopsView.tsx |
| BKG-03 | Review quotation and pay deposit | Service booking and quotation | Customer | P0 | Buildable | 5 / 0 / 0 | M§07, §08C, §14 | Doc COM-11, Doc COM-05 | BuyerWorkshopsView.tsx |
| BKG-04 | Approve change order | Service booking and quotation | Customer | P0 | Buildable | 3 / 0 / 0 | M§08C, App A change-order vector | Doc COM-11 | BuyerWorkshopsView.tsx |
| SEL-01 | Choose seller type | Seller/dealer onboarding | Customer becoming a seller | P0 | Buildable | 0 / 1 / 0 | M§02 personas, §05 plans | Doc COM-08, Doc COM-02 | Phase2SellerOnboardingView.tsx |
| SEL-02 | Seller/dealer application | Seller/dealer onboarding | Applicant | P0 | Buildable | 3 / 0 / 0 | M§09 activation bundle, §16 Seller verification | Doc COM-02, Doc COM-06 | Phase2SellerOnboardingView.tsx |
| SEL-03 | Application status | Seller/dealer onboarding | Applicant | P0 | Buildable | 1 / 0 / 0 | M§16 | Doc COM-02 | Phase2SellerOnboardingView.tsx |
| SEL-04 | Payout setup (Stripe) | Seller/dealer onboarding | Approved seller | P0 | Gated / pending | 0 / 1 / 0 | M§10 modes A/B, treasury invariants | Doc COM-05 | — |
| SEL-05 | Seller / dealer dashboard | Seller/dealer dashboard and listings | Seller / dealer | P0 | Buildable | 3 / 1 / 0 | M§15 Seller/Dealer console | Doc COM-10, Doc COM-08 | DealerDashboardView.tsx |
| SEL-06 | My listings | Seller/dealer dashboard and listings | Seller / dealer | P0 | Buildable | 2 / 0 / 0 | M§13.1, §13.2; E 1.4 listing states | Doc COM-03 | SellerInventoryView.tsx |
| SEL-07 | Create / edit vehicle listing | Seller/dealer dashboard and listings | Seller / dealer | P0 | Buildable | 5 / 1 / 0 | M§13.1, §14, §16 listing integrity | Doc COM-03, Doc COM-11 | SellerInventoryView.tsx, ListingPhotoManager.tsx |
| SEL-08 | Create / edit part listing and stock | Seller/dealer dashboard and listings | Seller / supplier | P0 | Buildable | 6 / 0 / 0 | M§13.2 | Doc COM-03 | SellerInventoryView.tsx |
| SEL-09 | Plan and billing | Seller/dealer dashboard and listings | Seller / dealer / workshop | P0 | Gated / pending | 1 / 1 / 0 | M§05, §06, §14 Plans & Pricing | Doc COM-08, Doc COM-04 | — |
| ADM-01 | Admin overview | Admin dashboard and user management | Admin / staff | P0 | Buildable | 1 / 0 / 0 | M§15 Executive / Admin | Doc COM-10 | AdminOverviewView.tsx, OperationsDashboardView.tsx |
| ADM-02 | User management (buyers, sellers, workshops) | Admin dashboard and user management | Admin | P0 | Buildable | 6 / 0 / 0 | M§15, §16 | Doc COM-10 | AdminBuyerManagementView.tsx, AdminSellerManagementView.tsx, AdminWorkshopManagementView.tsx |
| ADM-03 | Staff, roles and invitations | Admin dashboard and user management | Admin | P0 | Buildable | 5 / 0 / 0 | M§15; E 2.6 roles | Doc COM-10 | AdminStaffManagementView.tsx |
| ADM-04 | Approvals queue (maker-checker) | Admin dashboard and user management | Admin / approver | P0 | Buildable | 4 / 0 / 0 | M§07 Approval, §10 dual control; E 2.9 maker-checker | Doc COM-10 | AdminApprovalsView.tsx |
| ADM-05 | Seller application review | Admin dashboard and user management | Verification officer / admin | P0 | Buildable | 2 / 0 / 0 | M§16 Seller verification | Doc COM-02 | AdminSellerManagementView.tsx |
| ADM-06 | Listing moderation | Admin dashboard and user management | Moderator / admin | P0 | Buildable | 5 / 0 / 0 | M§16 listing integrity; E 1.4 review | Doc COM-03 | AdminMarketplaceReviewView.tsx |
| CMA-01 | SKU catalogue | Commercial catalogue and pricing administration | Commercial staff | P0 | Buildable | 3 / 0 / 0 | M§04, §06, §20 Commercial Catalog | Doc COM-03 | CommercialAdminView.tsx |
| CMA-02 | Rate schedules | Commercial catalogue and pricing administration | Commercial staff / CFO approver | P0 | Buildable | 2 / 0 / 0 | M§07 rate engine and controls | Doc COM-03 | CommercialAdminView.tsx |
| CMA-03 | Country gates (USA, UK) | Commercial catalogue and pricing administration | Country-gate manager | P0 | Buildable | 2 / 0 / 0 | M§21 country gate; §09 activation bundle; §22 | Doc COM-02, Doc COM-13 | CommercialAdminView.tsx |
| CMA-04 | Party role profiles | Commercial catalogue and pricing administration | Commercial staff / GC | P0 | Buildable | 2 / 0 / 0 | M§09, §10 | Doc COM-02 | CommercialAdminView.tsx |
| CMA-05 | Quote preview (non-binding) | Commercial catalogue and pricing administration | Commercial staff | P0 | Buildable | 2 / 0 / 0 | M§07, App A golden vectors | Doc COM-03, Doc COM-11 | CommercialAdminView.tsx |
| CMA-06 | Public plans and pricing page | Commercial catalogue and pricing administration | Visitor / business prospect | P0 | Gated / pending | 1 / 0 / 0 | M§05, §06, §14 Plans & Pricing; D10 | Doc COM-08, Doc COM-11 | — |
| LEAD-01 | My enquiries and offers (buyer) | Leads and enquiry management | Customer | P0 | Buildable | 5 / 0 / 0 | M§08A, §08D | Doc COM-07 | BuyerEnquiriesView.tsx, BuyerVehicleOrdersOffersSection.tsx |
| LEAD-02 | Seller enquiry inbox | Leads and enquiry management | Seller / dealer | P0 | Buildable | 5 / 0 / 0 | M§08A, §15 Seller/Dealer console | Doc COM-07 | SellerVehicleOrdersOffersSection.tsx |
| LEAD-03 | Qualified lead review and billing | Leads and enquiry management | Dealer / partner; commercial staff | P0 | Gated / pending | 0 / 1 / 0 | M§04 ADV-04, §08A, §21 qualified_lead; test COM-004 | Doc COM-07 | — |
| ORD-01 | Checkout and payment | Payments, orders and transaction status | Customer | P0 | Gated / pending | 5 / 1 / 1 | M§07, §08B, §10 modes A/B | Doc COM-05, Doc COM-11 | CartDrawer.tsx, BuyerOrdersView.tsx |
| ORD-02 | Order confirmation and status | Payments, orders and transaction status | Customer | P0 | Buildable | 4 / 0 / 0 | M§08B, §21 order flow | Doc COM-11, Doc COM-05 | BuyerOrdersView.tsx |
| ORD-03 | My orders | Payments, orders and transaction status | Customer | P0 | Buildable | 3 / 0 / 0 | M§15 | Doc COM-11 | BuyerOrdersView.tsx |
| ORD-04 | Returns and refunds | Payments, orders and transaction status | Customer | P0 | Buildable | 4 / 0 / 0 | M§10 refunds, §16 Refund & chargeback | Doc COM-05, Doc COM-04 | BuyerOrdersView.tsx |
| ORD-05 | Seller orders and fulfilment | Payments, orders and transaction status | Seller | P0 | Buildable | 6 / 0 / 0 | M§08B, §15 Supplier console | Doc COM-05 | SellerOrdersView.tsx |
| ORD-06 | Admin refunds and disputes | Payments, orders and transaction status | Finance / dispute staff | P0 | Buildable | 6 / 0 / 0 | M§10, §16; E 1.6 Disputes authorise, Payments execute | Doc COM-05, Doc COM-10 | AdminDisputesRefundsView.tsx |

## P1/P2 backlog (summary)

| ID | Screen | Workflow | Role | Priority | Backend state | — | Master | — | — |
|---|---|---|---|---|---|---|---|---|---|
| EV-01 | EV Gateway hub: chargers, installers, battery checks | — | Customer | P1 | No EV backend; partner sources not selected | — | M§13.4 | — | — |
| VEH-04 | Vehicle order: off-platform payment report and documents | — | Buyer / seller | P1 | APIs exist (vehicle-orders, documents) | — | M§08D, §10 mode C | — | — |
| VEH-05 | Dealer storefront page | — | Visitor | P1 | Proposed | — | M§14 For Dealers | — | — |
| ORD-07 | Disputes: buyer case view and messages | — | Customer | P1 | APIs exist | — | M§16; E 1.6 | — | — |
| REV-01 | Reviews: write, reply, report; seller reputation | — | Customer / seller | P1 | APIs exist | — | M§16 Service quality | — | — |
| NTF-01 | Notification center | — | All | P1 | APIs exist | — | E 2.4 Notifications | — | — |
| SUP-01 | Support tickets (customer and agent) | — | Customer / agent | P1 | APIs exist | — | M§16 incident | — | — |
| WSH-01 | WorkshopHub: bookings board, quotations, work orders, technicians, change orders | — | Workshop | P1 | APIs exist | — | M§13.6 WorkshopHub | — | — |
| WSH-02 | Workshop profile, services and opening hours management | — | Workshop | P1 | APIs exist | — | M§13.3 | — | — |
| ORG-01 | Organisation and multi-location members | — | Dealer group / fleet | P1 | APIs exist | — | M§05 parent/group contracting | — | — |
| FIN-A1 | Finance Admin: PSP reconciliation, payout exceptions, close pack (Doc COM-10) | — | Finance | P1 | Not implemented; Stripe verification pending | — | M§15 Finance Admin | — | — |
| FIN-A2 | Invoices and credit notes | — | Business customer / finance | P1 | Not implemented | — | M§11 | — | — |
| SUB-01 | Subscription checkout, plan change, proration, cancellation | — | Business customer | P1 | Not implemented; D03 | — | M§05; test COM-015 | — | — |
| TRU-01 | Trust & compliance console: KYB, recalls, takedowns | — | Trust staff | P1 | Partly (application review exists) | — | M§15, §16 | — | — |
| HLP-01 | Help & Trust center: roles, refunds, disputes, scam warnings | — | Visitor | P1 | Content pending counsel | — | M§14 Help & Trust | — | — |
| FLT-01 | FleetOps dashboard | — | Fleet manager | P1 | UI shell exists (FleetDashboardView); no fleet backend | — | M§13.6 | — | — |
| ADS-01 | Sponsored placement purchase and campaign reporting | — | Dealer / advertiser | P2 | Not implemented; no approved SKU | — | M§04 ADV-02, MKT-01 | — | — |
| EXE-01 | Executive / board dashboard | — | Executive | P2 | Not implemented | — | M§15, §19 | — | — |
| RVO-01 | Growth / RevOps console | — | Commercial | P2 | Not implemented | — | M§15 | — | — |
| PRM-01 | Promotions administration | — | Commercial | P2 | Not implemented | — | M§07 Promotions | — | — |
| API-01 | Developer portal: API keys, quotas, webhooks | — | OEM / enterprise | P2 | Not implemented | — | M§05 Infrastructure API | — | — |
| B2B-01 | B2B RFQ and procurement approvals | — | Fleet / supplier | P2 | Not implemented | — | M§13.6 | — | — |
| FEED-01 | Dealer and supplier bulk feeds | — | Dealer / supplier | P2 | Not implemented | — | M§13.1, §13.2 | — | — |
| RSA-01 | Roadside and recovery requests | — | Customer | P2 | Not implemented | — | M§13.5 | — | — |
| LOY-01 | Loyalty and partner benefits | — | Customer | P2 | Not implemented | — | M§03 Loyalty | — | — |
| F&I | Finance and insurance journeys | — | — | — | Out of scope here: separate workstream (Rithika) | — | M§13.7; D06 | — | — |

## Per-screen specifications

The full specification for each P0 screen (layout, actions, fields and validations, states, USA/UK differences, API dependencies) is in `P0_Wireframes.html` (open it in a browser) and repeated below.

### CUS-01 — Sign up
- **Role:** Visitor · **Workflow:** Customer onboarding, login and profile · **Priority:** P0

- **Primary actions:** Create account → CUS-02
- **Secondary actions:** Log in → CUS-03
- **Fields and validations:** Full name: required, 2–100 characters; Email: required, valid format, unique (server check); Password: required; strength rules per backend validator; Confirm password: must match; Country: required, USA or UK only; sets market, currency and units; Marketing consent: optional, unchecked; consent notice version stored (M App C consent_provenance_id); Terms acknowledgement: required
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Field-level errors (e.g. email already registered); password rules listed. · success — Account created; go to email verification.
- **USA/UK:** USA: currency USD; ZIP code; date MM/DD/YYYY; UK: currency GBP; postcode; date DD/MM/YYYY; Consent and privacy copy differs by market; text pending counsel (Appendix D item 6)
- **Master:** M§02, §05 (Driver/Buyer free account), §14, §16 Data and AI · **COM:** Doc COM-11
- **APIs:** [CONFIRMED] POST /api/v1/auth/register/; [PROPOSED] Market/country preference stored on the profile (no field confirmed); [PROPOSED] Consent provenance record (M App C consent_provenance_id)

### CUS-02 — Verify email
- **Role:** Visitor · **Workflow:** Customer onboarding, login and profile · **Priority:** P0

- **Primary actions:** Resend email → CUS-02
- **Secondary actions:** Back to log in → CUS-03
- **Fields and validations:** Token (from link): required; invalid or expired token shows error
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — n/a · error — Expired or invalid link: offer resend. · success — Email verified: continue to log in.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§16 Seller verification (account trust baseline) · **COM:** Doc COM-11
- **APIs:** [CONFIRMED] POST /api/v1/auth/verify-email/; [CONFIRMED] POST /api/v1/auth/resend-verification/

### CUS-03 — Log in (with MFA step for staff)
- **Role:** All users · **Workflow:** Customer onboarding, login and profile · **Priority:** P0

- **Primary actions:** Log in → CUS-06
- **Secondary actions:** Forgot password → CUS-04; Create account → CUS-01
- **Fields and validations:** Email: required; Password: required; MFA code: 6 digits, required when the account has MFA
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Generic "email or password incorrect" (no account enumeration); locked/suspended account message; rate-limit message (HTTP 429). · success — Role-based landing: customer home (CUS-06), seller dashboard (SEL-05) or admin overview (ADM-01).
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§20 qualities (zero trust); E 2.6 · **COM:** Doc COM-10 (staff roles)
- **APIs:** [CONFIRMED] POST /api/v1/auth/login/; [CONFIRMED] POST /api/v1/auth/mfa/verify/; [CONFIRMED] POST /api/v1/auth/token/refresh/; [CONFIRMED] POST /api/v1/auth/switch-role/

### CUS-04 — Reset password
- **Role:** Visitor · **Workflow:** Customer onboarding, login and profile · **Priority:** P0

- **Primary actions:** Send reset link → CUS-03
- **Secondary actions:** Back to log in → CUS-03
- **Fields and validations:** Email: required (response is the same whether or not the account exists); New password + confirm: strength rules; must match
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Same confirmation message for every email.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§20 qualities · **COM:** —
- **APIs:** [CONFIRMED] POST /api/v1/auth/password-reset/request/; [CONFIRMED] POST /api/v1/auth/password-reset/confirm/

### CUS-05 — Profile, preferences and security
- **Role:** Customer · **Workflow:** Customer onboarding, login and profile · **Priority:** P0

- **Primary actions:** Save changes → CUS-05
- **Secondary actions:** Become a seller → SEL-01; Log out → CUS-03
- **Fields and validations:** Name: required; Phone: optional; E.164 format; Address: per-market format (ZIP vs postcode); Market: USA or UK
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** USA: state + ZIP; UK: county optional + postcode
- **Master:** M§05 entitlement rules; M§16 Data and AI · **COM:** Doc COM-08
- **APIs:** [CONFIRMED] GET/PATCH /api/v1/users/me/; [CONFIRMED] POST /api/v1/auth/switch-role/; [CONFIRMED] POST /api/v1/auth/logout/; [PROPOSED] Market preference and consent management endpoints

### CUS-06 — Customer home
- **Role:** Customer / visitor · **Workflow:** Customer home and automotive discovery · **Priority:** P0

- **Primary actions:** Search → CUS-07
- **Secondary actions:** Browse vehicles → VEH-01; Browse parts → PRT-01; Find a workshop → WRK-01; My Garage → CUS-08
- **Fields and validations:** Search query: 2+ characters
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — New user: prompt to add a vehicle to My Garage. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Price formatting $/£ from market setting; USA vehicle cards show all-in price (test COM-013); Sponsored cards carry a visible "Sponsored" label in both markets (M§14)
- **Master:** M§01, §03, §14 Public IA · **COM:** Doc COM-11
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/browse/vehicles/; [CONFIRMED] GET /api/v1/marketplace/browse/parts/; [CONFIRMED] GET /api/v1/workshops/; [CONFIRMED] GET /api/v1/garage/vehicles/; [PROPOSED] Personalised recommendations; [PROPOSED] EV Gateway content (no backend)

### CUS-07 — Search results (all categories)
- **Role:** Customer / visitor · **Workflow:** Customer home and automotive discovery · **Priority:** P0

- **Primary actions:** Open result → VEH-02
- **Secondary actions:** Filter → CUS-07; Save search (proposed) → CUS-07
- **Fields and validations:** Price range: min ≤ max, non-negative
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — No results: suggest removing filters or checking fitment. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Distance in miles (both markets); Currency per market
- **Master:** M§14; E 2.4 (search is a derived copy) · **COM:** Doc COM-11
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/browse/vehicles/; [CONFIRMED] GET /api/v1/marketplace/browse/parts/; [CONFIRMED] GET /api/v1/workshops/; [PROPOSED] Unified cross-category search endpoint (none today; results come from three calls)

### CUS-08 — My Garage
- **Role:** Customer · **Workflow:** Customer home and automotive discovery · **Priority:** P0

- **Primary actions:** Add vehicle → CUS-08
- **Secondary actions:** Set primary → CUS-08; Find parts → PRT-02; Book a service → WRK-01
- **Fields and validations:** Make/model/variant: from catalogue lists; Year: 4 digits, not in the future; Odometer: integer ≥ 0; Identifier: VIN 17 characters (USA) or registration (UK); lookup provider not selected (D05)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** USA: VIN primary; UK: registration (VRM) primary; VIN optional; Lookup/validation provider not selected
- **Master:** M§03 Digital infrastructure; M§13.8 data rights · **COM:** Doc COM-11
- **APIs:** [CONFIRMED] GET/POST /api/v1/garage/vehicles/; [CONFIRMED] POST /api/v1/garage/vehicles/{id}/set-primary/; [CONFIRMED] GET /api/v1/garage/vehicles/{vehicle_id}/service-history/; [CONFIRMED] GET /api/v1/garage/vehicles/{vehicle_id}/passport/pdf/; [PROPOSED] VIN / registration lookup (provider not selected)

### VEH-01 — Vehicle search and listings
- **Role:** Customer / visitor · **Workflow:** Vehicle listings and details · **Priority:** P0

- **Primary actions:** Open vehicle → VEH-02
- **Secondary actions:** Save to favorites → VEH-01; Compare (proposed) → VEH-01
- **Fields and validations:** Price and year ranges: min ≤ max
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — No vehicles match: widen filters. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** USA: price shown is the all-in price incl. mandatory dealer fees (M§14, test COM-013); UK: price display rules pending counsel (Appendix D item 8); Mileage in miles
- **Master:** M§13.1, §14 Buy a Vehicle, §16 listing integrity · **COM:** Doc COM-11, Doc COM-07
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/browse/vehicles/; [CONFIRMED] GET/POST /api/v1/marketplace/favourites/; [PROPOSED] Mandatory-fee fields for all-in price (no field confirmed)

### VEH-02 — Vehicle details
- **Role:** Customer / visitor · **Workflow:** Vehicle listings and details · **Priority:** P0

- **Primary actions:** Contact seller → VEH-03
- **Secondary actions:** Make an offer → VEH-03; Save → VEH-02; Report listing → VEH-02
- **Fields and validations:** None (display only)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Listing unavailable (sold or withdrawn): show similar vehicles. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** USA: all-in price incl. mandatory non-government fees (FTC; test COM-013); UK: price rules per counsel (Appendix D item 8); Seller-of-record label in both (test COM-009)
- **Master:** M§08D, §13.1, §14, §16 · **COM:** Doc COM-11, Doc COM-02
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/browse/vehicles/{id}/; [CONFIRMED] POST /api/v1/marketplace/favourites/; [CONFIRMED] DELETE /api/v1/marketplace/favourites/{id}/; [PROPOSED] Report listing endpoint; [PROPOSED] Vehicle history / inspection partner data (not selected)

### VEH-03 — Enquiry or offer to seller
- **Role:** Customer · **Workflow:** Vehicle listings and details · **Priority:** P0

- **Primary actions:** Send → LEAD-01
- **Secondary actions:** Cancel → VEH-02
- **Fields and validations:** Message: required, 10–2000 characters; Offer amount: positive integer in minor units of the market currency; Consent: required to share contact details (lead consent, M§08A)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Rate limit reached (enquiry cooldown): show when the user can send again. · success — Enquiry sent: appears in My enquiries (LEAD-01).
- **USA/UK:** Currency per market; Consent wording per market (pending counsel)
- **Master:** M§08A, §08D, §18 Attribution · **COM:** Doc COM-07
- **APIs:** [CONFIRMED] POST /api/v1/marketplace/vehicles/{id}/enquire/; [CONFIRMED] POST /api/v1/marketplace/vehicles/{id}/offers/; [PROPOSED] Test-drive appointment booking

### PRT-01 — Parts catalogue
- **Role:** Customer / visitor · **Workflow:** Parts catalogue, search and fitment · **Priority:** P0

- **Primary actions:** Open category → PRT-02
- **Secondary actions:** Change vehicle → CUS-08
- **Fields and validations:** None (display only)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — No vehicle selected: prompt to choose one for fitment. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§13.2, §14 Parts & Accessories · **COM:** Doc COM-11
- **APIs:** [CONFIRMED] GET /api/v1/catalogue/categories/; [CONFIRMED] GET /api/v1/catalogue/makes/; [CONFIRMED] GET /api/v1/catalogue/models/; [CONFIRMED] GET /api/v1/catalogue/variants/

### PRT-02 — Parts search with fitment
- **Role:** Customer / visitor · **Workflow:** Parts catalogue, search and fitment · **Priority:** P0

- **Primary actions:** Open part → PRT-03
- **Secondary actions:** Add to cart → PRT-04
- **Fields and validations:** Price range: min ≤ max
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — No parts fit this vehicle: show parts with UNKNOWN fitment separately with a warning. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency per market; Delivery estimates per market carriers
- **Master:** M§08B, §13.2, §14; E 1.5 fitment values · **COM:** Doc COM-11, Doc COM-03
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/browse/parts/; [CONFIRMED] GET /api/v1/catalogue/fitment/; [CONFIRMED] GET /api/v1/catalogue/parts/

### PRT-03 — Part details and fitment
- **Role:** Customer / visitor · **Workflow:** Parts catalogue, search and fitment · **Priority:** P0

- **Primary actions:** Add to cart → PRT-04
- **Secondary actions:** Save → PRT-03; Check another vehicle → CUS-08
- **Fields and validations:** Quantity: integer 1..available stock
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Out of stock: show other sellers. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency per market; Return rights copy per market (pending, Appendix D item 9)
- **Master:** M§08B, §13.2, §16 Fitment and safety · **COM:** Doc COM-11
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/browse/parts/{id}/; [CONFIRMED] GET /api/v1/marketplace/browse/parts/catalogue/{catalogue_part_id}/offers/; [CONFIRMED] GET /api/v1/catalogue/parts/{id}/compatibilities/; [CONFIRMED] GET /api/v1/marketplace/browse/parts/{id}/reviews/

### PRT-04 — Cart
- **Role:** Customer · **Workflow:** Parts catalogue, search and fitment · **Priority:** P0

- **Primary actions:** Checkout → ORD-01
- **Secondary actions:** Continue shopping → PRT-02; Remove item → PRT-04
- **Fields and validations:** Quantity: 1..stock; price and stock revalidated before order (E 1.5)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Cart is empty: browse parts. · error — Price or stock changed: show old vs new and ask the user to confirm. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** USA: sales tax shown as "calculated at checkout": no US tax engine yet (PD-16, D09); UK: VAT from the implemented UK VAT engine (rates pending Global Tax validation)
- **Master:** M§07 quote formation, §08B · **COM:** Doc COM-11, Doc COM-06
- **APIs:** [CONFIRMED] POST /api/v1/marketplace/orders/calculate/; [PROPOSED] Server-side cart (cart is client-side today: CartDrawer.tsx)

### WRK-01 — Find a workshop or service
- **Role:** Customer / visitor · **Workflow:** Workshop and service discovery · **Priority:** P0

- **Primary actions:** Open workshop → WRK-02
- **Secondary actions:** Book → BKG-01
- **Fields and validations:** Location: ZIP (USA) or postcode (UK)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — No workshops in this area: widen the radius. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** ZIP vs postcode; Distance in miles; Credential types per market (pending Trust, M§16)
- **Master:** M§13.3, §14 Book a Service · **COM:** Doc COM-11
- **APIs:** [CONFIRMED] GET /api/v1/workshops/; [CONFIRMED] GET /api/v1/workshops/categories/; [PROPOSED] Geo search / map tiles provider

### WRK-02 — Workshop profile
- **Role:** Customer / visitor · **Workflow:** Workshop and service discovery · **Priority:** P0

- **Primary actions:** Book this service → BKG-01
- **Secondary actions:** Message workshop → WRK-02; Read reviews → WRK-02
- **Fields and validations:** None (display only)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency per market
- **Master:** M§13.3, §14, §16 Service quality · **COM:** Doc COM-11
- **APIs:** [CONFIRMED] GET /api/v1/workshops/{id_or_slug}/; [CONFIRMED] GET /api/v1/workshops/{id_or_slug}/reviews/; [CONFIRMED] GET /api/v1/workshops/conversations/

### BKG-01 — Book a service
- **Role:** Customer · **Workflow:** Service booking and quotation · **Priority:** P0

- **Primary actions:** Request booking → BKG-02
- **Secondary actions:** Back → WRK-02
- **Fields and validations:** Service: at least one; Vehicle: required; Date: today or later, within opening hours; Slot: required; Notes: max 1000 characters
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Slot no longer available: pick another. · success — Booking requested; awaiting workshop confirmation or quotation.
- **USA/UK:** Date format per market; Currency per market
- **Master:** M§08C, §13.3 · **COM:** Doc COM-11, Doc COM-03 (revenue code COM-02 earning event)
- **APIs:** [CONFIRMED] POST /api/v1/workshops/bookings/; [CONFIRMED] GET /api/v1/garage/vehicles/

### BKG-02 — My bookings and booking detail
- **Role:** Customer · **Workflow:** Service booking and quotation · **Priority:** P0

- **Primary actions:** View quotation → BKG-03
- **Secondary actions:** Cancel booking → BKG-02
- **Fields and validations:** Cancellation reason: required when cancelling
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — No bookings yet: find a workshop. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§08C, §21 order_booking · **COM:** Doc COM-11
- **APIs:** [CONFIRMED] GET /api/v1/workshops/bookings/my/; [CONFIRMED] GET /api/v1/workshops/bookings/my/{id}/; [CONFIRMED] POST /api/v1/workshops/bookings/my/{id}/cancel/; [CONFIRMED] GET /api/v1/workshops/bookings/my/{id}/work-order/; [CONFIRMED] GET /api/v1/workshops/bookings/{identifier}/conversation/

### BKG-03 — Review quotation and pay deposit
- **Role:** Customer · **Workflow:** Service booking and quotation · **Priority:** P0

- **Primary actions:** Accept and pay deposit → ORD-01
- **Secondary actions:** Reject quotation → BKG-02
- **Fields and validations:** Rejection reason: optional; Terms acknowledgement: required to accept
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Quotation expired or changed: reload. · success — Quotation accepted; deposit confirmed.
- **USA/UK:** USA: tax line pending US tax support (PD-16); UK: VAT line
- **Master:** M§07, §08C, §14 · **COM:** Doc COM-11, Doc COM-05
- **APIs:** [CONFIRMED] GET /api/v1/workshops/quotations/{id}/; [CONFIRMED] POST /api/v1/workshops/quotations/{id}/accept/; [CONFIRMED] POST /api/v1/workshops/quotations/{id}/reject/; [CONFIRMED] POST /api/v1/workshops/quotations/{id}/deposit/create/; [CONFIRMED] POST /api/v1/workshops/quotations/{id}/deposit/verify/

### BKG-04 — Approve change order
- **Role:** Customer · **Workflow:** Service booking and quotation · **Priority:** P0

- **Primary actions:** Approve → BKG-02
- **Secondary actions:** Reject → BKG-02
- **Fields and validations:** Rejection note: optional
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§08C, App A change-order vector · **COM:** Doc COM-11
- **APIs:** [CONFIRMED] GET /api/v1/workshops/bookings/my/{id}/change-orders/; [CONFIRMED] POST /api/v1/workshops/change-orders/{id}/approve/; [CONFIRMED] POST /api/v1/workshops/change-orders/{id}/reject/

### SEL-01 — Choose seller type
- **Role:** Customer becoming a seller · **Workflow:** Seller/dealer onboarding · **Priority:** P0

- **Primary actions:** Continue → SEL-02
- **Secondary actions:** Back → CUS-05
- **Fields and validations:** Seller type: required, one option
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Available seller types may differ by market (pending D02 role profiles)
- **Master:** M§02 personas, §05 plans · **COM:** Doc COM-08, Doc COM-02
- **APIs:** [PROPOSED] Seller-type selection (current application endpoint covers sellers; workshop onboarding path to be confirmed)

### SEL-02 — Seller/dealer application
- **Role:** Applicant · **Workflow:** Seller/dealer onboarding · **Priority:** P0

- **Primary actions:** Submit application → SEL-03
- **Secondary actions:** Save draft → SEL-02
- **Fields and validations:** Legal name: required; Registration identifier: required for businesses; format per market (list pending Compliance); Tax registration: per market (pending Global Tax); Address: per-market format; Documents: PDF/JPG/PNG, size limit per backend, malware-scanned (E 2.7)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Missing or invalid documents listed per field. · success — Submitted: status "Under review".
- **USA/UK:** USA: business identifier and tax fields pending Compliance/Global Tax; UK: company and VAT fields pending Compliance/Global Tax; DSA/DAC7-style trader data not required for USA/UK unless counsel says so (Doc COM-06)
- **Master:** M§09 activation bundle, §16 Seller verification · **COM:** Doc COM-02, Doc COM-06
- **APIs:** [CONFIRMED] GET/POST/PATCH /api/v1/seller/application/; [CONFIRMED] POST /api/v1/seller/application/submit/; [CONFIRMED] POST /api/v1/marketplace/images/upload/

### SEL-03 — Application status
- **Role:** Applicant · **Workflow:** Seller/dealer onboarding · **Priority:** P0

- **Primary actions:** Go to seller dashboard → SEL-05
- **Secondary actions:** Update application → SEL-02
- **Fields and validations:** None (display only)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — No application yet: start one. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§16 · **COM:** Doc COM-02
- **APIs:** [CONFIRMED] GET /api/v1/seller/application/

### SEL-04 — Payout setup (Stripe)
- **Role:** Approved seller · **Workflow:** Seller/dealer onboarding · **Priority:** P0
- **Gate:** DISABLED: Stripe Connect is not integrated and US/UK capabilities are not yet verified (D04). The screen is shown as approval-pending.
- **Primary actions:** Start payout setup (disabled) → SEL-04
- **Secondary actions:** Back to dashboard → SEL-05
- **Fields and validations:** Collected by Stripe-hosted onboarding (proposed); DriverXtra stores no raw bank or card data (M§10)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Shown disabled with explanation. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** USA and UK Connect requirements differ; verification pending (D04)
- **Master:** M§10 modes A/B, treasury invariants · **COM:** Doc COM-05
- **APIs:** [PROPOSED] Stripe Connect account link and status endpoints (none exist)

### SEL-05 — Seller / dealer dashboard
- **Role:** Seller / dealer · **Workflow:** Seller/dealer dashboard and listings · **Priority:** P0

- **Primary actions:** Create listing → SEL-07
- **Secondary actions:** View enquiries → LEAD-02; View orders → ORD-05
- **Fields and validations:** None (display only)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — New seller: checklist (complete profile, first listing, payout setup). · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency per market
- **Master:** M§15 Seller/Dealer console · **COM:** Doc COM-10, Doc COM-08
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/seller/orders/; [CONFIRMED] GET /api/v1/marketplace/seller/enquiries/; [CONFIRMED] GET /api/v1/marketplace/parts/low-stock/; [PROPOSED] Seller dashboard summary endpoint

### SEL-06 — My listings
- **Role:** Seller / dealer · **Workflow:** Seller/dealer dashboard and listings · **Priority:** P0

- **Primary actions:** New vehicle listing → SEL-07
- **Secondary actions:** New part listing → SEL-08; Bulk feed import (P2) → SEL-06
- **Fields and validations:** None (display only)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — No listings: create your first. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§13.1, §13.2; E 1.4 listing states · **COM:** Doc COM-03
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/vehicles/; [CONFIRMED] GET /api/v1/marketplace/parts/

### SEL-07 — Create / edit vehicle listing
- **Role:** Seller / dealer · **Workflow:** Seller/dealer dashboard and listings · **Priority:** P0

- **Primary actions:** Submit for review → SEL-06
- **Secondary actions:** Save draft → SEL-07
- **Fields and validations:** Make/model/variant: from catalogue; Year: valid, not future; Mileage: integer ≥ 0; VIN: 17 characters (USA, required for dealers per policy pending) / registration (UK); Price: integer minor units > 0; Mandatory fees (USA): itemised, included in the all-in price; Photos: 1–10, JPG/PNG/WebP, magic-byte checked
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Review rejection reasons shown per field on resubmit. · success — Submitted for review.
- **USA/UK:** USA: mandatory dealer fees captured for the all-in price (test COM-013); UK: price display rules pending counsel
- **Master:** M§13.1, §14, §16 listing integrity · **COM:** Doc COM-03, Doc COM-11
- **APIs:** [CONFIRMED] POST /api/v1/marketplace/vehicles/; [CONFIRMED] PATCH /api/v1/marketplace/vehicles/{id}/; [CONFIRMED] POST /api/v1/marketplace/vehicles/{id}/submit/; [CONFIRMED] POST /api/v1/marketplace/vehicles/{id}/resubmit/; [CONFIRMED] POST /api/v1/marketplace/images/upload/; [PROPOSED] Mandatory-fee fields

### SEL-08 — Create / edit part listing and stock
- **Role:** Seller / supplier · **Workflow:** Seller/dealer dashboard and listings · **Priority:** P0

- **Primary actions:** Submit for review → SEL-06
- **Secondary actions:** Adjust stock → SEL-08
- **Fields and validations:** Catalogue part: required (fitment comes from the catalogue); Price: integer minor units > 0; Stock: integer ≥ 0
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§13.2 · **COM:** Doc COM-03
- **APIs:** [CONFIRMED] POST /api/v1/marketplace/parts/; [CONFIRMED] PATCH /api/v1/marketplace/parts/{id}/; [CONFIRMED] POST /api/v1/marketplace/parts/{id}/submit/; [CONFIRMED] POST /api/v1/marketplace/parts/{id}/stock/; [CONFIRMED] GET /api/v1/marketplace/parts/{id}/stock-history/; [CONFIRMED] GET /api/v1/marketplace/parts/{id}/price-history/

### SEL-09 — Plan and billing
- **Role:** Seller / dealer / workshop · **Workflow:** Seller/dealer dashboard and listings · **Priority:** P0
- **Gate:** APPROVAL PENDING: no SKU, rate or country gate is approved (D03, M§06 ILLUSTRATIVE); subscriptions and invoicing are not implemented.
- **Primary actions:** Choose plan (disabled) → SEL-09
- **Secondary actions:** Contact sales → SEL-09
- **Fields and validations:** None (display only)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — No plans available in your market (public plans endpoint returns an empty list until the DISCOVERY gate is enabled). · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Prices in USD / GBP once approved; tax per market
- **Master:** M§05, §06, §14 Plans & Pricing · **COM:** Doc COM-08, Doc COM-04
- **APIs:** [CONFIRMED] GET /api/v1/commercial/plans/?market=US|GB; [PROPOSED] Subscription, invoice and billing endpoints (not in R1)

### ADM-01 — Admin overview
- **Role:** Admin / staff · **Workflow:** Admin dashboard and user management · **Priority:** P0

- **Primary actions:** Open queue → ADM-04
- **Secondary actions:** Users → ADM-02
- **Fields and validations:** None (display only)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§15 Executive / Admin · **COM:** Doc COM-10
- **APIs:** [CONFIRMED] GET /api/v1/admin/overview/metrics/

### ADM-02 — User management (buyers, sellers, workshops)
- **Role:** Admin · **Workflow:** Admin dashboard and user management · **Priority:** P0

- **Primary actions:** View detail → ADM-02
- **Secondary actions:** Change status → ADM-02
- **Fields and validations:** Status change reason: required
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Permission denied (HTTP 403) when the role lacks the permission. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§15, §16 · **COM:** Doc COM-10
- **APIs:** [CONFIRMED] GET /api/v1/admin/buyers/; [CONFIRMED] GET /api/v1/admin/sellers/; [CONFIRMED] GET /api/v1/admin/workshops/; [CONFIRMED] POST /api/v1/admin/sellers/{pk}/status/; [CONFIRMED] POST /api/v1/admin/buyers/{pk}/status/; [CONFIRMED] POST /api/v1/admin/workshops/{pk}/status/

### ADM-03 — Staff, roles and invitations
- **Role:** Admin · **Workflow:** Admin dashboard and user management · **Priority:** P0

- **Primary actions:** Invite staff → ADM-03
- **Secondary actions:** Resend invitation → ADM-03
- **Fields and validations:** Invite email: required, valid; Staff role: required (explicit role; unassigned staff get no permissions)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§15; E 2.6 roles · **COM:** Doc COM-10
- **APIs:** [CONFIRMED] GET /api/v1/admin/staff/; [CONFIRMED] GET /api/v1/admin/staff/roles/; [CONFIRMED] POST /api/v1/admin/staff/invite/; [CONFIRMED] POST /api/v1/admin/staff/invitations/{pk}/resend/; [CONFIRMED] POST /api/v1/admin/staff/invitations/{pk}/revoke/

### ADM-04 — Approvals queue (maker-checker)
- **Role:** Admin / approver · **Workflow:** Admin dashboard and user management · **Priority:** P0

- **Primary actions:** Approve → ADM-04
- **Secondary actions:** Reject → ADM-04
- **Fields and validations:** Decision note: required on reject
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§07 Approval, §10 dual control; E 2.9 maker-checker · **COM:** Doc COM-10
- **APIs:** [CONFIRMED] GET /api/v1/admin/approvals/; [CONFIRMED] POST /api/v1/admin/approvals/{pk}/approve/; [CONFIRMED] POST /api/v1/admin/approvals/{pk}/reject/; [CONFIRMED] POST /api/v1/admin/approvals/{pk}/execute/

### ADM-05 — Seller application review
- **Role:** Verification officer / admin · **Workflow:** Admin dashboard and user management · **Priority:** P0

- **Primary actions:** Approve → ADM-05
- **Secondary actions:** Request information → ADM-05; Reject → ADM-05
- **Fields and validations:** Rejection / information request reason: required
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§16 Seller verification · **COM:** Doc COM-02
- **APIs:** [CONFIRMED] GET /api/v1/admin/seller-applications/; [CONFIRMED] POST /api/v1/admin/seller-applications/{id}/review/

### ADM-06 — Listing moderation
- **Role:** Moderator / admin · **Workflow:** Admin dashboard and user management · **Priority:** P0

- **Primary actions:** Approve → ADM-06
- **Secondary actions:** Reject → ADM-06
- **Fields and validations:** Rejection reasons: at least one
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§16 listing integrity; E 1.4 review · **COM:** Doc COM-03
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/admin/vehicles/; [CONFIRMED] POST /api/v1/marketplace/admin/vehicles/{id}/review/; [CONFIRMED] GET /api/v1/marketplace/admin/parts/; [CONFIRMED] POST /api/v1/marketplace/admin/parts/{id}/review/; [CONFIRMED] POST /api/v1/catalogue/photo-proposals/{id}/review/

### CMA-01 — SKU catalogue
- **Role:** Commercial staff · **Workflow:** Commercial catalogue and pricing administration · **Priority:** P0

- **Primary actions:** New SKU → CMA-01
- **Secondary actions:** New version → CMA-01; Retire → CMA-01
- **Fields and validations:** SKU code: required, unique per version; Family, vertical, fee basis: from controlled lists; Regulated SKUs (REG-01, REG-02, FIN-01, revenue code COM-04): cannot be approved
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Rule violations shown with their rule code (e.g. REGULATED_SKU_BLOCKED, SEPARATION_OF_DUTIES). · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§04, §06, §20 Commercial Catalog · **COM:** Doc COM-03
- **APIs:** [CONFIRMED] GET/POST /api/v1/commercial/admin/skus/; [CONFIRMED] POST /api/v1/commercial/admin/skus/{id}/status/; [CONFIRMED] POST /api/v1/commercial/admin/skus/{id}/new-version/

### CMA-02 — Rate schedules
- **Role:** Commercial staff / CFO approver · **Workflow:** Commercial catalogue and pricing administration · **Priority:** P0

- **Primary actions:** Save draft → CMA-02
- **Secondary actions:** Approve → CMA-02; Retire → CMA-02
- **Fields and validations:** Amount: integer minor units or basis points; Effective from: not in the past; No overlapping approved rate for the same scope; Approval requires commercial.approve and a different user from the author
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** USA: USD; UK: GBP; the commercial app accepts both currencies
- **Master:** M§07 rate engine and controls · **COM:** Doc COM-03
- **APIs:** [CONFIRMED] GET/POST /api/v1/commercial/admin/rate-schedules/; [CONFIRMED] POST /api/v1/commercial/admin/rate-schedules/{id}/status/

### CMA-03 — Country gates (USA, UK)
- **Role:** Country-gate manager · **Workflow:** Commercial catalogue and pricing administration · **Priority:** P0

- **Primary actions:** Advance step → CMA-03
- **Secondary actions:** Suspend / withdraw → CMA-03
- **Fields and validations:** Evidence reference: required for each step; Enablement: requires tax schedule reference, currencies, an approved role profile and a different person from the finance sign-off; Regulated capability: cannot be enabled
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** USA and UK gates start as Designed (closed)
- **Master:** M§21 country gate; §09 activation bundle; §22 · **COM:** Doc COM-02, Doc COM-13
- **APIs:** [CONFIRMED] GET/POST /api/v1/commercial/admin/country-gates/; [CONFIRMED] POST /api/v1/commercial/admin/country-gates/{id}/transition/

### CMA-04 — Party role profiles
- **Role:** Commercial staff / GC · **Workflow:** Commercial catalogue and pricing administration · **Priority:** P0

- **Primary actions:** New profile → CMA-04
- **Secondary actions:** Approve (GC + CFO) → CMA-04
- **Fields and validations:** Gated types (regulated introducer, cross-border, principal seller, modes E/F): cannot be approved
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§09, §10 · **COM:** Doc COM-02
- **APIs:** [CONFIRMED] GET/POST /api/v1/commercial/admin/role-profiles/; [CONFIRMED] POST /api/v1/commercial/admin/role-profiles/{id}/status/

### CMA-05 — Quote preview (non-binding)
- **Role:** Commercial staff · **Workflow:** Commercial catalogue and pricing administration · **Priority:** P0

- **Primary actions:** Run preview → CMA-05
- **Secondary actions:** Open quotes log → CMA-05
- **Fields and validations:** Amounts: integer minor units; one currency (no FX)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§07, App A golden vectors · **COM:** Doc COM-03, Doc COM-11
- **APIs:** [CONFIRMED] POST /api/v1/commercial/admin/quote-preview/; [CONFIRMED] GET /api/v1/commercial/admin/quotes/

### CMA-06 — Public plans and pricing page
- **Role:** Visitor / business prospect · **Workflow:** Commercial catalogue and pricing administration · **Priority:** P0
- **Gate:** GATED: shows plans only when the market's DISCOVERY gate is enabled and rates are approved. Today the page shows the empty state.
- **Primary actions:** Contact sales → CMA-06
- **Secondary actions:** Switch market → CMA-06
- **Fields and validations:** None (display only)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — "Pricing for your market is coming soon": no hard-coded prices (M§14). · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** USA: USD; UK: GBP; Tax wording per market
- **Master:** M§05, §06, §14 Plans & Pricing; D10 · **COM:** Doc COM-08, Doc COM-11
- **APIs:** [CONFIRMED] GET /api/v1/commercial/plans/?market=US|GB

### LEAD-01 — My enquiries and offers (buyer)
- **Role:** Customer · **Workflow:** Leads and enquiry management · **Priority:** P0

- **Primary actions:** Open conversation → LEAD-01
- **Secondary actions:** Withdraw → LEAD-01
- **Fields and validations:** Counter amount: positive integer minor units
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — No enquiries yet: browse vehicles. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§08A, §08D · **COM:** Doc COM-07
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/buyer/enquiries/; [CONFIRMED] GET /api/v1/marketplace/buyer/vehicle-offers/; [CONFIRMED] POST /api/v1/marketplace/buyer/vehicle-offers/{id}/accept/; [CONFIRMED] POST /api/v1/marketplace/buyer/vehicle-offers/{id}/counter/; [CONFIRMED] POST /api/v1/marketplace/buyer/vehicle-offers/{id}/withdraw/

### LEAD-02 — Seller enquiry inbox
- **Role:** Seller / dealer · **Workflow:** Leads and enquiry management · **Priority:** P0

- **Primary actions:** Reply → LEAD-02
- **Secondary actions:** Counter → LEAD-02
- **Fields and validations:** Reply: required, 1–2000 characters
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — No enquiries yet. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§08A, §15 Seller/Dealer console · **COM:** Doc COM-07
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/seller/enquiries/; [CONFIRMED] GET /api/v1/marketplace/seller/vehicle-offers/; [CONFIRMED] POST /api/v1/marketplace/seller/vehicle-offers/{id}/accept/; [CONFIRMED] POST /api/v1/marketplace/seller/vehicle-offers/{id}/counter/; [CONFIRMED] POST /api/v1/marketplace/seller/vehicle-offers/{id}/reject/

### LEAD-03 — Qualified lead review and billing
- **Role:** Dealer / partner; commercial staff · **Workflow:** Leads and enquiry management · **Priority:** P0
- **Gate:** DISABLED: qualified leads, lead billing (ADV-04, REF-01) and lead disputes are not implemented and have no approved SKU or rate.
- **Primary actions:** Accept (disabled) → LEAD-03
- **Secondary actions:** Reject (disabled) → LEAD-03
- **Fields and validations:** Rejection reason: from the contract list (pending)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§04 ADV-04, §08A, §21 qualified_lead; test COM-004 · **COM:** Doc COM-07
- **APIs:** [PROPOSED] Lead, lead decision and lead billing endpoints (M§21 example only: POST /v1/leads, POST /v1/leads/{id}/decision; not implemented)

### ORD-01 — Checkout and payment
- **Role:** Customer · **Workflow:** Payments, orders and transaction status · **Priority:** P0
- **Gate:** PARTIAL: Stripe runs in test mode; live use pending country verification (D04). Cash on delivery is not offered for the USA/UK pending PD-14.
- **Primary actions:** Pay → ORD-02
- **Secondary actions:** Back to cart → PRT-04
- **Fields and validations:** Address: required; ZIP/postcode format per market; Card data: entered only in the Stripe element; never stored by DriverXtra (M§10)
- **States:** loading — Payment processing: no double-submit; an idempotency key per attempt. · empty — Plain-language empty message with one next step. · error — Payment failed or cancelled: order not placed; retry option. Unknown outcome: "Checking payment status", reconciled, never charged twice (E 1.5). · success — Payment confirmed: order confirmation.
- **USA/UK:** USA: USD; sales tax pending US tax support (PD-16); UK: GBP; VAT shown; Payment methods per Stripe country capabilities (pending verification)
- **Master:** M§07, §08B, §10 modes A/B · **COM:** Doc COM-05, Doc COM-11
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/orders/payment-methods/; [CONFIRMED] POST /api/v1/marketplace/orders/checkout/; [CONFIRMED] POST /api/v1/marketplace/orders/{identifier}/payment/create/; [CONFIRMED] POST /api/v1/marketplace/orders/{identifier}/payment/verify/; [CONFIRMED] POST /api/v1/marketplace/payments/webhook/{provider}/; [DISABLED] POST /api/v1/marketplace/orders/{identifier}/cod-collection/ — COD not offered for USA/UK pending PD-14; [PROPOSED] Commercial binding quote at checkout (checkout does not use the commercial quote today)

### ORD-02 — Order confirmation and status
- **Role:** Customer · **Workflow:** Payments, orders and transaction status · **Priority:** P0

- **Primary actions:** Track shipment → ORD-02
- **Secondary actions:** Request return → ORD-04; Cancel order → ORD-02
- **Fields and validations:** Cancellation reason: required
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Payment pending: show "awaiting confirmation" without asking the customer to pay again. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§08B, §21 order flow · **COM:** Doc COM-11, Doc COM-05
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/orders/{identifier}/; [CONFIRMED] POST /api/v1/marketplace/orders/{identifier}/cancel/; [CONFIRMED] GET /api/v1/marketplace/buyer/orders/{identifier}/shipments/; [CONFIRMED] GET /api/v1/marketplace/shipments/track/{tracking_number}/

### ORD-03 — My orders
- **Role:** Customer · **Workflow:** Payments, orders and transaction status · **Priority:** P0

- **Primary actions:** Open order → ORD-02
- **Secondary actions:** Filter → ORD-03
- **Fields and validations:** None (display only)
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — No orders yet. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§15 · **COM:** Doc COM-11
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/orders/; [CONFIRMED] GET /api/v1/marketplace/buyer/vehicle-orders/; [CONFIRMED] GET /api/v1/workshops/bookings/my/

### ORD-04 — Returns and refunds
- **Role:** Customer · **Workflow:** Payments, orders and transaction status · **Priority:** P0

- **Primary actions:** Submit return → ORD-02
- **Secondary actions:** Open dispute → ORD-04
- **Fields and validations:** Items: at least one, within the eligibility window; Reason: required; Evidence: images, size limit per backend
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Not eligible: show the reason from the eligibility check. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Return rights and timelines per market (pending Consumer Legal, Appendix D item 9)
- **Master:** M§10 refunds, §16 Refund & chargeback · **COM:** Doc COM-05, Doc COM-04
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/buyer/orders/{identifier}/return-eligibility/; [CONFIRMED] POST /api/v1/marketplace/buyer/orders/{identifier}/returns/; [CONFIRMED] GET /api/v1/marketplace/buyer/refunds/; [CONFIRMED] POST /api/v1/marketplace/buyer/orders/{identifier}/disputes/

### ORD-05 — Seller orders and fulfilment
- **Role:** Seller · **Workflow:** Payments, orders and transaction status · **Priority:** P0

- **Primary actions:** Mark shipped → ORD-05
- **Secondary actions:** Review return → ORD-05; Record refund → ORD-05
- **Fields and validations:** Carrier: from the carrier list; Tracking number: required to mark shipped
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§08B, §15 Supplier console · **COM:** Doc COM-05
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/seller/orders/; [CONFIRMED] POST /api/v1/marketplace/seller/orders/{identifier}/status/; [CONFIRMED] POST /api/v1/marketplace/seller/orders/{identifier}/shipments/; [CONFIRMED] GET /api/v1/marketplace/logistics/carriers/; [CONFIRMED] GET /api/v1/marketplace/seller/returns/; [CONFIRMED] POST /api/v1/marketplace/seller/returns/{identifier}/review/

### ORD-06 — Admin refunds and disputes
- **Role:** Finance / dispute staff · **Workflow:** Payments, orders and transaction status · **Priority:** P0

- **Primary actions:** Approve → ORD-06
- **Secondary actions:** Reject → ORD-06; Update dispute status → ORD-06
- **Fields and validations:** Decision note: required; Refund amount: ≤ refundable balance, integer minor units
- **States:** loading — Skeleton placeholders for each block; primary action disabled. · empty — Plain-language empty message with one next step. · error — Inline error with the API error message and request ID; retry action; form values kept. · success — Toast confirmation and navigation to the next screen.
- **USA/UK:** Currency, date and address formats follow the market setting.
- **Master:** M§10, §16; E 1.6 Disputes authorise, Payments execute · **COM:** Doc COM-05, Doc COM-10
- **APIs:** [CONFIRMED] GET /api/v1/marketplace/admin/refunds/; [CONFIRMED] POST /api/v1/marketplace/admin/refunds/{identifier}/approve/; [CONFIRMED] POST /api/v1/marketplace/admin/refunds/{identifier}/dispatch/; [CONFIRMED] POST /api/v1/marketplace/admin/refunds/{identifier}/reconcile/; [CONFIRMED] GET /api/v1/marketplace/admin/disputes/; [CONFIRMED] POST /api/v1/marketplace/admin/disputes/{identifier}/status/
