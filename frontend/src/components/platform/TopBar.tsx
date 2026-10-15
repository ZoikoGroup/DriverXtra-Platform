"use client";

import React, { useState } from "react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  Search,
  Bell,
  ChevronDown,
  CheckCircle2
} from "lucide-react";

interface TopBarProps {
  currentTabLabel: string;
  onOpenNotifications: () => void;
}

export default function TopBar({ currentTabLabel, onOpenNotifications }: TopBarProps) {
  const { user, switchRole, availablePrototypeUsers } = useAuth();
  const [roleDropdownOpen, setRoleDropdownOpen] = useState(false);

  if (!user) return null;

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

      {/* Right: Prototype Mode Pill & Role Switcher */}
      <div className="flex items-center gap-3">
        {/* Prototype Indicator */}
        <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-50 border border-amber-300 text-amber-900 text-[11px] font-bold">
          <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>
          <span>Prototype Mode</span>
        </div>

        {/* Quick Role Switcher Pill */}
        <div className="relative">
          <button
            onClick={() => setRoleDropdownOpen(!roleDropdownOpen)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition-all shadow-sm"
          >
            <span className="text-amber-400 text-[10px] font-black uppercase">Role:</span>
            <span>{user.role === "MARKETPLACE_ADMIN" ? "Admin" : user.roleLabel.split(" ")[0]}</span>
            <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
          </button>

          {roleDropdownOpen && (
            <div className="absolute right-0 mt-2 w-72 bg-white rounded-2xl shadow-2xl border border-slate-200 p-2 z-50 animate-in fade-in slide-in-from-top-2 duration-150">
              <div className="p-2 border-b border-slate-100 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Switch Documented Role
              </div>
              <div className="space-y-1 mt-1">
                {availablePrototypeUsers.map((u) => (
                  <button
                    key={u.id}
                    onClick={() => {
                      switchRole(u.role);
                      setRoleDropdownOpen(false);
                    }}
                    className={`w-full text-left p-2 rounded-xl text-xs flex items-center justify-between transition-colors ${
                      user.role === u.role
                        ? "bg-amber-50 text-amber-950 font-bold border border-amber-200"
                        : "hover:bg-slate-50 text-slate-700"
                    }`}
                  >
                    <div>
                      <div className="font-bold">{u.fullName}</div>
                      <div className="text-[10px] text-slate-500">{u.roleLabel}</div>
                    </div>
                    {user.role === u.role && (
                      <CheckCircle2 className="w-4 h-4 text-amber-500 shrink-0" />
                    )}
                  </button>
                ))}
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
