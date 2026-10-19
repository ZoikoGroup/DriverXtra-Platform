"use client";

import React, { useState } from "react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  Search,
  Bell,
  ChevronDown,
  CheckCircle2,
  ShieldCheck,
  RefreshCw
} from "lucide-react";

interface TopBarProps {
  currentTabLabel: string;
  onOpenNotifications: () => void;
}

export default function TopBar({ currentTabLabel, onOpenNotifications }: TopBarProps) {
  const { user, switchRole, isLoading } = useAuth();
  const [roleDropdownOpen, setRoleDropdownOpen] = useState(false);
  const [switchingRole, setSwitchingRole] = useState<string | null>(null);

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
    <header className="h-16 bg-white border-b border-slate-200 px-4 sm:px-6 flex items-center justify-between sticky top-0 z-20">
      {/* Left: Breadcrumbs & Current Module */}
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex items-center gap-1.5 text-xs text-slate-500 font-semibold truncate">
          <span>Platform</span>
          <span>/</span>
          <span className="text-slate-800 font-bold">{user.organizationName}</span>
          <span>/</span>
          <span className="text-amber-600 font-bold">{currentTabLabel}</span>
        </div>
      </div>

      {/* Center: Search input */}
      <div className="hidden md:flex items-center w-full max-w-sm h-9 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs text-slate-900 focus-within:border-amber-500 focus-within:bg-white focus-within:ring-2 focus-within:ring-amber-400/20">
        <Search className="w-3.5 h-3.5 text-slate-400 mr-2 shrink-0" />
        <input
          type="text"
          placeholder="Search records by VIN, Order #, or Part MPN…"
          className="w-full bg-transparent focus:outline-none placeholder:text-slate-400 font-medium"
        />
      </div>

      {/* Right: Environment Indicator & Real Role Switcher */}
      <div className="flex items-center gap-3">
        {/* Environment Indicator */}
        <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-50 border border-emerald-300 text-emerald-900">
          <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
          <span>Backend Live (Phase 1–5 RBAC)</span>
        </div>

        {/* Real Backend Role Switcher */}
        <div className="relative">
          <button
            onClick={() => setRoleDropdownOpen(!roleDropdownOpen)}
            disabled={isLoading || Boolean(switchingRole)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition-all shadow-sm disabled:opacity-60"
          >
            <span className="text-amber-400 text-[10px] font-black uppercase">Active Role:</span>
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

        {/* Notification Bell */}
        <button
          onClick={onOpenNotifications}
          className="w-9 h-9 rounded-xl border border-slate-200 hover:bg-slate-100 flex items-center justify-center text-slate-700 relative transition-colors"
          title="Notifications"
        >
          <Bell className="w-4 h-4" />
          <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-amber-500"></span>
        </button>
      </div>
    </header>
  );
}
