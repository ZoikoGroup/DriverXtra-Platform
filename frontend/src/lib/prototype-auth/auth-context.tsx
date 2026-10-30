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
  const activeBackendRole = backendUser.active_role || (rawRoles[0] || "BUYER");

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

  if (activeBackendRole === "ADMIN" || backendUser.is_superuser) {
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
  } else if (activeBackendRole === "STAFF" || backendUser.is_staff) {
    role = "MARKETPLACE_ADMIN";
    roleLabel = backendUser.staff_role ? `${backendUser.staff_role.name}` : "Operations Staff Member";
    tenantType = "INTERNAL_OPS";
    permissions = [
      "ops:queue.view",
      "ops:maker_checker.approve",
      "policy:evaluate"
    ];
  } else if (activeBackendRole === "SELLER") {
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
  } else if (activeBackendRole === "WORKSHOP") {
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
  } else {
    role = "CONSUMER";
    roleLabel = "Consumer & Vehicle Owner";
    tenantType = "INDIVIDUAL";
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
    permissions: backendUser.permissions && backendUser.permissions.length > 0 ? backendUser.permissions : permissions,
    first_name: backendUser.first_name,
    last_name: backendUser.last_name,
    phone_number: backendUser.phone_number,
    status: backendUser.status,
    rawRoles: backendUser.roles,
    activeRole: activeBackendRole,
    has_mfa_enabled: backendUser.has_mfa_enabled,
    staff_role: backendUser.staff_role,
    is_staff: backendUser.is_staff,
    is_superuser: backendUser.is_superuser,
    organisations: backendUser.organisations,
    date_joined: backendUser.date_joined,
    created_at: backendUser.created_at,
  };
}

function parseJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".");
    if (parts.length < 2) return null;
    const base64Url = parts[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    let json: string;
    if (typeof window !== "undefined" && typeof window.atob === "function") {
      json = decodeURIComponent(
        window
          .atob(base64)
          .split("")
          .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
          .join("")
      );
    } else {
      json = Buffer.from(base64, "base64").toString("utf-8");
    }
    return JSON.parse(json);
  } catch {
    return null;
  }
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<PrototypeUser | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [mfaChallenge, setMfaChallenge] = useState<{ preAuthToken: string; email: string } | null>(null);

  const clearAuthError = useCallback(() => {
    setAuthError(null);
  }, []);

  const clearMfaChallenge = useCallback(() => {
    setMfaChallenge(null);
  }, []);

  // Restore authenticated session on mount from Django backend token
  const refreshProfile = useCallback(async () => {
    const accessToken = tokenStorage.getAccessToken();
    const refreshToken = tokenStorage.getRefreshToken();
    if (!accessToken && !refreshToken) {
      setUser(null);
      return;
    }

    try {
      setIsLoading(true);
      const profile = await api.users.getMe();
      const token = tokenStorage.getAccessToken();
      if (token) {
        const tokenClaims = parseJwtPayload(token);
        if (tokenClaims && typeof tokenClaims.active_role === "string") {
          profile.active_role = tokenClaims.active_role;
        }
      }
      const mappedUser = mapBackendUserToPrototypeUser(profile);
      setUser(mappedUser);
      setAuthError(null);
    } catch (err: unknown) {
      const statusCode = err instanceof ApiError ? err.code : undefined;
      const errorMessage = err instanceof Error ? err.message : "Profile refresh failed";

      console.warn("[Auth] Profile refresh failed:", {
        status: statusCode,
        message: errorMessage,
      });

      if (statusCode === 401) {
        tokenStorage.clearTokens();
        setUser(null);
        setAuthError("Session expired. Please log in again.");
      } else {
        setUser(null);
        setAuthError(errorMessage);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let mounted = true;

    const initSession = async () => {
      const accessToken = tokenStorage.getAccessToken();
      const refreshToken = tokenStorage.getRefreshToken();

      if (accessToken || refreshToken) {
        try {
          setIsLoading(true);
          const profile = await api.users.getMe();
          if (mounted) {
            const token = tokenStorage.getAccessToken();
            if (token) {
              const tokenClaims = parseJwtPayload(token);
              if (tokenClaims && typeof tokenClaims.active_role === "string") {
                profile.active_role = tokenClaims.active_role;
              }
            }
            setUser(mapBackendUserToPrototypeUser(profile));
            setAuthError(null);
          }
        } catch (err: unknown) {
          const statusCode = err instanceof ApiError ? err.code : undefined;
          const errorMessage = err instanceof Error ? err.message : "Session restoration failed";

          console.warn("[Auth] Session restoration failed:", {
            status: statusCode,
            message: errorMessage,
          });

          if (mounted) {
            tokenStorage.clearTokens();
            setUser(null);
            // On initial session check/restoration failure, do not display a blocking error
            // to unauthenticated users visiting the login or public landing page.
            setAuthError(null);
          }
        } finally {
          if (mounted) {
            setIsLoading(false);
          }
        }
      }

      if (mounted) {
        setIsInitialized(true);
      }
    };

    initSession();

    return () => {
      mounted = false;
    };
  }, []);

  const login = async (email: string, password?: string, code?: string): Promise<{ success: boolean; mfaRequired?: boolean }> => {
    setIsLoading(true);
    setAuthError(null);

    if (!password) {
      setIsLoading(false);
      setAuthError("Password is required for platform authentication.");
      return { success: false };
    }

    try {
      const response = await api.auth.login(email, password, code);
      if (response.mfa_required && response.pre_auth_token) {
        setMfaChallenge({ preAuthToken: response.pre_auth_token, email: response.email || email });
        setIsLoading(false);
        return { success: true, mfaRequired: true };
      }

      if (!response?.tokens?.access || !response?.tokens?.refresh) {
        throw new ApiError("Authentication failed: server did not return both access and refresh tokens.", 500);
      }
      const profile = response.user || await api.users.getMe();
      const mappedUser = mapBackendUserToPrototypeUser(profile);
      setUser(mappedUser);
      setMfaChallenge(null);
      setIsLoading(false);
      return { success: true, mfaRequired: false };
    } catch (err: unknown) {
      setIsLoading(false);
      const msg = err instanceof ApiError ? err.message : "Authentication failed. Please verify credentials.";
      setAuthError(msg);
      return { success: false };
    }
  };

  const verifyMfaLogin = async (code: string): Promise<boolean> => {
    if (!mfaChallenge) return false;
    setIsLoading(true);
    setAuthError(null);
    try {
      const response = await api.auth.verifyMfa(code, mfaChallenge.preAuthToken);
      const profile = response.user || await api.users.getMe();
      setUser(mapBackendUserToPrototypeUser(profile));
      setMfaChallenge(null);
      return true;
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Invalid MFA code. Please try again.";
      setAuthError(msg);
      return false;
    } finally {
      setIsLoading(false);
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
      setMfaChallenge(null);
      setIsLoading(false);
    }
  };

  const switchRole = async (targetRole: CanonicalRole | string): Promise<boolean> => {
    if (!user) return false;
    let backendRole = targetRole;
    if (targetRole === "MARKETPLACE_ADMIN") backendRole = user.is_superuser || user.rawRoles?.includes("ADMIN") ? "ADMIN" : "STAFF";
    else if (targetRole === "INVENTORY_MANAGER") backendRole = "SELLER";
    else if (targetRole === "WORKSHOP_MANAGER") backendRole = "WORKSHOP";
    else if (targetRole === "CONSUMER") backendRole = "BUYER";
    else if (targetRole === "FLEET_MANAGER") backendRole = "BUYER";

    setIsLoading(true);
    setAuthError(null);
    try {
      const switchRes = await api.auth.switchRole(backendRole);
      const profile = await api.users.getMe();
      if (switchRes?.active_role) {
        profile.active_role = switchRes.active_role;
      }
      setUser(mapBackendUserToPrototypeUser(profile));
      return true;
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Failed to switch role.";
      setAuthError(msg);
      return false;
    } finally {
      setIsLoading(false);
    }
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


  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isInitialized,
        isLoading,
        authError,
        mfaChallenge,
        clearMfaChallenge,
        clearAuthError,
        login,
        verifyMfaLogin,
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
