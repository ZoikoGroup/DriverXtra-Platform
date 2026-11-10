"use client";

import React, { useState, useEffect, useCallback, useId } from "react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  api,
  SupportTicketSummary,
  SupportTicketDetail,
  SupportMetrics,
  SupportStaffMember,
  SupportTicketStatus,
  SupportTicketPriority,
} from "@/lib/api/client";
import {
  Headphones,
  ShoppingBag,
  Wrench,
  ShieldCheck,
  AlertCircle,
  Clock,
  CheckCircle2,
  AlertTriangle,
  UserCheck,
  Search,
  Filter,
  RefreshCw,
  Send,
  Lock,
  Globe,
  Paperclip,
  Download,
  X,
  ChevronRight,
  User,
  Flame,
  ArrowUpRight,
  EyeOff,
  History,
} from "lucide-react";

interface SupportAgentLandingViewProps {
  onNavigateTab: (tabId: string) => void;
}

export default function SupportAgentLandingView({ onNavigateTab }: SupportAgentLandingViewProps) {
  const { user } = useAuth();

  // Metrics & Queues state
  const [metrics, setMetrics] = useState<SupportMetrics | null>(null);
  const [tickets, setTickets] = useState<SupportTicketSummary[]>([]);
  const [staffMembers, setStaffMembers] = useState<SupportStaffMember[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [queueTab, setQueueTab] = useState<"all" | "mine" | "unassigned" | "sla_breached" | "escalated">("all");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [priorityFilter, setPriorityFilter] = useState<string>("ALL");
  const [categoryFilter, setCategoryFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Selected Ticket for Drawer
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [ticketDetail, setTicketDetail] = useState<SupportTicketDetail | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState<boolean>(false);
  const [activeDrawerTab, setActiveDrawerTab] = useState<"conversation" | "activity">("conversation");

  // Message composer state
  const [composerMode, setComposerMode] = useState<"public" | "internal">("public");
  const [messageText, setMessageText] = useState<string>("");
  const [isSendingMessage, setIsSendingMessage] = useState<boolean>(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputId = useId();

  // Modals for actions
  const [isResolveModalOpen, setIsResolveModalOpen] = useState<boolean>(false);
  const [resolutionSummary, setResolutionSummary] = useState<string>("");
  const [isReassignModalOpen, setIsReassignModalOpen] = useState<boolean>(false);
  const [selectedTargetAgent, setSelectedTargetAgent] = useState<string>("");
  const [isEscalateModalOpen, setIsEscalateModalOpen] = useState<boolean>(false);
  const [escalateReason, setEscalateReason] = useState<string>("");
  const [escalateStage, setEscalateStage] = useState<number>(2); // 2 = BREACH_100
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<boolean>(false);

  // 1. Load Data
  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [metricsRes, staffRes] = await Promise.all([
        api.support.getStaffMetrics().catch(() => ({ metrics: null })),
        api.support.getStaffMembers().catch(() => ({ staff: [] })),
      ]);

      if (metricsRes.metrics) setMetrics(metricsRes.metrics);
      if (staffRes.staff) setStaffMembers(staffRes.staff);

      const params: {
        queue?: string;
        status?: string;
        priority?: string;
        category?: string;
        is_escalated?: boolean;
        sla_breached?: boolean;
        search?: string;
      } = {};

      if (queueTab === "mine") params.queue = "mine";
      else if (queueTab === "unassigned") params.queue = "unassigned";
      else if (queueTab === "sla_breached") params.sla_breached = true;
      else if (queueTab === "escalated") params.is_escalated = true;
      else params.queue = "all";

      if (statusFilter !== "ALL") params.status = statusFilter;
      if (priorityFilter !== "ALL") params.priority = priorityFilter;
      if (categoryFilter !== "ALL") params.category = categoryFilter;
      if (searchQuery.trim()) params.search = searchQuery.trim();

      const ticketRes = await api.support.getStaffTickets(params);
      setTickets(ticketRes.tickets || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load support operations data.");
    } finally {
      setIsLoading(false);
    }
  }, [queueTab, statusFilter, priorityFilter, categoryFilter, searchQuery]);

  useEffect(() => {
    queueMicrotask(() => {
      void loadData();
    });
  }, [loadData]);

  // 2. Load Ticket Detail
  const openTicketDetail = async (identifier: string) => {
    setSelectedTicketId(identifier);
    setIsDetailLoading(true);
    setActionError(null);
    try {
      const res = await api.support.getStaffTicket(identifier);
      setTicketDetail(res.ticket);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to load ticket details.");
    } finally {
      setIsDetailLoading(false);
    }
  };

  const closeTicketDrawer = () => {
    setSelectedTicketId(null);
    setTicketDetail(null);
    setMessageText("");
    setSelectedFile(null);
    setUploadError(null);
  };

  // 3. Assign / Take ticket
  const handleAssignTicket = async (targetId: string | null) => {
    if (!ticketDetail) return;
    setActionLoading(true);
    setActionError(null);
    try {
      const res = await api.support.assignStaffTicket(ticketDetail.ticket_number, targetId);
      setTicketDetail(res.ticket);
      setIsReassignModalOpen(false);
      loadData();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to assign ticket.");
    } finally {
      setActionLoading(false);
    }
  };

  // 4. Update Status
  const handleUpdateStatus = async (
    newStatus: SupportTicketStatus,
    summary?: string,
    notes?: string
  ) => {
    if (!ticketDetail) return;
    setActionLoading(true);
    setActionError(null);
    try {
      const res = await api.support.updateStaffTicketStatus(ticketDetail.ticket_number, {
        status: newStatus,
        resolution_summary: summary,
        notes,
      });
      setTicketDetail(res.ticket);
      setIsResolveModalOpen(false);
      setResolutionSummary("");
      loadData();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to update ticket status.");
    } finally {
      setActionLoading(false);
    }
  };

  // 5. Update Priority
  const handleUpdatePriority = async (newPriority: SupportTicketPriority) => {
    if (!ticketDetail) return;
    setActionLoading(true);
    setActionError(null);
    try {
      const res = await api.support.updateStaffTicketPriority(ticketDetail.ticket_number, newPriority);
      setTicketDetail(res.ticket);
      loadData();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to update priority.");
    } finally {
      setActionLoading(false);
    }
  };

  // 6. Escalate
  const handleEscalateTicket = async () => {
    if (!ticketDetail || !escalateReason.trim()) return;
    setActionLoading(true);
    setActionError(null);
    try {
      const res = await api.support.escalateStaffTicket(ticketDetail.ticket_number, {
        reason: escalateReason.trim(),
        stage: escalateStage,
      });
      setTicketDetail(res.ticket);
      setIsEscalateModalOpen(false);
      setEscalateReason("");
      loadData();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to escalate ticket.");
    } finally {
      setActionLoading(false);
    }
  };

  // 7. Send Message / Add Internal Note
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticketDetail || (!messageText.trim() && !selectedFile)) return;

    setIsSendingMessage(true);
    setUploadError(null);

    try {
      const isInternal = composerMode === "internal";
      let sentMsgId: string | undefined;

      if (messageText.trim()) {
        const msgRes = await api.support.sendStaffMessage(ticketDetail.ticket_number, {
          message: messageText.trim(),
          is_internal_note: isInternal,
        });
        sentMsgId = msgRes.data?.id;
      }

      // Attach file if selected
      if (selectedFile) {
        await api.support.uploadAttachment(ticketDetail.ticket_number, selectedFile, {
          isInternal,
          messageId: sentMsgId,
        });
      }

      setMessageText("");
      setSelectedFile(null);

      // Refresh ticket detail & list
      const updatedRes = await api.support.getStaffTicket(ticketDetail.ticket_number);
      setTicketDetail(updatedRes.ticket);
      loadData();
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : "Failed to send message or upload attachment.");
    } finally {
      setIsSendingMessage(false);
    }
  };

  // 8. Download Attachment
  const handleDownloadAttachment = async (attachmentId: string, fileName: string) => {
    try {
      const blob = await api.support.downloadAttachment(attachmentId);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to download attachment.");
    }
  };

  // Helper formatting badges
  const getPriorityBadge = (p: SupportTicketPriority) => {
    switch (p) {
      case "CRITICAL":
        return <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-500/10 text-rose-600 border border-rose-200"><Flame className="w-3 h-3" /> Critical (24/7)</span>;
      case "HIGH":
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-orange-500/10 text-orange-600 border border-orange-200">High</span>;
      case "MEDIUM":
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-600 border border-amber-200">Medium</span>;
      default:
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">Low</span>;
    }
  };

  const getStatusBadge = (s: SupportTicketStatus) => {
    switch (s) {
      case "OPEN":
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-sky-500/10 text-sky-700 border border-sky-200">OPEN</span>;
      case "IN_PROGRESS":
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-500/10 text-indigo-700 border border-indigo-200">IN PROGRESS</span>;
      case "WAITING_FOR_CUSTOMER":
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-500/10 text-amber-800 border border-amber-200">WAITING CUSTOMER</span>;
      case "RESOLVED":
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-700 border border-emerald-200">RESOLVED</span>;
      case "CLOSED":
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-slate-200 text-slate-700 border border-slate-300">CLOSED</span>;
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* 1. Header Control Plane Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 text-white shadow-xl relative overflow-hidden">
        <div className="absolute right-0 top-0 translate-x-12 -translate-y-12 w-64 h-64 bg-amber-400/10 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-amber-400/20 text-amber-300 border border-amber-400/30 mb-2">
              <Headphones className="w-3.5 h-3.5" />
              <span>Support Operations Workspace</span>
            </div>
            <h1 className="text-2xl font-black text-white tracking-tight">
              Customer Support &amp; Ticketing Hub
            </h1>
            <p className="text-slate-300 text-xs mt-1 max-w-2xl leading-relaxed">
              Live operational triage, first-line inquiry handling, private internal notes, and automated SLA breach tracking.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
            <div className="bg-slate-800/80 border border-slate-700 rounded-2xl px-4 py-2 text-xs">
              <div className="text-slate-400 font-semibold uppercase text-[10px] tracking-wider">
                Agent Identity
              </div>
              <div className="font-bold text-white mt-0.5">{user?.fullName || user?.email}</div>
            </div>

            <div className="bg-slate-800/80 border border-slate-700 rounded-2xl px-4 py-2 text-xs">
              <div className="text-slate-400 font-semibold uppercase text-[10px] tracking-wider">
                Assigned Role
              </div>
              <div className="font-bold text-amber-400 mt-0.5 flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                <span>{user?.staff_role?.name || "Support Agent"}</span>
              </div>
            </div>

            <button
              onClick={loadData}
              disabled={isLoading}
              className="p-2.5 rounded-2xl bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 hover:border-slate-600 transition-colors"
              title="Refresh Queue"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>
      </div>

      {/* 2. Operations Metrics Bar */}
      {metrics && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Active Queue</div>
            <div className="text-2xl font-black text-slate-900 mt-1">{metrics.total_active}</div>
            <div className="text-[11px] text-slate-400 mt-0.5">{metrics.open} Open &bull; {metrics.in_progress} In Progress</div>
          </div>

          <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Assigned to Me</div>
            <div className="text-2xl font-black text-indigo-600 mt-1">{metrics.my_tickets_count}</div>
            <div className="text-[11px] text-slate-400 mt-0.5">My workload</div>
          </div>

          <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Unassigned Triage</div>
            <div className="text-2xl font-black text-amber-600 mt-1">{metrics.unassigned_count}</div>
            <div className="text-[11px] text-slate-400 mt-0.5">Requires pickup</div>
          </div>

          <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Awaiting Customer</div>
            <div className="text-2xl font-black text-slate-700 mt-1">{metrics.waiting_for_customer}</div>
            <div className="text-[11px] text-emerald-600 font-medium mt-0.5">SLA clock paused</div>
          </div>

          <div className={`border rounded-2xl p-4 shadow-sm ${metrics.sla_breached_count > 0 ? "bg-rose-50 border-rose-200" : "bg-white border-slate-200"}`}>
            <div className={`text-[11px] font-semibold uppercase tracking-wider ${metrics.sla_breached_count > 0 ? "text-rose-700" : "text-slate-500"}`}>
              SLA Breached
            </div>
            <div className={`text-2xl font-black mt-1 ${metrics.sla_breached_count > 0 ? "text-rose-600" : "text-slate-900"}`}>
              {metrics.sla_breached_count}
            </div>
            <div className="text-[11px] text-rose-600 mt-0.5">
              {metrics.first_response_overdue_count} first resp &bull; {metrics.resolution_overdue_count} resol
            </div>
          </div>

          <div className={`border rounded-2xl p-4 shadow-sm ${metrics.escalated_count > 0 ? "bg-purple-50 border-purple-200" : "bg-white border-slate-200"}`}>
            <div className={`text-[11px] font-semibold uppercase tracking-wider ${metrics.escalated_count > 0 ? "text-purple-700" : "text-slate-500"}`}>
              Escalated
            </div>
            <div className={`text-2xl font-black mt-1 ${metrics.escalated_count > 0 ? "text-purple-600" : "text-slate-900"}`}>
              {metrics.escalated_count}
            </div>
            <div className="text-[11px] text-purple-600 mt-0.5">Tier 1/2/3 breaches</div>
          </div>
        </div>
      )}

      {/* 3. Operational Queue Navigation Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2 overflow-x-auto">
          <button
            onClick={() => setQueueTab("all")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              queueTab === "all"
                ? "bg-slate-900 text-white shadow-sm"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            All Tickets
          </button>
          <button
            onClick={() => setQueueTab("mine")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 ${
              queueTab === "mine"
                ? "bg-indigo-600 text-white shadow-sm"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            <User className="w-3.5 h-3.5" />
            <span>Assigned to Me</span>
            {metrics?.my_tickets_count ? (
              <span className="ml-1 px-1.5 py-0.2 bg-white/20 rounded-full text-[10px]">{metrics.my_tickets_count}</span>
            ) : null}
          </button>
          <button
            onClick={() => setQueueTab("unassigned")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 ${
              queueTab === "unassigned"
                ? "bg-amber-600 text-white shadow-sm"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            <Clock className="w-3.5 h-3.5" />
            <span>Unassigned Triage</span>
            {metrics?.unassigned_count ? (
              <span className="ml-1 px-1.5 py-0.2 bg-amber-500/20 text-amber-700 rounded-full text-[10px] font-bold">
                {metrics.unassigned_count}
              </span>
            ) : null}
          </button>
          <button
            onClick={() => setQueueTab("sla_breached")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 ${
              queueTab === "sla_breached"
                ? "bg-rose-600 text-white shadow-sm"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>SLA Breached</span>
            {metrics?.sla_breached_count ? (
              <span className="ml-1 px-1.5 py-0.2 bg-rose-500/20 text-rose-700 rounded-full text-[10px] font-bold">
                {metrics.sla_breached_count}
              </span>
            ) : null}
          </button>
          <button
            onClick={() => setQueueTab("escalated")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 ${
              queueTab === "escalated"
                ? "bg-purple-600 text-white shadow-sm"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            <Flame className="w-3.5 h-3.5" />
            <span>Escalated</span>
            {metrics?.escalated_count ? (
              <span className="ml-1 px-1.5 py-0.2 bg-purple-500/20 text-purple-700 rounded-full text-[10px] font-bold">
                {metrics.escalated_count}
              </span>
            ) : null}
          </button>
        </div>

        {/* Search bar */}
        <div className="relative w-full sm:w-64">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search ticket # or subject..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-xs rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-slate-900"
          />
        </div>
      </div>

      {/* 4. Secondary Filter Dropdowns */}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-slate-400 font-semibold flex items-center gap-1">
          <Filter className="w-3.5 h-3.5" /> Filter:
        </span>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-2.5 py-1.5 rounded-xl border border-slate-200 bg-white text-slate-700 font-medium focus:ring-2 focus:ring-slate-900 focus:outline-none"
        >
          <option value="ALL">All Statuses</option>
          <option value="OPEN">Open</option>
          <option value="IN_PROGRESS">In Progress</option>
          <option value="WAITING_FOR_CUSTOMER">Waiting for Customer</option>
          <option value="RESOLVED">Resolved</option>
          <option value="CLOSED">Closed</option>
        </select>

        <select
          value={priorityFilter}
          onChange={(e) => setPriorityFilter(e.target.value)}
          className="px-2.5 py-1.5 rounded-xl border border-slate-200 bg-white text-slate-700 font-medium focus:ring-2 focus:ring-slate-900 focus:outline-none"
        >
          <option value="ALL">All Priorities</option>
          <option value="CRITICAL">Critical (24/7)</option>
          <option value="HIGH">High (4h SLA)</option>
          <option value="MEDIUM">Medium (12h SLA)</option>
          <option value="LOW">Low (24h SLA)</option>
        </select>

        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="px-2.5 py-1.5 rounded-xl border border-slate-200 bg-white text-slate-700 font-medium focus:ring-2 focus:ring-slate-900 focus:outline-none"
        >
          <option value="ALL">All Categories</option>
          <option value="GENERAL_INQUIRY">General Inquiry</option>
          <option value="ORDER_ISSUE">Order &amp; Delivery Issue</option>
          <option value="PART_COMPATIBILITY">Part Fitment &amp; Compatibility</option>
          <option value="WORKSHOP_BOOKING">Workshop Booking &amp; Services</option>
          <option value="PAYMENT_BILLING">Payment &amp; Invoice Assistance</option>
          <option value="ACCOUNT_SECURITY">Account &amp; Profile Security</option>
          <option value="RETURNS_ASSISTANCE">Returns &amp; Refunds Assistance</option>
          <option value="TECHNICAL_SUPPORT">Technical Platform Issue</option>
        </select>

        {(statusFilter !== "ALL" || priorityFilter !== "ALL" || categoryFilter !== "ALL" || searchQuery) && (
          <button
            onClick={() => {
              setStatusFilter("ALL");
              setPriorityFilter("ALL");
              setCategoryFilter("ALL");
              setSearchQuery("");
            }}
            className="text-xs text-rose-600 hover:text-rose-700 font-semibold underline ml-2"
          >
            Reset Filters
          </button>
        )}
      </div>

      {/* Error message */}
      {error && (
        <div className="bg-rose-50 border border-rose-200 rounded-2xl p-4 text-rose-900 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 5. Ticket Queue Table */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-12 text-center text-slate-400 text-xs">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-slate-300" />
            Loading support queue...
          </div>
        ) : tickets.length === 0 ? (
          <div className="p-12 text-center text-slate-500 text-xs space-y-1">
            <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
            <div className="font-bold text-slate-800 text-sm">Queue is clear</div>
            <p className="text-slate-400">No support tickets match the selected filters.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50/80 border-b border-slate-200 text-slate-500 uppercase tracking-wider text-[10px] font-bold">
                  <th className="py-3 px-4">Ticket</th>
                  <th className="py-3 px-4">Subject &amp; Category</th>
                  <th className="py-3 px-4">Customer</th>
                  <th className="py-3 px-4">Priority</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">SLA Deadlines</th>
                  <th className="py-3 px-4">Assigned To</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {tickets.map((t) => (
                  <tr
                    key={t.id}
                    onClick={() => openTicketDetail(t.ticket_number)}
                    className="hover:bg-slate-50/80 cursor-pointer transition-colors"
                  >
                    <td className="py-3.5 px-4 font-mono font-bold text-slate-900">
                      <div className="flex items-center gap-1.5">
                        <span>{t.ticket_number}</span>
                        {t.is_confidential && (
                          <span className="p-0.5 rounded bg-amber-100 text-amber-800" title="Confidential Ticket">
                            <EyeOff className="w-3 h-3" />
                          </span>
                        )}
                      </div>
                      <div className="text-[10px] text-slate-400 font-normal">
                        {new Date(t.created_at).toLocaleDateString()}
                      </div>
                    </td>

                    <td className="py-3.5 px-4 max-w-xs">
                      <div className="font-bold text-slate-900 truncate">{t.subject}</div>
                      <div className="text-[11px] text-slate-500">
                        {t.category_display || t.category}
                        {t.order_reference && (
                          <span className="ml-1 text-slate-400 font-mono">({t.order_reference})</span>
                        )}
                      </div>
                    </td>

                    <td className="py-3.5 px-4">
                      <div className="font-semibold text-slate-800">{t.customer?.full_name || "Customer"}</div>
                      <div className="text-[11px] text-slate-400">{t.customer?.email}</div>
                    </td>

                    <td className="py-3.5 px-4">
                      {getPriorityBadge(t.priority)}
                    </td>

                    <td className="py-3.5 px-4">
                      {getStatusBadge(t.status)}
                    </td>

                    <td className="py-3.5 px-4 text-[11px]">
                      {t.sla_breached ? (
                        <span className="inline-flex items-center gap-1 text-rose-600 font-bold">
                          <AlertTriangle className="w-3 h-3" /> SLA BREACHED
                        </span>
                      ) : t.status === "WAITING_FOR_CUSTOMER" ? (
                        <span className="text-amber-700 font-medium">Clock Paused</span>
                      ) : t.first_response_due_at && !t.first_responded_at ? (
                        <span className="text-slate-600">
                          Resp by: {new Date(t.first_response_due_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      ) : t.resolution_due_at ? (
                        <span className="text-slate-600">
                          Res by: {new Date(t.resolution_due_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                        </span>
                      ) : (
                        <span className="text-slate-400">&mdash;</span>
                      )}
                      {t.is_escalated && (
                        <div className="text-[10px] text-purple-600 font-bold mt-0.5">
                          Stage {t.escalation_stage} Escalation
                        </div>
                      )}
                    </td>

                    <td className="py-3.5 px-4">
                      {t.assigned_to ? (
                        <span className="inline-flex items-center gap-1 text-slate-700 font-semibold">
                          <UserCheck className="w-3.5 h-3.5 text-indigo-500" />
                          <span>{t.assigned_to.full_name || t.assigned_to.email}</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-amber-600 font-semibold bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200 text-[10px]">
                          Unassigned
                        </span>
                      )}
                    </td>

                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          openTicketDetail(t.ticket_number);
                        }}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                      >
                        <ChevronRight className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 6. Quick Access Catalog Workspaces */}
      <div>
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
          Accessible Inquiries &amp; Catalog Workspaces
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div
            onClick={() => onNavigateTab("marketplace_browse")}
            className="group bg-white border border-slate-200 hover:border-amber-400 rounded-2xl p-5 shadow-sm hover:shadow-md transition-all cursor-pointer flex flex-col justify-between"
          >
            <div>
              <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-100 flex items-center justify-center text-amber-600 mb-3 group-hover:scale-105 transition-transform">
                <ShoppingBag className="w-5 h-5" />
              </div>
              <h3 className="font-bold text-sm text-slate-900 group-hover:text-amber-600 transition-colors">
                Marketplace Listings
              </h3>
              <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                Search approved vehicles and verified spare parts catalogue to assist customer purchase inquiries.
              </p>
            </div>
            <div className="mt-4 flex items-center gap-1 text-xs font-bold text-amber-600">
              <span>Open Catalog</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </div>
          </div>

          <div
            onClick={() => onNavigateTab("workshops_public")}
            className="group bg-white border border-slate-200 hover:border-amber-400 rounded-2xl p-5 shadow-sm hover:shadow-md transition-all cursor-pointer flex flex-col justify-between"
          >
            <div>
              <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-100 flex items-center justify-center text-amber-600 mb-3 group-hover:scale-105 transition-transform">
                <Wrench className="w-5 h-5" />
              </div>
              <h3 className="font-bold text-sm text-slate-900 group-hover:text-amber-600 transition-colors">
                Workshop Directory
              </h3>
              <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                Browse accredited repair centers and available service slots for service booking guidance.
              </p>
            </div>
            <div className="mt-4 flex items-center gap-1 text-xs font-bold text-amber-600">
              <span>Find Workshops</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </div>
          </div>
        </div>
      </div>

      {/* 7. Slide-over Ticket Detail Drawer */}
      {selectedTicketId && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex justify-end">
          <div className="w-full max-w-3xl bg-white h-full shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-200">
            {/* Drawer Header */}
            <div className="bg-slate-900 text-white p-5 flex items-center justify-between border-b border-slate-800 shrink-0">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-bold text-amber-400 text-sm">
                    {ticketDetail?.ticket_number || selectedTicketId}
                  </span>
                  {ticketDetail?.is_confidential && (
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-400/20 text-amber-300 border border-amber-400/30 flex items-center gap-1">
                      <EyeOff className="w-3 h-3" /> CONFIDENTIAL
                    </span>
                  )}
                  {ticketDetail && getPriorityBadge(ticketDetail.priority)}
                  {ticketDetail && getStatusBadge(ticketDetail.status)}
                </div>
                <h2 className="text-base font-bold text-white leading-tight">
                  {ticketDetail?.subject || "Loading ticket..."}
                </h2>
              </div>

              <button
                onClick={closeTicketDrawer}
                className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer Body */}
            {isDetailLoading || !ticketDetail ? (
              <div className="flex-1 flex items-center justify-center text-slate-400 text-xs">
                <RefreshCw className="w-6 h-6 animate-spin mr-2 text-slate-400" />
                Loading ticket conversation &amp; details...
              </div>
            ) : (
              <div className="flex-1 flex flex-col overflow-hidden">
                {/* Meta details & Quick Action Toolbar */}
                <div className="bg-slate-50 border-b border-slate-200 p-4 space-y-3 shrink-0 text-xs">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <div>
                      <div className="text-[10px] text-slate-400 uppercase font-semibold">Customer</div>
                      <div className="font-bold text-slate-800">{ticketDetail.customer?.full_name}</div>
                      <div className="text-[10px] text-slate-500 truncate">{ticketDetail.customer?.email}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-slate-400 uppercase font-semibold">Category</div>
                      <div className="font-bold text-slate-800">{ticketDetail.category_display || ticketDetail.category}</div>
                      {ticketDetail.order_reference && (
                        <div className="text-[10px] text-indigo-600 font-mono">Ref: {ticketDetail.order_reference}</div>
                      )}
                    </div>
                    <div>
                      <div className="text-[10px] text-slate-400 uppercase font-semibold">Assigned Agent</div>
                      <div className="font-bold text-slate-800">
                        {ticketDetail.assigned_to?.full_name || ticketDetail.assigned_to?.email || "Unassigned"}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-slate-400 uppercase font-semibold">Resolution Due</div>
                      <div className="font-bold text-slate-800">
                        {ticketDetail.resolution_due_at
                          ? new Date(ticketDetail.resolution_due_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                          : "None"}
                      </div>
                      {ticketDetail.reopen_count > 0 && (
                        <div className="text-[10px] text-amber-600 font-semibold">Reopened {ticketDetail.reopen_count}x</div>
                      )}
                    </div>
                  </div>

                  {/* Action Bar */}
                  <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-200">
                    {ticketDetail.assigned_to?.id !== user?.id && (
                      <button
                        onClick={() => handleAssignTicket(user?.id || null)}
                        disabled={actionLoading}
                        className="px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs flex items-center gap-1 shadow-sm"
                      >
                        <UserCheck className="w-3.5 h-3.5" />
                        <span>Assign to Me</span>
                      </button>
                    )}

                    <button
                      onClick={() => setIsReassignModalOpen(true)}
                      disabled={actionLoading}
                      className="px-3 py-1.5 rounded-xl bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 font-bold text-xs"
                    >
                      Reassign...
                    </button>

                    {/* Status Transitions */}
                    {ticketDetail.status === "OPEN" && (
                      <button
                        onClick={() => handleUpdateStatus("IN_PROGRESS")}
                        disabled={actionLoading}
                        className="px-3 py-1.5 rounded-xl bg-sky-600 hover:bg-sky-700 text-white font-bold text-xs"
                      >
                        Start Investigation
                      </button>
                    )}

                    {ticketDetail.status === "IN_PROGRESS" && (
                      <button
                        onClick={() => handleUpdateStatus("WAITING_FOR_CUSTOMER", undefined, "Awaiting required details from customer.")}
                        disabled={actionLoading}
                        className="px-3 py-1.5 rounded-xl bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs"
                      >
                        Pause (Wait Customer)
                      </button>
                    )}

                    {ticketDetail.status === "WAITING_FOR_CUSTOMER" && (
                      <button
                        onClick={() => handleUpdateStatus("IN_PROGRESS", undefined, "Resumed investigation after customer check.")}
                        disabled={actionLoading}
                        className="px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs"
                      >
                        Resume Investigation
                      </button>
                    )}

                    {ticketDetail.status !== "RESOLVED" && ticketDetail.status !== "CLOSED" && (
                      <button
                        onClick={() => setIsResolveModalOpen(true)}
                        disabled={actionLoading}
                        className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs flex items-center gap-1"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Resolve Ticket</span>
                      </button>
                    )}

                    {ticketDetail.status !== "CLOSED" && (
                      <div className="flex items-center gap-1 bg-white border border-slate-300 rounded-xl px-2.5 py-1">
                        <span className="text-[10px] text-slate-400 font-semibold uppercase">Priority:</span>
                        <select
                          value={ticketDetail.priority}
                          onChange={(e) => handleUpdatePriority(e.target.value as SupportTicketPriority)}
                          disabled={actionLoading}
                          className="text-xs font-bold text-slate-700 bg-transparent focus:outline-none cursor-pointer"
                        >
                          <option value="LOW">Low</option>
                          <option value="MEDIUM">Medium</option>
                          <option value="HIGH">High</option>
                          <option value="CRITICAL">Critical</option>
                        </select>
                      </div>
                    )}

                    {ticketDetail.status !== "CLOSED" && (
                      <button
                        onClick={() => setIsEscalateModalOpen(true)}
                        disabled={actionLoading}
                        className="px-3 py-1.5 rounded-xl bg-purple-50 text-purple-700 border border-purple-200 hover:bg-purple-100 font-bold text-xs flex items-center gap-1"
                      >
                        <Flame className="w-3.5 h-3.5 text-purple-600" />
                        <span>Escalate</span>
                      </button>
                    )}
                  </div>

                  {actionError && (
                    <div className="p-2 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs">
                      {actionError}
                    </div>
                  )}
                </div>

                {/* Tabs: Conversation vs Activity History */}
                <div className="flex items-center gap-4 px-5 border-b border-slate-200 bg-white shrink-0 text-xs font-bold">
                  <button
                    onClick={() => setActiveDrawerTab("conversation")}
                    className={`py-2.5 border-b-2 transition-colors ${
                      activeDrawerTab === "conversation"
                        ? "border-slate-900 text-slate-900"
                        : "border-transparent text-slate-400 hover:text-slate-600"
                    }`}
                  >
                    Conversation &amp; Notes ({ticketDetail.messages?.length || 0})
                  </button>
                  <button
                    onClick={() => setActiveDrawerTab("activity")}
                    className={`py-2.5 border-b-2 transition-colors flex items-center gap-1 ${
                      activeDrawerTab === "activity"
                        ? "border-slate-900 text-slate-900"
                        : "border-transparent text-slate-400 hover:text-slate-600"
                    }`}
                  >
                    <History className="w-3.5 h-3.5" />
                    <span>Audit &amp; Activity Log ({ticketDetail.activities?.length || 0})</span>
                  </button>
                </div>

                {/* Tab 1: Conversation Timeline */}
                {activeDrawerTab === "conversation" && (
                  <div className="flex-1 overflow-y-auto p-5 space-y-4 bg-slate-50/50">
                    {/* Ticket initial description */}
                    <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm text-xs space-y-2">
                      <div className="flex items-center justify-between text-slate-400 text-[10px]">
                        <span className="font-bold uppercase tracking-wider text-slate-500">
                          Original Customer Request
                        </span>
                        <span>{new Date(ticketDetail.created_at).toLocaleString()}</span>
                      </div>
                      <p className="text-slate-800 whitespace-pre-wrap leading-relaxed">
                        {ticketDetail.description}
                      </p>
                    </div>

                    {/* Resolution summary card if resolved */}
                    {ticketDetail.resolution_summary && (
                      <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-4 text-xs space-y-1">
                        <div className="font-bold text-emerald-950 flex items-center gap-1.5">
                          <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                          <span>Resolution Summary</span>
                        </div>
                        <p className="text-emerald-900 whitespace-pre-wrap leading-relaxed">
                          {ticketDetail.resolution_summary}
                        </p>
                        {ticketDetail.resolved_by && (
                          <div className="text-[10px] text-emerald-700">
                            Resolved by {ticketDetail.resolved_by.full_name} ({ticketDetail.resolved_by.email})
                          </div>
                        )}
                      </div>
                    )}

                    {/* Messages */}
                    {ticketDetail.messages?.map((msg) => {
                      if (msg.is_internal_note) {
                        return (
                          /* Internal Private Staff Note */
                          <div
                            key={msg.id}
                            className="bg-amber-50/80 border-2 border-amber-300 rounded-2xl p-4 shadow-sm space-y-2"
                          >
                            <div className="flex items-center justify-between text-xs">
                              <div className="flex items-center gap-1.5 text-amber-900 font-bold">
                                <Lock className="w-3.5 h-3.5 text-amber-600" />
                                <span>INTERNAL NOTE (STAFF ONLY)</span>
                                <span className="text-amber-700 font-normal">&bull; {msg.sender_name || msg.sender_email}</span>
                              </div>
                              <span className="text-[10px] text-amber-700">
                                {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                              </span>
                            </div>
                            <p className="text-xs text-amber-950 whitespace-pre-wrap leading-relaxed">
                              {msg.message}
                            </p>
                            {msg.attachments && msg.attachments.length > 0 && (
                              <div className="pt-2 border-t border-amber-200 flex flex-wrap gap-2">
                                {msg.attachments.map((att) => (
                                  <button
                                    key={att.id}
                                    onClick={() => handleDownloadAttachment(att.id, att.file_name)}
                                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-amber-100 hover:bg-amber-200 text-amber-900 text-xs font-semibold"
                                  >
                                    <Download className="w-3 h-3 text-amber-700" />
                                    <span>{att.file_name}</span>
                                    <span className="text-[10px] text-amber-600 font-normal">({Math.round(att.file_size / 1024)} KB)</span>
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      }

                      const isAgent = msg.sender_type === "STAFF";
                      return (
                        /* Public Message (Customer or Agent) */
                        <div
                          key={msg.id}
                          className={`flex flex-col ${isAgent ? "items-end" : "items-start"}`}
                        >
                          <div
                            className={`max-w-[85%] rounded-2xl p-4 shadow-sm text-xs space-y-1.5 ${
                              isAgent
                                ? "bg-slate-900 text-white rounded-tr-none"
                                : "bg-white border border-slate-200 text-slate-900 rounded-tl-none"
                            }`}
                          >
                            <div className={`flex items-center justify-between gap-4 text-[10px] ${isAgent ? "text-slate-400" : "text-slate-500"}`}>
                              <span className="font-bold flex items-center gap-1">
                                {isAgent ? <Globe className="w-3 h-3 text-emerald-400" /> : <User className="w-3 h-3 text-sky-500" />}
                                {isAgent ? "Support Agent Reply" : (msg.sender_name || "Customer")}
                              </span>
                              <span>{new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                            </div>

                            <p className="whitespace-pre-wrap leading-relaxed">{msg.message}</p>

                            {msg.attachments && msg.attachments.length > 0 && (
                              <div className={`pt-2 border-t flex flex-wrap gap-2 ${isAgent ? "border-slate-800" : "border-slate-100"}`}>
                                {msg.attachments.map((att) => (
                                  <button
                                    key={att.id}
                                    onClick={() => handleDownloadAttachment(att.id, att.file_name)}
                                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold ${
                                      isAgent ? "bg-slate-800 hover:bg-slate-700 text-slate-200" : "bg-slate-100 hover:bg-slate-200 text-slate-800"
                                    }`}
                                  >
                                    <Download className="w-3 h-3" />
                                    <span>{att.file_name}</span>
                                    <span className="text-[10px] opacity-70">({Math.round(att.file_size / 1024)} KB)</span>
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Tab 2: Activity History Log */}
                {activeDrawerTab === "activity" && (
                  <div className="flex-1 overflow-y-auto p-5 space-y-3 bg-slate-50/50 text-xs">
                    {ticketDetail.activities?.map((act) => (
                      <div key={act.id} className="bg-white border border-slate-200 rounded-xl p-3 flex items-start gap-3">
                        <History className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                        <div className="flex-1 space-y-0.5">
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="font-bold text-slate-800">{act.activity_type.replace(/_/g, " ")}</span>
                            <span className="text-slate-400 text-[10px]">{new Date(act.created_at).toLocaleString()}</span>
                          </div>
                          {act.notes && <p className="text-slate-600">{act.notes}</p>}
                          {(act.old_value || act.new_value) && (
                            <div className="text-[10px] text-slate-400">
                              {act.old_value && <span className="line-through mr-1">{act.old_value}</span>}
                              {act.new_value && <span className="font-bold text-slate-700">&rarr; {act.new_value}</span>}
                            </div>
                          )}
                          <div className="text-[10px] text-slate-400">by {act.actor_name || act.actor_email}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Drawer Footer Composer */}
                {ticketDetail.status !== "CLOSED" ? (
                  <div className="bg-white border-t border-slate-200 p-4 space-y-3 shrink-0">
                    {/* Mode Toggle: Public vs Internal Note */}
                    <div className="flex items-center justify-between">
                      <div className="inline-flex rounded-xl p-1 bg-slate-100 border border-slate-200 text-xs font-bold">
                        <button
                          type="button"
                          onClick={() => setComposerMode("public")}
                          className={`px-3 py-1 rounded-lg transition-all flex items-center gap-1.5 ${
                            composerMode === "public"
                              ? "bg-white text-emerald-700 shadow-sm"
                              : "text-slate-500 hover:text-slate-800"
                          }`}
                        >
                          <Globe className="w-3.5 h-3.5" />
                          <span>Public Reply to Customer</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setComposerMode("internal")}
                          className={`px-3 py-1 rounded-lg transition-all flex items-center gap-1.5 ${
                            composerMode === "internal"
                              ? "bg-amber-400 text-amber-950 shadow-sm"
                              : "text-slate-500 hover:text-slate-800"
                          }`}
                        >
                          <Lock className="w-3.5 h-3.5" />
                          <span>Private Internal Staff Note</span>
                        </button>
                      </div>

                      {composerMode === "internal" ? (
                        <span className="text-[11px] font-semibold text-amber-700 flex items-center gap-1">
                          <Lock className="w-3 h-3" /> Visible to platform staff only
                        </span>
                      ) : (
                        <span className="text-[11px] font-semibold text-emerald-700 flex items-center gap-1">
                          <Globe className="w-3 h-3" /> Advances first-response SLA
                        </span>
                      )}
                    </div>

                    {/* Composer Input Form */}
                    <form onSubmit={handleSendMessage} className="space-y-2">
                      <textarea
                        rows={3}
                        value={messageText}
                        onChange={(e) => setMessageText(e.target.value)}
                        placeholder={
                          composerMode === "internal"
                            ? "Record an internal observation, verification finding, or team escalation note..."
                            : "Write a public response to the customer..."
                        }
                        className={`w-full p-3 rounded-xl border text-xs focus:outline-none focus:ring-2 resize-none ${
                          composerMode === "internal"
                            ? "bg-amber-50/50 border-amber-300 focus:ring-amber-500 text-amber-950 placeholder-amber-700/60"
                            : "bg-white border-slate-200 focus:ring-slate-900 text-slate-900"
                        }`}
                      />

                      {/* File attachment preview */}
                      {selectedFile && (
                        <div className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs">
                          <span className="font-semibold text-slate-700 truncate max-w-sm">
                            {selectedFile.name} ({Math.round(selectedFile.size / 1024)} KB)
                          </span>
                          <button
                            type="button"
                            onClick={() => setSelectedFile(null)}
                            className="text-slate-400 hover:text-rose-600 font-bold ml-2"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      )}

                      {uploadError && (
                        <div className="text-xs text-rose-600 font-semibold">{uploadError}</div>
                      )}

                      <div className="flex items-center justify-between">
                        <label
                          htmlFor={fileInputId}
                          className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-slate-800 cursor-pointer p-1 rounded-lg hover:bg-slate-100"
                        >
                          <Paperclip className="w-4 h-4" />
                          <span>Attach file (PNG, JPG, PDF, TXT)</span>
                        </label>
                        <input
                          id={fileInputId}
                          type="file"
                          onChange={(e) => {
                            if (e.target.files && e.target.files[0]) {
                              setSelectedFile(e.target.files[0]);
                            }
                          }}
                          className="hidden"
                        />

                        <button
                          type="submit"
                          disabled={isSendingMessage || (!messageText.trim() && !selectedFile)}
                          className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5 shadow-sm transition-all ${
                            composerMode === "internal"
                              ? "bg-amber-500 hover:bg-amber-600 text-amber-950"
                              : "bg-slate-900 hover:bg-slate-800 text-white"
                          } disabled:opacity-50`}
                        >
                          <Send className="w-3.5 h-3.5" />
                          <span>{composerMode === "internal" ? "Add Internal Note" : "Send Customer Reply"}</span>
                        </button>
                      </div>
                    </form>
                  </div>
                ) : (
                  <div className="bg-slate-100 border-t border-slate-200 p-4 text-center text-xs text-slate-500 font-medium">
                    This support ticket is CLOSED. Transitions and additional messages are blocked.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 8. Resolve Ticket Modal (Mandatory Summary) */}
      {isResolveModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between">
              <div className="font-bold text-base text-slate-900 flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                <span>Resolve Support Ticket</span>
              </div>
              <button onClick={() => setIsResolveModalOpen(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              To resolve this ticket, you must provide a detailed resolution summary of at least 10 characters explaining how the customer inquiry was addressed.
            </p>

            <textarea
              rows={4}
              value={resolutionSummary}
              onChange={(e) => setResolutionSummary(e.target.value)}
              placeholder="E.g., Verified vehicle brake disc fitment with OEM supplier catalogue and advised customer to order part #BK-7890."
              className="w-full p-3 rounded-xl border border-slate-200 text-xs focus:ring-2 focus:ring-emerald-500 focus:outline-none"
            />

            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>{resolutionSummary.trim().length} / 10 min characters</span>
              {resolutionSummary.trim().length < 10 && (
                <span className="text-rose-500 font-semibold">Minimum 10 characters required</span>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setIsResolveModalOpen(false)}
                className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleUpdateStatus("RESOLVED", resolutionSummary.trim())}
                disabled={actionLoading || resolutionSummary.trim().length < 10}
                className="px-4 py-2 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white disabled:opacity-50"
              >
                {actionLoading ? "Resolving..." : "Confirm & Resolve"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 9. Reassign Ticket Modal */}
      {isReassignModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between">
              <div className="font-bold text-base text-slate-900 flex items-center gap-2">
                <UserCheck className="w-5 h-5 text-indigo-600" />
                <span>Reassign Ticket</span>
              </div>
              <button onClick={() => setIsReassignModalOpen(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              Select an active Support Agent or Platform Admin to take ownership of this ticket:
            </p>

            <select
              value={selectedTargetAgent}
              onChange={(e) => setSelectedTargetAgent(e.target.value)}
              className="w-full p-3 rounded-xl border border-slate-200 text-xs font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            >
              <option value="">-- Return to Unassigned Triage --</option>
              {staffMembers.map((sm) => (
                <option key={sm.id} value={sm.id}>
                  {sm.full_name} ({sm.email}) &bull; {sm.active_tickets_count} active tickets
                </option>
              ))}
            </select>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setIsReassignModalOpen(false)}
                className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleAssignTicket(selectedTargetAgent || null)}
                disabled={actionLoading}
                className="px-4 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50"
              >
                {actionLoading ? "Updating..." : "Confirm Assignment"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 10. Escalate Ticket Modal */}
      {isEscalateModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between">
              <div className="font-bold text-base text-slate-900 flex items-center gap-2">
                <Flame className="w-5 h-5 text-purple-600" />
                <span>Escalate Support Ticket</span>
              </div>
              <button onClick={() => setIsEscalateModalOpen(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-2 text-xs">
              <label className="font-semibold text-slate-700">Target Escalation Stage</label>
              <select
                value={escalateStage}
                onChange={(e) => setEscalateStage(Number(e.target.value))}
                className="w-full p-2.5 rounded-xl border border-slate-200 text-xs font-medium focus:ring-2 focus:ring-purple-500 focus:outline-none"
              >
                <option value={1}>Stage 1: Warning (75% SLA elapsed)</option>
                <option value={2}>Stage 2: Breach (100% SLA elapsed)</option>
                <option value={3}>Stage 3: Prolonged Critical Breach (&gt;24h overdue)</option>
              </select>
            </div>

            <div className="space-y-2 text-xs">
              <label className="font-semibold text-slate-700">Escalation Reason</label>
              <textarea
                rows={3}
                value={escalateReason}
                onChange={(e) => setEscalateReason(e.target.value)}
                placeholder="Explain why this ticket is being escalated to senior leads..."
                className="w-full p-3 rounded-xl border border-slate-200 text-xs focus:ring-2 focus:ring-purple-500 focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setIsEscalateModalOpen(false)}
                className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleEscalateTicket}
                disabled={actionLoading || !escalateReason.trim()}
                className="px-4 py-2 rounded-xl text-xs font-bold bg-purple-600 hover:bg-purple-700 text-white disabled:opacity-50"
              >
                {actionLoading ? "Escalating..." : "Confirm Escalation"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
