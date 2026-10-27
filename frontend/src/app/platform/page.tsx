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
import BuyerOrdersView from "@/components/platform/BuyerOrdersView";
import SellerOrdersView from "@/components/platform/SellerOrdersView";
import NotificationDrawer, { useNotificationUnreadCount } from "@/components/platform/NotificationDrawer";

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
  const [selectedTab, setSelectedTab] = useState<{
    role: string;
    tab: string;
    itemData?: { type: string; id: string; raw?: unknown };
  } | null>(null);
  const [notificationDrawerOpen, setNotificationDrawerOpen] = useState(false);
  const { unreadCount, refreshUnreadCount } = useNotificationUnreadCount(isAuthenticated);

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
      my_orders: "My Orders — Order History & Status",
      seller_orders: "Customer Orders — Seller Order Fulfillment",
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

  const activeItemData = selectedTab?.role === activeRole && selectedTab.tab === currentTab ? selectedTab.itemData : undefined;

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
          unreadNotificationCount={unreadCount}
          onNavigate={(targetTab, itemData) => {
            setSelectedTab({ role: activeRole, tab: targetTab, itemData });
          }}
        />

        <main className="flex-1 overflow-y-auto">
          {currentTab === "my_orders" ? (
            <BuyerOrdersView
              onNavigateToBrowse={() => setSelectedTab({ role: activeRole, tab: "marketplace_browse" })}
              initialOrderId={activeItemData?.type === "order" ? activeItemData.id : undefined}
            />
          ) : currentTab === "seller_orders" ? (
            <SellerOrdersView
              initialOrderId={activeItemData?.type === "order" ? activeItemData.id : undefined}
            />
          ) : currentTab === "favourites" ? (
            <BuyerFavouritesView
              onNavigateToBrowse={() => setSelectedTab({ role: activeRole, tab: "marketplace_browse" })}
            />
          ) : currentTab === "my_enquiries" ? (
            <BuyerEnquiriesView
              onNavigateToBrowse={() => setSelectedTab({ role: activeRole, tab: "marketplace_browse" })}
            />
          ) : currentTab === "marketplace_browse" ? (
            <MarketplaceBrowseView
              initialVehicleId={activeItemData?.type === "marketplace_vehicle" ? activeItemData.id : undefined}
              initialPartId={activeItemData?.type === "marketplace_part" ? activeItemData.id : undefined}
            />
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
              <AdminMarketplaceReviewView
                initialVehicleId={activeItemData?.type === "admin_vehicle" ? activeItemData.id : undefined}
                initialPartId={activeItemData?.type === "admin_part" ? activeItemData.id : undefined}
              />
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
            <Phase2GarageView
              initialVehicleId={activeItemData?.type === "garage_vehicle" ? activeItemData.id : undefined}
            />
          ) : currentTab === "catalogue" || currentTab === "parts_fitment" ? (
            <Phase2CatalogueView
              initialPartId={activeItemData?.type === "catalogue_part" ? activeItemData.id : undefined}
            />
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

      {/* Notification Drawer: live data from /api/v1/notifications/ */}
      <NotificationDrawer
        open={notificationDrawerOpen}
        onClose={() => setNotificationDrawerOpen(false)}
        onUnreadCountChange={refreshUnreadCount}
        onNavigateTab={(tab) => setSelectedTab({ role: activeRole, tab })}
      />
    </div>
  );
}
