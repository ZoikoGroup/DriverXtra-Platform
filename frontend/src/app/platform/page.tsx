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
import BuyerWorkshopsView from "@/components/platform/BuyerWorkshopsView";
import AdminMarketplaceReviewView from "@/components/platform/AdminMarketplaceReviewView";
import AdminDisputesRefundsView from "@/components/platform/AdminDisputesRefundsView";
import AdminStaffManagementView from "@/components/platform/AdminStaffManagementView";
import AdminWorkshopOversightView from "@/components/platform/AdminWorkshopOversightView";
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

  const activeRole = user?.activeRole || (user?.rawRoles && user?.rawRoles[0]) || "BUYER";

  // Sync tab with URL search parameter if present (redirecting legacy dispute tabs to customer orders)
  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const tabParam = params.get("tab");
      if (tabParam) {
        if (tabParam === "seller_disputes" || tabParam === "admin_disputes_refunds") {
          setSelectedTab({ role: activeRole, tab: "seller_orders", itemData: { type: "tab", id: "disputes" } });
        } else {
          setSelectedTab({ role: activeRole, tab: tabParam });
        }
      }
    }
  }, [activeRole]);

  // Protected route check
  useEffect(() => {
    if (isInitialized && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isInitialized, isAuthenticated, router]);

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

  const isSellerOnlyTab = (tab: string) =>
    tab === "seller_orders" || tab === "seller_disputes" || tab === "admin_disputes_refunds";

  const getTabLabel = (tab: string) => {
    if (isAdmin && isSellerOnlyTab(tab)) {
      return "Admin Moderation — Listing Review Queue";
    }
    if (tab === "seller_disputes" || tab === "admin_disputes_refunds") {
      return "Customer Orders — Customer Disputes";
    }
    const map: Record<string, string> = {
      marketplace_browse: "Marketplace — Approved Vehicles & Spare Parts",
      my_orders: "My Orders — Order History & Status",
      seller_orders: "Customer Orders — Seller Order Fulfillment",
      favourites: "Saved Items — Vehicles & Spare Parts",
      my_enquiries: "My Enquiries — Vehicle Questions & Seller Replies",
      seller_inventory: "Seller Inventory — Vehicles & Spare Parts Submission",
      admin_marketplace_review: "Admin Moderation — Listing Review Queue",
      admin_staff_management: "Staff Administration & Access Control",
      admin_workshop_oversight: "Workshop Operations Oversight (Platform Administration)",
      profile: "User Profile & Account Settings",
      organisations: "Organisations & Teams",
      garage: "My Garage — Vehicle Management",
      catalogue: "Vehicle & Parts Catalogue",
      parts_fitment: "Vehicle Parts & Fitment Verification",
      seller_onboarding: "Apply to sell / Apply as workshop (Seller Verification)",
      seller_reviews: "Seller Applications Compliance Queue",
      workshop_landing: "Workshop Services — Workshop Partner Hub",
      workshops_browse: "Workshop Services & Bookings",
    };
    return map[tab] || "Dashboard Overview";
  };

  const isPlatformAdmin = activeRole === "ADMIN" || Boolean(user?.is_superuser || user?.rawRoles?.includes("ADMIN"));
  const isAdmin = activeRole === "ADMIN" || activeRole === "STAFF" || Boolean(user?.is_staff || user?.is_superuser);
  const isSellerOrWorkshop = activeRole === "SELLER" || activeRole === "WORKSHOP" || Boolean(user?.rawRoles?.includes("SELLER") || user?.rawRoles?.includes("WORKSHOP"));

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
          ) : currentTab === "seller_orders" || currentTab === "seller_disputes" || currentTab === "admin_disputes_refunds" ? (
            isAdmin ? (
              <AdminMarketplaceReviewView />
            ) : (
              <SellerOrdersView
                initialOrderId={activeItemData?.type === "order" ? activeItemData.id : undefined}
                initialMainTab={
                  currentTab === "seller_disputes" ||
                  currentTab === "admin_disputes_refunds" ||
                  (activeItemData?.type === "tab" && activeItemData.id === "disputes")
                    ? "disputes"
                    : "orders"
                }
              />
            )
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
          ) : currentTab === "workshops_browse" ? (
            <BuyerWorkshopsView
              onNavigateToGarage={() => setSelectedTab({ role: activeRole, tab: "garage" })}
            />
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
          ) : currentTab === "admin_workshop_oversight" ? (
            isAdmin ? (
              <AdminWorkshopOversightView />
            ) : (
              <MarketplaceBrowseView />
            )
          ) : currentTab === "admin_staff_management" ? (
            isPlatformAdmin ? (
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
