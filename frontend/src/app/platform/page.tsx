"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import { PrototypeUser } from "@/lib/prototype-auth/types";
import Sidebar from "@/components/platform/Sidebar";
import TopBar from "@/components/platform/TopBar";
import Phase1ProfileView from "@/components/platform/Phase1ProfileView";
import Phase1OrganisationsView from "@/components/platform/Phase1OrganisationsView";
import Phase2GarageView from "@/components/platform/Phase2GarageView";
import Phase2CatalogueView from "@/components/platform/Phase2CatalogueView";
import Phase2SellerOnboardingView from "@/components/platform/Phase2SellerOnboardingView";
import MarketplaceBrowseView from "@/components/platform/MarketplaceBrowseView";
import SellerInventoryView from "@/components/platform/SellerInventoryView";
import WorkshopLandingView from "@/components/platform/WorkshopLandingView";
import AdminMarketplaceReviewView from "@/components/platform/AdminMarketplaceReviewView";
import AdminStaffManagementView from "@/components/platform/AdminStaffManagementView";
import BuyerFavouritesView from "@/components/platform/BuyerFavouritesView";
import BuyerEnquiriesView from "@/components/platform/BuyerEnquiriesView";
import {
  Bell,
  X
} from "lucide-react";

function getDefaultTabForRole(user?: PrototypeUser | null): string {
  if (!user) return "marketplace_browse";
  const activeRole = user.activeRole || (user.rawRoles && user.rawRoles[0]) || "BUYER";
  if (activeRole === "ADMIN" || activeRole === "STAFF") {
    return "admin_marketplace_review";
  }
  const hasSeller = Boolean(user.rawRoles?.includes("SELLER") || activeRole === "SELLER");
  const hasWorkshop = Boolean(user.rawRoles?.includes("WORKSHOP") || activeRole === "WORKSHOP");
  if (hasWorkshop && !hasSeller) {
    return "workshop_landing";
  }
  if (hasSeller) {
    return "seller_inventory";
  }
  return "marketplace_browse";
}

export default function PlatformDashboardPage() {
  const router = useRouter();
  const { user, isAuthenticated, isInitialized } = useAuth();

  const [collapsed, setCollapsed] = useState(false);
  const [selectedTab, setSelectedTab] = useState<{ role: string; tab: string } | null>(null);
  const [notificationDrawerOpen, setNotificationDrawerOpen] = useState(false);

  // Protected route check
  useEffect(() => {
    if (isInitialized && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isInitialized, isAuthenticated, router]);

  const activeRole = user?.activeRole || (user?.rawRoles && user?.rawRoles[0]) || "BUYER";

  const currentTab = (selectedTab && selectedTab.role === activeRole)
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
      marketplace_browse: "Marketplace — Approved Vehicles & Spare Parts",
      favourites: "Saved Items — Vehicles & Spare Parts",
      my_enquiries: "My Enquiries — Vehicle Questions & Seller Replies",
      seller_inventory: "Seller Inventory — Vehicles & Spare Parts Submission",
      admin_marketplace_review: "Admin Moderation — Listing Review Queue",
      admin_staff_management: "Staff Administration & Access Control",
      profile: "User Profile (Phase 1 Identity & RBAC)",
      organisations: "Organisations & Teams (Phase 1 RBAC)",
      garage: "My Garage (Phase 2 Vehicle Master)",
      catalogue: "Vehicle & Parts Catalogue (Phase 2)",
      parts_fitment: "Vehicle Parts & Confirmed Fitment (Phase 2)",
      seller_onboarding: "Apply to sell / Apply as workshop (Seller Verification)",
      seller_reviews: "Seller Applications Compliance Queue (Phase 2)",
      workshop_landing: "Workshop Services — Workshop Partner Hub",
    };
    return map[tab] || "Dashboard Overview";
  };

  const isAdmin = activeRole === "ADMIN" || activeRole === "STAFF";
  const isSellerOrWorkshop = activeRole === "SELLER" || activeRole === "WORKSHOP" || isAdmin;

  return (
    <div className="min-h-screen bg-slate-100 flex flex-row">
      {/* Role-Governed Sidebar */}
      <Sidebar
        currentTab={currentTab}
        onTabChange={(tab) => setSelectedTab({ role: activeRole, tab })}
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
          {currentTab === "favourites" ? (
            <BuyerFavouritesView
              onNavigateToBrowse={() => setSelectedTab({ role: activeRole, tab: "marketplace_browse" })}
            />
          ) : currentTab === "my_enquiries" ? (
            <BuyerEnquiriesView
              onNavigateToBrowse={() => setSelectedTab({ role: activeRole, tab: "marketplace_browse" })}
            />
          ) : currentTab === "marketplace_browse" ? (
            <MarketplaceBrowseView />
          ) : currentTab === "workshop_landing" ? (
            <WorkshopLandingView />
          ) : currentTab === "seller_inventory" ? (
            isSellerOrWorkshop ? (
              <SellerInventoryView />
            ) : (
              <Phase2SellerOnboardingView initialTab="my_application" />
            )
          ) : currentTab === "admin_marketplace_review" ? (
            isAdmin ? (
              <AdminMarketplaceReviewView />
            ) : (
              <MarketplaceBrowseView />
            )
          ) : currentTab === "admin_staff_management" ? (
            isAdmin ? (
              <AdminStaffManagementView />
            ) : (
              <MarketplaceBrowseView />
            )
          ) : currentTab === "profile" ? (
            <Phase1ProfileView />
          ) : currentTab === "organisations" ? (
            <Phase1OrganisationsView />
          ) : currentTab === "garage" ? (
            <Phase2GarageView />
          ) : currentTab === "catalogue" || currentTab === "parts_fitment" ? (
            <Phase2CatalogueView />
          ) : currentTab === "seller_onboarding" ? (
            <Phase2SellerOnboardingView initialTab="my_application" />
          ) : currentTab === "seller_reviews" ? (
            isAdmin ? (
              <Phase2SellerOnboardingView initialTab="admin_queue" />
            ) : (
              <Phase2SellerOnboardingView initialTab="my_application" />
            )
          ) : (
            <MarketplaceBrowseView />
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
