# DriverXtra Platform — Backend Services

The official backend engine for the DriverXtra automotive commerce platform, built with Django 5.1, Django REST Framework, SimpleJWT, and PostgreSQL 17.

This codebase delivers end-to-end authentication, multi-tenant RBAC, staff security controls, seller KYB compliance, parts & vehicle cataloging, vehicle garage passports, moderated marketplace workflows, and an immutable audit ledger.

---

## Table of Contents

1. [Architecture & System Scope](#architecture--system-scope)
2. [Technology Stack](#technology-stack)
3. [Authentication & Session Architecture](#authentication--session-architecture)
4. [Role-Based Access Control (RBAC) & Permissions](#role-based-access-control-rbac--permissions)
5. [Staff Security & Multi-Factor Authentication (MFA)](#staff-security--multi-factor-authentication-mfa)
6. [API Endpoints Reference](#api-endpoints-reference)
7. [Automated Test Suite](#automated-test-suite)
8. [Local Development Setup](#local-development-setup)

---

## Architecture & System Scope

The backend is organized into decoupled domain modules:

- **Identity & RBAC (`apps.identity`)**:
  - Custom `User` model using UUIDv4 primary keys and email-based authentication.
  - Multi-role support via `UserRole` (`BUYER`, `SELLER`, `WORKSHOP`, `STAFF`, `ADMIN`).
  - Active role tracking in JWT access token claims and dynamic role switching (`/auth/switch-role/`).
  - Public registration restricted strictly to `BUYER` accounts; seller/workshop self-assignment blocked.
  - Granular permissions table with seeded capabilities and `HasPermission('code')` class.
  - Staff sub-roles (`VERIFICATION_OFFICER`, `DISPUTE_MANAGER`, `FINANCE_OFFICER`, `SUPPORT_AGENT`).
  - Admin-only staff invitation flow with single-use activation tokens (`/admin/staff/invite/`).
  - Encrypted TOTP MFA storage via AES-Fernet with pyotp challenge verification.
  - Rate throttling scopes customized for public vs. staff authentication.
  - Maker-checker segregation via the generic `ApprovalRequest` model (`requester != approver`).
  - Email verification & password reset flows with SHA-256 hashed single-use tokens and token blacklisting.
- **Organisations & Tenant Isolation (`apps.organisations`)**:
  - Multi-tenant organisation model (`Organisation`) and memberships (`OrganisationMembership`).
  - Creation of `INTERNAL_OPS` organisations restricted strictly to platform `ADMIN` users.
  - Member role enforcement (`OWNER`, `ADMIN`, `MEMBER`, `TECHNICIAN`, `ANALYST`).
- **Seller & Workshop Onboarding (`apps.onboarding`)**:
  - Multi-stage onboarding applications (`SellerApplication`).
  - Approval grants `SELLER` role, and also `WORKSHOP` role if `business_type == 'WORKSHOP'`.
  - Self-approval strictly forbidden (`admin != application.user`).
- **Vehicle Master & Parts Catalogue (`apps.catalogue`)**:
  - Standardized vehicle taxonomy (Make, Model, Generation, Variant) and part catalog.
- **Digital Vehicle Garage (`apps.garage`)**:
  - Canonical vehicle lifecycle passports (`Vehicle`), MOT records, and service history.
  - Strict user and organization tenant isolation.
- **Marketplace Engine (`apps.marketplace`)**:
  - Vehicle and spare parts inventory listings (`VehicleListing`, `PartListing`).
  - Review and moderation lifecycle (`DRAFT` → `PENDING_APPROVAL` → `APPROVED` / `REJECTED` / `CHANGES_REQUESTED`).
  - Org listing governance: only `OWNER` or `ADMIN` members may create, edit, or resubmit organisation listings.
  - Material field changes (price, description, specs, images, VIN, mileage) automatically demote `APPROVED` listings back to `PENDING_APPROVAL`; stock-only adjustments remain live.
- **Audit & Telemetry (`platform_core.audit`)**:
  - `CorrelationIdMiddleware` assigning `X-Request-ID` or generated UUIDs to each request.
  - Immutable audit logging (`AuditLog`) capturing actor, action, resource, IP, user-agent, and correlation ID.
  - Automated logging on registration, login success/failure, role grant/revoke, seller approvals/rejections, listing reviews, org member additions, password resets, and HTTP 403 permission denials.

---

## Technology Stack

- **Language**: Python 3.10+
- **Framework**: Django 5.1+
- **API Engine**: Django REST Framework (DRF) 3.15+
- **Authentication**: `djangorestframework-simplejwt` with refresh token blacklisting
- **Security & MFA**: `pyotp` (RFC 6238 TOTP) & `cryptography` (Fernet symmetric encryption)
- **Database**: PostgreSQL 17 (Docker/production) & SQLite fallback for isolated test runners
- **Middleware**: Custom Correlation ID middleware & custom DRF exception handler
- **Testing**: `pytest`, `pytest-django`, `pytest-xdist`

---

## Authentication & Session Architecture

### Token Lifecycle & Expiration Rules
- **Standard Public Tokens** (`BUYER`, `SELLER`, `WORKSHOP`):
  - Access Token: 60 minutes
  - Refresh Token: 7 days
- **Elevated Staff & Admin Tokens** (`STAFF`, `ADMIN`):
  - Access Token: **15 minutes** (automatically enforced via `UserLoginSerializer` and `SwitchRoleSerializer`)
  - Refresh Token: 7 days with active lock renewal

### Active Role Concept
The JWT carries an `active_role` claim indicating the user's current execution context:
- Defaults to the highest-priority role held on sign in: $\text{ADMIN} > \text{STAFF} > \text{SELLER} > \text{WORKSHOP} > \text{BUYER}$.
- Users holding multiple roles can invoke `POST /api/v1/auth/switch-role/` to obtain updated tokens without re-entering credentials.

### Revocation & Blacklisting
- Logging out (`POST /api/v1/auth/logout/`) blacklists the supplied refresh token.
- Confirming a password reset (`POST /api/v1/auth/password-reset/confirm/`) blacklists **all outstanding refresh tokens** associated with the user, ensuring compromised sessions are instantly terminated.

---

## Role-Based Access Control (RBAC) & Permissions

### Platform Roles

| Role | Code | Scope | Registration Policy |
|---|---|---|---|
| **Buyer / Consumer** | `BUYER` | Search, browse, vehicle garage, ordering | **Self-assignable (Default)** |
| **Seller / Dealer** | `SELLER` | Inventory listings, parts submission, dealer sales | **Granted via Seller Application Approval** |
| **Workshop Partner** | `WORKSHOP` | Work orders, service logs, fitment validation | **Granted via Workshop Application Approval** |
| **Operations Staff** | `STAFF` | Verification queues, dispute reviews, compliance | **Admin Invitation Only (`/admin/staff/invite/`)** |
| **Platform Admin** | `ADMIN` | Full administrative control, internal ops orgs | **Superuser / Platform Provisioning Only** |

### Granular Permissions
- `seller.verify`: Authorizes review and approval/rejection of seller applications.
- `listing.review`: Authorizes moderation and review of vehicle/part listings.
- `order.refund`: Authorizes approving refunds and chargebacks.
- `dispute.manage`: Authorizes dispute mediation and fraud investigation.
- `finance.payout`: Authorizes settlement payouts and ledger disbursements.
- `staff.manage`: Authorizes staff invitations and permission management.

### Staff Sub-Roles
- `VERIFICATION_OFFICER`: Holds `seller.verify`, `listing.review`.
- `DISPUTE_MANAGER`: Holds `dispute.manage`, `order.refund`.
- `FINANCE_OFFICER`: Holds `finance.payout`, `order.refund`.
- `SUPPORT_AGENT`: Read-only customer service assistance.

---

## Staff Security & Multi-Factor Authentication (MFA)

1. **Enrolment (`POST /api/v1/auth/mfa/enrol/`)**:
   Generates a cryptographically random TOTP secret, stores it encrypted using AES-Fernet, and returns the secret with an `otpauth://` QR URI.
2. **Verification (`POST /api/v1/auth/mfa/verify/`)**:
   Validates the 6-digit TOTP code against the decrypted secret and activates MFA.
3. **Login Challenge**:
   When signing in with an MFA-enabled account, the user receives an `mfa_required` status and `pre_auth_token`. Passing this along with the 6-digit TOTP code to `/auth/mfa/verify/` releases the final 15-minute access token.

---

## API Endpoints Reference

### Authentication & Identity (`apps.identity`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/auth/register/` | Public | Register new user. Grants `BUYER` role only. |
| `POST` | `/api/v1/auth/login/` | Public | Sign in; returns tokens with `active_role` or MFA challenge. |
| `POST` | `/api/v1/auth/logout/` | Bearer | Blacklists refresh token and terminates session. |
| `POST` | `/api/v1/auth/token/refresh/` | Public | Exchanges refresh token for new access token. |
| `POST` | `/api/v1/auth/verify-email/` | Public | Validates email token and marks account verified. |
| `POST` | `/api/v1/auth/resend-verification/` | Public | Resends email verification token (throttled). |
| `POST` | `/api/v1/auth/password-reset/request/` | Public | Requests password reset link (enumeration-safe). |
| `POST` | `/api/v1/auth/password-reset/confirm/` | Public | Resets password, blacklists all outstanding tokens. |
| `POST` | `/api/v1/auth/switch-role/` | Bearer | Switches `active_role` claim and issues fresh tokens. |
| `POST` | `/api/v1/auth/mfa/enrol/` | Bearer | Generates and encrypts new TOTP MFA secret. |
| `POST` | `/api/v1/auth/mfa/verify/` | Public/Bearer | Verifies TOTP code during enrolment or login. |
| `POST` | `/api/v1/auth/staff/set-password/` | Public | Redeems single-use staff invite token to activate account. |
| `POST` | `/api/v1/admin/staff/invite/` | Admin | Invites new staff member with assigned sub-role. |
| `GET` | `/api/v1/users/me/` | Bearer | Returns current authenticated profile, roles, and permissions. |
| `PATCH` | `/api/v1/users/me/` | Bearer | Updates editable profile attributes (`first_name`, etc.). |

### Organisations (`apps.organisations`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/organisations/` | Bearer | List organisations user belongs to (Admins see all). |
| `POST` | `/api/v1/organisations/` | Bearer | Create organisation. `INTERNAL_OPS` requires Admin role. |
| `GET` | `/api/v1/organisations/{id}/` | Bearer | Retrieve organisation details. |
| `GET` | `/api/v1/organisations/{id}/members/` | Bearer | List organisation members. |
| `POST` | `/api/v1/organisations/{id}/members/` | Bearer | Add member to organisation (requires `OWNER`/`ADMIN`). |

### Onboarding (`apps.onboarding`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/seller/application/` | Bearer | Get user's current seller application. |
| `POST` | `/api/v1/seller/application/` | Bearer | Create draft seller application. |
| `PATCH` | `/api/v1/seller/application/` | Bearer | Update draft seller application. |
| `POST` | `/api/v1/seller/application/submit/` | Bearer | Submit application for compliance review. |
| `GET` | `/api/v1/admin/seller-applications/` | Staff (`seller.verify`) | List applications in review queue. |
| `POST` | `/api/v1/admin/seller-applications/{id}/approve/` | Staff (`seller.verify`) | Approve application (grants `SELLER`/`WORKSHOP`). |
| `POST` | `/api/v1/admin/seller-applications/{id}/reject/` | Staff (`seller.verify`) | Reject application with mandatory reason. |

### Marketplace (`apps.marketplace`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/marketplace/browse/vehicles/` | Public | List approved public vehicle listings. |
| `GET` | `/api/v1/marketplace/browse/vehicles/{id}/` | Public | Retrieve public details for an approved vehicle listing. |
| `GET` | `/api/v1/marketplace/browse/parts/` | Public (Bearer optional) | List approved public spare part listings with deterministic sorting, multi-attribute filtering, pre-pagination fitment filtering, and aggregated facet counts. |

#### Spare Parts Browse Query Parameters (`/api/v1/marketplace/browse/parts/`)

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `search` | `string` | No | None | Keyword query tokenised on whitespace matching `name`, `brand`, `mpn`, `oem_numbers`, and `description`. Matches determine relevance ordering when `sort=relevance`. |
| `category_id` | `UUID` | No | None | Filter parts belonging to a specific `PartCategory`. |
| `brand` | `string` | No | None | Case-insensitive substring match against part brand. |
| `mpn` | `string` | No | None | Case-insensitive substring match against Manufacturer Part Number. |
| `price_min` | `decimal` | No | None | Filter parts with `price >= price_min`. |
| `price_max` | `decimal` | No | None | Filter parts with `price <= price_max`. |
| `sort` | `string` | No | `newest` | Ordering strategy: `newest` (`-created_at, id`), `relevance` (exact MPN/OEM > prefix MPN > brand > name > description), `price_asc` (`price, id`), `price_desc` (`-price, id`). Invalid value returns structured 400. |
| `condition` | `string` | No | None | Comma-separated list of valid `PartConditionChoices` (e.g. `NEW,REFURBISHED`). Invalid choice returns structured 400. |
| `in_stock` | `boolean` | No | None | `true` filters to `stock_quantity > 0`. `false` returns both in-stock and out-of-stock items (default browse behavior). Invalid value returns structured 400. |
| `fits_vehicle` | `UUID` | No | None | Active garage vehicle ID belonging to authenticated user. Annotates each listing with `fitment` verification without filtering or reordering. Requires Bearer authentication. |
| `fits_only` | `boolean` | No | `false` | When `true`, filters the database queryset pre-pagination to listings whose fitment status for the selected vehicle is `VERIFIED` or `CONDITIONAL`. Requires `fits_vehicle` (missing returns 400). If garage vehicle has no catalogue variant, returns an empty list. |
| `include_facets` | `boolean` | No | `false` | When `true`, computes aggregated counts across `brands`, `categories` (`id`, `name`, `slug`, `count`), and `conditions` over the full filtered queryset before pagination and includes a top-level `facets` payload. |
| `page` | `integer` | No | `1` | Page number for standard DRF pagination. |
| `page_size` | `integer` | No | `20` | Results per page (clamped at 50; values < 1 or non-integers return structured 400). |
| `GET` | `/api/v1/marketplace/browse/parts/{id}/` | Public (Bearer optional) | Retrieve public details for an approved spare part listing. Accepts optional `?fits_vehicle=<garage_vehicle_id>` (requires Bearer auth) to annotate with buyer vehicle fitment. |
| `GET` | `/api/v1/marketplace/browse/parts/catalogue/{catalogue_part_id}/offers/` | Public | List approved offers for a catalogue part sorted by price ascending, then newest. |
| `GET` | `/api/v1/marketplace/vehicles/` | Seller | List seller's own vehicle listings. |
| `POST` | `/api/v1/marketplace/vehicles/` | Seller | Create vehicle listing (enforces org OWNER/ADMIN). |
| `PATCH` | `/api/v1/marketplace/vehicles/{id}/` | Seller | Edit listing. Material changes demote to `PENDING_APPROVAL`. |
| `POST` | `/api/v1/marketplace/vehicles/{id}/submit/` | Seller | Submit draft vehicle for compliance review. |
| `POST` | `/api/v1/marketplace/vehicles/{id}/resubmit/` | Seller | Resubmit rejected listing (creator or org OWNER/ADMIN). |
| `GET` | `/api/v1/marketplace/parts/` | Seller | List seller's own spare part listings with computed `fitment_verification` and `fitment_summary`. |
| `POST` | `/api/v1/marketplace/parts/` | Seller | Create spare part listing (non-draft submissions gate: blocked if declared variant has CONFLICT). |
| `PATCH` | `/api/v1/marketplace/parts/{id}/` | Seller | Edit listing. Material changes demote to `PENDING_APPROVAL`; atomic conflict gate prevents demotion if edit introduces CONFLICT. |
| `POST` | `/api/v1/marketplace/parts/{id}/submit/` | Seller | Submit draft part for approval (blocked on CONFLICT). |
| `POST` | `/api/v1/marketplace/parts/{id}/resubmit/` | Seller | Resubmit rejected part for review (blocked on CONFLICT). |
| `POST` | `/api/v1/marketplace/parts/{id}/stock/` | Seller | Adjust part stock (`delta`, `reason`, `note`). Atomic row-lock protected; accepts ADJUSTMENT/CORRECTION. |
| `GET` | `/api/v1/marketplace/parts/{id}/stock-history/` | Seller | Retrieve immutable audit ledger of stock movements for part. |
| `GET` | `/api/v1/marketplace/parts/{id}/price-history/` | Seller | Retrieve immutable audit ledger of price changes for part (seller or org OWNER/ADMIN). |
| `GET` | `/api/v1/marketplace/parts/low-stock/` | Seller | List seller's part listings at or below `low_stock_threshold`. |
| `GET` | `/api/v1/marketplace/admin/vehicles/` | Staff (`listing.review`) | List vehicles in admin moderation queue. |
| `GET` | `/api/v1/marketplace/admin/vehicles/{id}/` | Staff (`listing.review`) | Retrieve admin details for a vehicle in review queue. |
| `POST` | `/api/v1/marketplace/admin/vehicles/{id}/review/` | Staff (`listing.review`) | Approve, reject, or request changes on vehicle. |
| `GET` | `/api/v1/marketplace/admin/parts/` | Staff (`listing.review`) | List spare parts in admin moderation queue with computed fitment summaries. |
| `GET` | `/api/v1/marketplace/admin/parts/{id}/` | Staff (`listing.review`) | Retrieve admin details for a spare part listing. |
| `POST` | `/api/v1/marketplace/admin/parts/{id}/review/` | Staff (`listing.review`) | Approve, reject, or request changes on part (APPROVE blocked if listing has CONFLICT). |

---

## Automated Test Suite

The test suite validates compliance with all architectural requirements:

- **206 Tests Passing** (3 database trigger tests skipped when running under SQLite test configuration).
- Complete coverage across:
  - `tests/test_search_and_browse_parts.py`: Phase 3 Part D public parts browse search, tokenised relevance ranking (MPN > OEM > brand > name > description), deterministic sorting, pagination clamping at 50, comma-separated condition filter, in-stock filter, pre-pagination fits_only filtering with 100% Part C decision-table parity, aggregated facet counts, and constant query counts.
  - `tests/test_authentication.py`: Login, token refresh, logout revocation, suspended accounts.
  - `tests/test_registration.py`: BUYER-only enforcement, SELLER/WORKSHOP rejection, hashing.
  - `tests/test_email_verification_and_password_reset.py`: Verification, resend, reset single-use, 1h expiry, session revocation.
  - `tests/platform_core/test_audit.py`: Middleware correlation ID, audit logging across auth, orgs, listings, permissions.
  - `tests/test_organisations.py`: Tenant isolation, owner assignment, INTERNAL_OPS admin restriction.
  - `tests/test_seller_onboarding.py`: Application lifecycle, role granting on approval, self-approval prevention.
  - `tests/test_marketplace.py`: Material field demotion, org OWNER/ADMIN rules, resubmit permissions, stock adjustments.
  - `tests/test_inventory_management.py`: Inventory service row-locking, negative stock prevention, zero-delta rejection, forbidden reason rejection, availability computation, low-stock filtering, audit logging, and migration backfill idempotency.
  - `tests/test_offers_and_pricing.py`: Price validation, compare-at validation, MAX_LISTING_PRICE, active catalogue_part validation, atomic change_price with select_for_update and audit logging, approved demotion on price/compare_at/catalogue_part changes, immutable PriceChange ledger blocking update/delete, public catalogue offers endpoint, seller price-history permissions, and reviewer price flags (median, deviation, outlier warning, non-blocking).
  - `tests/test_fitment_verification.py`: Phase 3 Part C spare parts fitment verification service, 5-status vocabulary (VERIFIED, CONDITIONAL, CONFLICT, SELLER_CLAIMED, UNKNOWN), universal part evaluation preservation, single-query batch evaluations (constant O(1) query count), submission gating on create/submit/resubmit/material-edit with atomic rollback, admin review approve gate, public buyer fits_vehicle parameter handling (401 unauth, 404 non-owner/archived, 400 invalid UUID, unlinked vehicle UNKNOWN, annotation without filtering/reordering), and seller permission isolation.
  - `tests/test_roles_and_permissions.py`: Staff sub-roles, `HasPermission`, staff invite & set password, active role JWT, TOTP MFA, 15-minute access tokens, maker-checker `ApprovalRequest`.
  - `tests/test_garage.py` & `tests/test_catalogue.py`: Vehicle master and catalog endpoints.

### Running Backend Tests

```bash
cd backend
.\.venv\Scripts\pytest.exe
```

Expected result:
```text
======================= 206 passed, 3 skipped in ~65s =======================
```

---

## Local Development Setup

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```
