"use client";

import React, { useState, useEffect, useCallback } from "react";
import { api, AdminOverviewResponse } from "@/lib/api/client";
import {
  Users,
  Building2,
  Wrench,
  ShieldCheck,
  ShoppingBag,
  Scale,
  AlertTriangle,
  FileCheck2,
  Layers,
  RefreshCw,
  ArrowRight,
  Clock,
  CheckCircle2,
  XCircle,
  Activity,
  Shield,
  Briefcase,
  Search,
  ExternalLink,
  ChevronRight,
} from "lucide-react";

interface AdminOverviewViewProps {
  onNavigateTab?: (tab: string) => void;
}

export default function AdminOverviewView({ onNavigateTab }: AdminOverviewViewProps) {
  const [data, setData] = useState<AdminOverviewResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState<boolean>(false);

  const loadMetrics = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const res = await api.admin.overview.getMetrics();
      setData(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load admin overview metrics.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadMetrics();
  }, [loadMetrics]);

  if (loading && !data) {
    return (
      <div className="p-6 md:p-8 space-y-6 max-w-7xl mx-auto">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <div className="h-8 w-64 bg-slate-200 rounded animate-pulse" />
            <div className="h-4 w-96 bg-slate-200/70 rounded animate-pulse" />
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-28 bg-white rounded-xl animate-pulse border border-slate-200 shadow-sm" />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 h-96 bg-white rounded-xl animate-pulse border border-slate-200 shadow-sm" />
          <div className="h-96 bg-white rounded-xl animate-pulse border border-slate-200 shadow-sm" />
        </div>
      </div>
    );
  }

  const m = data?.metrics;

  return (
    <div className="p-6 md:p-8 space-y-8 max-w-7xl mx-auto text-slate-900 bg-slate-100 min-h-screen">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
            <span className="px-2.5 py-0.5 text-xs font-bold uppercase tracking-wider rounded-full bg-amber-100 text-amber-900 border border-amber-300">
              Platform Governance Plane
            </span>
            <span className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              Live DB Synchronization
            </span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-slate-900">
            Admin Operations & Ecosystem Overview
          </h1>
          <p className="text-sm font-medium text-slate-600 mt-1">
            Centralized monitoring and governance over marketplace buyers, sellers, workshops, and compliance queues.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => loadMetrics(true)}
            disabled={refreshing}
            className="flex items-center gap-2 px-4 py-2 text-xs font-semibold bg-white hover:bg-slate-50 active:bg-slate-100 text-slate-800 rounded-lg border border-slate-300 shadow-sm hover:border-slate-400 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin text-amber-600" : "text-slate-600"}`} />
            <span>{refreshing ? "Refreshing..." : "Refresh Live Stats"}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-300 text-red-900 text-sm flex items-center justify-between shadow-sm">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-red-600 shrink-0" />
            <span className="font-medium">{error}</span>
          </div>
          <button
            onClick={() => loadMetrics()}
            className="text-xs font-semibold bg-red-600 hover:bg-red-700 text-white px-3 py-1.5 rounded-lg shadow-sm transition"
          >
            Retry
          </button>
        </div>
      )}

      {/* Primary Ecosystem KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {/* Buyers */}
        <div
          onClick={() => onNavigateTab?.("admin_buyers")}
          className="p-5 rounded-xl bg-white border border-slate-200 hover:border-blue-500 transition-all cursor-pointer group shadow-sm hover:shadow-md"
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Buyers</span>
            <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center text-blue-600 group-hover:scale-110 transition-transform">
              <Users className="w-4 h-4" />
            </div>
          </div>
          <div className="text-3xl font-extrabold text-slate-900">{m?.total_buyers ?? 0}</div>
          <div className="text-xs font-medium text-slate-600 mt-1.5 flex items-center justify-between">
            <span>Customer accounts</span>
            <ArrowRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-blue-600 group-hover:translate-x-1 transition-all" />
          </div>
        </div>

        {/* Sellers */}
        <div
          onClick={() => onNavigateTab?.("admin_sellers")}
          className="p-5 rounded-xl bg-white border border-slate-200 hover:border-amber-500 transition-all cursor-pointer group shadow-sm hover:shadow-md"
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Sellers</span>
            <div className="w-8 h-8 rounded-lg bg-amber-50 flex items-center justify-center text-amber-600 group-hover:scale-110 transition-transform">
              <Briefcase className="w-4 h-4" />
            </div>
          </div>
          <div className="text-3xl font-extrabold text-slate-900">{m?.total_sellers ?? 0}</div>
          <div className="text-xs font-medium text-slate-600 mt-1.5 flex items-center justify-between">
            <span>Dealers & Merchants</span>
            <ArrowRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-amber-600 group-hover:translate-x-1 transition-all" />
          </div>
        </div>

        {/* Workshops */}
        <div
          onClick={() => onNavigateTab?.("admin_workshops")}
          className="p-5 rounded-xl bg-white border border-slate-200 hover:border-emerald-500 transition-all cursor-pointer group shadow-sm hover:shadow-md"
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Workshops</span>
            <div className="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center text-emerald-600 group-hover:scale-110 transition-transform">
              <Wrench className="w-4 h-4" />
            </div>
          </div>
          <div className="text-3xl font-extrabold text-slate-900">{m?.total_workshops ?? 0}</div>
          <div className="text-xs font-medium text-slate-600 mt-1.5 flex items-center justify-between">
            <span>Service Hubs</span>
            <ArrowRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-emerald-600 group-hover:translate-x-1 transition-all" />
          </div>
        </div>

        {/* Orders */}
        <div
          onClick={() => onNavigateTab?.("admin_orders_monitoring")}
          className="p-5 rounded-xl bg-white border border-slate-200 hover:border-purple-500 transition-all cursor-pointer group shadow-sm hover:shadow-md"
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Orders</span>
            <div className="w-8 h-8 rounded-lg bg-purple-50 flex items-center justify-center text-purple-600 group-hover:scale-110 transition-transform">
              <ShoppingBag className="w-4 h-4" />
            </div>
          </div>
          <div className="text-3xl font-extrabold text-slate-900">{m?.total_orders ?? 0}</div>
          <div className="text-xs font-medium text-slate-600 mt-1.5 flex items-center justify-between">
            <span>Vehicles & Parts</span>
            <ArrowRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-purple-600 group-hover:translate-x-1 transition-all" />
          </div>
        </div>

        {/* Disputes */}
        <div
          onClick={() => onNavigateTab?.("admin_disputes_refunds")}
          className="p-5 rounded-xl bg-white border border-slate-200 hover:border-rose-500 transition-all cursor-pointer group shadow-sm hover:shadow-md"
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Disputes</span>
            <div className="w-8 h-8 rounded-lg bg-rose-50 flex items-center justify-center text-rose-600 group-hover:scale-110 transition-transform">
              <Scale className="w-4 h-4" />
            </div>
          </div>
          <div className="text-3xl font-extrabold text-slate-900">{m?.pending_disputes ?? 0}</div>
          <div className="text-xs font-medium text-slate-600 mt-1.5 flex items-center justify-between">
            <span>Active cases</span>
            <ArrowRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-rose-600 group-hover:translate-x-1 transition-all" />
          </div>
        </div>

        {/* Staff */}
        <div
          onClick={() => onNavigateTab?.("admin_staff_management")}
          className="p-5 rounded-xl bg-white border border-slate-200 hover:border-cyan-500 transition-all cursor-pointer group shadow-sm hover:shadow-md"
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Staff</span>
            <div className="w-8 h-8 rounded-lg bg-cyan-50 flex items-center justify-center text-cyan-600 group-hover:scale-110 transition-transform">
              <Shield className="w-4 h-4" />
            </div>
          </div>
          <div className="text-3xl font-extrabold text-slate-900">{m?.total_staff ?? 0}</div>
          <div className="text-xs font-medium text-slate-600 mt-1.5 flex items-center justify-between">
            <span>Platform RBAC</span>
            <ArrowRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-cyan-600 group-hover:translate-x-1 transition-all" />
          </div>
        </div>
      </div>

      {/* Secondary Status Badges / Compliance Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 p-5 rounded-xl bg-white border border-slate-200 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600 shrink-0">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Approved Sellers</div>
            <div className="text-base font-extrabold text-slate-900">{m?.approved_sellers ?? 0} Verified</div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600 shrink-0">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Verified Workshops</div>
            <div className="text-base font-extrabold text-slate-900">{m?.approved_workshops ?? 0} Active Hubs</div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-200 flex items-center justify-center text-amber-600 shrink-0">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Pending Inventory Reviews</div>
            <div className="text-base font-extrabold text-slate-900">
              {(m?.pending_vehicle_listings ?? 0) + (m?.pending_part_listings ?? 0)} Listings
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-red-50 border border-red-200 flex items-center justify-center text-red-600 shrink-0">
            <XCircle className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-slate-500">Suspended Accounts</div>
            <div className="text-base font-extrabold text-slate-900">{m?.suspended_accounts ?? 0} Accounts</div>
          </div>
        </div>
      </div>

      {/* Main Content Grid: Tasks Queue & Activity Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Pending Administrative Action Queue */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <Clock className="w-5 h-5 text-amber-500" />
              <span>Pending Administrative Tasks</span>
            </h2>
            <span className="text-xs font-semibold text-slate-500">Requires platform staff action</span>
          </div>

          <div className="space-y-3">
            {data?.pending_tasks && data.pending_tasks.length > 0 ? (
              data.pending_tasks.map((task) => (
                <div
                  key={task.id}
                  onClick={() => onNavigateTab?.(task.target_tab)}
                  className={`p-4 rounded-xl border transition-all flex items-center justify-between cursor-pointer group shadow-sm ${
                    task.count > 0
                      ? task.severity === "high"
                        ? "bg-amber-50/40 border-amber-300 hover:border-amber-500 hover:shadow-md"
                        : "bg-white border-slate-200 hover:border-amber-400 hover:shadow-md"
                      : "bg-white border-slate-200 text-slate-400"
                  }`}
                >
                  <div className="flex items-center gap-3.5">
                    <div
                      className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                        task.count > 0 ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-400"
                      }`}
                    >
                      {task.type === "SELLER_APPLICATIONS" ? (
                        <FileCheck2 className="w-5 h-5" />
                      ) : task.type === "DISPUTES" ? (
                        <Scale className="w-5 h-5" />
                      ) : (
                        <Layers className="w-5 h-5" />
                      )}
                    </div>
                    <div>
                      <div className="text-sm font-bold text-slate-900 group-hover:text-amber-600 transition-colors">
                        {task.label}
                      </div>
                      <div className="text-xs font-medium text-slate-600 mt-0.5">
                        {task.count > 0 ? "Action required from operations staff" : "All current records up to date"}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-extrabold ${
                        task.count > 0
                          ? "bg-amber-500 text-slate-950 shadow-sm"
                          : "bg-slate-100 text-slate-500 font-semibold"
                      }`}
                    >
                      {task.count}
                    </span>
                    <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-amber-600 group-hover:translate-x-1 transition-all" />
                  </div>
                </div>
              ))
            ) : (
              <div className="p-8 text-center text-sm font-medium text-slate-500 bg-white rounded-xl border border-slate-200 shadow-sm">
                No pending administrative tasks at this time.
              </div>
            )}
          </div>

          {/* Quick Management Shortcuts */}
          <div className="pt-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">
              Direct Governance Consoles
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <button
                onClick={() => onNavigateTab?.("admin_sellers")}
                className="p-4 text-left bg-white hover:bg-slate-50 border border-slate-200 hover:border-amber-400 rounded-xl transition-all shadow-sm hover:shadow flex items-center justify-between group"
              >
                <div>
                  <div className="text-sm font-bold text-slate-900 group-hover:text-amber-600 transition-colors">
                    Sellers Directory
                  </div>
                  <div className="text-xs font-medium text-slate-500 mt-0.5">KYC, inventory & audits</div>
                </div>
                <ExternalLink className="w-4 h-4 text-slate-400 group-hover:text-amber-600 transition-colors" />
              </button>

              <button
                onClick={() => onNavigateTab?.("admin_workshops")}
                className="p-4 text-left bg-white hover:bg-slate-50 border border-slate-200 hover:border-amber-400 rounded-xl transition-all shadow-sm hover:shadow flex items-center justify-between group"
              >
                <div>
                  <div className="text-sm font-bold text-slate-900 group-hover:text-amber-600 transition-colors">
                    Workshop Directory
                  </div>
                  <div className="text-xs font-medium text-slate-500 mt-0.5">Services, bays & bookings</div>
                </div>
                <ExternalLink className="w-4 h-4 text-slate-400 group-hover:text-amber-600 transition-colors" />
              </button>

              <button
                onClick={() => onNavigateTab?.("admin_buyers")}
                className="p-4 text-left bg-white hover:bg-slate-50 border border-slate-200 hover:border-amber-400 rounded-xl transition-all shadow-sm hover:shadow flex items-center justify-between group"
              >
                <div>
                  <div className="text-sm font-bold text-slate-900 group-hover:text-amber-600 transition-colors">
                    Buyer Directory
                  </div>
                  <div className="text-xs font-medium text-slate-500 mt-0.5">Order history & status</div>
                </div>
                <ExternalLink className="w-4 h-4 text-slate-400 group-hover:text-amber-600 transition-colors" />
              </button>
            </div>
          </div>
        </div>

        {/* Live Activity Feed */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <Activity className="w-5 h-5 text-emerald-600" />
              <span>Recent Activity</span>
            </h2>
            <span className="text-xs font-semibold text-slate-500">Live events</span>
          </div>

          <div className="p-5 rounded-xl bg-white border border-slate-200 shadow-sm space-y-4">
            {data?.recent_activity && data.recent_activity.length > 0 ? (
              <div className="divide-y divide-slate-100">
                {data.recent_activity.map((act) => (
                  <div key={act.id} className="py-3.5 first:pt-0 last:pb-0 flex items-start gap-3">
                    <div className="w-2.5 h-2.5 rounded-full bg-amber-500 mt-1.5 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-semibold text-slate-900 leading-snug break-words">
                        {act.description}
                      </p>
                      <span className="text-[11px] font-medium text-slate-500 mt-1 inline-block">
                        {new Date(act.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        {" · "}
                        {new Date(act.timestamp).toLocaleDateString([], { month: "short", day: "numeric" })}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs font-medium text-slate-500 py-6 text-center">No recent activity recorded.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
