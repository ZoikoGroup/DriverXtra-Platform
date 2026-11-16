"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  api,
  AdminBuyerItem,
  AdminBuyerDetailResponse,
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
  User,
  Phone,
  Mail,
  ShoppingBag,
  AlertOctagon,
  ChevronLeft,
  ChevronRight,
  X,
  Clock,
  CheckCircle,
} from "lucide-react";

export default function AdminBuyerManagementView() {
  const [buyers, setBuyers] = useState<AdminBuyerItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(20);

  const [searchQuery, setSearchQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [emailVerifiedFilter, setEmailVerifiedFilter] = useState<string>("ALL");
  const [ordering, setOrdering] = useState<string>("-created_at");

  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Detail Drawer state
  const [selectedBuyerId, setSelectedBuyerId] = useState<string | null>(null);
  const [buyerDetail, setBuyerDetail] = useState<AdminBuyerDetailResponse | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);

  // Status Action Modal state
  const [actionTarget, setActionTarget] = useState<AdminBuyerItem | null>(null);
  const [actionType, setActionType] = useState<"SUSPEND" | "REACTIVATE">("SUSPEND");
  const [actionReason, setActionReason] = useState<string>("");
  const [submittingAction, setSubmittingAction] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const fetchBuyers = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const isVerifiedParam =
        emailVerifiedFilter === "VERIFIED"
          ? true
          : emailVerifiedFilter === "UNVERIFIED"
          ? false
          : undefined;

      const res = await api.admin.buyers.list({
        page: currentPage,
        page_size: pageSize,
        q: searchQuery.trim() || undefined,
        status: statusFilter !== "ALL" ? statusFilter : undefined,
        is_email_verified: isVerifiedParam,
        ordering,
      });

      setBuyers(res.results || []);
      setTotalCount(res.count || 0);
      setTotalPages(res.total_pages || 1);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load buyer accounts.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [currentPage, pageSize, searchQuery, statusFilter, emailVerifiedFilter, ordering]);

  useEffect(() => {
    fetchBuyers();
  }, [fetchBuyers]);

  // Fetch full details when opening drawer
  const openDetailDrawer = async (id: string) => {
    setSelectedBuyerId(id);
    setLoadingDetail(true);
    setBuyerDetail(null);
    try {
      const detail = await api.admin.buyers.get(id);
      setBuyerDetail(detail);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load buyer details.");
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleStatusSubmit = async () => {
    if (!actionTarget) return;
    setSubmittingAction(true);
    try {
      await api.admin.buyers.updateStatus(actionTarget.id, {
        action: actionType,
        reason: actionReason.trim() || undefined,
      });

      setFeedback({
        type: "success",
        message: `Buyer account ${actionTarget.email} was successfully ${actionType.toLowerCase()}ed.`,
      });
      setActionTarget(null);
      setActionReason("");
      fetchBuyers(true);
      if (selectedBuyerId === actionTarget.id) {
        openDetailDrawer(actionTarget.id);
      }
    } catch (err: unknown) {
      setFeedback({
        type: "error",
        message: err instanceof Error ? err.message : "Failed to update buyer status.",
      });
    } finally {
      setSubmittingAction(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            Buyer Account Management
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Centrally oversee all registered marketplace buyers, monitor order activities, inspect buyer history, and govern account permissions.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchBuyers(true)}
            disabled={refreshing}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-slate-700 bg-white dark:bg-slate-800 dark:text-slate-200 border border-slate-300 dark:border-slate-700 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700/60 shadow-sm transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Alerts */}
      {feedback && (
        <div
          className={`p-4 rounded-xl flex items-center justify-between gap-3 text-sm ${
            feedback.type === "success"
              ? "bg-emerald-50 text-emerald-800 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800"
              : "bg-red-50 text-red-800 border border-red-200 dark:bg-red-950/40 dark:text-red-300 dark:border-red-800"
          }`}
        >
          <div className="flex items-center gap-2">
            {feedback.type === "success" ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 shrink-0" />
            ) : (
              <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0" />
            )}
            <span>{feedback.message}</span>
          </div>
          <button
            onClick={() => setFeedback(null)}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {error && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 dark:bg-red-950/40 dark:border-red-800 dark:text-red-300 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0" />
          <span className="text-sm">{error}</span>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-4 shadow-sm space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
          {/* Search */}
          <div className="md:col-span-5 relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
            <input
              type="text"
              placeholder="Search by buyer name, email, phone, or ID..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full pl-9 pr-4 py-2 text-sm bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Status Filter */}
          <div className="md:col-span-2">
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="ALL">Account: All Statuses</option>
              <option value="ACTIVE">Active</option>
              <option value="SUSPENDED">Suspended</option>
            </select>
          </div>

          {/* Email Verified Filter */}
          <div className="md:col-span-2">
            <select
              value={emailVerifiedFilter}
              onChange={(e) => {
                setEmailVerifiedFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="ALL">Email: All</option>
              <option value="VERIFIED">Email Verified</option>
              <option value="UNVERIFIED">Email Unverified</option>
            </select>
          </div>

          {/* Sorter */}
          <div className="md:col-span-3">
            <select
              value={ordering}
              onChange={(e) => {
                setOrdering(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="-created_at">Joined: Newest First</option>
              <option value="created_at">Joined: Oldest First</option>
              <option value="first_name">Name: A to Z</option>
              <option value="-first_name">Name: Z to A</option>
            </select>
          </div>
        </div>

        {/* Page size and counter */}
        <div className="flex flex-wrap items-center justify-between text-xs text-slate-500 dark:text-slate-400 pt-2 border-t border-slate-100 dark:border-slate-700/50">
          <div className="flex items-center gap-2">
            <span>Showing records:</span>
            <span className="font-semibold text-slate-700 dark:text-slate-200">
              {totalCount > 0 ? (currentPage - 1) * pageSize + 1 : 0} -{" "}
              {Math.min(currentPage * pageSize, totalCount)}
            </span>
            <span>of</span>
            <span className="font-semibold text-slate-700 dark:text-slate-200">{totalCount}</span>
            <span>registered buyers</span>
          </div>

          <div className="flex items-center gap-2">
            <span>Rows per page:</span>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setCurrentPage(1);
              }}
              className="px-2 py-1 text-xs bg-slate-50 dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded text-slate-700 dark:text-slate-200 focus:outline-none"
            >
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>
        </div>
      </div>

      {/* Table Section */}
      <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-600 dark:text-slate-300">
            <thead className="bg-slate-50 dark:bg-slate-900/50 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th scope="col" className="px-6 py-3.5">
                  Buyer Information
                </th>
                <th scope="col" className="px-6 py-3.5">
                  Contact
                </th>
                <th scope="col" className="px-6 py-3.5">
                  Account Status
                </th>
                <th scope="col" className="px-6 py-3.5">
                  Activity Metrics
                </th>
                <th scope="col" className="px-6 py-3.5">
                  Joined Date
                </th>
                <th scope="col" className="px-6 py-3.5 text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
              {loading && buyers.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-slate-400">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-slate-400" />
                    Loading buyer accounts...
                  </td>
                </tr>
              ) : buyers.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-slate-500 dark:text-slate-400">
                    <User className="w-8 h-8 mx-auto mb-2 text-slate-300 dark:text-slate-600" />
                    No buyer accounts match the selected filters.
                  </td>
                </tr>
              ) : (
                buyers.map((buyer) => (
                  <tr
                    key={buyer.id}
                    className="hover:bg-slate-50 dark:hover:bg-slate-700/40 transition-colors"
                  >
                    {/* Buyer Information */}
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 flex items-center justify-center font-semibold text-sm shrink-0">
                          {buyer.first_name?.[0]?.toUpperCase() ||
                            buyer.email[0]?.toUpperCase()}
                        </div>
                        <div>
                          <div className="font-medium text-slate-900 dark:text-white">
                            {buyer.full_name || "Unnamed Buyer"}
                          </div>
                          <div className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1.5 mt-0.5">
                            <Mail className="w-3.5 h-3.5" />
                            <span>{buyer.email}</span>
                          </div>
                        </div>
                      </div>
                    </td>

                    {/* Contact info */}
                    <td className="px-6 py-4">
                      <div className="space-y-1 text-xs">
                        {buyer.phone_number ? (
                          <div className="flex items-center gap-1.5 text-slate-600 dark:text-slate-300">
                            <Phone className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                            <span>{buyer.phone_number}</span>
                          </div>
                        ) : (
                          <span className="text-slate-400 italic">No phone recorded</span>
                        )}
                        <div className="flex items-center gap-1.5">
                          {buyer.is_email_verified ? (
                            <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400 font-medium">
                              <CheckCircle className="w-3 h-3" />
                              Email verified
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-400">
                              <Clock className="w-3 h-3" />
                              Unverified
                            </span>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Account Status */}
                    <td className="px-6 py-4">
                      {buyer.is_active ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-300 border border-red-200 dark:border-red-800">
                          <XCircle className="w-3.5 h-3.5" />
                          Suspended
                        </span>
                      )}
                    </td>

                    {/* Metrics */}
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-4 text-xs">
                        <div className="flex items-center gap-1.5 text-slate-700 dark:text-slate-300">
                          <ShoppingBag className="w-4 h-4 text-blue-500" />
                          <span>
                            <strong className="font-semibold">{buyer.metrics?.orders_count || 0}</strong> orders
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5 text-slate-700 dark:text-slate-300">
                          <AlertOctagon className="w-4 h-4 text-amber-500" />
                          <span>
                            <strong className="font-semibold">{buyer.metrics?.disputes_count || 0}</strong> disputes
                          </span>
                        </div>
                      </div>
                    </td>

                    {/* Joined Date */}
                    <td className="px-6 py-4 text-xs text-slate-500 dark:text-slate-400">
                      {buyer.date_joined || buyer.created_at ? (
                        new Date(buyer.date_joined || buyer.created_at!).toLocaleDateString("en-US", {
                          year: "numeric",
                          month: "short",
                          day: "numeric",
                        })
                      ) : (
                        "—"
                      )}
                    </td>

                    {/* Actions */}
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {/* Inspect detail */}
                        <button
                          onClick={() => openDetailDrawer(buyer.id)}
                          className="p-1.5 text-slate-500 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
                          title="Inspect Buyer Account Details"
                        >
                          <Eye className="w-4 h-4" />
                        </button>

                        {/* Suspend or Reactivate */}
                        {buyer.is_active ? (
                          <button
                            onClick={() => {
                              setActionTarget(buyer);
                              setActionType("SUSPEND");
                              setActionReason("");
                            }}
                            className="p-1.5 text-amber-600 hover:text-amber-700 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-950/40 rounded-lg transition-colors"
                            title="Suspend Buyer Account"
                          >
                            <ShieldAlert className="w-4 h-4" />
                          </button>
                        ) : (
                          <button
                            onClick={() => {
                              setActionTarget(buyer);
                              setActionType("REACTIVATE");
                              setActionReason("");
                            }}
                            className="p-1.5 text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/40 rounded-lg transition-colors"
                            title="Reactivate Buyer Account"
                          >
                            <ShieldCheck className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Server-Side Pagination Bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/40 text-sm">
          <div className="text-slate-500 dark:text-slate-400 text-xs">
            Page <span className="font-semibold text-slate-900 dark:text-white">{currentPage}</span> of{" "}
            <span className="font-semibold text-slate-900 dark:text-white">{totalPages}</span> ({totalCount} total buyers)
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage <= 1 || loading}
              className="px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors inline-flex items-center gap-1"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              Previous
            </button>

            {/* Page buttons */}
            {Array.from({ length: Math.min(5, totalPages) }, (_, idx) => {
              let pageNum = idx + 1;
              if (totalPages > 5 && currentPage > 3) {
                pageNum = Math.min(currentPage - 3 + idx + 1, totalPages);
              }
              return (
                <button
                  key={pageNum}
                  onClick={() => setCurrentPage(pageNum)}
                  disabled={loading}
                  className={`w-8 h-8 text-xs font-medium rounded-lg transition-colors ${
                    currentPage === pageNum
                      ? "bg-blue-600 text-white font-semibold shadow-sm"
                      : "bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700"
                  }`}
                >
                  {pageNum}
                </button>
              );
            })}

            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage >= totalPages || loading}
              className="px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors inline-flex items-center gap-1"
            >
              Next
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Inspect Detail Drawer */}
      {selectedBuyerId && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-slate-900/50 backdrop-blur-sm flex justify-end">
          <div className="w-full max-w-2xl bg-white dark:bg-slate-900 h-full shadow-2xl flex flex-col border-l border-slate-200 dark:border-slate-800">
            {/* Drawer Header */}
            <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  <User className="w-5 h-5 text-blue-600" />
                  Buyer Account Details
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  ID: {selectedBuyerId}
                </p>
              </div>
              <button
                onClick={() => setSelectedBuyerId(null)}
                className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {loadingDetail ? (
                <div className="py-20 text-center text-slate-400">
                  <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-2 text-blue-500" />
                  Loading buyer account details...
                </div>
              ) : buyerDetail ? (
                <>
                  {/* Account overview card */}
                  <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="font-semibold text-slate-900 dark:text-white text-base">
                        {buyerDetail.buyer.full_name || "Unnamed Buyer"}
                      </div>
                      {buyerDetail.buyer.is_active ? (
                        <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                          ACTIVE ACCOUNT
                        </span>
                      ) : (
                        <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300">
                          SUSPENDED
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-3 text-xs text-slate-600 dark:text-slate-300 pt-2 border-t border-slate-200 dark:border-slate-700/60">
                      <div>
                        <span className="text-slate-400 block">Email Address:</span>
                        <span className="font-medium text-slate-900 dark:text-white">
                          {buyerDetail.buyer.email}
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-400 block">Phone Number:</span>
                        <span className="font-medium text-slate-900 dark:text-white">
                          {buyerDetail.buyer.phone_number || "Not provided"}
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-400 block">Email Status:</span>
                        <span className="font-medium text-slate-900 dark:text-white">
                          {buyerDetail.buyer.is_email_verified ? "Verified" : "Unverified"}
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-400 block">Registered:</span>
                        <span className="font-medium text-slate-900 dark:text-white">
                          {buyerDetail.buyer.date_joined || buyerDetail.buyer.created_at
                            ? new Date(
                                buyerDetail.buyer.date_joined || buyerDetail.buyer.created_at!
                              ).toLocaleDateString()
                            : "—"}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Activity Summary Stats */}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="p-4 rounded-xl bg-blue-50/50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-900/50">
                      <div className="text-xs text-blue-600 dark:text-blue-400 font-medium">
                        Total Orders Placed
                      </div>
                      <div className="text-2xl font-bold text-slate-900 dark:text-white mt-1">
                        {buyerDetail.metrics?.orders_count || 0}
                      </div>
                    </div>
                    <div className="p-4 rounded-xl bg-amber-50/50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/50">
                      <div className="text-xs text-amber-600 dark:text-amber-400 font-medium">
                        Disputes / Return Requests
                      </div>
                      <div className="text-2xl font-bold text-slate-900 dark:text-white mt-1">
                        {buyerDetail.metrics?.disputes_count || 0}
                      </div>
                    </div>
                  </div>

                  {/* Recent Orders Section */}
                  <div className="space-y-3">
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                      <ShoppingBag className="w-4 h-4 text-blue-500" />
                      Recent Orders ({buyerDetail.recent_orders?.length || 0})
                    </h4>
                    {buyerDetail.recent_orders && buyerDetail.recent_orders.length > 0 ? (
                      <div className="space-y-2">
                        {buyerDetail.recent_orders.map((ord) => (
                          <div
                            key={ord.id}
                            className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/40 text-xs flex items-center justify-between"
                          >
                            <div>
                              <div className="font-semibold text-slate-900 dark:text-white">
                                {ord.order_number}
                              </div>
                              <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                                {ord.created_at
                                  ? new Date(ord.created_at).toLocaleDateString()
                                  : "—"}
                              </div>
                            </div>
                            <div className="text-right">
                              <div className="font-semibold text-slate-900 dark:text-white">
                                {ord.currency} {ord.total_amount}
                              </div>
                              <span className="inline-block mt-0.5 px-2 py-0.5 rounded text-[10px] font-medium uppercase bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300">
                                {ord.status}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-slate-400 italic">No orders found for this buyer.</p>
                    )}
                  </div>

                  {/* Recent Disputes Section */}
                  <div className="space-y-3">
                    <h4 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                      <AlertOctagon className="w-4 h-4 text-amber-500" />
                      Recent Disputes & Returns ({buyerDetail.recent_disputes?.length || 0})
                    </h4>
                    {buyerDetail.recent_disputes && buyerDetail.recent_disputes.length > 0 ? (
                      <div className="space-y-2">
                        {buyerDetail.recent_disputes.map((disp) => (
                          <div
                            key={disp.id}
                            className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/40 text-xs flex items-center justify-between"
                          >
                            <div>
                              <div className="font-semibold text-slate-900 dark:text-white">
                                {disp.dispute_number}
                              </div>
                              <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                                Category: {disp.category}
                              </div>
                            </div>
                            <div className="text-right">
                              <span className="inline-block px-2 py-0.5 rounded text-[10px] font-medium uppercase bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300">
                                {disp.status}
                              </span>
                              <div className="text-[11px] text-slate-400 mt-0.5">
                                {disp.created_at
                                  ? new Date(disp.created_at).toLocaleDateString()
                                  : "—"}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-slate-400 italic">No disputes registered for this buyer.</p>
                    )}
                  </div>
                </>
              ) : null}
            </div>

            {/* Drawer Footer Actions */}
            <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 flex items-center justify-end gap-3">
              <button
                onClick={() => setSelectedBuyerId(null)}
                className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Account Action Modal (Suspend / Reactivate) */}
      {actionTarget && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 p-6 space-y-4">
            <div className="flex items-center gap-3">
              {actionType === "SUSPEND" ? (
                <div className="w-10 h-10 rounded-full bg-red-100 dark:bg-red-950/60 text-red-600 dark:text-red-400 flex items-center justify-center shrink-0">
                  <ShieldAlert className="w-5 h-5" />
                </div>
              ) : (
                <div className="w-10 h-10 rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0">
                  <ShieldCheck className="w-5 h-5" />
                </div>
              )}
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-white">
                  {actionType === "SUSPEND" ? "Suspend Buyer Account" : "Reactivate Buyer Account"}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {actionTarget.email}
                </p>
              </div>
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
              {actionType === "SUSPEND"
                ? "Suspending this buyer account will immediately revoke login sessions and prevent the customer from placing orders or booking workshop services. Are you sure you wish to proceed?"
                : "Reactivating this account will restore standard marketplace access and ordering privileges for this customer."}
            </p>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Reason / Internal Notes (Optional)
              </label>
              <textarea
                value={actionReason}
                onChange={(e) => setActionReason(e.target.value)}
                placeholder="Specify policy violation, customer request, or administrative reason..."
                rows={3}
                className="w-full p-2.5 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setActionTarget(null)}
                disabled={submittingAction}
                className="px-4 py-2 text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleStatusSubmit}
                disabled={submittingAction}
                className={`px-4 py-2 text-xs font-semibold text-white rounded-lg transition-colors flex items-center gap-1.5 ${
                  actionType === "SUSPEND"
                    ? "bg-red-600 hover:bg-red-700"
                    : "bg-emerald-600 hover:bg-emerald-700"
                } disabled:opacity-50`}
              >
                {submittingAction && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                {actionType === "SUSPEND" ? "Confirm Suspension" : "Confirm Reactivation"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

