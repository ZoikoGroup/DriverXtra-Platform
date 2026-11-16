"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  api,
  AdminSellerItem,
  AdminSellerDetailResponse,
} from "@/lib/api/client";
import {
  Search,
  Filter,
  RefreshCw,
  Eye,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Building2,
  Phone,
  Mail,
  MapPin,
  Car,
  Package,
  ShoppingBag,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  X,
  FileText,
  User,
  Briefcase,
} from "lucide-react";

export default function AdminSellerManagementView() {
  const [sellers, setSellers] = useState<AdminSellerItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(20);

  const [searchQuery, setSearchQuery] = useState<string>("");
  const [verificationFilter, setVerificationFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [ordering, setOrdering] = useState<string>("-created_at");

  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Detail Drawer state
  const [selectedSellerId, setSelectedSellerId] = useState<string | null>(null);
  const [sellerDetail, setSellerDetail] = useState<AdminSellerDetailResponse | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);

  // Status Action Modal state
  const [actionTarget, setActionTarget] = useState<AdminSellerItem | null>(null);
  const [actionType, setActionType] = useState<"SUSPEND" | "REACTIVATE">("SUSPEND");
  const [actionReason, setActionReason] = useState<string>("");
  const [submittingAction, setSubmittingAction] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const fetchSellers = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const res = await api.admin.sellers.list({
        page: currentPage,
        page_size: pageSize,
        q: searchQuery.trim() || undefined,
        verification_status: verificationFilter !== "ALL" ? verificationFilter : undefined,
        status: statusFilter !== "ALL" ? statusFilter : undefined,
        ordering,
      });

      setSellers(res.results || []);
      setTotalCount(res.count || 0);
      setTotalPages(res.total_pages || 1);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load seller accounts.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [currentPage, pageSize, searchQuery, verificationFilter, statusFilter, ordering]);

  useEffect(() => {
    fetchSellers();
  }, [fetchSellers]);

  const openDetailDrawer = async (id: string) => {
    setSelectedSellerId(id);
    setLoadingDetail(true);
    setSellerDetail(null);
    try {
      const detail = await api.admin.sellers.get(id);
      setSellerDetail(detail);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load seller details.");
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleStatusSubmit = async () => {
    if (!actionTarget) return;
    setSubmittingAction(true);
    try {
      await api.admin.sellers.updateStatus(actionTarget.id, {
        action: actionType,
        reason: actionReason.trim() || undefined,
      });

      setFeedback({
        type: "success",
        message: `Seller account ${actionTarget.email} was successfully ${actionType.toLowerCase()}ed.`,
      });
      setActionTarget(null);
      setActionReason("");
      fetchSellers(true);
      if (selectedSellerId === actionTarget.id) {
        openDetailDrawer(actionTarget.id);
      }
    } catch (err: unknown) {
      setFeedback({
        type: "error",
        message: err instanceof Error ? err.message : "Failed to update seller status.",
      });
    } finally {
      setSubmittingAction(false);
    }
  };

  return (
    <div className="p-6 md:p-8 space-y-6 max-w-7xl mx-auto text-slate-900 bg-slate-100 min-h-screen">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
            <span className="px-2.5 py-0.5 text-xs font-bold uppercase tracking-wider rounded-full bg-amber-100 text-amber-900 border border-amber-300">
              Account Governance
            </span>
            <span className="text-xs font-semibold text-slate-500">
              {totalCount} total seller{totalCount === 1 ? "" : "s"}
            </span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-slate-900">
            Seller & Dealership Management
          </h1>
          <p className="text-sm font-medium text-slate-600 mt-1">
            Server-side paginated governance of commercial vehicle dealerships, spare-parts merchants, and traders.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchSellers(true)}
            disabled={refreshing}
            className="flex items-center gap-2 px-4 py-2 text-xs font-semibold bg-white hover:bg-slate-50 text-slate-800 rounded-lg border border-slate-300 shadow-sm hover:border-slate-400 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin text-amber-600" : "text-slate-600"}`} />
            <span>{refreshing ? "Refreshing..." : "Refresh"}</span>
          </button>
        </div>
      </div>

      {feedback && (
        <div
          className={`p-4 rounded-xl flex items-center justify-between text-sm shadow-sm ${
            feedback.type === "success"
              ? "bg-emerald-50 border border-emerald-300 text-emerald-900"
              : "bg-red-50 border border-red-300 text-red-900"
          }`}
        >
          <div className="flex items-center gap-2 font-medium">
            {feedback.type === "success" ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
            ) : (
              <AlertTriangle className="w-5 h-5 text-red-600 shrink-0" />
            )}
            <span>{feedback.message}</span>
          </div>
          <button onClick={() => setFeedback(null)} className="text-slate-400 hover:text-slate-700">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {error && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-300 text-red-900 text-sm flex items-center justify-between shadow-sm">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="w-5 h-5 text-red-600 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={() => fetchSellers()}
            className="text-xs font-semibold bg-red-600 hover:bg-red-700 text-white px-3 py-1.5 rounded-lg shadow-sm transition"
          >
            Retry
          </button>
        </div>
      )}

      {/* Filter and Search Controls */}
      <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm flex flex-col md:flex-row gap-4 items-center justify-between">
        {/* Search Input */}
        <div className="relative w-full md:w-80">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setCurrentPage(1);
            }}
            placeholder="Search business, email, ID..."
            className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-300 rounded-lg text-xs font-semibold text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-amber-500 transition"
          />
        </div>

        {/* Dropdowns */}
        <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
          {/* Verification Status */}
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <span>Verification:</span>
            <select
              value={verificationFilter}
              onChange={(e) => {
                setVerificationFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="bg-slate-50 border border-slate-300 text-slate-900 rounded-lg px-2.5 py-1.5 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              <option value="ALL">All Verification</option>
              <option value="APPROVED">Approved / Verified</option>
              <option value="PENDING">Pending Review</option>
              <option value="REJECTED">Rejected</option>
              <option value="UNVERIFIED">Unverified / Draft</option>
            </select>
          </div>

          {/* Account Status */}
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
            <span>Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="bg-slate-50 border border-slate-300 text-slate-900 rounded-lg px-2.5 py-1.5 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              <option value="ALL">All Statuses</option>
              <option value="ACTIVE">Active</option>
              <option value="SUSPENDED">Suspended</option>
            </select>
          </div>

          {/* Page Size Selector */}
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
            <span>Page Size:</span>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setCurrentPage(1);
              }}
              className="bg-slate-50 border border-slate-300 text-slate-900 rounded-lg px-2 py-1.5 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>
        </div>
      </div>

      {/* Main Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-600 uppercase tracking-wider text-[11px] font-bold border-b border-slate-200">
              <tr>
                <th className="py-3.5 px-4">Business / Trader</th>
                <th className="py-3.5 px-4">Contact</th>
                <th className="py-3.5 px-4">Verification</th>
                <th className="py-3.5 px-4">Status</th>
                <th className="py-3.5 px-4 text-center">Vehicles</th>
                <th className="py-3.5 px-4 text-center">Parts</th>
                <th className="py-3.5 px-4 text-center">Orders</th>
                <th className="py-3.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700 font-medium">
              {loading && sellers.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-14 text-center text-slate-500">
                    <div className="flex items-center justify-center gap-2">
                      <RefreshCw className="w-5 h-5 animate-spin text-amber-500" />
                      <span className="font-semibold text-xs">Loading seller directory...</span>
                    </div>
                  </td>
                </tr>
              ) : sellers.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-14 text-center text-slate-500">
                    <div className="text-sm font-bold text-slate-900">No sellers found</div>
                    <p className="text-xs text-slate-500 mt-1">Try adjusting your search query or verification filter.</p>
                  </td>
                </tr>
              ) : (
                sellers.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-50 transition-colors">
                    {/* Business Name */}
                    <td className="py-3.5 px-4">
                      <div className="font-extrabold text-slate-900 text-sm">{s.business_name}</div>
                      <div className="text-[11px] text-slate-500 flex items-center gap-1.5 mt-0.5">
                        <span className="capitalize">{s.business_type.toLowerCase().replace(/_/g, " ")}</span>
                        {s.organisation && (
                          <span className="px-1.5 py-0.5 rounded bg-slate-100 text-[10px] text-slate-700 font-semibold border border-slate-200">
                            {s.organisation.name}
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Contact */}
                    <td className="py-3.5 px-4">
                      <div className="text-slate-900 font-semibold">{s.email}</div>
                      {s.phone_number && (
                        <div className="text-[11px] text-slate-500 mt-0.5">{s.phone_number}</div>
                      )}
                    </td>

                    {/* Verification Status */}
                    <td className="py-3.5 px-4">
                      {s.verification_status === "APPROVED" ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <CheckCircle2 className="w-3 h-3" />
                          Verified
                        </span>
                      ) : s.verification_status === "PENDING" ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-300">
                          Pending Review
                        </span>
                      ) : s.verification_status === "REJECTED" ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-red-50 text-red-700 border border-red-200">
                          Rejected
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-600 border border-slate-200">
                          Unverified
                        </span>
                      )}
                    </td>

                    {/* Account Status */}
                    <td className="py-3.5 px-4">
                      {s.status === "ACTIVE" ? (
                        <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          Active
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-red-50 text-red-700 border border-red-200">
                          Suspended
                        </span>
                      )}
                    </td>

                    {/* Metrics */}
                    <td className="py-3.5 px-4 text-center font-bold text-slate-900">
                      {s.metrics.vehicle_listings_count}
                    </td>
                    <td className="py-3.5 px-4 text-center font-bold text-slate-900">
                      {s.metrics.part_listings_count}
                    </td>
                    <td className="py-3.5 px-4 text-center font-bold text-slate-900">
                      {s.metrics.orders_count}
                    </td>

                    {/* Actions */}
                    <td className="py-3.5 px-4 text-right space-x-2">
                      <button
                        onClick={() => openDetailDrawer(s.id)}
                        className="px-3 py-1.5 rounded-lg bg-white hover:bg-slate-50 text-slate-800 border border-slate-300 shadow-sm transition text-xs font-semibold"
                      >
                        Inspect
                      </button>

                      {s.status === "ACTIVE" ? (
                        <button
                          onClick={() => {
                            setActionTarget(s);
                            setActionType("SUSPEND");
                          }}
                          className="px-3 py-1.5 rounded-lg bg-red-50 hover:bg-red-100 text-red-700 border border-red-200 transition text-xs font-semibold"
                        >
                          Suspend
                        </button>
                      ) : (
                        <button
                          onClick={() => {
                            setActionTarget(s);
                            setActionType("REACTIVATE");
                          }}
                          className="px-3 py-1.5 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 transition text-xs font-semibold"
                        >
                          Reactivate
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Server-Side Pagination Bar */}
        <div className="p-4 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-600 font-medium">
          <div>
            Showing page <span className="font-bold text-slate-900">{currentPage}</span> of{" "}
            <span className="font-bold text-slate-900">{totalPages}</span> (
            <span className="font-bold text-slate-900">{totalCount}</span> total records)
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage <= 1 || loading}
              className="px-3 py-1.5 bg-white hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg border border-slate-300 text-slate-700 font-semibold shadow-sm flex items-center gap-1 transition"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              <span>Previous</span>
            </button>

            <span className="px-2 text-slate-400">|</span>

            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage >= totalPages || loading}
              className="px-3 py-1.5 bg-white hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg border border-slate-300 text-slate-700 font-semibold shadow-sm flex items-center gap-1 transition"
            >
              <span>Next</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Inspect Seller Detail Drawer */}
      {selectedSellerId && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex justify-end">
          <div className="w-full max-w-2xl bg-white border-l border-slate-200 h-full overflow-y-auto p-6 space-y-6 shadow-2xl">
            {/* Drawer Header */}
            <div className="flex items-center justify-between pb-4 border-b border-slate-200">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-amber-50 flex items-center justify-center text-amber-600 border border-amber-200">
                  <Briefcase className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-lg font-extrabold text-slate-900">Seller Account Details</h3>
                  <p className="text-xs font-mono text-slate-500">
                    ID: {selectedSellerId}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedSellerId(null)}
                className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {loadingDetail || !sellerDetail ? (
              <div className="py-20 text-center text-slate-500 text-xs">
                <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-amber-500" />
                Loading complete seller dossier...
              </div>
            ) : (
              <div className="space-y-6 text-xs">
                {/* Account Summary Card */}
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-900">Identity & Account</span>
                    <span
                      className={`px-2.5 py-0.5 rounded text-[11px] font-semibold ${
                        sellerDetail.seller.status === "ACTIVE"
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                          : "bg-red-50 text-red-700 border border-red-200"
                      }`}
                    >
                      {sellerDetail.seller.status}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-3 text-slate-600">
                    <div>
                      <span className="text-slate-500 font-semibold block text-[11px]">Email:</span>
                      <span className="text-slate-900 font-bold">{sellerDetail.seller.email}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-semibold block text-[11px]">Full Name:</span>
                      <span className="text-slate-900 font-bold">{sellerDetail.seller.full_name}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-semibold block text-[11px]">Phone:</span>
                      <span className="text-slate-900 font-bold">{sellerDetail.seller.phone_number || "Not provided"}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-semibold block text-[11px]">Email Verified:</span>
                      <span className="text-slate-900 font-bold">
                        {sellerDetail.seller.is_email_verified ? "Yes" : "No"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Organisation & KYC Card */}
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
                  <span className="font-bold text-slate-900 block">Dealership / Organisation Profile</span>
                  {sellerDetail.organisation ? (
                    <div className="grid grid-cols-2 gap-3 text-slate-600">
                      <div>
                        <span className="text-slate-500 font-semibold block text-[11px]">Trading Name:</span>
                        <span className="text-slate-900 font-bold">{sellerDetail.organisation.name}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 font-semibold block text-[11px]">Type:</span>
                        <span className="text-slate-900 font-bold">{sellerDetail.organisation.type}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 font-semibold block text-[11px]">Jurisdiction:</span>
                        <span className="text-slate-900 font-bold">{sellerDetail.organisation.jurisdiction || "—"}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 font-semibold block text-[11px]">Country:</span>
                        <span className="text-slate-900 font-bold">{sellerDetail.organisation.country || "—"}</span>
                      </div>
                    </div>
                  ) : (
                    <p className="text-slate-500 italic">No formal organization membership recorded.</p>
                  )}
                </div>

                {/* Inventory Metrics */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm text-center">
                    <span className="text-[11px] font-bold text-slate-500 block uppercase">Vehicles Listed</span>
                    <span className="text-2xl font-extrabold text-slate-900 mt-1 block">
                      {sellerDetail.metrics.vehicle_listings_count}
                    </span>
                  </div>
                  <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm text-center">
                    <span className="text-[11px] font-bold text-slate-500 block uppercase">Parts Listed</span>
                    <span className="text-2xl font-extrabold text-slate-900 mt-1 block">
                      {sellerDetail.metrics.part_listings_count}
                    </span>
                  </div>
                  <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm text-center">
                    <span className="text-[11px] font-bold text-slate-500 block uppercase">Total Orders</span>
                    <span className="text-2xl font-extrabold text-slate-900 mt-1 block">
                      {sellerDetail.metrics.orders_count}
                    </span>
                  </div>
                </div>

                {/* Recent Orders List */}
                <div className="space-y-3">
                  <span className="font-bold text-slate-900 block text-sm">Recent Fulfillments ({sellerDetail.recent_orders.length})</span>
                  {sellerDetail.recent_orders.length === 0 ? (
                    <p className="text-slate-500 italic">No orders fulfilled yet.</p>
                  ) : (
                    <div className="space-y-2">
                      {sellerDetail.recent_orders.map((ord) => (
                        <div
                          key={ord.id}
                          className="p-3 bg-white border border-slate-200 rounded-lg flex items-center justify-between shadow-sm"
                        >
                          <div>
                            <span className="font-bold text-slate-900 block">{ord.order_number}</span>
                            <span className="text-[11px] text-slate-500 font-medium">
                              Placed: {ord.created_at ? new Date(ord.created_at).toLocaleDateString() : "—"}
                            </span>
                          </div>
                          <div className="text-right">
                            <span className="font-bold text-slate-900 block">
                              {ord.currency} {ord.total_amount}
                            </span>
                            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700">
                              {ord.status}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Drawer Footer */}
            <div className="pt-4 border-t border-slate-200 flex justify-end">
              <button
                onClick={() => setSelectedSellerId(null)}
                className="px-4 py-2 bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold shadow-sm transition"
              >
                Close Drawer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Status Action Confirmation Modal */}
      {actionTarget && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center gap-3">
              {actionType === "SUSPEND" ? (
                <div className="w-10 h-10 rounded-xl bg-red-50 flex items-center justify-center text-red-600 border border-red-200 shrink-0">
                  <ShieldAlert className="w-5 h-5" />
                </div>
              ) : (
                <div className="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center text-emerald-600 border border-emerald-200 shrink-0">
                  <ShieldCheck className="w-5 h-5" />
                </div>
              )}
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  {actionType === "SUSPEND" ? "Suspend Seller Account" : "Reactivate Seller Account"}
                </h3>
                <p className="text-xs font-medium text-slate-500">{actionTarget.business_name} ({actionTarget.email})</p>
              </div>
            </div>

            <p className="text-xs font-medium text-slate-600 leading-relaxed">
              {actionType === "SUSPEND"
                ? "Suspending this account will immediately deactivate all live vehicle and parts listings from the public marketplace, prevent login access, and halt new order transactions."
                : "Reactivating this account will restore marketplace publishing privileges, enable active seller features, and restore login access."}
            </p>

            <div className="space-y-1">
              <label className="text-[11px] font-bold text-slate-700 uppercase tracking-wider block">
                Administrative Reason / Notes (Audit logged):
              </label>
              <textarea
                value={actionReason}
                onChange={(e) => setActionReason(e.target.value)}
                placeholder="Enter regulatory, compliance, or operational reason..."
                className="w-full p-2.5 bg-slate-50 border border-slate-300 rounded-lg text-xs font-medium text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-amber-500 h-20"
              />
            </div>

            <div className="flex items-center justify-end gap-3 pt-2 border-t border-slate-100">
              <button
                onClick={() => setActionTarget(null)}
                disabled={submittingAction}
                className="px-4 py-2 bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold shadow-sm transition"
              >
                Cancel
              </button>
              <button
                onClick={handleStatusSubmit}
                disabled={submittingAction}
                className={`px-4 py-2 rounded-lg text-xs font-bold text-white shadow-sm transition flex items-center gap-1.5 ${
                  actionType === "SUSPEND"
                    ? "bg-red-600 hover:bg-red-700"
                    : "bg-emerald-600 hover:bg-emerald-700"
                }`}
              >
                {submittingAction && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>{actionType === "SUSPEND" ? "Confirm Suspension" : "Confirm Reactivation"}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
