"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import Sidebar from "@/components/platform/Sidebar";
import TopBar from "@/components/platform/TopBar";
import Phase1ProfileView from "@/components/platform/Phase1ProfileView";
import Phase1OrganisationsView from "@/components/platform/Phase1OrganisationsView";
import Phase2GarageView from "@/components/platform/Phase2GarageView";
import Phase2CatalogueView from "@/components/platform/Phase2CatalogueView";
import Phase2SellerOnboardingView from "@/components/platform/Phase2SellerOnboardingView";
import {
  Bell,
  X
} from "lucide-react";

function getDefaultTabForRole(user?: { is_superuser?: boolean; is_staff?: boolean; role?: string; rawRoles?: string[] } | null): string {
  if (!user) return "garage";
  const isAdmin = Boolean(
    user.is_superuser ||
    user.is_staff ||
    user.role === "MARKETPLACE_ADMIN" ||
    user.rawRoles?.includes("ADMIN") ||
    user.rawRoles?.includes("STAFF")
  );
  if (isAdmin) return "seller_reviews";
  if (user.role === "INVENTORY_MANAGER" || user.rawRoles?.includes("SELLER")) return "catalogue";
  if (user.role === "WORKSHOP_MANAGER" || user.rawRoles?.includes("WORKSHOP")) return "catalogue";
  return "garage";
}

export default function PlatformDashboardPage() {
  const router = useRouter();
  const { user, isAuthenticated } = useAuth();

  const [collapsed, setCollapsed] = useState(false);
  const [selectedTab, setSelectedTab] = useState<{ role: string; tab: string } | null>(null);
  const [notificationDrawerOpen, setNotificationDrawerOpen] = useState(false);

  // Protected route check
  useEffect(() => {
    if (!isAuthenticated) {
      router.push("/login");
    }
  }, [isAuthenticated, router]);

  const currentTab = (selectedTab && selectedTab.role === user?.role)
    ? selectedTab.tab
    : getDefaultTabForRole(user);

  if (!isAuthenticated || !user) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-white text-xs">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin"></div>
          <span>Validating Authorization...</span>
        </div>
      </div>
    );
  }

  const getTabLabel = (tab: string) => {
    const map: Record<string, string> = {
      profile: "User Profile (Phase 1 Identity & RBAC)",
      organisations: "Organisations & Teams (Phase 1 RBAC)",
      garage: "My Garage (Phase 2 Vehicle Master)",
      catalogue: "Vehicle & Parts Catalogue (Phase 2)",
      parts_fitment: "Guaranteed Fit Parts & Catalogue (Phase 2)",
      seller_onboarding: "Seller Onboarding & Verification (Phase 2)",
      seller_reviews: "Seller Applications Compliance Queue (Phase 2)",
    };
    return map[tab] || "Dashboard Overview";
  };

  return (
    <div className="min-h-screen bg-slate-100 flex flex-row">
      {/* Role-Governed Sidebar */}
      <Sidebar
        currentTab={currentTab}
        onTabChange={(tab) => setSelectedTab({ role: user.role, tab })}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed(!collapsed)}
      />

      {/* Main Body */}
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar
          currentTabLabel={getTabLabel(currentTab)}
          onOpenNotifications={() => setNotificationDrawerOpen(true)}
        />

        <main className="flex-1 overflow-y-auto">
          {currentTab === "profile" ? (
            <Phase1ProfileView />
          ) : currentTab === "organisations" ? (
            <Phase1OrganisationsView />
          ) : currentTab === "garage" ? (
            <Phase2GarageView />
          ) : currentTab === "catalogue" || currentTab === "parts_fitment" ? (
            <Phase2CatalogueView />
          ) : currentTab === "seller_onboarding" || currentTab === "seller_reviews" ? (
            <Phase2SellerOnboardingView key={currentTab} initialTab={currentTab === "seller_reviews" ? "admin_queue" : "my_application"} />
          ) : (
            <Phase2GarageView />
          )}
        </main>
      </div>

      {/* Notification Drawer (Doc 19) */}
      {notificationDrawerOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex justify-end">
          <div className="bg-white w-full max-w-sm h-full p-6 shadow-2xl flex flex-col justify-between border-l border-slate-200">
            <div>
              <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <Bell className="w-4 h-4 text-amber-500" />
                  <h4 className="text-sm font-black text-slate-950">
                    Notifications & Telemetry (Doc 19)
                  </h4>
                </div>
                <button
                  onClick={() => setNotificationDrawerOpen(false)}
                  className="text-slate-400 hover:text-slate-600"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-3 mt-4 text-xs">
                <div className="p-3 bg-amber-50 rounded-xl border border-amber-200">
                  <div className="flex items-center justify-between font-bold text-amber-950">
                    <span>Escrow Hold Confirmed</span>
                    <span className="text-[10px] text-amber-700">12m ago</span>
                  </div>
                  <p className="text-slate-600 mt-1">
                    Deposit of £500.00 secured in banking custody for Order #DX-ORD-2026-98421.
                  </p>
                </div>

                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                  <div className="flex items-center justify-between font-bold text-slate-900">
                    <span>Work Order Sign-Off</span>
                    <span className="text-[10px] text-slate-400">1h ago</span>
                  </div>
                  <p className="text-slate-600 mt-1">
                    Apex Bavarian workshop logged major service to 2021 BMW 330i passport.
                  </p>
                </div>

                <div className="p-3 bg-emerald-50 rounded-xl border border-emerald-200">
                  <div className="flex items-center justify-between font-bold text-emerald-950">
                    <span>Guaranteed Fitment Alert</span>
                    <span className="text-[10px] text-emerald-700">3h ago</span>
                  </div>
                  <p className="text-emerald-800 mt-1">
                    4 new OEM-compatible brake components indexed for your Garage vehicle.
                  </p>
                </div>
              </div>
            </div>

            <button
              onClick={() => setNotificationDrawerOpen(false)}
              className="w-full h-10 bg-slate-950 text-white text-xs font-bold rounded-xl"
            >
              Close Notifications
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
