"use client";

import React, { useState, useEffect, useCallback, useId } from "react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  api,
  SupportTicketSummary,
  SupportTicketDetail,
  SupportTicketCategory,
  SupportTicketPriority,
  SupportTicketStatus,
} from "@/lib/api/client";
import {
  Headphones,
  Plus,
  Search,
  RefreshCw,
  Clock,
  CheckCircle2,
  AlertCircle,
  X,
  Send,
  Paperclip,
  Download,
  User,
  ShieldCheck,
  ChevronRight,
} from "lucide-react";

export default function CustomerSupportTicketsView() {
  const { user } = useAuth();

  const [tickets, setTickets] = useState<SupportTicketSummary[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Create Ticket Modal
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [newSubject, setNewSubject] = useState<string>("");
  const [newCategory, setNewCategory] = useState<SupportTicketCategory>("GENERAL_INQUIRY");
  const [newPriority, setNewPriority] = useState<SupportTicketPriority>("MEDIUM");
  const [newDescription, setNewDescription] = useState<string>("");
  const [newOrderRef, setNewOrderRef] = useState<string>("");
  const [createFile, setCreateFile] = useState<File | null>(null);
  const [isCreating, setIsCreating] = useState<boolean>(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const newFileInputId = useId();

  // Detail Modal / Drawer
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [ticketDetail, setTicketDetail] = useState<SupportTicketDetail | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState<boolean>(false);

  // Customer Reply Composer
  const [replyMessage, setReplyMessage] = useState<string>("");
  const [replyFile, setReplyFile] = useState<File | null>(null);
  const [isSendingReply, setIsSendingReply] = useState<boolean>(false);
  const [replyError, setReplyError] = useState<string | null>(null);
  const replyFileInputId = useId();

  // Close / Reopen state
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isCloseModalOpen, setIsCloseModalOpen] = useState<boolean>(false);
  const [closeReason, setCloseReason] = useState<string>("");

  // 1. Load Customer Tickets
  const loadTickets = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.support.getMyTickets(statusFilter !== "ALL" ? statusFilter : undefined);
      let list = res.tickets || [];
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        list = list.filter(
          (t) =>
            t.ticket_number.toLowerCase().includes(q) ||
            t.subject.toLowerCase().includes(q) ||
            (t.order_reference && t.order_reference.toLowerCase().includes(q))
        );
      }
      setTickets(list);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load support tickets.");
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter, searchQuery]);

  useEffect(() => {
    queueMicrotask(() => {
      void loadTickets();
    });
  }, [loadTickets]);

  // 2. Load Ticket Detail
  const openTicketDetail = async (identifier: string) => {
    setSelectedTicketId(identifier);
    setIsDetailLoading(true);
    setActionError(null);
    try {
      const res = await api.support.getMyTicket(identifier);
      setTicketDetail(res.ticket);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to load ticket details.");
    } finally {
      setIsDetailLoading(false);
    }
  };

  const closeTicketDetail = () => {
    setSelectedTicketId(null);
    setTicketDetail(null);
    setReplyMessage("");
    setReplyFile(null);
    setReplyError(null);
  };

  // 3. Create Ticket
  const handleCreateTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSubject.trim() || newDescription.trim().length < 10) return;

    setIsCreating(true);
    setCreateError(null);

    try {
      const res = await api.support.createTicket({
        subject: newSubject.trim(),
        category: newCategory,
        priority: newPriority,
        description: newDescription.trim(),
        order_reference: newOrderRef.trim() || undefined,
      });

      // Upload attachment if selected
      if (createFile && res.ticket?.ticket_number) {
        await api.support.uploadAttachment(res.ticket.ticket_number, createFile);
      }

      setIsCreateModalOpen(false);
      setNewSubject("");
      setNewDescription("");
      setNewOrderRef("");
      setCreateFile(null);
      loadTickets();
      if (res.ticket?.ticket_number) {
        openTicketDetail(res.ticket.ticket_number);
      }
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : "Failed to create support ticket.");
    } finally {
      setIsCreating(false);
    }
  };

  // 4. Send Customer Reply
  const handleSendReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticketDetail || (!replyMessage.trim() && !replyFile)) return;

    setIsSendingReply(true);
    setReplyError(null);

    try {
      let sentMsgId: string | undefined;

      if (replyMessage.trim()) {
        const msgRes = await api.support.sendCustomerMessage(ticketDetail.ticket_number, {
          message: replyMessage.trim(),
        });
        sentMsgId = msgRes.message?.id;
      }

      if (replyFile) {
        await api.support.uploadAttachment(ticketDetail.ticket_number, replyFile, {
          messageId: sentMsgId,
        });
      }

      setReplyMessage("");
      setReplyFile(null);

      // Refresh ticket detail & list
      const updatedRes = await api.support.getMyTicket(ticketDetail.ticket_number);
      setTicketDetail(updatedRes.ticket);
      loadTickets();
    } catch (err: unknown) {
      setReplyError(err instanceof Error ? err.message : "Failed to send message.");
    } finally {
      setIsSendingReply(false);
    }
  };

  // 5. Customer Confirm & Close Ticket
  const handleConfirmClose = async () => {
    if (!ticketDetail) return;
    setActionLoading(true);
    setActionError(null);
    try {
      const res = await api.support.closeCustomerTicket(ticketDetail.ticket_number, closeReason.trim() || undefined);
      setTicketDetail(res.ticket);
      setIsCloseModalOpen(false);
      setCloseReason("");
      loadTickets();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to close ticket.");
    } finally {
      setActionLoading(false);
    }
  };

  // 6. Download Attachment
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

  // Status badge helper
  const getStatusBadge = (s: SupportTicketStatus) => {
    switch (s) {
      case "OPEN":
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-sky-50 text-sky-700 border border-sky-200">OPEN</span>;
      case "IN_PROGRESS":
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">IN INVESTIGATION</span>;
      case "WAITING_FOR_CUSTOMER":
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-50 text-amber-800 border border-amber-200">ACTION REQUIRED</span>;
      case "RESOLVED":
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">RESOLVED</span>;
      case "CLOSED":
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-slate-100 text-slate-700 border border-slate-200">CLOSED</span>;
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* 1. Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 text-white shadow-xl relative overflow-hidden">
        <div className="absolute right-0 top-0 translate-x-12 -translate-y-12 w-64 h-64 bg-amber-400/10 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-amber-400/20 text-amber-300 border border-amber-400/30 mb-2">
              <Headphones className="w-3.5 h-3.5" />
              <span>Customer Help &amp; Support</span>
            </div>
            <h1 className="text-2xl font-black text-white tracking-tight">
              Support Inquiries &amp; Assistance
            </h1>
            <p className="text-slate-300 text-xs mt-1 max-w-2xl leading-relaxed">
              Have a question about a vehicle listing, spare parts compatibility, workshop booking, or payment refund? Our dedicated support team is here to help{user ? ` for ${user.fullName || user.email}` : ""}.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsCreateModalOpen(true)}
              className="px-4 py-2.5 rounded-2xl bg-amber-400 hover:bg-amber-300 text-slate-950 font-bold text-xs flex items-center gap-1.5 shadow-lg shadow-amber-400/20 transition-all hover:scale-105"
            >
              <Plus className="w-4 h-4" />
              <span>Create New Ticket</span>
            </button>
            <button
              onClick={loadTickets}
              disabled={isLoading}
              className="p-2.5 rounded-2xl bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
              title="Refresh Tickets"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>
      </div>

      {/* 2. Controls & Search */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2 overflow-x-auto text-xs">
          <button
            onClick={() => setStatusFilter("ALL")}
            className={`px-3 py-1.5 rounded-xl font-bold transition-all ${
              statusFilter === "ALL" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            All Tickets
          </button>
          <button
            onClick={() => setStatusFilter("OPEN")}
            className={`px-3 py-1.5 rounded-xl font-bold transition-all ${
              statusFilter === "OPEN" ? "bg-sky-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Open
          </button>
          <button
            onClick={() => setStatusFilter("WAITING_FOR_CUSTOMER")}
            className={`px-3 py-1.5 rounded-xl font-bold transition-all ${
              statusFilter === "WAITING_FOR_CUSTOMER" ? "bg-amber-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Awaiting Your Action
          </button>
          <button
            onClick={() => setStatusFilter("RESOLVED")}
            className={`px-3 py-1.5 rounded-xl font-bold transition-all ${
              statusFilter === "RESOLVED" ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Resolved
          </button>
          <button
            onClick={() => setStatusFilter("CLOSED")}
            className={`px-3 py-1.5 rounded-xl font-bold transition-all ${
              statusFilter === "CLOSED" ? "bg-slate-700 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Closed
          </button>
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search your tickets..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-xs rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-slate-900"
          />
        </div>
      </div>

      {error && (
        <div className="bg-rose-50 border border-rose-200 rounded-2xl p-4 text-rose-900 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 3. Tickets List */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-12 text-center text-slate-400 text-xs">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-slate-300" />
            Loading your tickets...
          </div>
        ) : tickets.length === 0 ? (
          <div className="p-12 text-center text-slate-500 text-xs space-y-2">
            <Headphones className="w-8 h-8 text-slate-300 mx-auto mb-2" />
            <div className="font-bold text-slate-800 text-sm">No support tickets found</div>
            <p className="text-slate-400 max-w-sm mx-auto">
              You haven&apos;t opened any support tickets yet. Click &ldquo;Create New Ticket&rdquo; above if you need assistance.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {tickets.map((t) => (
              <div
                key={t.id}
                onClick={() => openTicketDetail(t.ticket_number)}
                className="p-4 sm:p-5 hover:bg-slate-50/80 cursor-pointer transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
              >
                <div className="space-y-1 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-slate-900">{t.ticket_number}</span>
                    {getStatusBadge(t.status)}
                    <span className="text-[11px] text-slate-500 font-medium">
                      &bull; {t.category_display || t.category}
                    </span>
                    {t.order_reference && (
                      <span className="text-[11px] text-indigo-600 font-mono">
                        (Order: {t.order_reference})
                      </span>
                    )}
                  </div>
                  <h3 className="font-bold text-slate-900 text-sm">{t.subject}</h3>
                  <div className="text-[11px] text-slate-400">
                    Created on {new Date(t.created_at).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}
                    {t.status === "WAITING_FOR_CUSTOMER" && (
                      <span className="ml-2 font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                        Agent is waiting for your reply
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <div className="text-right hidden sm:block">
                    <div className="text-[10px] text-slate-400 uppercase font-semibold">Priority</div>
                    <div className="font-bold text-slate-700">{t.priority}</div>
                  </div>
                  <ChevronRight className="w-5 h-5 text-slate-300" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 4. Ticket Detail Drawer */}
      {selectedTicketId && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex justify-end">
          <div className="w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-200">
            {/* Drawer Header */}
            <div className="bg-slate-900 text-white p-5 flex items-center justify-between border-b border-slate-800 shrink-0">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-bold text-amber-400 text-sm">
                    {ticketDetail?.ticket_number || selectedTicketId}
                  </span>
                  {ticketDetail && getStatusBadge(ticketDetail.status)}
                </div>
                <h2 className="text-base font-bold text-white leading-tight">
                  {ticketDetail?.subject || "Loading..."}
                </h2>
              </div>
              <button
                onClick={closeTicketDetail}
                className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer Body */}
            {isDetailLoading || !ticketDetail ? (
              <div className="flex-1 flex items-center justify-center text-slate-400 text-xs">
                <RefreshCw className="w-6 h-6 animate-spin mr-2" />
                Loading conversation thread...
              </div>
            ) : (
              <div className="flex-1 flex flex-col overflow-hidden">
                {/* Resolution Summary Banner if resolved */}
                {ticketDetail.resolution_summary && (
                  <div className="bg-emerald-50 border-b border-emerald-200 p-4 shrink-0 text-xs space-y-2">
                    <div className="font-bold text-emerald-950 flex items-center gap-1.5">
                      <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                      <span>Resolution Provided by Support</span>
                    </div>
                    <p className="text-emerald-900 whitespace-pre-wrap leading-relaxed">
                      {ticketDetail.resolution_summary}
                    </p>
                    {ticketDetail.status === "RESOLVED" && (
                      <div className="pt-2 flex items-center gap-2">
                        <button
                          onClick={() => setIsCloseModalOpen(true)}
                          className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs"
                        >
                          Confirm &amp; Close Ticket
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* Messages Timeline */}
                <div className="flex-1 overflow-y-auto p-5 space-y-4 bg-slate-50/50 text-xs">
                  {/* Original Customer Problem Description */}
                  <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-2">
                    <div className="flex items-center justify-between text-slate-400 text-[10px]">
                      <span className="font-bold uppercase tracking-wider text-slate-500">
                        Your Initial Message
                      </span>
                      <span>{new Date(ticketDetail.created_at).toLocaleString()}</span>
                    </div>
                    <p className="text-slate-800 whitespace-pre-wrap leading-relaxed">
                      {ticketDetail.description}
                    </p>
                  </div>

                  {/* Messages */}
                  {ticketDetail.messages?.map((msg) => {
                    const isStaff = msg.sender_type === "STAFF";
                    return (
                      <div
                        key={msg.id}
                        className={`flex flex-col ${isStaff ? "items-start" : "items-end"}`}
                      >
                        <div
                          className={`max-w-[85%] rounded-2xl p-4 shadow-sm text-xs space-y-1.5 ${
                            isStaff
                              ? "bg-white border-2 border-indigo-100 text-slate-900 rounded-tl-none"
                              : "bg-slate-900 text-white rounded-tr-none"
                          }`}
                        >
                          <div className={`flex items-center justify-between gap-4 text-[10px] ${isStaff ? "text-indigo-600 font-bold" : "text-slate-400"}`}>
                            <span className="flex items-center gap-1">
                              {isStaff ? <ShieldCheck className="w-3.5 h-3.5 text-indigo-600" /> : <User className="w-3.5 h-3.5" />}
                              {isStaff ? "DriverXtra Support Team" : "You"}
                            </span>
                            <span>{new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                          </div>

                          <p className="whitespace-pre-wrap leading-relaxed">{msg.message}</p>

                          {msg.attachments && msg.attachments.length > 0 && (
                            <div className="pt-2 border-t border-slate-100 flex flex-wrap gap-2">
                              {msg.attachments.map((att) => (
                                <button
                                  key={att.id}
                                  onClick={() => handleDownloadAttachment(att.id, att.file_name)}
                                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold ${
                                    isStaff ? "bg-indigo-50 text-indigo-800 hover:bg-indigo-100" : "bg-slate-800 text-slate-200 hover:bg-slate-700"
                                  }`}
                                >
                                  <Download className="w-3 h-3" />
                                  <span>{att.file_name}</span>
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Customer Reply Composer */}
                {ticketDetail.status !== "CLOSED" ? (
                  <div className="bg-white border-t border-slate-200 p-4 space-y-2 shrink-0">
                    {ticketDetail.status === "WAITING_FOR_CUSTOMER" && (
                      <div className="bg-amber-50 border border-amber-200 rounded-xl p-2.5 text-amber-900 text-xs flex items-center gap-2">
                        <Clock className="w-4 h-4 text-amber-600 shrink-0" />
                        <span>Sending a response will automatically update your ticket and notify our support agents.</span>
                      </div>
                    )}

                    <form onSubmit={handleSendReply} className="space-y-2">
                      <textarea
                        rows={3}
                        value={replyMessage}
                        onChange={(e) => setReplyMessage(e.target.value)}
                        placeholder="Type your reply to the support agent..."
                        className="w-full p-3 rounded-xl border border-slate-200 text-xs focus:ring-2 focus:ring-slate-900 focus:outline-none resize-none"
                      />

                      {replyFile && (
                        <div className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs">
                          <span className="font-semibold text-slate-700 truncate max-w-sm">
                            {replyFile.name} ({Math.round(replyFile.size / 1024)} KB)
                          </span>
                          <button
                            type="button"
                            onClick={() => setReplyFile(null)}
                            className="text-slate-400 hover:text-rose-600 font-bold ml-2"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      )}

                      {replyError && (
                        <div className="text-xs text-rose-600 font-semibold">{replyError}</div>
                      )}

                      <div className="flex items-center justify-between">
                        <label
                          htmlFor={replyFileInputId}
                          className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-slate-800 cursor-pointer p-1 rounded-lg hover:bg-slate-100"
                        >
                          <Paperclip className="w-4 h-4" />
                          <span>Attach File</span>
                        </label>
                        <input
                          id={replyFileInputId}
                          type="file"
                          onChange={(e) => {
                            if (e.target.files && e.target.files[0]) {
                              setReplyFile(e.target.files[0]);
                            }
                          }}
                          className="hidden"
                        />

                        <button
                          type="submit"
                          disabled={isSendingReply || (!replyMessage.trim() && !replyFile)}
                          className="px-4 py-2 rounded-xl text-xs font-bold bg-slate-900 hover:bg-slate-800 text-white flex items-center gap-1.5 disabled:opacity-50"
                        >
                          <Send className="w-3.5 h-3.5" />
                          <span>Send Reply</span>
                        </button>
                      </div>
                    </form>
                  </div>
                ) : (
                  <div className="bg-slate-100 border-t border-slate-200 p-4 text-center text-xs text-slate-500 font-medium">
                    This support ticket has been closed. If you have an unrelated question, please create a new ticket.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 5. Create Ticket Modal */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 space-y-4 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between">
              <div className="font-bold text-base text-slate-900 flex items-center gap-2">
                <Headphones className="w-5 h-5 text-amber-500" />
                <span>Create Support Ticket</span>
              </div>
              <button onClick={() => setIsCreateModalOpen(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateTicket} className="space-y-3 text-xs">
              <div className="space-y-1">
                <label className="font-semibold text-slate-700">Subject</label>
                <input
                  type="text"
                  required
                  value={newSubject}
                  onChange={(e) => setNewSubject(e.target.value)}
                  placeholder="Brief summary of your question or issue..."
                  className="w-full p-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-slate-900 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="font-semibold text-slate-700">Category</label>
                  <select
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value as SupportTicketCategory)}
                    className="w-full p-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-slate-900 focus:outline-none bg-white"
                  >
                    <option value="GENERAL_INQUIRY">General Inquiry</option>
                    <option value="ORDER_ISSUE">Order &amp; Delivery Issue</option>
                    <option value="PART_COMPATIBILITY">Part Fitment &amp; Compatibility</option>
                    <option value="WORKSHOP_BOOKING">Workshop Booking &amp; Services</option>
                    <option value="PAYMENT_BILLING">Payment &amp; Invoice Assistance</option>
                    <option value="ACCOUNT_SECURITY">Account &amp; Profile Security</option>
                    <option value="RETURNS_ASSISTANCE">Returns &amp; Refunds Assistance</option>
                    <option value="TECHNICAL_SUPPORT">Technical Platform Issue</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="font-semibold text-slate-700">Priority</label>
                  <select
                    value={newPriority}
                    onChange={(e) => setNewPriority(e.target.value as SupportTicketPriority)}
                    className="w-full p-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-slate-900 focus:outline-none bg-white"
                  >
                    <option value="LOW">Low</option>
                    <option value="MEDIUM">Medium (Standard)</option>
                    <option value="HIGH">High (Urgent)</option>
                    <option value="CRITICAL">Critical (24/7)</option>
                  </select>
                </div>
              </div>

              <div className="space-y-1">
                <label className="font-semibold text-slate-700">Order Reference (Optional)</label>
                <input
                  type="text"
                  value={newOrderRef}
                  onChange={(e) => setNewOrderRef(e.target.value)}
                  placeholder="E.g., ORD-20261110-123456"
                  className="w-full p-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-slate-900 focus:outline-none font-mono"
                />
              </div>

              <div className="space-y-1">
                <label className="font-semibold text-slate-700">Detailed Description</label>
                <textarea
                  rows={4}
                  required
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="Provide all relevant details, vehicle registration, part numbers, or symptoms..."
                  className="w-full p-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-slate-900 focus:outline-none resize-none"
                />
                <div className="text-[10px] text-slate-400">
                  {newDescription.trim().length} / 10 minimum characters required
                </div>
              </div>

              {/* File Attachment */}
              <div className="space-y-1">
                <label className="font-semibold text-slate-700">Attach Document or Screenshot (Optional)</label>
                <input
                  id={newFileInputId}
                  type="file"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      setCreateFile(e.target.files[0]);
                    }
                  }}
                  className="block w-full text-xs text-slate-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200"
                />
              </div>

              {createError && (
                <div className="p-2.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-semibold">
                  {createError}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-100"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isCreating || !newSubject.trim() || newDescription.trim().length < 10}
                  className="px-4 py-2 rounded-xl text-xs font-bold bg-amber-400 hover:bg-amber-300 text-slate-950 disabled:opacity-50 shadow-sm"
                >
                  {isCreating ? "Submitting..." : "Submit Ticket"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 6. Confirm Close Modal */}
      {isCloseModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between">
              <div className="font-bold text-base text-slate-900 flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                <span>Confirm Resolution &amp; Close</span>
              </div>
              <button onClick={() => setIsCloseModalOpen(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              Are you satisfied with the assistance provided? Closing this ticket marks it as resolved.
            </p>

            <textarea
              rows={2}
              value={closeReason}
              onChange={(e) => setCloseReason(e.target.value)}
              placeholder="Optional feedback or notes on resolution..."
              className="w-full p-2.5 rounded-xl border border-slate-200 text-xs focus:ring-2 focus:ring-emerald-500 focus:outline-none"
            />

            {actionError && (
              <div className="p-2.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-semibold">
                {actionError}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setIsCloseModalOpen(false)}
                className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmClose}
                disabled={actionLoading}
                className="px-4 py-2 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white disabled:opacity-50"
              >
                {actionLoading ? "Closing..." : "Close Ticket"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
