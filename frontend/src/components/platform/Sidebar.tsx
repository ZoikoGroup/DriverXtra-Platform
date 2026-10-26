"use client";

import React from "react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  Layers,
  Settings,
  FileCheck2,
  ShieldCheck,
  Building2,
  User,
  LogOut,
  ChevronRight,
  ShoppingBag,
  UserPlus,
  Wrench,
  Heart,
  MessageSquare,
  Package,
  Boxes,
} from "lucide-react";

interface SidebarProps {
  currentTab: string;
  onTabChange: (tabId: string) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export default function Sidebar({
  currentTab,
  onTabChange,
  collapsed,
  onToggleCollapse
}: SidebarProps) {
  const { user, logout } = useAuth();

  if (!user) return null;

  // Render navigation strictly according to active_role and granted roles
  const activeRole = user.activeRole || (user.rawRoles && user.rawRoles[0]) || "BUYER";
  const isAdmin = activeRole === "ADMIN" || activeRole === "STAFF";
  const hasSeller = Boolean(user.rawRoles?.includes("SELLER") || activeRole === "SELLER");
  const hasWorkshop = Boolean(user.rawRoles?.includes("WORKSHOP") || activeRole === "WORKSHOP");

  let roleNavItems: {
    id: string;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    badge?: string;
  }[] = [];

  if (isAdmin) {
    roleNavItems = [
      { id: "admin_marketplace_review", label: "Marketplace Moderation", icon: ShieldCheck, badge: "Review" },
      { id: "admin_staff_management", label: "Staff Invitations & Roles", icon: UserPlus, badge: "Admin" },
      { id: "seller_orders", label: "Customer Orders", icon: Boxes, badge: "Orders" },
      { id: "my_orders", label: "My Orders", icon: Package, badge: "Purchases" },
      { id: "marketplace_browse", label: "Marketplace (Browse)", icon: ShoppingBag, badge: "Browse" },
      { id: "favourites", label: "Saved Items", icon: Heart, badge: "Saved" },
      { id: "my_enquiries", label: "My Enquiries", icon: MessageSquare, badge: "Direct" },
      { id: "seller_reviews", label: "Seller Compliance Queue", icon: FileCheck2, badge: "Review" },
      { id: "catalogue", label: "Parts & Catalogue", icon: Settings, badge: "Catalogue" },
      { id: "organisations", label: "Organisations & Teams", icon: Building2, badge: "Management" },
      { id: "profile", label: "My Profile", icon: User },
    ];
  } else if (hasSeller && hasWorkshop) {
    // Both roles approved: access to both seller features and workshop hub
    roleNavItems = [
      { id: "seller_inventory", label: "My Inventory (Vehicles & Parts)", icon: Layers, badge: "Manage" },
      { id: "seller_orders", label: "Customer Orders", icon: Boxes, badge: "Orders" },
      { id: "workshop_landing", label: "Workshop Services", icon: Wrench, badge: "Workshop" },
      { id: "my_orders", label: "My Orders", icon: Package, badge: "Purchases" },
      { id: "marketplace_browse", label: "Marketplace (Browse)", icon: ShoppingBag, badge: "Browse" },
      { id: "favourites", label: "Saved Items", icon: Heart, badge: "Saved" },
      { id: "my_enquiries", label: "My Enquiries", icon: MessageSquare, badge: "Direct" },
      { id: "catalogue", label: "Parts & Catalogue", icon: Settings, badge: "Catalogue" },
      { id: "seller_onboarding", label: "Partner & Seller Status", icon: FileCheck2, badge: "Verified" },
      { id: "organisations", label: "Dealership & Workshop Teams", icon: Building2, badge: "Organisation" },
      { id: "garage", label: "Vehicle Garage", icon: Layers, badge: "Vehicles" },
      { id: "profile", label: "My Profile", icon: User },
    ];
  } else if (hasSeller) {
    // Seller-only: retain existing seller dashboard and features
    roleNavItems = [
      { id: "seller_inventory", label: "My Inventory (Vehicles & Parts)", icon: Layers, badge: "Manage" },
      { id: "seller_orders", label: "Customer Orders", icon: Boxes, badge: "Orders" },
      { id: "my_orders", label: "My Orders", icon: Package, badge: "Purchases" },
      { id: "marketplace_browse", label: "Marketplace (Browse)", icon: ShoppingBag, badge: "Browse" },
      { id: "favourites", label: "Saved Items", icon: Heart, badge: "Saved" },
      { id: "my_enquiries", label: "My Enquiries", icon: MessageSquare, badge: "Direct" },
      { id: "catalogue", label: "Parts & Catalogue", icon: Settings, badge: "Catalogue" },
      { id: "seller_onboarding", label: "Seller Verification Status", icon: FileCheck2, badge: "Verified" },
      { id: "organisations", label: "Dealership & Teams", icon: Building2, badge: "Organisation" },
      { id: "garage", label: "My Garage", icon: Layers, badge: "Vehicles" },
      { id: "profile", label: "My Profile", icon: User },
    ];
  } else if (hasWorkshop) {
    // Workshop-only: workshop-oriented navigation and landing view, not seller inventory
    roleNavItems = [
      { id: "workshop_landing", label: "Workshop Services", icon: Wrench, badge: "Workshop" },
      { id: "seller_orders", label: "Customer Orders", icon: Boxes, badge: "Orders" },
      { id: "my_orders", label: "My Orders", icon: Package, badge: "Purchases" },
      { id: "marketplace_browse", label: "Marketplace (Browse)", icon: ShoppingBag, badge: "Browse" },
      { id: "favourites", label: "Saved Items", icon: Heart, badge: "Saved" },
      { id: "my_enquiries", label: "My Enquiries", icon: MessageSquare, badge: "Direct" },
      { id: "catalogue", label: "Parts & Catalogue", icon: Settings, badge: "Fitment" },
      { id: "garage", label: "Vehicle Garage", icon: Layers, badge: "Vehicles" },
      { id: "seller_onboarding", label: "Partner Status", icon: FileCheck2, badge: "Workshop" },
      { id: "organisations", label: "Workshop & Teams", icon: Building2, badge: "Organisation" },
      { id: "profile", label: "My Profile", icon: User },
    ];
  } else {
    // Default: Buyer / Consumer (Search & Browse only)
    roleNavItems = [
      { id: "marketplace_browse", label: "Marketplace (Vehicles & Parts)", icon: ShoppingBag, badge: "Browse" },
      { id: "my_orders", label: "My Orders", icon: Package, badge: "Purchases" },
      { id: "favourites", label: "Saved Items", icon: Heart, badge: "Saved" },
      { id: "my_enquiries", label: "My Enquiries", icon: MessageSquare, badge: "Direct" },
      { id: "garage", label: "My Garage", icon: Layers, badge: "Vehicles" },
      { id: "catalogue", label: "Parts & Catalogue", icon: Settings, badge: "Fitment" },
      { id: "seller_onboarding", label: "Apply to sell / Apply as workshop", icon: FileCheck2, badge: "Apply" },
      { id: "profile", label: "My Profile", icon: User },
      { id: "organisations", label: "Organisations & Teams", icon: Building2 },
    ];
  }

  return (
    <aside
      className={`bg-slate-950 text-slate-300 border-r border-slate-800 flex flex-col justify-between transition-all duration-300 z-30 ${
        collapsed ? "w-20" : "w-64"
      }`}
    >
      {/* Top: Logo & Tenant Switcher */}
      <div>
        {/* Brand */}
        <div className="h-16 flex items-center justify-between px-4 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-amber-400 flex items-center justify-center font-black text-slate-950 text-lg shrink-0 shadow">
              DX
            </div>
            {!collapsed && (
              <div className="flex flex-col min-w-0">
                <span className="font-black text-base tracking-tight text-white flex items-center">
                  Driver<span className="text-amber-400">Xtra</span>
                </span>
                <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                  Enterprise Platform
                </span>
              </div>
            )}
          </div>
          <button
            onClick={onToggleCollapse}
            className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <ChevronRight className={`w-4 h-4 transition-transform duration-200 ${collapsed ? "" : "rotate-180"}`} />
          </button>
        </div>

        {/* Tenant Organization Context Card */}
        {!collapsed && (
          <div className="p-3 mx-3 my-3 bg-slate-900 border border-slate-800 rounded-xl">
            <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
              Active Context
            </div>
            <div className="text-xs font-bold text-white truncate mt-0.5">
              {user.organizationName || "Personal Garage"}
            </div>
            <div className="mt-1 flex items-center gap-1.5 text-[10px] text-amber-400 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
              <span>Active Role: <strong className="font-bold">{activeRole}</strong></span>
            </div>
          </div>
        )}

        {/* Role-Specific Navigation Links */}
        <div className="px-3 py-2 space-y-1">
          {!collapsed && (
            <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Navigation
            </div>
          )}

          {roleNavItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-bold transition-all ${
                  isActive
                    ? "bg-amber-400 text-slate-950 shadow-sm"
                    : "text-slate-300 hover:text-white hover:bg-slate-900"
                }`}
                title={collapsed ? item.label : undefined}
              >
                <Icon className={`w-4 h-4 shrink-0 ${isActive ? "text-slate-950" : "text-amber-400"}`} />
                {!collapsed && (
                  <div className="flex items-center justify-between w-full min-w-0">
                    <span className="truncate">{item.label}</span>
                    {item.badge && (
                      <span
                        className={`text-[9px] font-bold px-1.5 py-0.2 rounded ml-1 shrink-0 ${
                          isActive
                            ? "bg-slate-950 text-amber-300"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {item.badge}
                      </span>
                    )}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Bottom: User Card & Sign Out */}
      <div className="p-3 border-t border-slate-800">
        {!collapsed && (
          <div className="mb-2 p-2.5 rounded-xl bg-slate-900/60 border border-slate-800/80">
            <div className="text-xs font-bold text-white truncate">{user.fullName}</div>
            <div className="text-[10px] text-amber-400 font-semibold truncate mt-0.5">
              {activeRole} • {user.email}
            </div>
          </div>
        )}

        <button
          onClick={logout}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-xs font-bold text-slate-400 hover:text-rose-400 hover:bg-slate-900 transition-colors"
          title="Sign Out"
        >
          <LogOut className="w-4 h-4 shrink-0" />
          {!collapsed && <span>Sign Out</span>}
        </button>
      </div>
    </aside>
  );
}
