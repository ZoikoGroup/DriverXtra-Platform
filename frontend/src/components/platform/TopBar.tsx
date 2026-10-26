"use client";

import React, { useState } from "react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import { useCart } from "@/context/CartContext";
import {
  Search,
  Bell,
  ChevronDown,
  CheckCircle2,
  ShieldCheck,
  RefreshCw,
  ShoppingCart,
} from "lucide-react";

import GlobalSearch from "./GlobalSearch";
import CartDrawer from "./CartDrawer";

interface TopBarProps {
  currentTabLabel: string;
  onOpenNotifications: () => void;
  unreadNotificationCount?: number;
  onNavigate?: (tab: string, itemData?: { type: string; id: string; raw?: unknown }) => void;
}

export default function TopBar({
  currentTabLabel,
  onOpenNotifications,
  unreadNotificationCount = 0,
  onNavigate,
}: TopBarProps) {
  const { user, switchRole, isLoading } = useAuth();
  const { totalUnits, isCartOpen, openCart, closeCart } = useCart();
  const [roleDropdownOpen, setRoleDropdownOpen] = useState(false);
  const [switchingRole, setSwitchingRole] = useState<string | null>(null);
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false);

  if (!user) return null;

  // Determine selectable roles based on user's granted roles
  const heldRoles: string[] = [];
  if (user.rawRoles && user.rawRoles.length > 0) {
    user.rawRoles.forEach((r) => {
      if (!heldRoles.includes(r)) heldRoles.push(r);
    });
  } else if (user.activeRole) {
    heldRoles.push(user.activeRole);
  }

  // Superuser / Admin has access to ADMIN and STAFF
  if (user.is_superuser || user.is_staff) {
    if (!heldRoles.includes("ADMIN")) heldRoles.push("ADMIN");
    if (!heldRoles.includes("STAFF")) heldRoles.push("STAFF");
  }

  // Ensure BUYER is always available
  if (!heldRoles.includes("BUYER")) {
    heldRoles.push("BUYER");
  }

  const activeRole = user.activeRole || (user.rawRoles && user.rawRoles[0]) || "BUYER";

  const getRoleDisplayName = (r: string) => {
    switch (r) {
      case "ADMIN":
        return "Marketplace Admin";
      case "STAFF":
        return user.staff_role ? `Staff (${user.staff_role.name})` : "Operations Staff";
      case "SELLER":
        return "Verified Seller";
      case "WORKSHOP":
        return "Workshop Partner";
      case "BUYER":
      default:
        return "Vehicle Owner / Buyer";
    }
  };

  const handleRoleSelect = async (targetRole: string) => {
    if (targetRole === activeRole) {
      setRoleDropdownOpen(false);
      return;
    }
    setSwitchingRole(targetRole);
    await switchRole(targetRole);
    setSwitchingRole(null);
    setRoleDropdownOpen(false);
  };

  return (
    <>
      <header className="h-16 bg-white border-b border-slate-200 px-4 sm:px-6 flex items-center justify-between gap-3 sm:gap-4 sticky top-0 z-20">
        {/* Left: Breadcrumbs & Current Module */}
        <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1 md:flex-initial">
          <nav aria-label="Breadcrumb" className="flex items-center gap-1 sm:gap-1.5 text-xs text-slate-500 font-semibold min-w-0">
            <span className="shrink-0 text-slate-400 hover:text-slate-600 transition-colors">Platform</span>
            <span className="shrink-0 text-slate-300">/</span>
            <span
              className="text-slate-700 font-bold truncate max-w-[80px] sm:max-w-[120px] md:max-w-[150px] lg:max-w-[200px] shrink-0"
              title={user.organizationName}
            >
              {user.organizationName}
            </span>
            <span className="shrink-0 text-slate-300">/</span>
            <span
              className="text-amber-600 font-bold whitespace-nowrap overflow-visible"
              title={currentTabLabel}
            >
              {currentTabLabel}
            </span>
          </nav>
        </div>

        {/* Center: Functional Global Search (desktop/tablet) */}
        <div className="hidden md:block w-64 lg:w-80 xl:w-96 relative shrink-0">
          <GlobalSearch onNavigate={onNavigate} />
        </div>

        {/* Right: Controls & Role Switcher */}
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          {/* Mobile Search Toggle Button */}
          <button
            onClick={() => setMobileSearchOpen(!mobileSearchOpen)}
            className="md:hidden w-9 h-9 rounded-xl border border-slate-200 hover:bg-slate-100 flex items-center justify-center text-slate-700 transition-colors"
            title="Search records by VIN, Order #, or Part MPN"
            aria-label="Toggle search"
          >
            <Search className="w-4 h-4 text-slate-600" />
          </button>

          {/* Real Backend Role Switcher */}
          <div className="relative">
            <button
              onClick={() => setRoleDropdownOpen(!roleDropdownOpen)}
              disabled={isLoading || Boolean(switchingRole)}
              className="flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition-all shadow-sm disabled:opacity-60"
            >
              <span className="text-amber-400 text-[10px] font-black uppercase hidden sm:inline">Active Role:</span>
              <span className="text-amber-400 text-[10px] font-black uppercase sm:hidden">Role:</span>
              <span>{activeRole}</span>
              {switchingRole ? (
                <RefreshCw className="w-3.5 h-3.5 text-amber-400 animate-spin" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
              )}
            </button>

            {roleDropdownOpen && (
              <div className="absolute right-0 mt-2 w-72 bg-white rounded-2xl shadow-2xl border border-slate-200 p-2 z-50 animate-in fade-in slide-in-from-top-2 duration-150">
                <div className="p-2 border-b border-slate-100 flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    Switch Active Role (JWT Claim)
                  </span>
                  <ShieldCheck className="w-3.5 h-3.5 text-amber-500" />
                </div>
                <div className="space-y-1 mt-1">
                  {heldRoles.map((r) => {
                    const isCurrent = r === activeRole;
                    const isPending = switchingRole === r;
                    return (
                      <button
                        key={r}
                        onClick={() => handleRoleSelect(r)}
                        disabled={Boolean(switchingRole)}
                        className={`w-full text-left p-2.5 rounded-xl text-xs flex items-center justify-between transition-colors ${
                          isCurrent
                            ? "bg-amber-50 text-amber-950 font-bold border border-amber-200"
                            : "hover:bg-slate-50 text-slate-700 font-medium"
                        }`}
                      >
                        <div>
                          <div className="font-bold flex items-center gap-1.5">
                            <span>{r}</span>
                            {isCurrent && (
                              <span className="text-[9px] bg-amber-200 text-amber-900 px-1.5 py-0.2 rounded font-black">
                                ACTIVE
                              </span>
                            )}
                          </div>
                          <div className="text-[10px] text-slate-500 mt-0.5">
                            {getRoleDisplayName(r)}
                          </div>
                        </div>
                        {isCurrent ? (
                          <CheckCircle2 className="w-4 h-4 text-amber-600 shrink-0" />
                        ) : isPending ? (
                          <RefreshCw className="w-3.5 h-3.5 text-amber-500 animate-spin shrink-0" />
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Shopping Cart Button */}
          <button
            onClick={openCart}
            className="w-9 h-9 rounded-xl border border-slate-200 hover:bg-slate-100 flex items-center justify-center text-slate-700 relative transition-colors"
            title="Shopping Cart"
            aria-label={
              totalUnits > 0
                ? `Shopping Cart (${totalUnits} items)`
                : "Shopping Cart"
            }
          >
            <ShoppingCart className="w-4 h-4 text-slate-700" />
            {totalUnits > 0 && (
              <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-amber-500 text-[10px] font-black text-slate-950 flex items-center justify-center">
                {totalUnits > 99 ? "99+" : totalUnits}
              </span>
            )}
          </button>

          {/* Notification Bell */}
          <button
            onClick={onOpenNotifications}
            className="w-9 h-9 rounded-xl border border-slate-200 hover:bg-slate-100 flex items-center justify-center text-slate-700 relative transition-colors"
            title="Notifications"
            aria-label={
              unreadNotificationCount > 0
                ? `Notifications (${unreadNotificationCount} unread)`
                : "Notifications"
            }
          >
            <Bell className="w-4 h-4" />
            {unreadNotificationCount > 0 && (
              <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-amber-500 text-[10px] font-black text-slate-950 flex items-center justify-center">
                {unreadNotificationCount > 99 ? "99+" : unreadNotificationCount}
              </span>
            )}
          </button>
        </div>
      </header>

      {/* Mobile Search Bar Expandable Drawer */}
      {mobileSearchOpen && (
        <div className="md:hidden bg-slate-50 border-b border-slate-200 px-4 py-2.5 sticky top-16 z-20 animate-in fade-in slide-in-from-top-1 duration-150">
          <GlobalSearch
            autoFocus
            onNavigate={onNavigate}
            onClose={() => setMobileSearchOpen(false)}
          />
        </div>
      )}

      {/* Cart Drawer */}
      <CartDrawer
        isOpen={isCartOpen}
        onClose={closeCart}
        onNavigate={onNavigate}
      />
    </>
  );
}
