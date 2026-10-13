// Canonical User and RBAC Types Grounded in Doc 04 (Identity, Organization & RBAC Architecture)

export type CanonicalRole =
  | "CONSUMER"             // Human vehicle owner / retail buyer
  | "INVENTORY_MANAGER"    // Dealer / Seller inventory & listings
  | "WORKSHOP_MANAGER"     // Workshop bay & work order management
  | "FLEET_MANAGER"        // Enterprise fleet operator
  | "MARKETPLACE_ADMIN"    // Internal operations & Maker-Checker governance
  | "DISPUTE_ANALYST"      // Case adjudication & remedies
  | "FINANCE_OPS";         // Escrow & payout approvals

export interface PrototypeUser {
  id: string;               // UUIDv7 as per Doc 03
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
}

export interface AuthContextType {
  user: PrototypeUser | null;
  isAuthenticated: boolean;
  login: (email: string, role?: CanonicalRole) => boolean;
  logout: () => void;
  switchRole: (role: CanonicalRole) => void;
  availablePrototypeUsers: PrototypeUser[];
}
