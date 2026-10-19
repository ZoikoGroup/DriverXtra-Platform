# DriverXtra Identity, Authentication & RBAC Architecture

This document describes the production identity, role-based access control (RBAC), multi-factor authentication (MFA), active role switching, and session token architecture implemented across the DriverXtra platform backend (Django 5.1 / DRF / SimpleJWT) and frontend (Next.js 16 / React 19).

---

## 1. Platform Roles & Registration Rules

### Canonical Roles

| Role Code | Public Registration | Role Acquisition Flow | Scope & Access |
|---|---|---|---|
| `BUYER` | **Allowed (Default)** | Public registration (`/auth/register/`) | Marketplace browsing, parts search, consumer digital garage, order creation. |
| `SELLER` | **Blocked (400 Bad Request)** | Granted via `SellerApplication.approve()` | Vehicle & spare parts catalog management, inventory publishing, order settlement. |
| `WORKSHOP` | **Blocked (400 Bad Request)** | Granted via `SellerApplication.approve()` when `business_type == 'WORKSHOP'` | Service work orders, change orders, fitment verification, vehicle passports. |
| `STAFF` | **Forbidden** | Admin-only invitation (`POST /admin/staff/invite/`) | Internal operations queue, verification, moderation, dispute resolution. |
| `ADMIN` | **Forbidden** | Django superuser / CLI provisioning | Full platform administration, staff invitation, maker-checker management. |

### Public Registration Security (Phase 1)
- Public user registration (`POST /api/v1/auth/register/`) explicitly grants the `BUYER` role only.
- Any request attempting to assign `SELLER` or `WORKSHOP` is rejected with `HTTP 400 Bad Request` and a clear message explaining that merchant accounts require a seller compliance application.
- Public requests attempting to assign `STAFF` or `ADMIN` are rejected with `HTTP 400 Bad Request`.
- Self-approval of applications is blocked at both model and API levels (`admin != application.user`).

---

## 2. Granular Permissions & Staff Sub-Roles

### Permissions System
Permissions are granular, string-coded capabilities stored in the `Permission` table and enforced via DRF's `HasPermission(perm_code)` permission class factory:

- `seller.verify`: Authorizes review and approval/rejection of seller and workshop KYB compliance applications (`apps.onboarding`).
- `listing.review`: Authorizes moderation, approval, rejection, and change requests on vehicle and part listings (`apps.marketplace`).
- `order.refund`: Authorizes approving customer refunds and escrow chargebacks.
- `dispute.manage`: Authorizes mediation of customer disputes and odometer fraud flags.
- `finance.payout`: Authorizes settlement payouts and ledger releases.
- `staff.manage`: Authorizes inviting staff and modifying sub-role configurations.

*Note: Platform `ADMIN` users (`is_superuser=True` or `ADMIN` role) automatically bypass permission checks and hold all permissions.*

### Staff Sub-Roles (`StaffRole` and `StaffProfile`)
Platform operations staff (`STAFF` role) are assigned a specific operational sub-role with associated permissions:

| Staff Role Code | Role Name | Associated Seeded Permissions |
|---|---|---|
| `VERIFICATION_OFFICER` | Verification Officer | `seller.verify`, `listing.review` |
| `DISPUTE_MANAGER` | Dispute Manager | `dispute.manage`, `order.refund` |
| `FINANCE_OFFICER` | Finance Officer | `finance.payout`, `order.refund` |
| `SUPPORT_AGENT` | Support Agent | Customer support assistance (Read-only queues) |

---

## 3. JWT Tokens & Active Role Architecture

### Token Claims
SimpleJWT access tokens carry canonical claims identifying the user's active execution context:
```json
{
  "token_type": "access",
  "exp": 1774000000,
  "iat": 1773999100,
  "jti": "uuid-here",
  "user_id": "d0434771-4fb2-44f2-95f0-62e92cff8a4d",
  "email": "user@example.com",
  "active_role": "SELLER",
  "roles": ["BUYER", "SELLER"],
  "staff_role": null
}
```

### Active Role Priority on Sign In
When a user signs in, their `active_role` claim is initialized to their highest-priority role held:
$$\text{ADMIN} > \text{STAFF} > \text{SELLER} > \text{WORKSHOP} > \text{BUYER}$$

### Real Role Switching (`POST /api/v1/auth/switch-role/`)
Users holding multiple roles (e.g. `BUYER` and `SELLER`) can dynamically switch their execution context:
1. Client sends `POST /api/v1/auth/switch-role/` with body `{"role": "SELLER"}` and current Bearer token.
2. Backend validates that the authenticated user actually holds the requested role.
3. Backend issues a fresh JWT pair (`access` and `refresh`) embedding the new `active_role`.
4. The client replaces stored session tokens and updates UI navigation without re-authenticating.

