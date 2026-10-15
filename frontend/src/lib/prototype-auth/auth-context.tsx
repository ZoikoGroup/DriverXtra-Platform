"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { PrototypeUser, CanonicalRole, AuthContextType } from "./types";

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

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<PrototypeUser | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);

  useEffect(() => {
    // Load existing prototype session if saved in localStorage
    const timer = setTimeout(() => {
      try {
        const savedUserJson = localStorage.getItem("driverxtra_prototype_user");
        if (savedUserJson) {
          setUser(JSON.parse(savedUserJson));
        }
      } catch {
        // ignore
      } finally {
        setIsInitialized(true);
      }
    }, 0);

    return () => clearTimeout(timer);
  }, []);

  const login = (email: string, role?: CanonicalRole): boolean => {
    const normalizedEmail = email.toLowerCase().trim();
    let matchedUser = PROTOTYPE_USERS.find(
      (u) => u.email.toLowerCase() === normalizedEmail
    );

    // Support admin aliases or partial matches (e.g. priya.patel, sarah.chen, admin)
    if (!matchedUser && (normalizedEmail.includes("admin") || normalizedEmail.includes("priya") || normalizedEmail.includes("sarah") || normalizedEmail.includes("ops"))) {
      matchedUser = PROTOTYPE_USERS.find((u) => u.role === "MARKETPLACE_ADMIN");
    }

    if (!matchedUser && role) {
      matchedUser = PROTOTYPE_USERS.find((u) => u.role === role);
    }

    if (!matchedUser) {
      // Default fallback to first prototype user if arbitrary email entered
      matchedUser = PROTOTYPE_USERS[0];
    }

    setUser(matchedUser);
    try {
      localStorage.setItem("driverxtra_prototype_user", JSON.stringify(matchedUser));
    } catch {
      // ignore
    }
    return true;
  };

  const logout = () => {
    setUser(null);
    try {
      localStorage.removeItem("driverxtra_prototype_user");
    } catch {
      // ignore
    }
  };

  const switchRole = (role: CanonicalRole) => {
    const targetUser = PROTOTYPE_USERS.find((u) => u.role === role) || PROTOTYPE_USERS[0];
    setUser(targetUser);
    try {
      localStorage.setItem("driverxtra_prototype_user", JSON.stringify(targetUser));
    } catch {
      // ignore
    }
  };

  // Avoid flash of unauthenticated before hydration
  if (!isInitialized) {
    return null;
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        login,
        logout,
        switchRole,
        availablePrototypeUsers: PROTOTYPE_USERS
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
