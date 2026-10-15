"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { PrototypeUser, CanonicalRole, AuthContextType } from "./types";
import { api, tokenStorage, ApiError, BackendUserProfile, RegisterPayload } from "@/lib/api/client";

export const PROTOTYPE_USERS: PrototypeUser[] = [
  {
    id: "usr_01j7x9p2k0001",
    email: "mark.harrison@example.co.uk",
    fullName: "Mark Harrison",
    role: "CONSUMER",
    roleLabel: "Consumer & Vehicle Owner",
    organizationId: "org_personal_001",
    organizationName: "Personal Garage",
    jurisdiction: "GB-ENG",
    tenantType: "INDIVIDUAL",
    permissions: [
      "garage:view",
      "garage:manage",
      "order:create",
      "order:view",
      "booking:create",
      "dispute:create"
    ]
  },
  {
    id: "usr_01j7x9p2k0002",
    email: "elena.rostova@apexautogroup.co.uk",
    fullName: "Elena Rostova",
    role: "INVENTORY_MANAGER",
    roleLabel: "Dealer Principal / Inventory Manager",
    organizationId: "org_dealer_0182",
    organizationName: "Apex Automotive Group UK",
    jurisdiction: "GB-ENG",
    tenantType: "DEALER_GROUP",
    permissions: [
      "listing:create",
      "listing:update",
      "listing:publish",
      "inventory:manage",
      "feed:sync",
      "payout:view",
      "payout:request"
    ]
  },
  {
    id: "usr_01j7x9p2k0003",
    email: "david.kowalski@apexbavarian.co.uk",
    fullName: "David Kowalski",
    role: "WORKSHOP_MANAGER",
    roleLabel: "Workshop Bay Manager",
    organizationId: "org_wksh_0419",
    organizationName: "Apex Bavarian Workshop Bay",
    jurisdiction: "GB-ENG",
    tenantType: "WORKSHOP",
    permissions: [
      "workorder:view",
      "workorder:update",
      "changeorder:create",
      "servicerecord:write",
      "capacity:manage"
    ]
  },
  {
    id: "usr_01j7x9p2k0004",
    email: "marcus.vance@nationalfreight.co.uk",
    fullName: "Marcus Vance",
    role: "FLEET_MANAGER",
    roleLabel: "Enterprise Fleet Director",
    organizationId: "org_fleet_0982",
    organizationName: "National Freight & Logistics Ltd",
    jurisdiction: "GB-ENG",
    tenantType: "FLEET_OPERATOR",
    permissions: [
      "fleet:view",
      "fleet:manage",
      "requisition:create",
      "rfq:manage",
      "driver:assign"
    ]
  },
  {
    id: "usr_01j7x9p2k0005",
    email: "priya.patel@driverxtra.internal",
    fullName: "Priya Patel",
    role: "MARKETPLACE_ADMIN",
    roleLabel: "Marketplace Administrator (Operations Lead)",
    organizationId: "org_driverxtra_ops",
    organizationName: "DriverXtra Global Operations Control",
    jurisdiction: "GB-GLOBAL",
    tenantType: "INTERNAL_OPS",
    permissions: [
      "ops:queue.view",
      "ops:maker_checker.approve",
      "dispute:adjudicate",
      "trust:kyb_review",
      "policy:evaluate"
    ]
  }
];

