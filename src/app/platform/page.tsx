"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import Sidebar from "@/components/platform/Sidebar";
import TopBar from "@/components/platform/TopBar";
import ConsumerDashboardView from "@/components/platform/ConsumerDashboardView";
import DealerDashboardView from "@/components/platform/DealerDashboardView";
import WorkshopDashboardView from "@/components/platform/WorkshopDashboardView";
import FleetDashboardView from "@/components/platform/FleetDashboardView";
import OperationsDashboardView from "@/components/platform/OperationsDashboardView";
import {
  Bell,
  X
} from "lucide-react";

function getDefaultTabForRole(role?: string): string {
  switch (role) {
    case "CONSUMER": return "garage";
    case "INVENTORY_MANAGER": return "inventory";
    case "WORKSHOP_MANAGER": return "work_orders";
    case "FLEET_MANAGER": return "fleet_portfolio";
    case "MARKETPLACE_ADMIN": return "maker_checker";
    default: return "garage";
  }
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
    : getDefaultTabForRole(user?.role);

  if (!isAuthenticated || !user) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-white text-xs">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin"></div>
          <span>Validating Prototype Authorization...</span>
        </div>
      </div>
    );
  }

  const getTabLabel = (tab: string) => {
    const map: Record<string, string> = {
      garage: "My Garage (Vehicle Master)",
      orders: "Orders & Escrow Holds",
      parts_fitment: "Guaranteed Fit Parts",
      service_bookings: "Workshop Bookings",
      disputes: "Disputes & Protection",
      inventory: "Vehicle Inventory",
      feeds: "DMS Ingestion Feeds",
      escrow_payouts: "Escrow & Settlements",
      leads: "Buyer Inquiries",
      team: "Dealership RBAC",
      work_orders: "Bay Work Orders",
      change_orders: "Change-Order Authorizer",
      service_writeback: "Service History Records",
      parts_requisitions: "Parts Procurement",
      fleet_portfolio: "Fleet Portfolio",
      maintenance_due: "Maintenance Due",
      drivers: "Driver Assignments",
      procurement: "Procurement & RFQs",
      maker_checker: "Maker-Checker Queue",
      trust_kyb: "Trust & KYB Clearance",
      disputes_admin: "Dispute Adjudication",
      jurisdictions: "Jurisdiction Packs",
      audit_stream: "Immutable Audit Log",
      default: "Dashboard Overview"
    };
    return map[tab] || "Dashboard";
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
          {user.role === "CONSUMER" && (
            <ConsumerDashboardView activeTab={currentTab} />
          )}

          {user.role === "INVENTORY_MANAGER" && (
            <DealerDashboardView activeTab={currentTab} />
          )}

          {user.role === "WORKSHOP_MANAGER" && (
            <WorkshopDashboardView activeTab={currentTab} />
          )}

          {user.role === "FLEET_MANAGER" && (
            <FleetDashboardView activeTab={currentTab} />
          )}

          {user.role === "MARKETPLACE_ADMIN" && (
            <OperationsDashboardView activeTab={currentTab} />
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
