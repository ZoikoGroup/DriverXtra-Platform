// Canonical User and RBAC Types Grounded in Doc 04 (Identity, Organization & RBAC Architecture)
import { BackendOrganisationSummary, RegisterPayload } from "@/lib/api/client";

export type CanonicalRole =
  | "CONSUMER"             // Human vehicle owner / retail buyer (Backend BUYER)
  | "INVENTORY_MANAGER"    // Dealer / Seller inventory & listings (Backend SELLER)
  | "WORKSHOP_MANAGER"     // Workshop bay & work order management (Backend WORKSHOP)
  | "FLEET_MANAGER"        // Enterprise fleet operator
  | "MARKETPLACE_ADMIN"    // Internal operations & Maker-Checker governance (Backend ADMIN)
  | "DISPUTE_ANALYST"      // Case adjudication & remedies (Backend STAFF)
  | "FINANCE_OPS";         // Escrow & payout approvals (Backend STAFF)

export interface PrototypeUser {
  id: string;               // UUID from backend
  email: string;
  fullName: string;
  avatarUrl?: string;
  role: CanonicalRole;
  roleLabel: string;
  organizationId?: string;
  organizationName?: string;
  jurisdiction: string;     // e.g. "GB-ENG" as per Doc 18
  tenantType: "INDIVIDUAL" | "DEALER_GROUP" | "WORKSHOP" | "FLEET_OPERATOR" | "INTERNAL_OPS";
  permissions: string[];
  // Real backend fields from Phase 1 API
  first_name?: string;
  last_name?: string;
  phone_number?: string;
  status?: string;
  rawRoles?: string[];
  activeRole?: string;
  has_mfa_enabled?: boolean;
  staff_role?: { code: string; name: string; department?: string } | null;
  is_staff?: boolean;
  is_superuser?: boolean;
  organisations?: BackendOrganisationSummary[];
  created_at?: string;
  date_joined?: string;
}

export interface AuthContextType {
  user: PrototypeUser | null;
  isAuthenticated: boolean;
  isInitialized: boolean;
  isLoading: boolean;
  authError: string | null;
  mfaChallenge: { preAuthToken: string; email: string } | null;
  clearMfaChallenge: () => void;
  clearAuthError: () => void;
  login: (email: string, password?: string, code?: string) => Promise<{ success: boolean; mfaRequired?: boolean }>;
  verifyMfaLogin: (code: string) => Promise<boolean>;
  register: (payload: RegisterPayload) => Promise<{ success: boolean; error?: string }>;
  logout: () => Promise<void>;
  switchRole: (role: CanonicalRole | string) => Promise<boolean>;
  availablePrototypeUsers: PrototypeUser[];
  refreshProfile: () => Promise<void>;
  updateProfile: (data: { first_name?: string; last_name?: string; phone_number?: string }) => Promise<boolean>;
}
