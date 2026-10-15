"use client";

import React from "react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  Car,
  Layers,
  ShoppingBag,
  Settings,
  Wrench,
  Scale,
  RefreshCw,
  DollarSign,
  MessageSquare,
  Users,
  Clock,
  Truck,
  FileCheck2,
  ShieldAlert,
  FolderLock,
  Globe2,
  LogOut,
  ChevronRight,
  ShieldCheck,
  FileText,
  User,
  Building2
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

  // Role-governed navigation items based on Doc 04 RBAC permissions
  let navItems: { id: string; label: string; icon: React.ComponentType<{ className?: string }>; badge?: string }[] = [];

  if (user.role === "CONSUMER") {
    navItems = [
      { id: "garage", label: "My Garage (Vehicle Master)", icon: Layers, badge: "Doc 05" },
      { id: "orders", label: "Orders & Escrow Holds", icon: ShoppingBag, badge: "Doc 09" },
      { id: "parts_fitment", label: "Guaranteed Fit Parts", icon: Settings, badge: "Doc 06" },
      { id: "service_bookings", label: "Workshop Bookings", icon: Wrench, badge: "Doc 13" },
      { id: "disputes", label: "Disputes & Protection", icon: Scale, badge: "Doc 15" }
    ];
  } else if (user.role === "INVENTORY_MANAGER") {
    navItems = [
      { id: "inventory", label: "Vehicle Inventory", icon: Car, badge: "Doc 07" },
      { id: "feeds", label: "DMS Ingestion Feeds", icon: RefreshCw, badge: "Doc 16" },
      { id: "escrow_payouts", label: "Escrow & Settlements", icon: DollarSign, badge: "Doc 10" },
      { id: "leads", label: "Buyer Inquiries", icon: MessageSquare, badge: "Doc 12" },
      { id: "team", label: "Dealership RBAC", icon: Users, badge: "Doc 04" }
    ];
  } else if (user.role === "WORKSHOP_MANAGER") {
    navItems = [
      { id: "work_orders", label: "Bay Work Orders", icon: Wrench, badge: "Doc 13" },
      { id: "change_orders", label: "Change-Order Authorizer", icon: Clock, badge: "Doc 13" },
      { id: "service_writeback", label: "Service History Records", icon: FileCheck2, badge: "Doc 05" },
      { id: "parts_requisitions", label: "Parts Procurement", icon: Settings, badge: "Doc 06" }
    ];
  } else if (user.role === "FLEET_MANAGER") {
    navItems = [
      { id: "fleet_portfolio", label: "Fleet Portfolio", icon: Truck, badge: "Doc 16" },
      { id: "maintenance_due", label: "Maintenance Due", icon: Wrench, badge: "Doc 13" },
      { id: "drivers", label: "Driver Assignments", icon: Users, badge: "Doc 16" },
      { id: "procurement", label: "Procurement & RFQs", icon: FileText, badge: "Doc 16" }
    ];
  } else if (user.role === "MARKETPLACE_ADMIN") {
    navItems = [
      { id: "maker_checker", label: "Maker-Checker Queue", icon: ShieldAlert, badge: "Doc 24" },
      { id: "trust_kyb", label: "Trust & KYB Clearance", icon: ShieldCheck, badge: "Doc 11" },
      { id: "disputes_admin", label: "Dispute Adjudication", icon: Scale, badge: "Doc 15" },
      { id: "jurisdictions", label: "Jurisdiction Packs", icon: Globe2, badge: "Doc 18" },
      { id: "audit_stream", label: "Immutable Audit Log", icon: FolderLock, badge: "Doc 22" }
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

        {/* Tenant Organization Context Card (Doc 04 §10) */}
        {!collapsed && (
          <div className="p-3 mx-3 my-3 bg-slate-900 border border-slate-800 rounded-xl">
            <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
              Active Organization
            </div>
            <div className="text-xs font-bold text-white truncate mt-0.5">
              {user.organizationName}
            </div>
            <div className="mt-1 flex items-center gap-1.5 text-[10px] text-amber-400 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
              <span>Jurisdiction: {user.jurisdiction}</span>
            </div>
          </div>
        )}

          {/* Role-Specific Navigation Links */}
        <div className="px-3 py-2 space-y-1">
          {!collapsed && (
            <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Permitted Modules
            </div>
          )}

          {[
            { id: "profile", label: "My Profile (Phase 1)", icon: User, badge: "Phase 1" },
            { id: "organisations", label: "Organisations & Teams", icon: Building2, badge: "Phase 1" },
            ...navItems
          ].map((item) => {
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
              {user.roleLabel}
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