---

## 4. Staff Security & Multi-Factor Authentication (MFA)

### 15-Minute Short-Lived Access Tokens
- For standard public accounts (`BUYER`, `SELLER`, `WORKSHOP`), access tokens have a 60-minute lifetime.
- For elevated security accounts (`active_role in ['STAFF', 'ADMIN']` or `is_staff=True`), access tokens automatically expire after **15 minutes**.
- Active session renewal uses the refresh token lock flow implemented in the frontend client.

### Time-Based One-Time Password (TOTP MFA)
Staff members and administrators are protected by mandatory TOTP 2FA:
1. **Enrolment (`POST /api/v1/auth/mfa/enrol/`)**:
   - Generates a cryptographically random Base32 secret.
   - Encrypts the secret using AES-Fernet derived from `SECRET_KEY` and persists it in `StaffProfile`.
   - Returns the secret and `otpauth://` provisioning URI for QR code scanning.
2. **Verification & Activation (`POST /api/v1/auth/mfa/verify/`)**:
   - Accepts 6-digit TOTP code. Verifies code against the decrypted secret with a $\pm 1$ time-step window.
   - Marks `has_mfa_enabled = True` on success.
3. **Login Challenge Flow**:
   - If an account has `has_mfa_enabled = True`, `POST /api/v1/auth/login/` does **not** return access/refresh tokens.
   - It returns `{ "status": "mfa_required", "pre_auth_token": "<signed-challenge-token>" }`.
   - The user inputs their 6-digit code to `POST /api/v1/auth/mfa/verify/` with `pre_auth_token`.
   - On valid code, the final access/refresh tokens are released.

### Rate Throttling
Stricter DRF throttling scopes are enforced on sensitive authentication endpoints:
- **Login**: `10/min` for public users, `5/min` for staff/admin.
- **Password Reset Request**: `5/min` for public users, `3/min` for staff/admin.

---

## 5. Staff Onboarding & Set Password Flow

Staff accounts cannot be registered publicly. They must be provisioned via enterprise invitation:
1. Platform Administrator calls `POST /api/v1/admin/staff/invite/` with `email`, `first_name`, `last_name`, `staff_role`, and `department`.
2. Backend creates an inactive `User` with `STAFF` role, creates their `StaffProfile`, generates a cryptographically secure 32-byte token, and stores its SHA-256 hash in `StaffInviteToken` (48-hour expiration).
3. The raw token is delivered via email (or returned in development mode).
4. The invited officer navigates to `/set-password?token=...` and calls `POST /api/v1/auth/staff/set-password/`.
5. Upon setting an 8+ character password, the token is consumed, the account status becomes `ACTIVE`, and the staff member can sign in.

---

## 6. Email Verification & Password Reset Flows

Tokens are stored exclusively as **SHA-256 hashes**; raw tokens are never persisted in the database.

### Email Verification
- Registration creates an `EmailVerificationToken` (24-hour expiration) and sends a verification link.
- `POST /api/v1/auth/verify-email/` with `{"token": "..."}` validates the hash, marks the user's email as verified, and activates the account.
- `POST /api/v1/auth/resend-verification/` provides an enumeration-safe response ("If the account exists, a link has been sent").
- Unverified accounts are strictly blocked from logging in.

### Password Reset
- `POST /api/v1/auth/password-reset/request/` accepts an email and produces a generic enumeration-safe response.
- `POST /api/v1/auth/password-reset/confirm/` validates single-use token within 1 hour.
- **Session Termination**: Blacklists all outstanding refresh tokens associated with the user via `OutstandingToken.objects.filter(user=user)`, ensuring stolen or stale sessions are immediately revoked.

---

## 7. Maker-Checker Controls (`ApprovalRequest`)

To prevent insider fraud and unauthorized unilateral actions, the generic `ApprovalRequest` model enforces dual-custody approval:
- **Segregation of Duties**: `ApprovalRequest.approve()` and `reject()` raise a `ValueError` if `approver.id == requester.id`.
- Designed for high-risk operations (dispute payouts, fee refunds, high-value seller overrides).

---

## 8. Immutable Audit Logging & Telemetry

- **Correlation ID Middleware**: Every inbound request receives an `X-Request-ID` or generated UUID correlation ID attached to `threading.local`.
- **Audit Writers**: `record_audit_entry` and `record_denied_audit_entry` log:
  - Actor ID, action code, resource type, resource ID, client IP, user agent, and correlation ID.
- **Wired Event Triggers**:
  - Registration, Login success & failure, Password reset confirm, Role grant & revoke, Seller application approve & reject, Listing approve & reject & request-changes, Organisation member add, and HTTP 403 Permission Denials.
