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
