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
import AdminOverviewView from "@/components/platform/AdminOverviewView";
import AdminSellerManagementView from "@/components/platform/AdminSellerManagementView";
import AdminWorkshopManagementView from "@/components/platform/AdminWorkshopManagementView";
import AdminBuyerManagementView from "@/components/platform/AdminBuyerManagementView";
import AdminOrdersMonitoringView from "@/components/platform/AdminOrdersMonitoringView";
import AdminStaffManagementView from "@/components/platform/AdminStaffManagementView";
import AdminWorkshopOversightView from "@/components/platform/AdminWorkshopOversightView";
import AdminDisputesRefundsView from "@/components/platform/AdminDisputesRefundsView";
import AdminApprovalsView from "@/components/platform/AdminApprovalsView";
import SupportAgentLandingView from "@/components/platform/SupportAgentLandingView";
import CustomerSupportTicketsView from "@/components/platform/CustomerSupportTicketsView";
import CommercialAdminView from "@/components/platform/CommercialAdminView";
import BuyerFavouritesView from "@/components/platform/BuyerFavouritesView";
import BuyerEnquiriesView from "@/components/platform/BuyerEnquiriesView";
import BuyerOrdersView from "@/components/platform/BuyerOrdersView";
import SellerOrdersView from "@/components/platform/SellerOrdersView";
import NotificationDrawer, { useNotificationUnreadCount } from "@/components/platform/NotificationDrawer";
import { getDefaultTabForRole, isTabAllowedForRole, getTabLabel } from "@/lib/navigation";

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

  // Sync tab with URL search parameter if present
  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const tabParam = params.get("tab");
      if (tabParam) {
        queueMicrotask(() => {
          if (tabParam === "seller_disputes") {
            setSelectedTab({ role: activeRole, tab: "seller_orders", itemData: { type: "tab", id: "disputes" } });
          } else {
            setSelectedTab({ role: activeRole, tab: tabParam });
          }
        });
      }
    }
  }, [activeRole, router, user]);

  // Protected route check
  useEffect(() => {
    if (isInitialized && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isInitialized, isAuthenticated, router]);

  const candidateTab = (selectedTab && selectedTab.role === activeRole)
    ? selectedTab.tab
    : getDefaultTabForRole(activeRole, user);

  // Enforce role-based route protection: if currentTab is not allowed for activeRole, fall back to default
  const currentTab = isTabAllowedForRole(candidateTab, activeRole, user)
    ? candidateTab
    : getDefaultTabForRole(activeRole, user);

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

  const isPlatformAdmin = activeRole === "ADMIN";
  const isAdmin = activeRole === "ADMIN" || activeRole === "STAFF";
  const isSellerOrWorkshop = activeRole === "SELLER" || activeRole === "WORKSHOP";

  const userPerms = Array.isArray(user?.permissions) ? user.permissions : [];
  const hasPerm = (code: string) => isPlatformAdmin || userPerms.includes(code);
  const staffRoleCode = user?.staff_role?.code?.toUpperCase();

  const canAccessDisputes = Boolean(
    isPlatformAdmin ||
    hasPerm("dispute.manage") ||
    hasPerm("order.refund") ||
    staffRoleCode === "DISPUTE_MANAGER" ||
    staffRoleCode === "FINANCE_OFFICER"
  );

  const canAccessApprovals = Boolean(
    isPlatformAdmin ||
    hasPerm("finance.payout") ||
    staffRoleCode === "FINANCE_OFFICER"
  );

  const canAccessListingReview = Boolean(
    isPlatformAdmin ||
    hasPerm("listing.review") ||
    staffRoleCode === "VERIFICATION_OFFICER"
  );

  const canAccessSellerReview = Boolean(
    isPlatformAdmin ||
    hasPerm("seller.verify") ||
    staffRoleCode === "VERIFICATION_OFFICER"
  );

  const canAccessSupport = Boolean(
    isPlatformAdmin ||
    hasPerm("support.ticket.manage") ||
    staffRoleCode === "SUPPORT_AGENT"
  );

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
          {currentTab === "my_orders" || currentTab === "buyer_returns_refunds" ? (
            <BuyerOrdersView
              onNavigateToBrowse={() => setSelectedTab({ role: activeRole, tab: "marketplace_browse" })}
              initialOrderId={activeItemData?.type === "order" ? activeItemData.id : undefined}
              initialSection={currentTab === "buyer_returns_refunds" ? "returns" : undefined}
            />
          ) : currentTab === "seller_orders" || currentTab === "seller_disputes" ? (
            <SellerOrdersView
              initialOrderId={activeItemData?.type === "order" ? activeItemData.id : undefined}
              initialMainTab={
                currentTab === "seller_disputes" ||
                (activeItemData?.type === "tab" && activeItemData.id === "disputes")
                  ? "disputes"
                  : "orders"
              }
            />
          ) : currentTab === "admin_overview" ? (
            isPlatformAdmin ? (
              <AdminOverviewView onNavigateTab={(tab) => setSelectedTab({ role: activeRole, tab })} />
            ) : (
              <MarketplaceBrowseView />
            )
          ) : currentTab === "admin_sellers" ? (
            isPlatformAdmin ? (
              <AdminSellerManagementView />
            ) : (
              <MarketplaceBrowseView />
            )
          ) : currentTab === "admin_workshops" ? (
            isPlatformAdmin ? (
              <AdminWorkshopManagementView />
            ) : (
              <MarketplaceBrowseView />
            )
          ) : currentTab === "admin_buyers" ? (
            isPlatformAdmin ? (
              <AdminBuyerManagementView />
            ) : (
              <MarketplaceBrowseView />
            )
          ) : currentTab === "admin_orders_monitoring" ? (
            isPlatformAdmin ? (
              <AdminOrdersMonitoringView />
            ) : (
              <MarketplaceBrowseView />
            )
          ) : currentTab === "admin_disputes_refunds" ? (
            canAccessDisputes ? (
              <AdminDisputesRefundsView />
            ) : (
              <MarketplaceBrowseView />
            )
          ) : currentTab === "admin_approvals" ? (
            canAccessApprovals ? (
              <AdminApprovalsView />
            ) : (
              <MarketplaceBrowseView />
            )
          ) : currentTab === "support_overview" ? (
            canAccessSupport ? (
              <SupportAgentLandingView onNavigateTab={(tab) => setSelectedTab({ role: activeRole, tab })} />
            ) : (
              <MarketplaceBrowseView />
            )
          ) : currentTab === "my_tickets" ? (
            <CustomerSupportTicketsView />
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
          ) : currentTab === "workshop_settlements" ? (
            <WorkshopLandingView initialTab="settlements" />
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
            canAccessListingReview ? (
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
          ) : currentTab === "commercial_admin" ? (
            isAdmin ? (
              <CommercialAdminView />
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
            canAccessSellerReview ? (
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
