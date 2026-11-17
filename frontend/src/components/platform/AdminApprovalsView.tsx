"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import { api, ApprovalRequestItem } from "@/lib/api/client";
import {
  ShieldCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Search,
  RefreshCw,
  Eye,
  Check,
  Ban,
  PlayCircle,
  AlertOctagon,
  Lock,
  FileText,
} from "lucide-react";

type TabStatus = "ALL" | "PENDING" | "APPROVED" | "EXECUTED" | "REJECTED" | "CANCELLED";

export default function AdminApprovalsView() {
  const { user } = useAuth();
  const [requests, setRequests] = useState<ApprovalRequestItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabStatus>("PENDING");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [actionFilter, setActionFilter] = useState<string>("ALL");

  // Review & Detail Modal state
  const [selectedRequest, setSelectedRequest] = useState<ApprovalRequestItem | null>(null);
  const [actionModalType, setActionModalType] = useState<"REVIEW" | "EXECUTE" | "CANCEL" | null>(null);
  const [actionNotes, setActionNotes] = useState<string>("");
  const [rejectionReason, setRejectionReason] = useState<string>("");
  const [submittingAction, setSubmittingAction] = useState<boolean>(false);
  const [feedbackMessage, setFeedbackMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const fetchApprovals = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const params: { status?: string; search?: string } = {};
      if (activeTab !== "ALL") {
        params.status = activeTab;
      }
      if (searchQuery.trim()) {
        params.search = searchQuery.trim();
      }
      const resp = await api.approvals.list(params);
      if (resp && resp.results) {
        setRequests(resp.results);
      }
    } catch (err: unknown) {
      setError((err as Error)?.message || "Failed to load approval requests from the platform server.");
    } finally {
      setLoading(false);
    }
  }, [activeTab, searchQuery]);

  useEffect(() => {
    let isMounted = true;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const params: { status?: string; search?: string } = {};
        if (activeTab !== "ALL") {
          params.status = activeTab;
        }
        if (searchQuery.trim()) {
          params.search = searchQuery.trim();
        }
        const resp = await api.approvals.list(params);
        if (isMounted && resp && resp.results) {
          setRequests(resp.results);
        }
      } catch (err: unknown) {
        if (isMounted) {
          setError((err as Error)?.message || "Failed to load approval requests from the platform server.");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    })();
    return () => {
      isMounted = false;
    };
  }, [activeTab, searchQuery]);

  // Key metrics
  const metrics = useMemo(() => {
    const pending = requests.filter((r) => r.status === "PENDING").length;
    const approved = requests.filter((r) => r.status === "APPROVED").length;
    const executed = requests.filter((r) => r.status === "EXECUTED").length;
    const rejected = requests.filter((r) => r.status === "REJECTED" || r.status === "CANCELLED").length;
    return { pending, approved, executed, rejected, total: requests.length };
  }, [requests]);

  const filteredRequests = useMemo(() => {
    return requests.filter((req) => {
      if (actionFilter !== "ALL" && req.action_type !== actionFilter) {
        return false;
      }
      return true;
    });
  }, [requests, actionFilter]);

  const handleApprove = async () => {
    if (!selectedRequest) return;
    try {
      setSubmittingAction(true);
      const resp = await api.approvals.approve(selectedRequest.id, actionNotes);
      setFeedbackMessage({
        type: "success",
        text: resp.message || "Approval request approved successfully.",
      });
      closeModal();
      await fetchApprovals();
    } catch (err: unknown) {
      setFeedbackMessage({
        type: "error",
        text: (err as Error)?.message || "Failed to approve request. Maker-checker policy violated or insufficient permissions.",
      });
    } finally {
      setSubmittingAction(false);
    }
  };

  const handleReject = async () => {
    if (!selectedRequest) return;
    if (!rejectionReason.trim()) {
      setFeedbackMessage({ type: "error", text: "Please enter a mandatory rejection reason." });
      return;
    }
    try {
      setSubmittingAction(true);
      const resp = await api.approvals.reject(selectedRequest.id, rejectionReason, actionNotes);
      setFeedbackMessage({
        type: "success",
        text: resp.message || "Approval request rejected.",
      });
      closeModal();
      await fetchApprovals();
    } catch (err: unknown) {
      setFeedbackMessage({
        type: "error",
        text: (err as Error)?.message || "Failed to reject request.",
      });
    } finally {
      setSubmittingAction(false);
    }
  };

  const handleCancel = async () => {
    if (!selectedRequest) return;
    try {
      setSubmittingAction(true);
      const resp = await api.approvals.cancel(selectedRequest.id, actionNotes);
      setFeedbackMessage({
        type: "success",
        text: resp.message || "Approval request cancelled.",
      });
      closeModal();
      await fetchApprovals();
    } catch (err: unknown) {
      setFeedbackMessage({
        type: "error",
        text: (err as Error)?.message || "Failed to cancel request.",
      });
    } finally {
      setSubmittingAction(false);
    }
  };

  const handleExecute = async () => {
    if (!selectedRequest) return;
    try {
      setSubmittingAction(true);
      const resp = await api.approvals.execute(selectedRequest.id);
      setFeedbackMessage({
        type: "success",
        text: resp.message || "Request executed successfully. Financial gateway dispatched.",
      });
      closeModal();
      await fetchApprovals();
    } catch (err: unknown) {
      setFeedbackMessage({
        type: "error",
        text: (err as Error)?.message || "Execution failed. Check gateway provider status and payment references.",
      });
    } finally {
      setSubmittingAction(false);
    }
  };

  const openModal = (req: ApprovalRequestItem, type: "REVIEW" | "EXECUTE" | "CANCEL") => {
    setSelectedRequest(req);
    setActionModalType(type);
    setActionNotes("");
    setRejectionReason("");
    setFeedbackMessage(null);
  };

  const closeModal = () => {
    setSelectedRequest(null);
    setActionModalType(null);
    setActionNotes("");
    setRejectionReason("");
  };

  return (
    <div className="space-y-6 p-6 max-w-7xl mx-auto">
      {/* Top Header */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-white shadow-xl relative overflow-hidden">
        <div className="absolute right-0 top-0 translate-x-8 -translate-y-8 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="p-2 bg-emerald-500/20 text-emerald-400 rounded-lg">
                <ShieldCheck className="w-6 h-6" />
              </span>
              <h1 className="text-2xl font-bold tracking-tight">Maker-Checker Approval Engine</h1>
            </div>
            <p className="text-slate-400 text-sm mt-1.5 max-w-2xl">
              Strict dual-authorization governance. Requester cannot review or approve their own submissions. High-value
              financial actions require independent checker authorization prior to external gateway execution.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
            {user?.email && (
              <div className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700/80 text-xs text-slate-300">
                Staff: <strong className="text-white">{user.email}</strong>
              </div>
            )}
            <div className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700/80 text-xs text-slate-300 flex items-center gap-2">
              <Lock className="w-3.5 h-3.5 text-amber-400" />
              <span>
                Proposed Dual-Auth Thresholds: <strong className="text-white">£500.00 GBP</strong> /{" "}
                <strong className="text-white">₹50,000.00 INR</strong>
              </span>
            </div>
            <button
              onClick={fetchApprovals}
              disabled={loading}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg border border-slate-700 transition flex items-center gap-1.5"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
          </div>
        </div>

        {/* Global Feedback Alert */}
        {feedbackMessage && (
          <div
            className={`mt-4 p-3.5 rounded-lg border text-sm flex items-start justify-between gap-3 ${
              feedbackMessage.type === "success"
                ? "bg-emerald-950/60 border-emerald-800/80 text-emerald-300"
                : "bg-red-950/60 border-red-800/80 text-red-300"
            }`}
          >
            <div className="flex items-center gap-2">
              {feedbackMessage.type === "success" ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
              ) : (
                <AlertTriangle className="w-5 h-5 text-red-400 shrink-0" />
              )}
              <span>{feedbackMessage.text}</span>
            </div>
            <button
              onClick={() => setFeedbackMessage(null)}
              className="text-xs text-slate-400 hover:text-white transition"
            >
              Dismiss
            </button>
          </div>
        )}
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div
          onClick={() => setActiveTab("PENDING")}
          className={`cursor-pointer p-4 rounded-xl border transition ${
            activeTab === "PENDING"
              ? "bg-amber-500/10 border-amber-500/50"
              : "bg-slate-900/60 border-slate-800 hover:border-slate-700"
          }`}
        >
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Pending Review</span>
            <Clock className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-white mt-1">{metrics.pending}</div>
          <div className="text-[11px] text-amber-400/90 mt-1">Awaiting independent checker</div>
        </div>

        <div
          onClick={() => setActiveTab("APPROVED")}
          className={`cursor-pointer p-4 rounded-xl border transition ${
            activeTab === "APPROVED"
              ? "bg-blue-500/10 border-blue-500/50"
              : "bg-slate-900/60 border-slate-800 hover:border-slate-700"
          }`}
        >
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Approved / Ready</span>
            <CheckCircle2 className="w-4 h-4 text-blue-400" />
          </div>
          <div className="text-2xl font-bold text-white mt-1">{metrics.approved}</div>
          <div className="text-[11px] text-blue-400/90 mt-1">Authorized for gateway execution</div>
        </div>

        <div
          onClick={() => setActiveTab("EXECUTED")}
          className={`cursor-pointer p-4 rounded-xl border transition ${
            activeTab === "EXECUTED"
              ? "bg-emerald-500/10 border-emerald-500/50"
              : "bg-slate-900/60 border-slate-800 hover:border-slate-700"
          }`}
        >
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Executed</span>
            <PlayCircle className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-white mt-1">{metrics.executed}</div>
          <div className="text-[11px] text-emerald-400/90 mt-1">Dispatched to payment gateway</div>
        </div>

        <div
          onClick={() => setActiveTab("REJECTED")}
          className={`cursor-pointer p-4 rounded-xl border transition ${
            activeTab === "REJECTED"
              ? "bg-red-500/10 border-red-500/50"
              : "bg-slate-900/60 border-slate-800 hover:border-slate-700"
          }`}
        >
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Rejected / Cancelled</span>
            <Ban className="w-4 h-4 text-red-400" />
          </div>
          <div className="text-2xl font-bold text-white mt-1">{metrics.rejected}</div>
          <div className="text-[11px] text-red-400/90 mt-1">Denied or revoked requests</div>
        </div>
      </div>

      {/* Filter and Tab Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto w-full md:w-auto pb-1 md:pb-0">
          {(["PENDING", "APPROVED", "EXECUTED", "REJECTED", "CANCELLED", "ALL"] as TabStatus[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-3.5 py-1.5 text-xs font-medium rounded-lg transition whitespace-nowrap ${
                activeTab === tab
                  ? "bg-emerald-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              }`}
            >
              {tab === "ALL" ? "All Requests" : tab}
            </button>
          ))}
        </div>

        {/* Search and Action Filter */}
        <div className="flex items-center gap-3 w-full md:w-auto">
          <div className="relative flex-1 md:w-64">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search by ID, target, reason..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 bg-slate-800/80 border border-slate-700 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
            />
          </div>

          <select
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="px-3 py-1.5 bg-slate-800/80 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
          >
            <option value="ALL">All Actions</option>
            <option value="REFUND_DISPATCH">Refund Dispatch</option>
          </select>
        </div>
      </div>

      {/* Main Table / Requests List */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow">
        {loading ? (
          <div className="py-20 flex flex-col items-center justify-center gap-3 text-slate-400">
            <RefreshCw className="w-8 h-8 animate-spin text-emerald-400" />
            <span className="text-sm">Loading dual-authorization requests...</span>
          </div>
        ) : error ? (
          <div className="py-16 text-center text-red-400">
            <AlertOctagon className="w-10 h-10 mx-auto text-red-500 mb-2" />
            <p className="text-sm font-semibold">{error}</p>
            <button
              onClick={fetchApprovals}
              className="mt-3 px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs text-white rounded-lg border border-slate-700"
            >
              Try Again
            </button>
          </div>
        ) : filteredRequests.length === 0 ? (
          <div className="py-20 text-center text-slate-400">
            <FileText className="w-12 h-12 mx-auto text-slate-600 mb-3" />
            <p className="text-sm font-medium text-slate-300">No approval requests found</p>
            <p className="text-xs text-slate-500 mt-1">
              {activeTab === "PENDING"
                ? "There are currently no high-value transactions awaiting checker review."
                : "No records match the current filter selection."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-800/80 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="py-3.5 px-4 font-semibold">Request / Target</th>
                  <th className="py-3.5 px-4 font-semibold">Amount & Currency</th>
                  <th className="py-3.5 px-4 font-semibold">Maker (Requester)</th>
                  <th className="py-3.5 px-4 font-semibold">Checker (Approver)</th>
                  <th className="py-3.5 px-4 font-semibold">Status</th>
                  <th className="py-3.5 px-4 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filteredRequests.map((req) => {
                  const isMaker = req.is_requester;
                  return (
                    <tr key={req.id} className="hover:bg-slate-800/40 transition">
                      {/* Request / Target */}
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-white flex items-center gap-1.5">
                          <span>{req.action_type}</span>
                        </div>
                        <div className="text-[11px] text-slate-400 mt-0.5">
                          Target: {req.target_type} <span className="font-mono text-slate-300">{req.target_id.slice(0, 18)}...</span>
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          {new Date(req.requested_at).toLocaleString()}
                        </div>
                      </td>

                      {/* Amount & Currency */}
                      <td className="py-3.5 px-4">
                        {req.amount ? (
                          <div className="font-mono font-bold text-white text-sm">
                            {req.currency === "GBP" ? "£" : req.currency === "INR" ? "₹" : ""}
                            {Number(req.amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                            <span className="text-[10px] text-slate-400 ml-1 font-normal">{req.currency}</span>
                          </div>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                        <div className="text-[10px] text-slate-400 truncate max-w-[200px]" title={req.reason}>
                          {req.reason || "High-value dual-authorization"}
                        </div>
                      </td>

                      {/* Maker / Requester */}
                      <td className="py-3.5 px-4">
                        <div className="text-white font-medium">
                          {req.requester.first_name || req.requester.last_name
                            ? `${req.requester.first_name} ${req.requester.last_name}`
                            : req.requester.email}
                        </div>
                        <div className="text-[10px] text-slate-400">{req.requester.email}</div>
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          Role: <span className="text-slate-400">{req.requester.staff_role || "Staff"}</span>
                        </div>
                      </td>

                      {/* Checker / Approver */}
                      <td className="py-3.5 px-4">
                        {req.approver ? (
                          <div>
                            <div className="text-white font-medium">
                              {req.approver.first_name || req.approver.last_name
                                ? `${req.approver.first_name} ${req.approver.last_name}`
                                : req.approver.email}
                            </div>
                            <div className="text-[10px] text-slate-400">{req.approver.email}</div>
                            {req.reviewed_at && (
                              <div className="text-[10px] text-slate-500 mt-0.5">
                                Reviewed: {new Date(req.reviewed_at).toLocaleDateString()}
                              </div>
                            )}
                          </div>
                        ) : req.status === "PENDING" ? (
                          <span className="text-amber-400/90 text-xs italic flex items-center gap-1">
                            <Clock className="w-3 h-3" /> Awaiting Checker
                          </span>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>

                      {/* Status */}
                      <td className="py-3.5 px-4">
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold ${
                            req.status === "PENDING"
                              ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                              : req.status === "APPROVED"
                              ? "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                              : req.status === "EXECUTED"
                              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                              : req.status === "REJECTED"
                              ? "bg-red-500/20 text-red-300 border border-red-500/30"
                              : "bg-slate-700/40 text-slate-400 border border-slate-600/30"
                          }`}
                        >
                          {req.status === "PENDING" && <Clock className="w-3 h-3" />}
                          {req.status === "APPROVED" && <CheckCircle2 className="w-3 h-3" />}
                          {req.status === "EXECUTED" && <PlayCircle className="w-3 h-3" />}
                          {req.status === "REJECTED" && <XCircle className="w-3 h-3" />}
                          {req.status}
                        </span>

                        {isMaker && req.status === "PENDING" && (
                          <div className="text-[10px] text-amber-400 font-medium mt-1">
                            Maker (You submitted this)
                          </div>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {/* Review button for eligible checkers */}
                          {req.can_approve && (
                            <button
                              onClick={() => openModal(req, "REVIEW")}
                              className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-medium transition flex items-center gap-1"
                            >
                              <Check className="w-3.5 h-3.5" />
                              Review
                            </button>
                          )}

                          {/* Execute button for approved items */}
                          {req.can_execute && (
                            <button
                              onClick={() => openModal(req, "EXECUTE")}
                              className="px-2.5 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-xs font-medium transition flex items-center gap-1"
                            >
                              <PlayCircle className="w-3.5 h-3.5" />
                              Execute
                            </button>
                          )}

                          {/* Cancel button */}
                          {req.can_cancel && (
                            <button
                              onClick={() => openModal(req, "CANCEL")}
                              className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded text-xs font-medium transition border border-slate-700"
                            >
                              Cancel
                            </button>
                          )}

                          {/* View details */}
                          <button
                            onClick={() => openModal(req, "REVIEW")}
                            className="p-1 hover:bg-slate-800 text-slate-400 hover:text-white rounded transition"
                            title="View Details"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Review / Execute Modal */}
      {selectedRequest && actionModalType && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl">
            {/* Modal Header */}
            <div className="px-6 py-4 bg-slate-800/80 border-b border-slate-700 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-emerald-400" />
                <h3 className="text-base font-semibold text-white">
                  {actionModalType === "REVIEW"
                    ? "Checker Review & Authorization"
                    : actionModalType === "EXECUTE"
                    ? "Execute Approved Transaction"
                    : "Cancel Approval Request"}
                </h3>
              </div>
              <button
                onClick={closeModal}
                disabled={submittingAction}
                className="text-slate-400 hover:text-white transition text-lg"
              >
                &times;
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 space-y-4 max-h-[75vh] overflow-y-auto text-xs text-slate-300">
              {/* Maker-Checker Warning if current user is requester */}
              {selectedRequest.is_requester && selectedRequest.status === "PENDING" && (
                <div className="p-3 bg-amber-950/60 border border-amber-800/80 rounded-xl text-amber-300 flex items-start gap-2.5">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <strong className="font-semibold">Maker-Checker Policy Enforcement:</strong>
                    <p className="mt-0.5 text-slate-300">
                      You are the maker (creator) of this approval request. Under DriverXtra security controls, you cannot
                      approve or reject your own submission. An independent Finance Officer or Platform Administrator must
                      review and authorize this request.
                    </p>
                  </div>
                </div>
              )}

              {/* Transaction Overview Card */}
              <div className="grid grid-cols-2 gap-3 p-4 bg-slate-950/50 rounded-xl border border-slate-800">
                <div>
                  <span className="text-slate-500 text-[10px] uppercase font-bold">Action Type</span>
                  <div className="text-sm font-semibold text-white mt-0.5">{selectedRequest.action_type}</div>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] uppercase font-bold">Target Resource</span>
                  <div className="text-sm font-mono text-slate-300 mt-0.5">
                    {selectedRequest.target_type}: {selectedRequest.target_id}
                  </div>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] uppercase font-bold">Amount</span>
                  <div className="text-base font-bold text-emerald-400 font-mono mt-0.5">
                    {selectedRequest.amount
                      ? `${selectedRequest.currency === "GBP" ? "£" : selectedRequest.currency === "INR" ? "₹" : ""}${Number(
                          selectedRequest.amount
                        ).toLocaleString(undefined, { minimumFractionDigits: 2 })} ${selectedRequest.currency}`
                      : "N/A"}
                  </div>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] uppercase font-bold">Status</span>
                  <div className="mt-0.5">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold ${
                        selectedRequest.status === "PENDING"
                          ? "bg-amber-500/20 text-amber-300"
                          : selectedRequest.status === "APPROVED"
                          ? "bg-blue-500/20 text-blue-300"
                          : selectedRequest.status === "EXECUTED"
                          ? "bg-emerald-500/20 text-emerald-300"
                          : "bg-red-500/20 text-red-300"
                      }`}
                    >
                      {selectedRequest.status}
                    </span>
                  </div>
                </div>
              </div>

              {/* Requester & Reviewer metadata */}
              <div className="grid grid-cols-2 gap-3 p-3 bg-slate-800/40 rounded-xl border border-slate-800">
                <div>
                  <span className="text-slate-500 text-[10px]">Requester</span>
                  <p className="text-white font-medium">{selectedRequest.requester.email}</p>
                  <p className="text-[10px] text-slate-400">Role: {selectedRequest.requester.staff_role || "Staff"}</p>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px]">Approver</span>
                  {selectedRequest.approver ? (
                    <>
                      <p className="text-white font-medium">{selectedRequest.approver.email}</p>
                      <p className="text-[10px] text-slate-400">Role: {selectedRequest.approver.staff_role || "Staff"}</p>
                    </>
                  ) : (
                    <p className="text-amber-400 italic">Pending independent review</p>
                  )}
                </div>
              </div>

              {/* Reason & Payload Details */}
              {selectedRequest.reason && (
                <div>
                  <label className="block text-slate-400 text-[11px] font-semibold mb-1">Reason for Action</label>
                  <div className="p-3 bg-slate-950/60 border border-slate-800 rounded-lg text-slate-200">
                    {selectedRequest.reason}
                  </div>
                </div>
              )}

              {selectedRequest.rejection_reason && (
                <div>
                  <label className="block text-red-400 text-[11px] font-semibold mb-1">Rejection Reason</label>
                  <div className="p-3 bg-red-950/40 border border-red-900/50 rounded-lg text-red-200">
                    {selectedRequest.rejection_reason}
                  </div>
                </div>
              )}

              {selectedRequest.execution_error && (
                <div>
                  <label className="block text-red-400 text-[11px] font-semibold mb-1">Gateway Execution Error</label>
                  <div className="p-3 bg-red-950/40 border border-red-900/50 rounded-lg text-red-200 font-mono text-[11px]">
                    {selectedRequest.execution_error}
                  </div>
                </div>
              )}

              {/* Action Form Elements */}
              {actionModalType === "REVIEW" && selectedRequest.can_approve && (
                <div className="space-y-3 pt-2 border-t border-slate-800">
                  <div>
                    <label className="block text-slate-300 font-medium mb-1">
                      Reviewer Notes (Optional for approval)
                    </label>
                    <textarea
                      rows={2}
                      value={actionNotes}
                      onChange={(e) => setActionNotes(e.target.value)}
                      placeholder="Add compliance notes or gateway dispatch confirmation..."
                      className="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-emerald-500"
                    />
                  </div>

                  <div>
                    <label className="block text-slate-300 font-medium mb-1">
                      Rejection Reason (Mandatory if rejecting)
                    </label>
                    <input
                      type="text"
                      value={rejectionReason}
                      onChange={(e) => setRejectionReason(e.target.value)}
                      placeholder="Provide clear justification if denying authorization..."
                      className="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-red-500"
                    />
                  </div>
                </div>
              )}

              {actionModalType === "EXECUTE" && (
                <div className="p-4 bg-blue-950/40 border border-blue-800/80 rounded-xl space-y-2">
                  <div className="flex items-center gap-2 text-blue-300 font-semibold">
                    <PlayCircle className="w-4 h-4" />
                    <span>Authoritative Gateway Execution</span>
                  </div>
                  <p className="text-slate-300 text-xs">
                    Executing this approved request will trigger the external payment gateway (Razorpay for INR / Stripe
                    for GBP) to dispatch funds. This action creates immutable audit entries and cannot be undone.
                  </p>
                </div>
              )}

              {actionModalType === "CANCEL" && (
                <div className="space-y-3 pt-2 border-t border-slate-800">
                  <p className="text-slate-300 text-xs">
                    Are you sure you want to cancel this pending approval request?
                  </p>
                  <textarea
                    rows={2}
                    value={actionNotes}
                    onChange={(e) => setActionNotes(e.target.value)}
                    placeholder="Reason for cancellation..."
                    className="w-full p-2.5 bg-slate-950 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-slate-500"
                  />
                </div>
              )}
            </div>

            {/* Modal Actions Footer */}
            <div className="px-6 py-4 bg-slate-800/60 border-t border-slate-800 flex items-center justify-between gap-3">
              <button
                onClick={closeModal}
                disabled={submittingAction}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg font-medium transition"
              >
                Close
              </button>

              <div className="flex items-center gap-2">
                {actionModalType === "REVIEW" && selectedRequest.can_approve && (
                  <>
                    <button
                      onClick={handleReject}
                      disabled={submittingAction}
                      className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg font-semibold transition flex items-center gap-1.5"
                    >
                      <XCircle className="w-4 h-4" />
                      Reject Request
                    </button>
                    <button
                      onClick={handleApprove}
                      disabled={submittingAction}
                      className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-semibold transition flex items-center gap-1.5"
                    >
                      <Check className="w-4 h-4" />
                      Approve Request
                    </button>
                  </>
                )}

                {actionModalType === "EXECUTE" && selectedRequest.can_execute && (
                  <button
                    onClick={handleExecute}
                    disabled={submittingAction}
                    className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-semibold transition flex items-center gap-1.5"
                  >
                    <PlayCircle className="w-4 h-4" />
                    Confirm & Execute Dispatch
                  </button>
                )}

                {actionModalType === "CANCEL" && selectedRequest.can_cancel && (
                  <button
                    onClick={handleCancel}
                    disabled={submittingAction}
                    className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg font-semibold transition flex items-center gap-1.5"
                  >
                    Confirm Cancellation
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
