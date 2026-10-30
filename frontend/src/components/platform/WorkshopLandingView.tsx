"use client";

import React from "react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  Wrench,
  AlertCircle,
  Building2,
  User,
  ShieldCheck,
  CheckCircle2,
  CalendarX,
  FileSpreadsheet
} from "lucide-react";

export default function WorkshopLandingView() {
  const { user } = useAuth();

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      {/* Header Banner */}
      <div className="bg-slate-950 text-white rounded-2xl p-6 shadow-sm border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-purple-500/10 text-purple-400 text-xs font-bold border border-purple-500/20">
            <Wrench className="w-3.5 h-3.5" />
            <span>Approved Workshop Partner</span>
          </div>
          <h1 className="text-2xl font-black tracking-tight text-white">
            Workshop Partner Hub
          </h1>
          <p className="text-xs text-slate-400 max-w-xl">
            Welcome to the DriverXtra Workshop Portal. Your commercial workshop account has been approved and verified.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="bg-slate-900 border border-slate-800 px-4 py-3 rounded-xl flex items-center gap-3">
            <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0" />
            <div className="text-xs">
              <span className="block text-slate-400 text-[10px] font-bold uppercase tracking-wider">Account Status</span>
              <span className="font-bold text-white">Active Workshop Role</span>
            </div>
          </div>
        </div>
      </div>

      {/* Prominent Service Availability Panel as specified in requirements */}
      <div className="bg-amber-50/70 border-2 border-amber-300 rounded-2xl p-6 shadow-sm space-y-3">
        <div className="flex items-start gap-3">
          <div className="p-2.5 rounded-xl bg-amber-100 text-amber-800 shrink-0">
            <AlertCircle className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h2 className="text-lg font-black text-amber-950">
              Workshop services: Not yet available
            </h2>
            <p className="text-xs text-amber-900/90 leading-relaxed max-w-3xl">
              Workshop service-management functionality—including customer booking management, workshop bay allocation, work orders, service quotes, and diagnostic logging—is currently under active development and not yet available on the platform.
            </p>
            <p className="text-xs text-amber-800 font-medium">
              Your workshop account and credentials are verified and on record. You will receive notification as soon as workshop service workflows and bay management tools are activated.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-3 border-t border-amber-200">
          <div className="bg-white/80 rounded-xl p-3 border border-amber-200/80 flex items-center gap-3 text-xs text-amber-950">
            <CalendarX className="w-4 h-4 text-amber-700 shrink-0" />
            <div>
              <span className="font-bold block">Service Bookings</span>
              <span className="text-[11px] text-amber-800 font-semibold">Coming Soon</span>
            </div>
          </div>
          <div className="bg-white/80 rounded-xl p-3 border border-amber-200/80 flex items-center gap-3 text-xs text-amber-950">
            <Wrench className="w-4 h-4 text-amber-700 shrink-0" />
            <div>
              <span className="font-bold block">Work Orders & Diagnostics</span>
              <span className="text-[11px] text-amber-800 font-semibold">Coming Soon</span>
            </div>
          </div>
          <div className="bg-white/80 rounded-xl p-3 border border-amber-200/80 flex items-center gap-3 text-xs text-amber-950">
            <FileSpreadsheet className="w-4 h-4 text-amber-700 shrink-0" />
            <div>
              <span className="font-bold block">Quotes & Labour Billing</span>
              <span className="text-[11px] text-amber-800 font-semibold">Coming Soon</span>
            </div>
          </div>
        </div>
      </div>

      {/* Profile & Organisation Details */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Profile Card */}
        <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <User className="w-4 h-4 text-purple-600" />
              <h3 className="text-sm font-black text-slate-950">Authorized Representative</h3>
            </div>
            <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
              <CheckCircle2 className="w-3 h-3" />
              <span>Verified Contact</span>
            </span>
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-bold">Representative Name</span>
              <span className="font-bold text-slate-900">{user?.fullName || "—"}</span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-bold">Account Email</span>
              <span className="font-mono text-slate-800">{user?.email || "—"}</span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-bold">Approved Roles</span>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {(user?.rawRoles || [user?.role || "WORKSHOP"]).map((r) => (
                  <span
                    key={r}
                    className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-100 text-purple-800"
                  >
                    {r}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Organisation Card */}
        <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Building2 className="w-4 h-4 text-purple-600" />
              <h3 className="text-sm font-black text-slate-950">Workshop Organisation</h3>
            </div>
            <span className="text-[11px] text-slate-500 font-medium">Tenant Entity</span>
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-bold">Trading Organisation</span>
              <span className="font-bold text-slate-900">
                {user?.organisations && user.organisations[0]?.organisation_name
                  ? user.organisations[0].organisation_name
                  : user?.organizationName || "Independent Registered Workshop"}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-bold">Entity Type</span>
              <span className="font-medium text-slate-800">
                {user?.tenantType || "Commercial Workshop"}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-bold">Catalogue Access</span>
              <span className="font-medium text-emerald-700">
                Full Parts Catalogue & Fitment Evaluation Available
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
