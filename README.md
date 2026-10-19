# DriverXtra Platform Monorepo

Enterprise Automotive Commerce Infrastructure uniting B2C marketplace browsing, dealer inventory management, workshop service records, digital garage lifecycle passports, and internal operations moderation.

## Monorepo Architecture

- **`/backend`**: Django 5.1 / Django REST Framework / SimpleJWT API service.
  - Multi-tenant RBAC (`BUYER`, `SELLER`, `WORKSHOP`, `STAFF`, `ADMIN`).
  - Staff sub-roles (`VERIFICATION_OFFICER`, `DISPUTE_MANAGER`, `FINANCE_OFFICER`, `SUPPORT_AGENT`).
  - Granular permissions (`seller.verify`, `listing.review`, `order.refund`, `dispute.manage`, `finance.payout`, `staff.manage`).
  - Active role JWT claims with dynamic role switching (`/auth/switch-role/`).
  - 15-minute access tokens and mandatory TOTP MFA for staff/admin.
  - Email verification & password reset with SHA-256 tokens and refresh token blacklisting.
  - Immutable audit logging with correlation ID middleware.
  - Full automated test suite (130 tests passing).
- **`/frontend`**: Next.js 16 / React 19 / Tailwind CSS v4 portal.
  - Role-governed dashboard views and active role switching.
  - MFA enrolment in user profile and MFA step during login.
  - Public registration restricted strictly to `BUYER` accounts (merchant roles granted via seller compliance applications).
  - Quick-login developer presets gated behind `NEXT_PUBLIC_ENABLE_DEV_LOGIN=true` (off by default).
  - Staff invitation screen for platform administrators and `/set-password` activation page.

## Quick Start

### 1. Backend Service

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # On Windows
source .venv/bin/activate      # On Linux/macOS
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Run tests:
```bash
pytest
```

### 2. Frontend Web Application

```bash
cd frontend
npm install
npm run dev
```

Run lint and production build:
```bash
npm run lint
npm run build
```

## Security & Architecture Documentation
- Comprehensive authentication and RBAC specifications: [`docs/auth-design.md`](docs/auth-design.md)
- Backend endpoint reference and test details: [`backend/README.md`](backend/README.md)