export function mapBackendUserToPrototypeUser(backendUser: BackendUserProfile): PrototypeUser {
  const rawRoles = backendUser.roles || [];
  let role: CanonicalRole = "CONSUMER";
  let roleLabel = "Consumer & Vehicle Owner";
  let tenantType: PrototypeUser["tenantType"] = "INDIVIDUAL";
  let permissions: string[] = [
    "garage:view",
    "garage:manage",
    "order:create",
    "order:view",
    "booking:create",
    "dispute:create"
  ];

  // Strictly enforce least privilege role mapping based on inspected backend roles
  if (backendUser.is_superuser || rawRoles.includes("ADMIN")) {
    role = "MARKETPLACE_ADMIN";
    roleLabel = "Marketplace Administrator (Operations Lead)";
    tenantType = "INTERNAL_OPS";
    permissions = [
      "ops:queue.view",
      "ops:maker_checker.approve",
      "dispute:adjudicate",
      "trust:kyb_review",
      "policy:evaluate"
    ];
  } else if (rawRoles.includes("SELLER")) {
    role = "INVENTORY_MANAGER";
    roleLabel = "Dealer Principal / Inventory Manager";
    tenantType = "DEALER_GROUP";
    permissions = [
      "listing:create",
      "listing:update",
      "listing:publish",
      "inventory:manage",
      "feed:sync",
      "payout:view",
      "payout:request"
    ];
  } else if (rawRoles.includes("WORKSHOP")) {
    role = "WORKSHOP_MANAGER";
    roleLabel = "Workshop Bay Manager";
    tenantType = "WORKSHOP";
    permissions = [
      "workorder:view",
      "workorder:update",
      "changeorder:create",
      "servicerecord:write",
      "capacity:manage"
    ];
  } else if (backendUser.is_staff || rawRoles.includes("STAFF")) {
    role = "MARKETPLACE_ADMIN";
    roleLabel = "Operations Staff Member";
    tenantType = "INTERNAL_OPS";
    permissions = [
      "ops:queue.view",
      "ops:maker_checker.approve",
      "policy:evaluate"
    ];
  } else if (rawRoles.includes("BUYER")) {
    role = "CONSUMER";
    roleLabel = "Consumer & Vehicle Owner";
    tenantType = "INDIVIDUAL";
    permissions = [
      "garage:view",
      "garage:manage",
      "order:create",
      "order:view",
      "booking:create",
      "dispute:create"
    ];
  }

  // Active organisation context from real backend data
  const primaryOrg = backendUser.organisations && backendUser.organisations[0];
  const orgName = primaryOrg ? primaryOrg.organisation_name : (tenantType === "INDIVIDUAL" ? "Personal Garage" : "DriverXtra Platform");
  const orgId = primaryOrg ? primaryOrg.organisation_id : undefined;

  return {
    id: String(backendUser.id),
    email: backendUser.email,
    fullName: backendUser.full_name || `${backendUser.first_name || ""} ${backendUser.last_name || ""}`.trim() || backendUser.email,
    role,
    roleLabel,
    organizationId: orgId,
    organizationName: orgName,
    jurisdiction: "GB-ENG",
    tenantType,
    permissions,
    first_name: backendUser.first_name,
    last_name: backendUser.last_name,
    phone_number: backendUser.phone_number,
    status: backendUser.status,
    rawRoles: backendUser.roles,
    is_staff: backendUser.is_staff,
    is_superuser: backendUser.is_superuser,
    organisations: backendUser.organisations,
    date_joined: backendUser.date_joined,
    created_at: backendUser.created_at,
  };
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<PrototypeUser | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  const clearAuthError = useCallback(() => {
    setAuthError(null);
  }, []);

  // Restore authenticated session on mount from Django backend token
  const refreshProfile = useCallback(async () => {
    const token = tokenStorage.getAccessToken();
    if (!token) {
      setUser(null);
      return;
    }

    try {
      setIsLoading(true);
      const profile = await api.users.getMe();
      const mappedUser = mapBackendUserToPrototypeUser(profile);
      setUser(mappedUser);
      setAuthError(null);
    } catch {
      tokenStorage.clearTokens();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const initSession = async () => {
      const token = tokenStorage.getAccessToken();
      if (token) {
        try {
          const profile = await api.users.getMe();
          setUser(mapBackendUserToPrototypeUser(profile));
        } catch {
          tokenStorage.clearTokens();
          setUser(null);
        }
      }
      setIsInitialized(true);
    };

    initSession();
  }, []);

  const login = async (email: string, password?: string): Promise<boolean> => {
    setIsLoading(true);
    setAuthError(null);

    // Require password for authentication and disallow prototype fallback for login attempts
    if (!password) {
      setIsLoading(false);
      setAuthError("Password is required for platform authentication.");
      return false;
    }

    try {
      const response = await api.auth.login(email, password);
      if (!response?.tokens?.access || !response?.tokens?.refresh) {
        throw new ApiError("Authentication failed: server did not return both access and refresh tokens.", 500);
      }
      const mappedUser = mapBackendUserToPrototypeUser(response.user);
      setUser(mappedUser);
      setIsLoading(false);
      return true;
    } catch (err: unknown) {
      setIsLoading(false);
      const msg = err instanceof ApiError ? err.message : "Authentication failed. Please verify credentials.";
      setAuthError(msg);
      return false;
    }
  };

  const register = async (payload: RegisterPayload): Promise<{ success: boolean; error?: string }> => {
    setIsLoading(true);
    setAuthError(null);
    try {
      await api.auth.register(payload);
      setIsLoading(false);
      return { success: true };
    } catch (err: unknown) {
      setIsLoading(false);
      const msg = err instanceof ApiError ? err.message : "Registration failed. Please check form inputs.";
      setAuthError(msg);
      return { success: false, error: msg };
    }
  };

  const logout = async (): Promise<void> => {
    setIsLoading(true);
    try {
      await api.auth.logout();
    } finally {
      tokenStorage.clearTokens();
      setUser(null);
      setIsLoading(false);
    }
  };

  const switchRole = (role: CanonicalRole) => {
    if (!user) return;
    // When real user is authenticated, keep backend fields and adjust view role
    const updatedUser: PrototypeUser = {
      ...user,
      role,
      roleLabel: role === "MARKETPLACE_ADMIN" ? "Marketplace Administrator" :
                 role === "INVENTORY_MANAGER" ? "Dealer Principal" :
                 role === "WORKSHOP_MANAGER" ? "Workshop Bay Manager" :
                 role === "FLEET_MANAGER" ? "Fleet Manager" : "Consumer & Vehicle Owner"
    };
    setUser(updatedUser);
  };

  const updateProfile = async (data: { first_name?: string; last_name?: string; phone_number?: string }): Promise<boolean> => {
    try {
      setIsLoading(true);
      const updatedProfile = await api.users.updateMe(data);
      const mappedUser = mapBackendUserToPrototypeUser(updatedProfile);
      setUser(mappedUser);
      setIsLoading(false);
      return true;
    } catch (err: unknown) {
      setIsLoading(false);
      const msg = err instanceof ApiError ? err.message : "Failed to update profile.";
      setAuthError(msg);
      return false;
    }
  };

  // Avoid flash before hydration/token inspection
  if (!isInitialized) {
    return null;
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        authError,
        clearAuthError,
        login,
        register,
        logout,
        switchRole,
        availablePrototypeUsers: PROTOTYPE_USERS,
        refreshProfile,
        updateProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
