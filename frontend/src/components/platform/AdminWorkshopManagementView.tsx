"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  api,
  AdminWorkshopItem,
  AdminWorkshopDetailResponse,
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
  Wrench,
  Calendar,
  ChevronLeft,
  ChevronRight,
  X,
  ClipboardList,
} from "lucide-react";

export default function AdminWorkshopManagementView() {
  const [workshops, setWorkshops] = useState<AdminWorkshopItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(20);

  const [searchQuery, setSearchQuery] = useState<string>("");
  const [verificationFilter, setVerificationFilter] = useState<string>("ALL");
  const [bookingFilter, setBookingFilter] = useState<string>("ALL");
  const [ordering, setOrdering] = useState<string>("-created_at");

  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Detail Drawer state
  const [selectedWorkshopId, setSelectedWorkshopId] = useState<string | null>(null);
  const [workshopDetail, setWorkshopDetail] = useState<AdminWorkshopDetailResponse | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);

  // Status Action Modal state
  const [actionTarget, setActionTarget] = useState<AdminWorkshopItem | null>(null);
  const [actionType, setActionType] = useState<"VERIFY" | "UNVERIFY" | "SUSPEND" | "REACTIVATE">("VERIFY");
  const [actionReason, setActionReason] = useState<string>("");
  const [submittingAction, setSubmittingAction] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const fetchWorkshops = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const isVerifiedParam =
        verificationFilter === "VERIFIED"
          ? true
          : verificationFilter === "UNVERIFIED"
          ? false
          : undefined;

      const isBookingParam =
        bookingFilter === "ACCEPTING"
          ? true
          : bookingFilter === "PAUSED"
          ? false
          : undefined;

      const res = await api.admin.workshops.list({
        page: currentPage,
        page_size: pageSize,
        q: searchQuery.trim() || undefined,
        is_verified: isVerifiedParam,
        is_accepting_bookings: isBookingParam,
        ordering,
      });

      setWorkshops(res.results || []);
      setTotalCount(res.count || 0);
      setTotalPages(res.total_pages || 1);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load workshops directory.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [currentPage, pageSize, searchQuery, verificationFilter, bookingFilter, ordering]);

  useEffect(() => {
    fetchWorkshops();
  }, [fetchWorkshops]);

  const openDetailDrawer = async (id: string) => {
    setSelectedWorkshopId(id);
    setLoadingDetail(true);
    setWorkshopDetail(null);
    try {
      const detail = await api.admin.workshops.get(id);
      setWorkshopDetail(detail);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load workshop details.");
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleStatusSubmit = async () => {
    if (!actionTarget) return;
    setSubmittingAction(true);
    try {
      await api.admin.workshops.updateStatus(actionTarget.id, {
        action: actionType,
        reason: actionReason.trim() || undefined,
      });

      setFeedback({
        type: "success",
        message: `Workshop '${actionTarget.business_name}' status successfully updated to ${actionType.toLowerCase()}.`,
      });
      setActionTarget(null);
      setActionReason("");
      fetchWorkshops(true);
      if (selectedWorkshopId === actionTarget.id) {
        openDetailDrawer(actionTarget.id);
      }
    } catch (err: unknown) {
      setFeedback({
        type: "error",
        message: err instanceof Error ? err.message : "Failed to update workshop status.",
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
            <span className="px-2.5 py-0.5 text-xs font-bold uppercase tracking-wider rounded-full bg-emerald-100 text-emerald-900 border border-emerald-300">
              Service Partner Oversight
            </span>
            <span className="text-xs font-semibold text-slate-500">
              {totalCount} total workshop{totalCount === 1 ? "" : "s"}
            </span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-slate-900">
            Workshop & Service Center Governance
          </h1>
          <p className="text-sm font-medium text-slate-600 mt-1">
            Server-side paginated oversight of certified service bays, diagnostic hubs, and workshop appointments.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchWorkshops(true)}
            disabled={refreshing}
            className="flex items-center gap-2 px-4 py-2 text-xs font-semibold bg-white hover:bg-slate-50 text-slate-800 rounded-lg border border-slate-300 shadow-sm hover:border-slate-400 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin text-emerald-600" : "text-slate-600"}`} />
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
            onClick={() => fetchWorkshops()}
            className="text-xs font-semibold bg-red-600 hover:bg-red-700 text-white px-3 py-1.5 rounded-lg shadow-sm transition"
          >
            Retry
          </button>
        </div>
      )}

      {/* Filter and Search Controls */}
      <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm flex flex-col md:flex-row gap-4 items-center justify-between">
        {/* Search */}
        <div className="relative w-full md:w-80">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setCurrentPage(1);
            }}
            placeholder="Search workshop, city, email..."
            className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-300 rounded-lg text-xs font-semibold text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 transition"
          />
        </div>

        {/* Dropdowns */}
        <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
          {/* Verification */}
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <span>Verification:</span>
            <select
              value={verificationFilter}
              onChange={(e) => {
                setVerificationFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="bg-slate-50 border border-slate-300 text-slate-900 rounded-lg px-2.5 py-1.5 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-emerald-500"
            >
              <option value="ALL">All Statuses</option>
              <option value="VERIFIED">Verified / Approved</option>
              <option value="UNVERIFIED">Unverified</option>
            </select>
          </div>

          {/* Bookings */}
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
            <span>Bookings:</span>
            <select
              value={bookingFilter}
              onChange={(e) => {
                setBookingFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="bg-slate-50 border border-slate-300 text-slate-900 rounded-lg px-2.5 py-1.5 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-emerald-500"
            >
              <option value="ALL">All</option>
              <option value="ACCEPTING">Accepting Bookings</option>
              <option value="PAUSED">Suspended / Paused</option>
            </select>
          </div>

          {/* Page Size */}
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
            <span>Page Size:</span>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setCurrentPage(1);
              }}
              className="bg-slate-50 border border-slate-300 text-slate-900 rounded-lg px-2 py-1.5 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-emerald-500"
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
                <th className="py-3.5 px-4">Workshop Service Center</th>
                <th className="py-3.5 px-4">Location</th>
                <th className="py-3.5 px-4">Owner / Contact</th>
                <th className="py-3.5 px-4 text-center">Bays</th>
                <th className="py-3.5 px-4">Verification</th>
                <th className="py-3.5 px-4">Bookings</th>
                <th className="py-3.5 px-4 text-center">Services</th>
                <th className="py-3.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700 font-medium">
              {loading && workshops.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-14 text-center text-slate-500">
                    <div className="flex items-center justify-center gap-2">
                      <RefreshCw className="w-5 h-5 animate-spin text-emerald-500" />
                      <span className="font-semibold text-xs">Loading workshop partner network...</span>
                    </div>
                  </td>
                </tr>
              ) : workshops.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-14 text-center text-slate-500">
                    <div className="text-sm font-bold text-slate-900">No workshops found</div>
                    <p className="text-xs text-slate-500 mt-1">Try clearing your filters or search keywords.</p>
                  </td>
                </tr>
              ) : (
                workshops.map((w) => (
                  <tr key={w.id} className="hover:bg-slate-50 transition-colors">
                    {/* Workshop Business */}
                    <td className="py-3.5 px-4">
                      <div className="font-extrabold text-slate-900 text-sm flex items-center gap-1.5">
                        <Wrench className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                        <span>{w.business_name}</span>
                      </div>
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        {w.organisation_id ? `Org ID: ${w.organisation_id.slice(0, 8)}...` : "Independent Service Hub"}
                      </div>
                    </td>

                    {/* Location */}
                    <td className="py-3.5 px-4">
                      <div className="text-slate-900 font-semibold">{w.city || "—"}</div>
                      <div className="text-[11px] text-slate-500 mt-0.5">{w.postal_code || ""}</div>
                    </td>

                    {/* Owner / Contact */}
                    <td className="py-3.5 px-4">
                      <div className="text-slate-900 font-semibold">{w.owner?.email || "No owner assigned"}</div>
                      <div className="text-[11px] text-slate-500 mt-0.5">{w.contact_phone || "No phone"}</div>
                    </td>

                    {/* Service Bays */}
                    <td className="py-3.5 px-4 text-center font-bold text-slate-900">
                      {w.bay_capacity}
                    </td>

                    {/* Verification Status */}
                    <td className="py-3.5 px-4">
                      {w.is_verified ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <CheckCircle2 className="w-3 h-3" />
                          Verified
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-300">
                          Pending Audit
                        </span>
                      )}
                    </td>

                    {/* Bookings Status */}
                    <td className="py-3.5 px-4">
                      {w.is_accepting_bookings ? (
                        <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 font-semibold">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                          Accepting
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] text-rose-700 font-semibold">
                          <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                          Paused
                        </span>
                      )}
                    </td>

                    {/* Services Count */}
                    <td className="py-3.5 px-4 text-center font-bold text-slate-900">
                      {w.metrics.services_count}
                    </td>

                    {/* Actions */}
                    <td className="py-3.5 px-4 text-right space-x-2">
                      <button
                        onClick={() => openDetailDrawer(w.id)}
                        className="px-3 py-1.5 rounded-lg bg-white hover:bg-slate-50 text-slate-800 border border-slate-300 shadow-sm transition text-xs font-semibold"
                      >
                        Inspect
                      </button>

                      {!w.is_verified ? (
                        <button
                          onClick={() => {
                            setActionTarget(w);
                            setActionType("VERIFY");
                          }}
                          className="px-3 py-1.5 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 transition text-xs font-semibold"
                        >
                          Verify
                        </button>
                      ) : (
                        <button
                          onClick={() => {
                            setActionTarget(w);
                            setActionType("UNVERIFY");
                          }}
                          className="px-3 py-1.5 rounded-lg bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200 transition text-xs font-semibold"
                        >
                          Revoke
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
            <span className="font-bold text-slate-900">{totalCount}</span> total workshops)
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

      {/* Inspect Workshop Detail Drawer */}
      {selectedWorkshopId && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex justify-end">
          <div className="w-full max-w-2xl bg-white border-l border-slate-200 h-full overflow-y-auto p-6 space-y-6 shadow-2xl">
            {/* Drawer Header */}
            <div className="flex items-center justify-between pb-4 border-b border-slate-200">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center text-emerald-600 border border-emerald-200">
                  <Wrench className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-lg font-extrabold text-slate-900">Workshop Operational Profile</h3>
                  <p className="text-xs font-mono text-slate-500">ID: {selectedWorkshopId}</p>
                </div>
              </div>
              <button
                onClick={() => setSelectedWorkshopId(null)}
                className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {loadingDetail || !workshopDetail ? (
              <div className="py-20 text-center text-slate-500 text-xs">
                <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-emerald-500" />
                Loading workshop operational dossier...
              </div>
            ) : (
              <div className="space-y-6 text-xs">
                {/* Facility Overview Card */}
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-900">Facility & Verification Status</span>
                    <span
                      className={`px-2.5 py-0.5 rounded text-[11px] font-semibold ${
                        workshopDetail.workshop.is_verified
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                          : "bg-amber-50 text-amber-800 border border-amber-300"
                      }`}
                    >
                      {workshopDetail.workshop.is_verified ? "Verified Partner" : "Pending Verification"}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-3 text-slate-600">
                    <div>
                      <span className="text-slate-500 font-semibold block text-[11px]">Center Name:</span>
                      <span className="text-slate-900 font-bold">{workshopDetail.workshop.business_name}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-semibold block text-[11px]">Owner / Manager:</span>
                      <span className="text-slate-900 font-bold">{workshopDetail.owner?.email || "No owner assigned"}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-semibold block text-[11px]">Service Bays:</span>
                      <span className="text-slate-900 font-bold">{workshopDetail.workshop.bay_capacity} Bays</span>
                    </div>
                    <div>
                      <span className="text-slate-500 font-semibold block text-[11px]">Accepting Bookings:</span>
                      <span className="text-slate-900 font-bold">
                        {workshopDetail.workshop.is_accepting_bookings ? "Yes (Active)" : "No (Paused)"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Services Catalog */}
                <div className="space-y-3">
                  <span className="font-bold text-slate-900 block text-sm">Active Services Catalog ({workshopDetail.services.length})</span>
                  {workshopDetail.services.length === 0 ? (
                    <p className="text-slate-500 italic">No services listed yet.</p>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {workshopDetail.services.map((svc) => (
                        <div key={svc.id} className="p-3 bg-white border border-slate-200 rounded-lg shadow-sm">
                          <div className="font-bold text-slate-900">{svc.name}</div>
                          <div className="text-[11px] text-slate-500 mt-1 flex items-center justify-between">
                            <span>{svc.estimated_duration_minutes} mins</span>
                            <span className="font-extrabold text-slate-900">
                              £{svc.price}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Operational Activity Counts */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm text-center">
                    <span className="text-[11px] font-bold text-slate-500 block uppercase">Total Bookings</span>
                    <span className="text-2xl font-extrabold text-slate-900 mt-1 block">
                      {workshopDetail.metrics.bookings_count}
                    </span>
                  </div>
                  <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm text-center">
                    <span className="text-[11px] font-bold text-slate-500 block uppercase">Work Orders</span>
                    <span className="text-2xl font-extrabold text-slate-900 mt-1 block">
                      {workshopDetail.metrics.work_orders_count}
                    </span>
                  </div>
                  <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm text-center">
                    <span className="text-[11px] font-bold text-slate-500 block uppercase">Active Services</span>
                    <span className="text-2xl font-extrabold text-slate-900 mt-1 block">
                      {workshopDetail.metrics.services_count}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Drawer Footer */}
            <div className="pt-4 border-t border-slate-200 flex justify-end">
              <button
                onClick={() => setSelectedWorkshopId(null)}
                className="px-4 py-2 bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold shadow-sm transition"
              >
                Close Drawer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Action Modal */}
      {actionTarget && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center text-emerald-600 border border-emerald-200 shrink-0">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  {actionType === "VERIFY"
                    ? "Verify Workshop Partner"
                    : actionType === "UNVERIFY"
                    ? "Revoke Verification"
                    : actionType === "SUSPEND"
                    ? "Suspend Workshop"
                    : "Reactivate Workshop"}
                </h3>
                <p className="text-xs font-medium text-slate-500">{actionTarget.business_name}</p>
              </div>
            </div>

            <p className="text-xs font-medium text-slate-600 leading-relaxed">
              Confirm status modification for this workshop facility. This action will be recorded in the platform compliance audit log.
            </p>

            <div className="space-y-1">
              <label className="text-[11px] font-bold text-slate-700 uppercase tracking-wider block">
                Administrative Notes / Reason:
              </label>
              <textarea
                value={actionReason}
                onChange={(e) => setActionReason(e.target.value)}
                placeholder="Enter audit or inspection notes..."
                className="w-full p-2.5 bg-slate-50 border border-slate-300 rounded-lg text-xs font-medium text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 h-20"
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
                className="px-4 py-2 rounded-lg text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-700 shadow-sm transition flex items-center gap-1.5"
              >
                {submittingAction && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>Confirm Action</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
