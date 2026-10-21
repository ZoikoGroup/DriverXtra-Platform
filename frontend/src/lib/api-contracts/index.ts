// Documented API Contracts Grounded in Docs 01 to 24
// Note: These interfaces define the blueprint for future backend integration.

export interface ApiContractDescriptor {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  path: string;
  sourceDoc: string;
  description: string;
}

export const DOCUMENTED_API_CONTRACTS: Record<string, ApiContractDescriptor> = {
  // Identity & RBAC (Doc 04)
  AUTHENTICATE_SESSION: {
    method: "POST",
    path: "/api/v1/sessions",
    sourceDoc: "Doc 04 §7",
    description: "Issue short-lived bearer session token with role/actor context."
  },
  GET_CURRENT_ACTOR: {
    method: "GET",
    path: "/api/v1/me",
    sourceDoc: "Doc 04 §8",
    description: "Return authenticated person, organization memberships, and active tenant."
  },
  VERIFY_EMAIL: {
    method: "POST",
    path: "/api/v1/auth/verify-email/",
    sourceDoc: "Doc 04 §12",
    description: "Verify email address ownership with raw token."
  },
  RESEND_VERIFICATION: {
    method: "POST",
    path: "/api/v1/auth/resend-verification/",
    sourceDoc: "Doc 04 §13",
    description: "Request a fresh email verification token (rate limited, enumeration safe)."
  },
  PASSWORD_RESET_REQUEST: {
    method: "POST",
    path: "/api/v1/auth/password-reset/request/",
    sourceDoc: "Doc 04 §14",
    description: "Request password reset link and token (enumeration safe)."
  },
  PASSWORD_RESET_CONFIRM: {
    method: "POST",
    path: "/api/v1/auth/password-reset/confirm/",
    sourceDoc: "Doc 04 §15",
    description: "Confirm password reset using single-use 1h token and invalidate active sessions."
  },
  SWITCH_ROLE: {
    method: "POST",
    path: "/api/v1/auth/switch-role/",
    sourceDoc: "Doc 04 §16",
    description: "Switch active platform role in JWT tokens and session context."
  },
  MFA_ENROL: {
    method: "POST",
    path: "/api/v1/auth/mfa/enrol/",
    sourceDoc: "Doc 04 §17",
    description: "Generate TOTP secret and QR code URI for staff/admin two-factor authentication."
  },
  MFA_VERIFY: {
    method: "POST",
    path: "/api/v1/auth/mfa/verify/",
    sourceDoc: "Doc 04 §18",
    description: "Verify TOTP code for MFA enrolment activation or login challenge completion."
  },
  STAFF_INVITE: {
    method: "POST",
    path: "/api/v1/admin/staff/invite/",
    sourceDoc: "Doc 04 §19",
    description: "Admin-only invitation for pending staff member with single-use set-password token."
  },
  STAFF_SET_PASSWORD: {
    method: "POST",
    path: "/api/v1/auth/staff/set-password/",
    sourceDoc: "Doc 04 §20",
    description: "Set initial password for invited staff member using single-use invite token."
  },

  // Vehicle Master & Garage (Doc 05)
  RESOLVE_VEHICLE_VIN: {
    method: "POST",
    path: "/api/v1/vehicle-instances/resolve",
    sourceDoc: "Doc 05 §8",
    description: "Decode registration plate or VIN against national vehicle databases."
  },
  GET_GARAGE_ENTRIES: {
    method: "GET",
    path: "/api/v1/garage-entries",
    sourceDoc: "Doc 05 §9",
    description: "Fetch vehicles associated with the current actor's digital garage."
  },
  LOG_ODOMETER_OBSERVATION: {
    method: "POST",
    path: "/api/v1/odometer-observations",
    sourceDoc: "Doc 05 §18",
    description: "Append timestamped verified mileage evidence to the vehicle passport."
  },

  // Catalog & Fitment (Doc 06)
  EVALUATE_FITMENT: {
    method: "POST",
    path: "/api/v1/fitment/evaluate",
    sourceDoc: "Doc 06 §14",
    description: "Validate compatibility between a vehicle instance and canonical product."
  },

  // Listings & Marketplace (Doc 07)
  SUBMIT_LISTING: {
    method: "POST",
    path: "/api/v1/listings/{id}/submit",
    sourceDoc: "Doc 07 §10",
    description: "Submit vehicle draft to moderation and publication pipeline."
  },
  RESERVE_INVENTORY: {
    method: "POST",
    path: "/api/v1/inventory/reservations",
    sourceDoc: "Doc 07 §25",
    description: "Place atomic reservation lock during checkout."
  },
  ADJUST_PART_STOCK: {
    method: "POST",
    path: "/api/v1/marketplace/parts/{id}/stock/",
    sourceDoc: "Doc 07 §26",
    description: "Record manual stock adjustment or inventory correction under row lock."
  },
  GET_PART_STOCK_HISTORY: {
    method: "GET",
    path: "/api/v1/marketplace/parts/{id}/stock-history/",
    sourceDoc: "Doc 07 §26",
    description: "Fetch immutable audit movement ledger for a spare part listing."
  },
  LIST_LOW_STOCK_PARTS: {
    method: "GET",
    path: "/api/v1/marketplace/parts/low-stock/",
    sourceDoc: "Doc 07 §26",
    description: "List seller spare part inventory at or below low stock threshold."
  },
  GET_CATALOGUE_PART_OFFERS: {
    method: "GET",
    path: "/api/v1/marketplace/browse/parts/catalogue/{catalogue_part_id}/offers/",
    sourceDoc: "Doc 07 §27",
    description: "Public competitive offers for a canonical catalogue part sorted by price ascending."
  },
  GET_PART_PRICE_HISTORY: {
    method: "GET",
    path: "/api/v1/marketplace/parts/{id}/price-history/",
    sourceDoc: "Doc 07 §28",
    description: "Fetch immutable audit ledger of price modifications for a spare part listing."
  },
  BROWSE_PARTS_FITMENT: {
    method: "GET",
    path: "/api/v1/marketplace/browse/parts/?sort={newest|price_asc|price_desc|relevance}&search={q}&condition={NEW,USED,...}&in_stock={bool}&fits_vehicle={id}&fits_only={bool}&include_facets={bool}&page={n}&page_size={1-50}",
    sourceDoc: "Doc 07 §29, §30",
    description: "Public browse and search of spare parts with deterministic sorting, multi-condition and in-stock filtering, vehicle fitment annotation, pre-pagination fits-only filtering, and aggregated facets."
  },

  // Commerce & Orders (Doc 09)
  PLACE_ORDER: {
    method: "POST",
    path: "/api/v1/orders:place",
    sourceDoc: "Doc 09 §18",
    description: "Orchestrate multi-seller order-split saga and create immutable snapshot."
  },

  // Payments & Ledger (Doc 10)
  CREATE_PAYMENT_INTENT: {
    method: "POST",
    path: "/api/v1/payment-intents",
    sourceDoc: "Doc 10 §8",
    description: "Create PSP payment authorization and journal double-entry escrow hold."
  },

  // Automotive Services (Doc 13)
  CREATE_CHANGE_ORDER: {
    method: "POST",
    path: "/api/v1/work-orders/{id}/change-orders",
    sourceDoc: "Doc 13 §22",
    description: "Technician submits additional work item requiring customer authorization."
  },
  SIGN_OFF_WORK_ORDER: {
    method: "POST",
    path: "/api/v1/work-orders/{id}/complete",
    sourceDoc: "Doc 13 §24",
    description: "Complete job, release escrow payout, and write service history to Vehicle Master."
  },

  // Operations & Governance (Doc 24)
  MAKER_CHECKER_APPROVE: {
    method: "POST",
    path: "/api/v1/ops/action-requests/{id}:approve",
    sourceDoc: "Doc 24 §15",
    description: "Secondary checker authorizes high-risk administrative action."
  }
};
