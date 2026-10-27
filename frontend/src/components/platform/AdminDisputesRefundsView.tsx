"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  api,
  PlatformDispute,
  PlatformRefund,
  PlatformDisputeEvent,
  OrderRefundSummary,
  DisputeCategory,
  DisputeStatus,
  DisputePriority,
  DisputeResolution,
  RefundMethod,
  resolveMediaUrl,
} from "@/lib/api/client";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  Scale,
  RotateCcw,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Search,
  Filter,
  CreditCard,
  Banknote,
  Send,
  MessageSquare,
  ShieldAlert,
  ShieldCheck,
  FileText,
  DollarSign,
  User,
  ArrowRight,
  ExternalLink,
  ChevronRight,
  Copy,
  Check,
  X,
  Loader2,
  RefreshCw,
  Eye,
  AlertCircle,
} from "lucide-react";

export default function AdminDisputesRefundsView() {
  const { user } = useAuth();

  // Navigation
  const [activeTab, setActiveTab] = useState<"disputes" | "refunds" | "issue_refund">("disputes");

  // Disputes state
  const [disputes, setDisputes] = useState<PlatformDispute[]>([]);
  const [disputeFilter, setDisputeFilter] = useState<string>("ALL");
  const [disputeCategoryFilter, setDisputeCategoryFilter] = useState<string>("ALL");
  const [disputeSearch, setDisputeSearch] = useState("");
  const [loadingDisputes, setLoadingDisputes] = useState(false);
  const [disputesError, setDisputesError] = useState<string | null>(null);

  // Selected dispute / Adjudication modal
  const [selectedDispute, setSelectedDispute] = useState<PlatformDispute | null>(null);
  const [adjudicateStatus, setAdjudicateStatus] = useState<DisputeStatus>("UNDER_REVIEW");
  const [adjudicateResolution, setAdjudicateResolution] = useState<DisputeResolution | "">("");
  const [adjudicateNotes, setAdjudicateNotes] = useState("");
  const [isAdjudicating, setIsAdjudicating] = useState(false);
  const [adjudicateError, setAdjudicateError] = useState<string | null>(null);

  // Dispute messaging
  const [chatMessage, setChatMessage] = useState("");
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  // Refunds state
  const [refunds, setRefunds] = useState<PlatformRefund[]>([]);
  const [refundFilter, setRefundFilter] = useState<string>("ALL");
  const [refundSearch, setRefundSearch] = useState("");
  const [loadingRefunds, setLoadingRefunds] = useState(false);
  const [refundsError, setRefundsError] = useState<string | null>(null);

  // Settle / Process refund modal
  const [processModalRefund, setProcessModalRefund] = useState<PlatformRefund | null>(null);
  const [gatewayRefInput, setGatewayRefInput] = useState("");
  const [processNotesInput, setProcessNotesInput] = useState("");
  const [isProcessingRefund, setIsProcessingRefund] = useState(false);
  const [processRefundError, setProcessRefundError] = useState<string | null>(null);

  // Issue Refund Tool State
  const [orderQuery, setOrderQuery] = useState("");
  const [refundSummary, setRefundSummary] = useState<OrderRefundSummary | null>(null);
  const [fetchingSummary, setFetchingSummary] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const [refundAmountInput, setRefundAmountInput] = useState("");
  const [refundReasonInput, setRefundReasonInput] = useState("");
  const [refundMethodInput, setRefundMethodInput] = useState<RefundMethod>("ORIGINAL_PAYMENT");
  const [refundNotesInput, setRefundNotesInput] = useState("");
  const [autoProcessInput, setAutoProcessInput] = useState(true);
  const [linkedDisputeId, setLinkedDisputeId] = useState("");
  const [isSubmittingRefund, setIsSubmittingRefund] = useState(false);
  const [issueRefundError, setIssueRefundError] = useState<string | null>(null);

  // Feedback banners
  const [successBanner, setSuccessBanner] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Load disputes
  const loadDisputes = useCallback(async () => {
    setLoadingDisputes(true);
    setDisputesError(null);
    try {
      const data = await api.marketplace.listAdminDisputes(
        disputeFilter !== "ALL" ? disputeFilter : undefined,
        disputeCategoryFilter !== "ALL" ? disputeCategoryFilter : undefined
      );
      setDisputes(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      setDisputesError(err instanceof Error ? err.message : "Failed to load disputes queue.");
    } finally {
      setLoadingDisputes(false);
    }
  }, [disputeFilter, disputeCategoryFilter]);

  // Load refunds
  const loadRefunds = useCallback(async () => {
    setLoadingRefunds(true);
    setRefundsError(null);
    try {
      const data = await api.marketplace.listAdminRefunds(
        refundFilter !== "ALL" ? refundFilter : undefined
      );
      setRefunds(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      setRefundsError(err instanceof Error ? err.message : "Failed to load refunds list.");
    } finally {
      setLoadingRefunds(false);
    }
  }, [refundFilter]);

  useEffect(() => {
    if (activeTab === "disputes") {
      loadDisputes();
    } else if (activeTab === "refunds") {
      loadRefunds();
    }
  }, [activeTab, loadDisputes, loadRefunds]);

  // Handle dispute adjudication
  const handleAdjudicateDispute = async () => {
    if (!selectedDispute) return;
    setIsAdjudicating(true);
    setAdjudicateError(null);
    try {
      const res = await api.marketplace.updateAdminDisputeStatus(selectedDispute.dispute_number, {
        status: adjudicateStatus,
        resolution: adjudicateResolution ? (adjudicateResolution as DisputeResolution) : undefined,
        resolution_notes: adjudicateNotes,
      });

      if (res.status === "success" && res.dispute) {
        setDisputes((prev) =>
          prev.map((d) => (d.id === res.dispute.id ? res.dispute : d))
        );
        setSelectedDispute(res.dispute);
        setSuccessBanner(`Dispute ${res.dispute.dispute_number} updated to ${res.dispute.status}.`);
      } else {
        throw new Error(res.message || "Failed to update dispute.");
      }
    } catch (err: unknown) {
      setAdjudicateError(err instanceof Error ? err.message : "Failed to adjudicate dispute.");
    } finally {
      setIsAdjudicating(false);
    }
  };

  // Handle staff chat message
  const handleSendMessage = async () => {
    if (!selectedDispute || !chatMessage.trim()) return;
    setIsSendingMessage(true);
    setChatError(null);
    try {
      const res = await api.marketplace.addDisputeMessage(selectedDispute.dispute_number, {
        message: chatMessage.trim(),
      });
      if (res.status === "success" && res.event) {
        // Refresh dispute details
        const updated = await api.marketplace.getDispute(selectedDispute.dispute_number);
        setSelectedDispute(updated);
        setDisputes((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
        setChatMessage("");
      }
    } catch (err: unknown) {
      setChatError(err instanceof Error ? err.message : "Failed to send message.");
    } finally {
      setIsSendingMessage(false);
    }
  };

  // Handle refund settlement
  const handleProcessRefund = async () => {
    if (!processModalRefund) return;
    setIsProcessingRefund(true);
    setProcessRefundError(null);
    try {
      const res = await api.marketplace.processAdminRefund(
        processModalRefund.refund_number,
        gatewayRefInput.trim(),
        processNotesInput.trim()
      );
      if (res.status === "success" && res.refund) {
        setRefunds((prev) =>
          prev.map((r) => (r.id === res.refund.id ? res.refund : r))
        );
        setSuccessBanner(`Refund ${res.refund.refund_number} successfully marked as ${res.refund.status}.`);
        setProcessModalRefund(null);
        setGatewayRefInput("");
        setProcessNotesInput("");
      }
    } catch (err: unknown) {
      setProcessRefundError(err instanceof Error ? err.message : "Failed to settle refund.");
    } finally {
      setIsProcessingRefund(false);
    }
  };

  // Inspect order refund summary
  const handleFetchOrderSummary = async () => {
    if (!orderQuery.trim()) return;
    setFetchingSummary(true);
    setSummaryError(null);
    setRefundSummary(null);
    try {
      const summary = await api.marketplace.getOrderRefundSummary(orderQuery.trim());
      setRefundSummary(summary);
      setRefundAmountInput(String(summary.available_refundable_balance));
      // Preselect refund method based on COD
      if (summary.is_cod) {
        setRefundMethodInput("BANK_TRANSFER");
      } else {
        setRefundMethodInput("ORIGINAL_PAYMENT");
      }
    } catch (err: unknown) {
      setSummaryError(err instanceof Error ? err.message : "Order not found or refund summary unavailable.");
    } finally {
      setFetchingSummary(false);
    }
  };

  // Submit new refund
  const handleIssueRefund = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!refundSummary || !orderQuery.trim()) return;
    setIsSubmittingRefund(true);
    setIssueRefundError(null);

    const amt = parseFloat(refundAmountInput);
    if (isNaN(amt) || amt <= 0) {
      setIssueRefundError("Please enter a valid positive refund amount.");
      setIsSubmittingRefund(false);
      return;
    }

    if (amt > Number(refundSummary.available_refundable_balance)) {
      setIssueRefundError(
        `Refund amount (${refundSummary.currency} ${amt}) exceeds available balance (${refundSummary.currency} ${refundSummary.available_refundable_balance}).`
      );
      setIsSubmittingRefund(false);
      return;
    }

    try {
      const res = await api.marketplace.createAdminRefund(refundSummary.order_number, {
        amount: amt,
        reason: refundReasonInput.trim(),
        refund_method: refundMethodInput,
        notes: refundNotesInput.trim(),
        auto_process: autoProcessInput,
        dispute_id: linkedDisputeId.trim() || undefined,
      });

      if (res.status === "success" && res.refund) {
        setSuccessBanner(
          `Refund ${res.refund.refund_number} for ${res.refund.currency} ${Number(res.refund.amount).toFixed(2)} created successfully (${res.refund.status}).`
        );
        // Refresh summary
        handleFetchOrderSummary();
        setRefundReasonInput("");
        setRefundNotesInput("");
        setLinkedDisputeId("");
      }
    } catch (err: unknown) {
      setIssueRefundError(err instanceof Error ? err.message : "Failed to issue refund.");
    } finally {
      setIsSubmittingRefund(false);
    }
  };

  // Filtered lists
  const filteredDisputes = useMemo(() => {
    return disputes.filter((d) => {
      const q = disputeSearch.toLowerCase().trim();
      const matchesSearch =
        !q ||
        d.dispute_number.toLowerCase().includes(q) ||
        d.order_number.toLowerCase().includes(q) ||
        (d.buyer_email && d.buyer_email.toLowerCase().includes(q)) ||
        d.description.toLowerCase().includes(q);
      return matchesSearch;
    });
  }, [disputes, disputeSearch]);

  const filteredRefunds = useMemo(() => {
    return refunds.filter((r) => {
      const q = refundSearch.toLowerCase().trim();
      const matchesSearch =
        !q ||
        r.refund_number.toLowerCase().includes(q) ||
        r.order_number.toLowerCase().includes(q) ||
        r.reason.toLowerCase().includes(q) ||
        (r.gateway_reference && r.gateway_reference.toLowerCase().includes(q));
      return matchesSearch;
    });
  }, [refunds, refundSearch]);

  const getDisputeStatusBadge = (status: string) => {
    switch (status) {
      case "OPEN":
        return <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-300">Open</span>;
      case "UNDER_REVIEW":
        return <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-100 text-blue-800 border border-blue-300">Under Review</span>;
      case "RESOLVED":
        return <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">Resolved</span>;
      case "REJECTED":
        return <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-100 text-rose-800 border border-rose-300">Rejected</span>;
      case "ESCALATED":
        return <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-purple-100 text-purple-800 border border-purple-300">Escalated</span>;
      default:
        return <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-800">{status}</span>;
    }
  };

  const getPriorityBadge = (priority: string) => {
    switch (priority) {
      case "URGENT":
        return <span className="px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider bg-rose-600 text-white">Urgent</span>;
      case "HIGH":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-amber-500 text-white">High</span>;
      case "MEDIUM":
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-blue-500 text-white">Medium</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-slate-400 text-white">Low</span>;
    }
  };

  const getRefundStatusBadge = (status: string) => {
    switch (status) {
      case "SUCCEEDED":
        return <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">Succeeded</span>;
      case "PENDING":
        return <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-300">Pending</span>;
      case "PROCESSING":
        return <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-100 text-blue-800 border border-blue-300">Processing</span>;
      case "FAILED":
        return <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-100 text-rose-800 border border-rose-300">Failed</span>;
      case "CANCELLED":
        return <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-700 border border-slate-300">Cancelled</span>;
      default:
        return <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-800">{status}</span>;
    }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-slate-950 via-slate-900 to-indigo-950 text-white rounded-3xl p-6 sm:p-8 shadow-2xl relative overflow-hidden border border-slate-800">
        <div className="relative z-10 space-y-3">
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-wider bg-amber-400 text-slate-950 shadow-xs">
              Operations Control
            </span>
            <span className="text-xs text-indigo-300 font-semibold">
              Phase 5 Task 3 • Returns, Refunds & Dispute Adjudication
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white flex items-center gap-3">
            <Scale className="w-8 h-8 text-amber-400" />
            <span>Disputes & Refunds Management</span>
          </h1>
          <p className="text-xs sm:text-sm text-slate-300 max-w-2xl leading-relaxed">
            Review commercial customer disputes, record formal adjudications with immutable audit history, issue validated order refunds with over-refund prevention, and settle manual COD payouts.
          </p>
        </div>
        <div className="absolute right-0 top-0 bottom-0 w-96 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-amber-500/10 via-indigo-500/10 to-transparent pointer-events-none" />
      </div>

      {/* Success Banner */}
      {successBanner && (
        <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-950 flex items-start justify-between gap-3 shadow-xs">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
            <p className="text-xs font-bold">{successBanner}</p>
          </div>
          <button onClick={() => setSuccessBanner(null)} className="text-emerald-700 hover:text-emerald-950">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Primary Tab Switcher */}
      <div className="flex items-center gap-2 p-1 bg-white rounded-2xl border border-slate-200 shadow-xs max-w-xl">
        <button
          onClick={() => setActiveTab("disputes")}
          className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2 ${
            activeTab === "disputes"
              ? "bg-slate-900 text-white shadow-md"
              : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
          }`}
        >
          <Scale className="w-4 h-4 text-amber-400" />
          <span>Dispute Queue</span>
        </button>

        <button
          onClick={() => setActiveTab("refunds")}
          className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2 ${
            activeTab === "refunds"
              ? "bg-slate-900 text-white shadow-md"
              : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
          }`}
        >
          <RotateCcw className="w-4 h-4 text-indigo-400" />
          <span>Platform Refunds</span>
        </button>

        <button
          onClick={() => setActiveTab("issue_refund")}
          className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2 ${
            activeTab === "issue_refund"
              ? "bg-slate-900 text-white shadow-md"
              : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
          }`}
        >
          <CreditCard className="w-4 h-4 text-emerald-400" />
          <span>Issue Refund</span>
        </button>
      </div>

      {/* ========================================================= */}
      {/* TAB 1: DISPUTES QUEUE                                     */}
      {/* ========================================================= */}
      {activeTab === "disputes" && (
        <div className="space-y-4">
          {/* Filter Bar */}
          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={disputeSearch}
                onChange={(e) => setDisputeSearch(e.target.value)}
                placeholder="Search by dispute #, order #, buyer email..."
                className="w-full pl-9 pr-4 py-2 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-amber-400"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <select
                value={disputeFilter}
                onChange={(e) => setDisputeFilter(e.target.value)}
                className="px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs text-slate-800 font-bold"
              >
                <option value="ALL">All Statuses</option>
                <option value="OPEN">Open</option>
                <option value="UNDER_REVIEW">Under Review</option>
                <option value="RESOLVED">Resolved</option>
                <option value="REJECTED">Rejected</option>
                <option value="ESCALATED">Escalated</option>
              </select>

              <select
                value={disputeCategoryFilter}
                onChange={(e) => setDisputeCategoryFilter(e.target.value)}
                className="px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs text-slate-800 font-bold"
              >
                <option value="ALL">All Categories</option>
                <option value="ITEM_NOT_RECEIVED">Item Not Received</option>
                <option value="SIGNIFICANTLY_NOT_AS_DESCRIBED">Not As Described</option>
                <option value="DAMAGED_OR_DEFECTIVE">Damaged / Defective</option>
                <option value="UNAUTHORIZED_TRANSACTION">Unauthorized</option>
                <option value="REFUND_NOT_PROCESSED">Refund Delayed</option>
                <option value="CANCELLATION_ISSUE">Cancellation Issue</option>
                <option value="OTHER">Other</option>
              </select>

              <button
                onClick={loadDisputes}
                className="p-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-600 transition-colors"
                title="Refresh Queue"
              >
                <RefreshCw className={`w-4 h-4 ${loadingDisputes ? "animate-spin" : ""}`} />
              </button>
            </div>
          </div>

          {/* Disputes List */}
          {loadingDisputes ? (
            <div className="p-12 text-center text-slate-400 text-xs">
              <Loader2 className="w-6 h-6 animate-spin mx-auto text-amber-500 mb-2" />
              <span>Loading commercial disputes...</span>
            </div>
          ) : disputesError ? (
            <div className="p-6 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-xs space-y-1">
              <h4 className="font-bold">Error loading disputes</h4>
              <p>{disputesError}</p>
            </div>
          ) : filteredDisputes.length === 0 ? (
            <div className="bg-white rounded-3xl border border-slate-200/80 p-12 text-center space-y-2">
              <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto" />
              <h3 className="text-sm font-black text-slate-900">No Disputes Found</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No cases match the selected status and category filters. All customer issues are currently resolved.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredDisputes.map((dispute) => (
                <div
                  key={dispute.id}
                  className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs hover:border-slate-300 hover:shadow-md transition-all space-y-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono font-black text-sm text-slate-950">
                        {dispute.dispute_number}
                      </span>
                      <button
                        onClick={() => handleCopy(dispute.dispute_number)}
                        className="p-1 text-slate-400 hover:text-slate-700"
                        title="Copy Dispute #"
                      >
                        {copiedId === dispute.dispute_number ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                      </button>

                      <span className="text-slate-300">·</span>
                      <span className="font-mono text-xs text-slate-600">
                        Order #{dispute.order_number}
                      </span>

                      {getPriorityBadge(dispute.priority)}
                      {getDisputeStatusBadge(dispute.status)}
                    </div>

                    <div className="text-xs text-slate-400">
                      Opened {new Date(dispute.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                    <div>
                      <span className="text-[10px] uppercase font-bold text-slate-400 block">Category</span>
                      <span className="font-bold text-slate-900">{dispute.category_display || dispute.category}</span>
                    </div>
                    <div>
                      <span className="text-[10px] uppercase font-bold text-slate-400 block">Buyer</span>
                      <span className="font-semibold text-slate-800">{dispute.buyer_email || dispute.buyer_name || dispute.buyer_id}</span>
                    </div>
                    <div>
                      <span className="text-[10px] uppercase font-bold text-slate-400 block">Seller</span>
                      <span className="font-semibold text-slate-800">{dispute.seller_name || dispute.seller_id}</span>
                    </div>
                  </div>

                  <div className="p-3 rounded-xl bg-slate-50 text-xs text-slate-700 leading-relaxed">
                    <span className="font-bold text-slate-900">Claim Description: </span>
                    {dispute.description}
                  </div>

                  {dispute.resolution && (
                    <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-950 space-y-1">
                      <div className="flex items-center gap-2 font-bold">
                        <ShieldCheck className="w-4 h-4 text-emerald-600" />
                        <span>Adjudicated Resolution: {dispute.resolution}</span>
                      </div>
                      {dispute.resolution_notes && <p className="text-emerald-800">{dispute.resolution_notes}</p>}
                    </div>
                  )}

                  <div className="pt-2 flex flex-wrap items-center justify-between gap-3">
                    <div className="text-[11px] text-slate-500 flex items-center gap-1.5">
                      <MessageSquare className="w-3.5 h-3.5 text-indigo-500" />
                      <span>{dispute.events?.length || 0} event checkpoint(s) in thread</span>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => {
                          setSelectedDispute(dispute);
                          setAdjudicateStatus(dispute.status);
                          setAdjudicateResolution(dispute.resolution || "");
                          setAdjudicateNotes(dispute.resolution_notes || "");
                        }}
                        className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5"
                      >
                        <Scale className="w-3.5 h-3.5 text-amber-400" />
                        <span>Adjudicate & View Thread</span>
                      </button>

                      <button
                        onClick={() => {
                          setOrderQuery(dispute.order_number);
                          setLinkedDisputeId(dispute.dispute_number);
                          setActiveTab("issue_refund");
                          setTimeout(() => {
                            api.marketplace.getOrderRefundSummary(dispute.order_number).then((s) => {
                              setRefundSummary(s);
                              setRefundAmountInput(String(s.available_refundable_balance));
                            });
                          }, 100);
                        }}
                        className="px-3 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-xs font-bold text-slate-700 transition-colors flex items-center gap-1.5"
                      >
                        <CreditCard className="w-3.5 h-3.5 text-indigo-600" />
                        <span>Issue Order Refund</span>
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ========================================================= */}
      {/* TAB 2: PLATFORM REFUNDS LIST                              */}
      {/* ========================================================= */}
      {activeTab === "refunds" && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={refundSearch}
                onChange={(e) => setRefundSearch(e.target.value)}
                placeholder="Search by refund #, order #, reason, gateway ref..."
                className="w-full pl-9 pr-4 py-2 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-amber-400"
              />
            </div>

            <div className="flex items-center gap-2">
              <select
                value={refundFilter}
                onChange={(e) => setRefundFilter(e.target.value)}
                className="px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs text-slate-800 font-bold"
              >
                <option value="ALL">All Statuses</option>
                <option value="PENDING">Pending</option>
                <option value="PROCESSING">Processing</option>
                <option value="SUCCEEDED">Succeeded</option>
                <option value="FAILED">Failed</option>
                <option value="CANCELLED">Cancelled</option>
              </select>

              <button
                onClick={loadRefunds}
                className="p-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-600 transition-colors"
                title="Refresh Refunds"
              >
                <RefreshCw className={`w-4 h-4 ${loadingRefunds ? "animate-spin" : ""}`} />
              </button>
            </div>
          </div>

          {loadingRefunds ? (
            <div className="p-12 text-center text-slate-400 text-xs">
              <Loader2 className="w-6 h-6 animate-spin mx-auto text-indigo-500 mb-2" />
              <span>Loading platform refund records...</span>
            </div>
          ) : refundsError ? (
            <div className="p-6 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 text-xs">
              {refundsError}
            </div>
          ) : filteredRefunds.length === 0 ? (
            <div className="bg-white rounded-3xl border border-slate-200/80 p-12 text-center space-y-2">
              <RotateCcw className="w-10 h-10 text-slate-400 mx-auto" />
              <h3 className="text-sm font-black text-slate-900">No Refunds Found</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No refunds match your current filter. Use the &quot;Issue Refund&quot; tab to disburse funds.
              </p>
            </div>
          ) : (
            <div className="bg-white rounded-3xl border border-slate-200 overflow-hidden shadow-xs divide-y divide-slate-100">
              {filteredRefunds.map((refund) => (
                <div key={refund.id} className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-slate-50/60 transition-colors">
                  <div className="space-y-1.5 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono font-black text-xs text-slate-900">
                        {refund.refund_number}
                      </span>
                      <button onClick={() => handleCopy(refund.refund_number)} className="text-slate-400 hover:text-slate-600">
                        {copiedId === refund.refund_number ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                      </button>

                      <span className="text-slate-300">·</span>
                      <span className="text-xs text-slate-600 font-mono">
                        Order #{refund.order_number}
                      </span>

                      {getRefundStatusBadge(refund.status)}

                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700">
                        Method: {refund.refund_method_display || refund.refund_method}
                      </span>
                    </div>

                    <div className="text-xs text-slate-600">
                      Reason: <strong className="text-slate-800">{refund.reason}</strong>
                      {refund.notes && <span className="text-slate-400 italic"> · {refund.notes}</span>}
                    </div>

                    <div className="text-[11px] text-slate-400 flex flex-wrap items-center gap-4">
                      {refund.gateway_reference && (
                        <span>Gateway Ref: <strong className="font-mono text-slate-700">{refund.gateway_reference}</strong></span>
                      )}
                      <span>Issued: {new Date(refund.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
                      {refund.processed_at && (
                        <span className="text-emerald-700 font-medium">Settled: {new Date(refund.processed_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}</span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-4 shrink-0">
                    <div className="text-right">
                      <span className="text-[10px] uppercase font-bold text-slate-400 block">Refund Amount</span>
                      <span className="font-mono font-black text-lg text-slate-900">
                        {refund.currency} {Number(refund.amount).toFixed(2)}
                      </span>
                    </div>

                    {refund.status === "PENDING" && (
                      <button
                        onClick={() => {
                          setProcessModalRefund(refund);
                          setGatewayRefInput(refund.gateway_reference || "");
                          setProcessNotesInput(refund.notes || "");
                        }}
                        className="px-3.5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition-all shadow-xs"
                      >
                        Settle / Process
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ========================================================= */}
      {/* TAB 3: DIRECT ISSUE REFUND TOOL                          */}
      {/* ========================================================= */}
      {activeTab === "issue_refund" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Order Search & Balance Inspection */}
          <div className="lg:col-span-1 space-y-4">
            <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-xs space-y-4">
              <div className="space-y-1">
                <h3 className="text-sm font-black text-slate-900 flex items-center gap-2">
                  <Search className="w-4 h-4 text-amber-500" />
                  <span>Inspect Order Refund Balance</span>
                </h3>
                <p className="text-xs text-slate-500">
                  Search by Order Number or UUID to verify actual collected payments and remaining balance before creating a refund.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={orderQuery}
                  onChange={(e) => setOrderQuery(e.target.value)}
                  placeholder="e.g. ORD-20261027-123456"
                  className="flex-1 px-3.5 py-2 rounded-xl border border-slate-200 text-xs font-mono text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-amber-400"
                />
                <button
                  type="button"
                  onClick={handleFetchOrderSummary}
                  disabled={fetchingSummary || !orderQuery.trim()}
                  className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition-all disabled:opacity-50 flex items-center gap-1.5"
                >
                  {fetchingSummary ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <span>Inspect</span>}
                </button>
              </div>

              {summaryError && (
                <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs">
                  {summaryError}
                </div>
              )}

              {refundSummary && (
                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-3 text-xs">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-200">
                    <span className="font-mono font-bold text-slate-900">{refundSummary.order_number}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${refundSummary.can_refund ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"}`}>
                      {refundSummary.can_refund ? "Eligible for Refund" : "Ineligible"}
                    </span>
                  </div>

                  <div className="space-y-1.5 text-slate-600">
                    <div className="flex justify-between">
                      <span>Order Total:</span>
                      <strong className="font-mono text-slate-900">{refundSummary.currency} {Number(refundSummary.total_amount).toFixed(2)}</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Payment Method:</span>
                      <strong className="text-slate-900">{refundSummary.payment_method}</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Payment Status:</span>
                      <strong className="text-slate-900">{refundSummary.payment_status}</strong>
                    </div>
                    {refundSummary.is_cod && (
                      <div className="flex justify-between">
                        <span>COD Collection:</span>
                        <strong className={refundSummary.is_cod_collected ? "text-emerald-700 font-bold" : "text-amber-700 font-bold"}>
                          {refundSummary.cod_collection_status}
                        </strong>
                      </div>
                    )}
                    <div className="flex justify-between">
                      <span>Paid Amount:</span>
                      <strong className="font-mono text-emerald-700">{refundSummary.currency} {Number(refundSummary.paid_amount).toFixed(2)}</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Active Refunds:</span>
                      <strong className="font-mono text-rose-700">-{refundSummary.currency} {Number(refundSummary.active_refunded_amount).toFixed(2)}</strong>
                    </div>
                    <div className="flex justify-between pt-2 border-t border-slate-200 font-bold text-slate-900 text-sm">
                      <span>Available Balance:</span>
                      <span className="font-mono text-indigo-700">{refundSummary.currency} {Number(refundSummary.available_refundable_balance).toFixed(2)}</span>
                    </div>
                  </div>

                  {refundSummary.reason_ineligible && (
                    <div className="p-2.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-[11px] flex items-start gap-1.5">
                      <AlertCircle className="w-3.5 h-3.5 text-amber-600 shrink-0 mt-0.5" />
                      <span>{refundSummary.reason_ineligible}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Refund Formulation Form */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-3xl border border-slate-200 p-6 sm:p-8 shadow-xs space-y-6">
              <div className="space-y-1">
                <h3 className="text-base font-black text-slate-900 flex items-center gap-2">
                  <CreditCard className="w-5 h-5 text-indigo-600" />
                  <span>Issue Order Refund</span>
                </h3>
                <p className="text-xs text-slate-500">
                  Refunds are validated server-side against actual received payments. Over-refunding and uncollected COD payouts are strictly prevented.
                </p>
              </div>

              {issueRefundError && (
                <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs">
                  {issueRefundError}
                </div>
              )}

              <form onSubmit={handleIssueRefund} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">
                      Refund Amount ({refundSummary?.currency || "Currency"}) *
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0.01"
                      max={refundSummary ? Number(refundSummary.available_refundable_balance) : undefined}
                      value={refundAmountInput}
                      onChange={(e) => setRefundAmountInput(e.target.value)}
                      placeholder="0.00"
                      disabled={!refundSummary || !refundSummary.can_refund}
                      required
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 font-mono text-sm text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-indigo-400 disabled:bg-slate-100"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">
                      Refund Disbursement Method *
                    </label>
                    <select
                      value={refundMethodInput}
                      onChange={(e) => setRefundMethodInput(e.target.value as RefundMethod)}
                      disabled={!refundSummary || !refundSummary.can_refund}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-xs text-slate-800 font-bold focus:outline-hidden focus:ring-2 focus:ring-indigo-400 disabled:bg-slate-100"
                    >
                      <option value="ORIGINAL_PAYMENT">Original Payment Gateway (Razorpay/Stripe)</option>
                      <option value="BANK_TRANSFER">Bank Transfer / NEFT / IMPS</option>
                      <option value="MANUAL_PAYOUT">Manual Payout / Ledger Settlement</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Refund Reason *
                  </label>
                  <input
                    type="text"
                    value={refundReasonInput}
                    onChange={(e) => setRefundReasonInput(e.target.value)}
                    placeholder="e.g. Return request approved / Damaged item replacement / Commercial dispute resolution"
                    disabled={!refundSummary || !refundSummary.can_refund}
                    required
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-400 disabled:bg-slate-100"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">
                      Linked Dispute Number (Optional)
                    </label>
                    <input
                      type="text"
                      value={linkedDisputeId}
                      onChange={(e) => setLinkedDisputeId(e.target.value)}
                      placeholder="e.g. DIS-20261027-123456"
                      disabled={!refundSummary || !refundSummary.can_refund}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-xs font-mono text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-400 disabled:bg-slate-100"
                    />
                  </div>

                  <div className="flex items-center pt-6">
                    <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-slate-700">
                      <input
                        type="checkbox"
                        checked={autoProcessInput}
                        onChange={(e) => setAutoProcessInput(e.target.checked)}
                        disabled={!refundSummary || !refundSummary.can_refund}
                        className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500"
                      />
                      <span>Auto-mark as settled (Immediate completion)</span>
                    </label>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Internal Operations Notes
                  </label>
                  <textarea
                    rows={2}
                    value={refundNotesInput}
                    onChange={(e) => setRefundNotesInput(e.target.value)}
                    placeholder="Reference UTR, reason for settlement, or supervisor authorization reference..."
                    disabled={!refundSummary || !refundSummary.can_refund}
                    className="w-full px-3.5 py-2 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-400 disabled:bg-slate-100"
                  />
                </div>

                <button
                  type="submit"
                  disabled={isSubmittingRefund || !refundSummary || !refundSummary.can_refund}
                  className="w-full py-3 rounded-2xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-black transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-40"
                >
                  {isSubmittingRefund ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Validating & Processing Refund...</span>
                    </>
                  ) : (
                    <>
                      <CreditCard className="w-4 h-4 text-emerald-400" />
                      <span>Issue Refund ({refundSummary ? `${refundSummary.currency} ${refundAmountInput || "0.00"}` : "Select Order"})</span>
                    </>
                  )}
                </button>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* ADJUDICATION & DISPUTE THREAD MODAL                       */}
      {/* ========================================================= */}
      {selectedDispute && (
        <div className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
          <div className="bg-white rounded-3xl max-w-3xl w-full max-h-[92vh] overflow-hidden flex flex-col shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            {/* Header */}
            <div className="p-5 sm:p-6 bg-slate-900 text-white flex items-center justify-between shrink-0">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-black text-amber-400 text-base">
                    {selectedDispute.dispute_number}
                  </span>
                  <span className="text-slate-400">·</span>
                  <span className="text-xs text-slate-300">Order #{selectedDispute.order_number}</span>
                  {getPriorityBadge(selectedDispute.priority)}
                </div>
                <p className="text-xs text-slate-400">
                  Category: <strong>{selectedDispute.category_display || selectedDispute.category}</strong>
                </p>
              </div>

              <div className="flex items-center gap-2">
                {getDisputeStatusBadge(selectedDispute.status)}
                <button
                  onClick={() => setSelectedDispute(null)}
                  className="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-slate-800"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Scrollable Body */}
            <div className="p-5 sm:p-6 overflow-y-auto space-y-6">
              {/* Adjudication Controls Card */}
              <div className="p-4 sm:p-5 rounded-2xl bg-amber-50/70 border border-amber-200 space-y-4">
                <div className="space-y-1">
                  <h4 className="text-xs font-black uppercase tracking-wider text-amber-950 flex items-center gap-2">
                    <Scale className="w-4 h-4 text-amber-700" />
                    <span>Adjudicate Dispute (Staff Decision Authority)</span>
                  </h4>
                  <p className="text-[11px] text-amber-800">
                    Update status, record formal findings, and choose binding resolution remedy.
                  </p>
                </div>

                {adjudicateError && (
                  <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs">
                    {adjudicateError}
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Status Transition</label>
                    <select
                      value={adjudicateStatus}
                      onChange={(e) => setAdjudicateStatus(e.target.value as DisputeStatus)}
                      className="w-full px-3 py-2 rounded-xl border border-slate-300 bg-white font-bold text-slate-900"
                    >
                      <option value="UNDER_REVIEW">UNDER_REVIEW</option>
                      <option value="RESOLVED">RESOLVED</option>
                      <option value="REJECTED">REJECTED</option>
                      <option value="ESCALATED">ESCALATED</option>
                    </select>
                  </div>

                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Resolution Remedy</label>
                    <select
                      value={adjudicateResolution}
                      onChange={(e) => setAdjudicateResolution(e.target.value as DisputeResolution)}
                      className="w-full px-3 py-2 rounded-xl border border-slate-300 bg-white font-bold text-slate-900"
                    >
                      <option value="">-- No Resolution Recorded --</option>
                      <option value="BUYER_REFUND">BUYER_REFUND (Full or Partial)</option>
                      <option value="REPLACEMENT">REPLACEMENT (Seller Ships New Item)</option>
                      <option value="SELLER_UPHELD">SELLER_UPHELD (Claim Dismissed)</option>
                      <option value="MUTUAL_AGREEMENT">MUTUAL_AGREEMENT</option>
                      <option value="DISMISSED">DISMISSED (Invalid / Duplicate)</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Resolution Findings & Rationale</label>
                  <textarea
                    rows={2}
                    value={adjudicateNotes}
                    onChange={(e) => setAdjudicateNotes(e.target.value)}
                    placeholder="Document evidence evaluation, courier tracking findings, and terms of resolution..."
                    className="w-full px-3 py-2 rounded-xl border border-slate-300 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-amber-500"
                  />
                </div>

                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={handleAdjudicateDispute}
                    disabled={isAdjudicating}
                    className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5 disabled:opacity-50"
                  >
                    {isAdjudicating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5 text-amber-400" />}
                    <span>Record Decision</span>
                  </button>
                </div>
              </div>

              {/* Dispute Description & Original Evidence */}
              <div className="space-y-2">
                <span className="text-[10px] uppercase font-bold text-slate-400 block">Buyer Claim Details</span>
                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 text-xs text-slate-800 space-y-3">
                  <p className="leading-relaxed">{selectedDispute.description}</p>
                  {selectedDispute.evidence_urls && selectedDispute.evidence_urls.length > 0 && (
                    <div className="space-y-1 pt-2 border-t border-slate-200">
                      <span className="text-[10px] uppercase font-bold text-slate-500 block">Attached Evidence</span>
                      <div className="flex flex-wrap gap-2">
                        {selectedDispute.evidence_urls.map((url, idx) => (
                          <a
                            key={idx}
                            href={resolveMediaUrl(url)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="block w-16 h-16 rounded-xl border border-slate-300 overflow-hidden hover:opacity-80 transition-opacity bg-white"
                          >
                            <img src={resolveMediaUrl(url)} alt={`Evidence ${idx + 1}`} className="w-full h-full object-cover" />
                          </a>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Multi-Party Message Timeline */}
              <div className="space-y-3">
                <span className="text-[10px] uppercase font-bold text-slate-400 block">
                  Communication Timeline ({selectedDispute.events?.length || 0} messages & checkpoints)
                </span>

                <div className="space-y-3 max-h-72 overflow-y-auto pr-1">
                  {selectedDispute.events && selectedDispute.events.length > 0 ? (
                    selectedDispute.events.map((evt) => (
                      <div
                        key={evt.id}
                        className={`p-3.5 rounded-2xl border text-xs space-y-1 ${
                          evt.actor_role === "DISPUTE_MANAGER" || evt.actor_role === "STAFF" || evt.actor_role === "ADMIN"
                            ? "bg-amber-50/80 border-amber-200 ml-6"
                            : evt.actor_role === "SELLER"
                            ? "bg-indigo-50/80 border-indigo-200 ml-6"
                            : "bg-slate-50 border-slate-200 mr-6"
                        }`}
                      >
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="font-bold text-slate-900">
                            {evt.actor_name || "User"} ({evt.actor_role || "BUYER"})
                          </span>
                          <span className="text-slate-400 font-mono text-[10px]">
                            {new Date(evt.created_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}
                          </span>
                        </div>
                        <p className="text-slate-700 leading-relaxed">{evt.message}</p>
                      </div>
                    ))
                  ) : (
                    <div className="p-4 text-center text-xs text-slate-400">No events recorded.</div>
                  )}
                </div>

                {/* Staff Reply Box */}
                <div className="pt-2 border-t border-slate-200 space-y-2">
                  {chatError && <div className="text-rose-600 text-xs">{chatError}</div>}
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={chatMessage}
                      onChange={(e) => setChatMessage(e.target.value)}
                      placeholder="Post formal staff notice or request further evidence from buyer/seller..."
                      className="flex-1 px-3.5 py-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-amber-400"
                    />
                    <button
                      type="button"
                      onClick={handleSendMessage}
                      disabled={isSendingMessage || !chatMessage.trim()}
                      className="px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition-all disabled:opacity-40 flex items-center gap-1.5"
                    >
                      {isSendingMessage ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5 text-amber-400" />}
                      <span>Send</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* SETTLE / PROCESS MANUAL REFUND MODAL                      */}
      {/* ========================================================= */}
      {processModalRefund && (
        <div className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-200">
            <div className="space-y-1">
              <h3 className="text-base font-black text-slate-900 flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-indigo-600" />
                <span>Settle Refund {processModalRefund.refund_number}</span>
              </h3>
              <p className="text-xs text-slate-500">
                Record bank transfer transaction UTR or provider payout reference to confirm settlement to the customer.
              </p>
            </div>

            {processRefundError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs">
                {processRefundError}
              </div>
            )}

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs space-y-1">
              <div className="flex justify-between">
                <span className="text-slate-500">Amount:</span>
                <strong className="font-mono text-slate-900">{processModalRefund.currency} {Number(processModalRefund.amount).toFixed(2)}</strong>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Method:</span>
                <strong className="text-slate-800">{processModalRefund.refund_method}</strong>
              </div>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Bank Reference / Gateway Payout Reference
                </label>
                <input
                  type="text"
                  value={gatewayRefInput}
                  onChange={(e) => setGatewayRefInput(e.target.value)}
                  placeholder="e.g. UTR-9823472394 / REF-STRIPE-001"
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-xs font-mono text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-indigo-400"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Settlement Notes
                </label>
                <input
                  type="text"
                  value={processNotesInput}
                  onChange={(e) => setProcessNotesInput(e.target.value)}
                  placeholder="Processed via finance account / confirmed with buyer"
                  className="w-full px-3.5 py-2 rounded-xl border border-slate-200 text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-indigo-400"
                />
              </div>
            </div>

            <div className="flex items-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => setProcessModalRefund(null)}
                disabled={isProcessingRefund}
                className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-bold"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleProcessRefund}
                disabled={isProcessingRefund}
                className="flex-1 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {isProcessingRefund ? <Loader2 className="w-4 h-4 animate-spin" /> : <span>Confirm Succeeded</span>}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
