# DriverXtra Platform — Backend (Phase 1: Authentication & User Management)

The official backend service for the DriverXtra Platform, built with Django, Django REST Framework, SimpleJWT, and PostgreSQL.

This codebase provides the foundation and implements **Phase 1: Authentication & User Management**, strictly adhering to backend isolation and canonical role-based access control.

---

## Table of Contents

1. [Architecture & Phase 1 Scope](#architecture--phase-1-scope)
2. [Technology Stack](#technology-stack)
3. [Authentication Strategy & Architectural Decision](#authentication-strategy--architectural-decision)
4. [Role-Based Access Control (RBAC)](#role-based-access-control-rbac)
5. [Project Structure](#project-structure)
6. [Local Setup Guide](#local-setup-guide)
7. [Docker & Containerized Setup](#docker--containerized-setup)
8. [API Endpoints Reference](#api-endpoints-reference)
9. [Automated Test Suite](#automated-test-suite)

---

## Architecture & Phase 1 Scope

The backend service is structured as a modular Django application designed for high security, horizontal scalability, and clean tenant isolation:

- **Identity & RBAC (`apps.identity`)**:
  - Custom `User` model using UUIDv4 primary keys.
  - Email-based authentication (no usernames).
  - Password hashing via standard PBKDF2 with SHA-256.
  - Multi-role support per user via `UserRole` bridge model.
  - Account status lifecycle (`ACTIVE`, `PENDING`, `SUSPENDED`, `DEACTIVATED`).
  - Strict security controls preventing public users from self-assigning staff or admin roles.
- **Organisations & Tenant Management (`apps.organisations`)**:
  - Multi-tenant organisation model (`Organisation`).
  - Organisation memberships (`OrganisationMembership`) with granular roles (`OWNER`, `ADMIN`, `MEMBER`, `TECHNICIAN`, `ANALYST`).
  - Automatic `OWNER` role assignment to the creator.
  - Organisation-scoped access control preventing non-members and unprivileged members from viewing or altering tenant resources.
- **Shared Commons (`common`)**:
  - `BaseUUIDModel` providing consistent UUID primary keys and timestamps.
  - Custom RBAC permission classes (`IsMarketplaceAdmin`, `IsPlatformStaff`, `IsOrganisationMember`, `IsOrganisationAdminOrOwner`).
  - Normalized error response handler.
  - System health check endpoint (`/api/health/`).

---

## Technology Stack

- **Language**: Python 3.10+
- **Framework**: Django 5.1+
- **API Engine**: Django REST Framework (DRF) 3.15+
- **Authentication**: `djangorestframework-simplejwt` with token blacklisting
- **Database**: PostgreSQL 17 (production/Docker) & SQLite fallback for isolated zero-dependency unit tests
- **CORS**: `django-cors-headers` (configured for Next.js frontend on `http://localhost:3000`)
- **Containerization**: Docker & Docker Compose
- **Testing**: `pytest` and `pytest-django`

---

## Authentication Strategy & Architectural Decision

### Decision: Stateless JWT (JSON Web Tokens) with Refresh Token Blacklisting

1. **Decoupled Frontend Compatibility**:
   - The DriverXtra frontend is built on Next.js. Decoupled Single Page Applications and server-rendered Next.js edge runtimes require stateless, bearer-token-compatible authentication.
   - Traditional session-based authentication requires shared server session state, cookies, and stateful CSRF synchronizer tokens that create cross-origin friction when frontend and backend run on different subdomains or ports.
2. **Access Token & Refresh Token Flow**:
   - Short-lived **Access Tokens** (default: 60 minutes) are issued upon login and carried in the `Authorization: Bearer <token>` header.
   - Longer-lived **Refresh Tokens** (default: 7 days) allow seamless session renewal via `POST /api/v1/auth/token/refresh/` without prompting the user for credentials.
3. **Revocation & Logout (Blacklisting)**:
   - When a user logs out via `POST /api/v1/auth/logout/`, the refresh token is blacklisted in the database using `rest_framework_simplejwt.token_blacklist`.
   - Blacklisted tokens cannot be reused to obtain new access tokens, guaranteeing true session revocation.
4. **CSRF Protection**:
   - Pure Bearer token authentication in API headers is immune to browser-driven Cross-Site Request Forgery (CSRF) because browsers do not automatically attach custom `Authorization` headers to cross-site requests.
   - Django's `CsrfViewMiddleware` is retained for admin panel session access.

---

## Role-Based Access Control (RBAC)

### Platform Roles

| Role | Code | Scope | Self-Assignable at Registration |
|------|------|-------|---------------------------------|
| **Buyer / Customer** | `BUYER` | Consumer marketplace browsing, ordering, digital garage | Yes (Default) |
| **Seller / Dealer** | `SELLER` | Inventory listings, dealership vehicles, sales payouts | Yes |
| **Workshop / Service Provider** | `WORKSHOP` | Workshop bay management, work orders, service records | Yes |
| **Staff / Operations** | `STAFF` | Operational dispute handling, KYB reviews, internal queues | **NO (Forbidden)** |
| **Marketplace Admin** | `ADMIN` | Full administrative control, maker-checker, system config | **NO (Forbidden)** |

*Note: Role aliases (e.g., `CONSUMER`, `INVENTORY_MANAGER`, `WORKSHOP_MANAGER`, `MARKETPLACE_ADMIN`) are automatically normalized to canonical platform roles.*

### Organisation Roles

- **OWNER**: Full administrative control over the organisation, member invites, role changes, and tenant deletion. Automatically assigned to the user creating the organisation.
- **ADMIN**: Administrative control, ability to invite members and assign roles up to ADMIN.
- **MEMBER / TECHNICIAN / ANALYST**: Standard tenant operator roles with view/execution permissions scoped to their organisation.

---

## Project Structure

```text
backend/
├── config/
│   ├── __init__.py
│   ├── settings.py           # Core Django settings, JWT, DB, and CORS
│   ├── urls.py               # Root URL configuration
│   ├── asgi.py
│   └── wsgi.py
├── apps/
│   ├── __init__.py
│   ├── identity/
│   │   ├── __init__.py
│   │   ├── admin.py          # Django admin integration for User & Roles
│   │   ├── apps.py
│   │   ├── models.py         # User, UserRole, RoleChoices, StatusChoices
│   │   ├── serializers.py    # Registration, Login, Logout, Profile serializers
│   │   ├── urls.py           # Auth & User routing
│   │   ├── views.py          # Register, Login, Logout, Me API views
│   │   └── migrations/
│   └── organisations/
│       ├── __init__.py
│       ├── admin.py          # Organisation & Membership admin
│       ├── apps.py
│       ├── models.py         # Organisation, OrganisationMembership
│       ├── serializers.py    # Organisation & Membership serializers
│       ├── urls.py           # Organisation routing
│       ├── views.py          # Org CRUD & member management views
│       └── migrations/
├── common/
│   ├── __init__.py
│   ├── models.py             # BaseUUIDModel with created_at/updated_at
│   ├── permissions.py        # RBAC and tenant-scoped permission classes
│   ├── exceptions.py         # Unified error formatting handler
│   └── views.py              # GET /api/health/ endpoint
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Pytest fixtures for users, tokens, orgs
│   ├── test_health.py        # Healthcheck endpoint tests
│   ├── test_registration.py  # Validation, duplicate email, password hashing
│   ├── test_authentication.py# Login, invalid credentials, logout, refresh
│   ├── test_user_profile.py  # Profile retrieval & update field protection
│   ├── test_roles_and_permissions.py # Escalation prevention & multiple roles
│   └── test_organisations.py # Tenant creation, membership, ownership access
├── manage.py
├── requirements.txt
├── pytest.ini
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## Local Setup Guide

### 1. Prerequisites

- Python 3.10+
- PostgreSQL 14+ (or SQLite for development fallback)

### 2. Virtual Environment Setup

Navigate to the `backend/` directory:

```bash
cd backend
python -m venv .venv

# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# On Linux/macOS:
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Adjust the database credentials in `.env` if connecting to your local PostgreSQL instance:

```env
DB_ENGINE=django.db.backends.postgresql
DB_NAME=driverxtra_db
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432
```

*(Note: For instant local testing without configuring PostgreSQL, set `USE_SQLITE=True` in `.env`)*

### 5. Apply Migrations

```bash
python manage.py migrate
```

### 6. Create Superuser (Admin)

```bash
python manage.py createsuperuser
```

### 7. Run the Development Server

```bash
python manage.py runserver 0.0.0.0:8000
```

The API will be available at `http://localhost:8000/`.

---

## Docker & Containerized Setup

To launch the full backend stack with PostgreSQL 17 via Docker:

```bash
docker-compose up --build
```

Docker Compose spins up:
- `db`: PostgreSQL 17 Alpine database on port `5432`.
- `backend`: Django REST service on port `8000` with automatic migrations.

---

## API Endpoints Reference

### System & Health

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/health/` | Public | Returns system health, database status, and timestamp. |

### Authentication & Users

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/v1/auth/register/` | Public | Register new user. Blocks staff/admin role escalation. |
| `POST` | `/api/v1/auth/login/` | Public | Authenticates user; returns JWT access/refresh tokens. |
| `POST` | `/api/v1/auth/logout/` | Bearer | Revokes and blacklists the provided refresh token. |
| `POST` | `/api/v1/auth/token/refresh/` | Public | Exchanges a valid refresh token for a new access token. |
| `GET` | `/api/v1/users/me/` | Bearer | Retrieve authenticated user profile and roles. |
| `PATCH` | `/api/v1/users/me/` | Bearer | Update user profile (`first_name`, `last_name`, `phone_number`). |

### Organisations & Tenancy

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/v1/organisations/` | Bearer | List organisations the user is an active member of (Admins see all). |
| `POST` | `/api/v1/organisations/` | Bearer | Create a new organisation; caller automatically becomes `OWNER`. |
| `GET` | `/api/v1/organisations/{id}/` | Bearer | Retrieve organisation details. Enforces membership check. |
| `GET` | `/api/v1/organisations/{id}/members/` | Bearer | List members of the organisation. |
| `POST` | `/api/v1/organisations/{id}/members/` | Bearer | Add member to organisation. Requires `OWNER` or `ADMIN` role. |

---

## Automated Test Suite

The test suite covers 100% of the Phase 1 requirements:

- **Registration & Hashing**: Validates PBKDF2 hashing, required fields, and duplicate email prevention.
- **Login & Credentials**: Validates valid credentials, invalid passwords, nonexistent accounts, and suspended account blocks.
- **Tokens & Blacklist**: Validates JWT issuance, access token refresh, and refresh token revocation upon logout.
- **Profile & Permissions**: Validates authenticated profile retrieval and verifies that sensitive fields (`is_staff`, `is_superuser`, `roles`, `email`) cannot be modified via profile patch.
- **Role Assignment Restrictions**: Validates that public self-assignment of `ADMIN` or `STAFF` is blocked with HTTP 400.
- **Tenancy & Ownership**: Validates organisation creation, automatic owner assignment, membership filtering, cross-tenant 403 blocks, and non-admin member invite denial.

### Running Tests

Execute pytest from the `backend/` directory:

```bash
pytest
```

Output:
```text
============================= test session starts =============================
tests/test_authentication.py ......                                      [ 20%]
tests/test_health.py .                                                   [ 23%]
tests/test_organisations.py .........                                    [ 53%]
tests/test_registration.py .....                                         [ 70%]
tests/test_roles_and_permissions.py ......                               [ 86%]
tests/test_user_profile.py ....                                          [100%]

============================= 30 passed in 10.67s =============================
```
