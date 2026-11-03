"use client";

import React, { useState, useEffect } from "react";
import { api, WorkshopBooking } from "@/lib/api/client";
import {
  Calendar,
  Clock,
  Filter,
  Search,
  RefreshCw,
  FileText,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  Building2,
  Wrench,
  Mail,
  Phone,
  X,
  ClipboardList,
  History,
  ChevronRight,
} from "lucide-react";

export default function AdminWorkshopOversightView() {
  const [bookings, setBookings] = useState<WorkshopBooking[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedBooking, setSelectedBooking] = useState<WorkshopBooking | null>(null);

  const loadOversightBookings = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const res = await api.workshops.adminBookings.list({
        status: statusFilter !== "ALL" ? statusFilter : undefined,
        q: searchQuery.trim() || undefined,
      });
      setBookings(res.results || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load platform workshop bookings.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    let ignore = false;
    api.workshops.adminBookings
      .list({
        status: statusFilter !== "ALL" ? statusFilter : undefined,
        q: searchQuery.trim() || undefined,
      })
      .then((res) => {
        if (!ignore) {
          setBookings(res.results || []);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : "Failed to load platform workshop bookings.");
          setLoading(false);
        }
      });
    return () => {
      ignore = true;
    };
  }, [statusFilter, searchQuery]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadOversightBookings();
  };

  // Comprehensive client-side search across loaded records
  const filteredBookings = bookings.filter((b) => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return true;

    const ref = (b.booking_reference || b.booking_number || "").toLowerCase();
    const ws = (b.workshop_name || "").toLowerCase();
    const buyer = (b.customer_name || b.buyer_name || "").toLowerCase();
    const buyerEmail = (b.buyer_email || "").toLowerCase();
    const plate = (b.vehicle_registration || b.vehicle_registration_plate || "").toLowerCase();
    const make = (b.vehicle_make || "").toLowerCase();
    const model = (b.vehicle_model || "").toLowerCase();
    const woRef = (b.work_order_number || "").toLowerCase();

    // Check quotations references
    const activeQuoteRef = (b.active_quotation?.quotation_number || "").toLowerCase();
    const quotesRefs = (b.quotations || []).map((quote) => quote.quotation_number.toLowerCase());

    return (
      ref.includes(q) ||
      ws.includes(q) ||
      buyer.includes(q) ||
      buyerEmail.includes(q) ||
      plate.includes(q) ||
      make.includes(q) ||
      model.includes(q) ||
      woRef.includes(q) ||
      activeQuoteRef.includes(q) ||
      quotesRefs.some((qr) => qr.includes(q))
    );
  });

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "CONFIRMED":
        return "bg-emerald-50 text-emerald-700 border-emerald-200";
      case "QUOTED":
        return "bg-purple-50 text-purple-700 border-purple-200";
      case "ACCEPTED":
        return "bg-blue-50 text-blue-700 border-blue-200";
      case "REQUESTED":
      case "UNDER_REVIEW":
        return "bg-amber-50 text-amber-700 border-amber-200";
      case "REJECTED":
      case "CANCELLED":
        return "bg-rose-50 text-rose-700 border-rose-200";
      default:
        return "bg-slate-50 text-slate-700 border-slate-200";
    }
  };

  const getQuotationStatusBadge = (status: string) => {
    switch (status) {
      case "ACCEPTED":
        return "bg-emerald-100 text-emerald-800 border-emerald-300";
      case "ISSUED":
        return "bg-amber-100 text-amber-900 border-amber-300";
      case "REJECTED":
        return "bg-rose-100 text-rose-800 border-rose-300";
      case "DRAFT":
        return "bg-slate-100 text-slate-700 border-slate-300";
      case "SUPERSEDED":
        return "bg-slate-50 text-slate-500 border-slate-200";
      default:
        return "bg-slate-100 text-slate-700 border-slate-300";
    }
  };

  const getWorkOrderStatusBadge = (status: string) => {
    switch (status) {
      case "COMPLETED":
        return "bg-emerald-100 text-emerald-800 border-emerald-300";
      case "IN_PROGRESS":
        return "bg-purple-100 text-purple-800 border-purple-300";
      case "ASSIGNED":
        return "bg-blue-100 text-blue-800 border-blue-300";
      case "AWAITING_PARTS":
        return "bg-amber-100 text-amber-800 border-amber-300";
      case "QUALITY_CHECK":
        return "bg-cyan-100 text-cyan-800 border-cyan-300";
      case "CANCELLED":
        return "bg-rose-100 text-rose-800 border-rose-300";
      default:
        return "bg-slate-100 text-slate-700 border-slate-300";
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Banner */}
      <div className="bg-slate-950 text-white rounded-3xl p-6 shadow-sm border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-purple-500/10 text-purple-400 text-xs font-bold border border-purple-500/20">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Platform Governance & Operational Audit</span>
          </div>
          <h1 className="text-2xl font-black tracking-tight text-white">
            Workshop Operations Oversight
          </h1>
          <p className="text-xs text-slate-400 max-w-2xl">
            Live platform audit stream of all commercial workshop service requests, appointments, bay schedules, customer quotation lifecycle states, and active work orders across all registered workshop tenants.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => loadOversightBookings(true)}
            disabled={refreshing}
            className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-white text-xs font-bold flex items-center gap-2 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin text-purple-400" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1 mr-2">
            <Filter className="w-3.5 h-3.5" /> Filter:
          </span>
          {[
            { label: "All", value: "ALL", desc: "All platform bookings" },
            { label: "Requested", value: "REQUESTED", desc: "Pending initial workshop review" },
            { label: "Accepted", value: "ACCEPTED", desc: "Booking request accepted by workshop" },
            { label: "Confirmed", value: "CONFIRMED", desc: "Scheduled and confirmed (including accepted quotes)" },
            { label: "Quoted", value: "QUOTED", desc: "Official estimate issued and awaiting buyer action" },
            { label: "Rejected", value: "REJECTED", desc: "Declined booking requests" },
            { label: "Cancelled", value: "CANCELLED", desc: "Cancelled bookings" },
          ].map((f) => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              title={f.desc}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition whitespace-nowrap ${
                statusFilter === f.value
                  ? "bg-purple-100 text-purple-900 font-extrabold border border-purple-300 shadow-xs"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <form onSubmit={handleSearchSubmit} className="relative w-full md:w-80">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search ref, quote, WO, workshop, buyer, reg..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-xs bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-purple-500 transition"
          />
        </form>
      </div>

      {/* Main Content */}
      {loading ? (
        <div className="bg-white rounded-2xl p-12 text-center border border-slate-200 space-y-3">
          <RefreshCw className="w-8 h-8 animate-spin text-purple-600 mx-auto" />
          <span className="text-sm font-bold text-slate-600">Loading platform workshop records...</span>
        </div>
      ) : error ? (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-2xl p-6 text-xs text-center space-y-2">
          <XCircle className="w-6 h-6 text-rose-600 mx-auto" />
          <h3 className="font-bold text-sm">Failed to Load Records</h3>
          <p>{error}</p>
        </div>
      ) : filteredBookings.length === 0 ? (
        <div className="bg-white rounded-2xl p-12 text-center border border-slate-200 space-y-2">
          <Calendar className="w-10 h-10 text-slate-300 mx-auto" />
          <h3 className="text-sm font-bold text-slate-700">No Workshop Bookings Found</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            {searchQuery
              ? `No bookings match your search query "${searchQuery}".`
              : statusFilter !== "ALL"
              ? `No bookings currently match status "${statusFilter}".`
              : "No workshop service bookings have been submitted on the platform yet."}
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-4 border-b border-slate-100 flex items-center justify-between">
            <span className="text-xs font-bold text-slate-700">
              Total Recorded Bookings: <strong className="text-slate-900">{filteredBookings.length}</strong>
            </span>
          </div>

          <div className="divide-y divide-slate-100">
            {filteredBookings.map((b) => {
              const activeQuote = b.active_quotation || (b.quotations && b.quotations.length > 0 ? b.quotations[0] : null);
              const hasWorkOrder = Boolean(b.work_order_number);

              return (
                <div
                  key={b.id}
                  className="p-5 hover:bg-slate-50/80 transition space-y-4 cursor-pointer"
                  onClick={() => setSelectedBooking(b)}
                >
                  {/* Top Bar: Booking Number, Status Badges, Workshop, Customer */}
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-3">
                      <div className="px-3 py-1.5 rounded-xl bg-purple-50 text-purple-800 font-mono font-black text-xs border border-purple-200 flex items-center gap-1.5">
                        <Wrench className="w-3.5 h-3.5 text-purple-600" />
                        <span>{b.booking_reference || b.booking_number}</span>
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <Building2 className="w-3.5 h-3.5 text-purple-600" />
                          <span className="font-black text-sm text-slate-950">{b.workshop_name}</span>
                          {b.workshop_city && (
                            <span className="text-xs text-slate-400 font-medium">({b.workshop_city})</span>
                          )}
                        </div>
                        <span className="text-xs text-slate-500 block mt-0.5">
                          Customer: <strong className="text-slate-800">{b.customer_name || b.buyer_name}</strong> &lt;{b.buyer_email}&gt;
                        </span>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[11px] text-slate-400 font-medium mr-1">
                        Booked: {new Date(b.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                      </span>
                      <span className={`px-2.5 py-1 rounded-full text-xs font-black border ${getStatusBadge(b.status)}`}>
                        Booking: {b.status}
                      </span>
                    </div>
                  </div>

                  {/* 4-Column Operational Information Grid */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs bg-slate-50 p-4 rounded-xl border border-slate-100">
                    {/* Col 1: Vehicle & Services */}
                    <div className="space-y-1">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                        Vehicle & Services
                      </span>
                      <span className="font-black text-slate-900 block">
                        {b.vehicle_year} {b.vehicle_make} {b.vehicle_model}
                      </span>
                      <span className="inline-block px-1.5 py-0.5 rounded bg-amber-100 text-amber-900 font-mono text-[10px] font-bold">
                        {b.vehicle_registration || b.vehicle_registration_plate || "N/A"}
                      </span>
                      <span className="text-slate-600 block text-[11px] mt-1 truncate">
                        {b.service_items && b.service_items.length > 0
                          ? b.service_items.map((s) => s.service_name).join(", ")
                          : "Class 4 MOT / Inspection"}
                      </span>
                    </div>

                    {/* Col 2: Appointment & Bay Schedule */}
                    <div className="space-y-1">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                        Appointment Slot
                      </span>
                      {b.scheduled_appointment_start ? (
                        <div className="text-emerald-800 font-bold space-y-0.5">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3.5 h-3.5 text-emerald-600" />
                            {new Date(b.scheduled_appointment_start).toLocaleDateString("en-GB", {
                              weekday: "short",
                              day: "numeric",
                              month: "short",
                            })}
                          </span>
                          <span className="block text-[11px] text-slate-600 font-normal">
                            {new Date(b.scheduled_appointment_start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} &ndash;{" "}
                            {new Date(b.scheduled_appointment_end || "").toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                          </span>
                        </div>
                      ) : (
                        <div className="text-slate-600">
                          <span>Preferred: {b.preferred_date}</span>
                          <span className="block text-[10px] text-amber-700 font-medium">Awaiting bay schedule</span>
                        </div>
                      )}
                    </div>

                    {/* Col 3: Quotation Details */}
                    <div className="space-y-1">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                        Quotation Record
                      </span>
                      {activeQuote ? (
                        <div>
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="font-mono font-bold text-slate-800">
                              #{activeQuote.quotation_number} (v{activeQuote.version})
                            </span>
                            <span className={`px-2 py-0.5 rounded text-[10px] font-black border ${getQuotationStatusBadge(activeQuote.status)}`}>
                              {activeQuote.status}
                            </span>
                          </div>
                          <span className="text-purple-950 font-black text-sm block mt-0.5">
                            £{parseFloat(String(activeQuote.total_amount || 0)).toFixed(2)}
                            <span className="text-[10px] text-slate-500 font-normal ml-1">
                              (Tax: {activeQuote.tax_rate_percent}% £{activeQuote.tax_amount})
                            </span>
                          </span>
                          {activeQuote.accepted_at && (
                            <span className="text-[10px] text-emerald-700 font-medium block">
                              Accepted: {new Date(activeQuote.accepted_at).toLocaleDateString("en-GB")}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-slate-400 italic block">No quotation issued yet</span>
                      )}
                    </div>

                    {/* Col 4: Work Order Details */}
                    <div className="space-y-1">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                        Work Order Execution
                      </span>
                      {hasWorkOrder ? (
                        <div>
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="font-mono font-bold text-slate-800">
                              #{b.work_order_number}
                            </span>
                            <span className={`px-2 py-0.5 rounded text-[10px] font-black border ${getWorkOrderStatusBadge(b.work_order_status || "ASSIGNED")}`}>
                              {b.work_order_status}
                            </span>
                          </div>
                          <span className="text-slate-600 block text-[11px] mt-0.5">
                            Tech: <strong className="text-slate-800">{b.work_order_technician || "Unassigned"}</strong>
                          </span>
                          <span className="text-[10px] text-slate-500 block">
                            Tasks: {b.work_order_tasks_count || (b.work_order?.tasks?.length ?? 1)} allocated
                          </span>
                        </div>
                      ) : (
                        <span className="text-slate-400 italic block">Pending quote acceptance</span>
                      )}
                    </div>
                  </div>

                  {/* Card Footer: Action & Summary */}
                  <div className="flex items-center justify-between pt-1">
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      {activeQuote?.status === "ACCEPTED" && hasWorkOrder && (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-800 font-bold text-[11px] border border-emerald-200">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                          Authorized Repair in Progress
                        </span>
                      )}
                      {activeQuote?.status === "ISSUED" && (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-800 font-bold text-[11px] border border-amber-200">
                          <Clock className="w-3.5 h-3.5 text-amber-600" />
                          Quotation Awaiting Customer Review
                        </span>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedBooking(b);
                      }}
                      className="px-3.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs rounded-xl transition flex items-center gap-1 shadow-xs"
                    >
                      <span>Audit & Inspect</span>
                      <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* BOOKING DETAILS INSPECTION MODAL (READ-ONLY OPERATIONAL OVERSIGHT) */}
      {/* ========================================================================= */}
      {selectedBooking && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white rounded-3xl max-w-4xl w-full shadow-2xl border border-slate-200 overflow-hidden my-8 max-h-[90vh] flex flex-col">
            {/* Modal Header */}
            <div className="p-6 bg-slate-950 text-white flex items-center justify-between border-b border-slate-800 shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-purple-500/20 text-purple-400 flex items-center justify-center font-bold">
                  <Wrench className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-bold text-slate-400">
                      {selectedBooking.booking_reference || selectedBooking.booking_number}
                    </span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-black border ${getStatusBadge(selectedBooking.status)}`}>
                      {selectedBooking.status}
                    </span>
                  </div>
                  <h3 className="text-lg font-black text-white mt-0.5">
                    {selectedBooking.workshop_name} &bull; Operational Audit Detail
                  </h3>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setSelectedBooking(null)}
                className="w-9 h-9 rounded-xl bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Scrollable Content */}
            <div className="p-6 space-y-6 overflow-y-auto flex-1 text-xs">
              {/* Grid 1: Customer, Vehicle, and Schedule Overview */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Customer Details */}
                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                    Customer & Account
                  </span>
                  <div className="font-black text-sm text-slate-900">
                    {selectedBooking.customer_name || selectedBooking.buyer_name}
                  </div>
                  <div className="text-slate-600 space-y-1">
                    <span className="flex items-center gap-1.5">
                      <Mail className="w-3.5 h-3.5 text-slate-400" />
                      {selectedBooking.buyer_email}
                    </span>
                    {selectedBooking.workshop_phone && (
                      <span className="flex items-center gap-1.5">
                        <Phone className="w-3.5 h-3.5 text-slate-400" />
                        {selectedBooking.workshop_phone}
                      </span>
                    )}
                  </div>
                </div>

                {/* Vehicle Details */}
                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                    Vehicle Specification
                  </span>
                  <div className="font-black text-sm text-slate-900">
                    {selectedBooking.vehicle_year} {selectedBooking.vehicle_make} {selectedBooking.vehicle_model}
                  </div>
                  <div className="space-y-1 text-slate-600">
                    <span className="inline-block px-1.5 py-0.5 rounded bg-amber-100 text-amber-900 font-mono text-[10px] font-bold">
                      {selectedBooking.vehicle_registration || selectedBooking.vehicle_registration_plate || "N/A"}
                    </span>
                    {selectedBooking.vehicle_vin && (
                      <span className="block font-mono text-[11px] text-slate-500">
                        VIN: {selectedBooking.vehicle_vin}
                      </span>
                    )}
                    {selectedBooking.current_odometer && (
                      <span className="block text-[11px] text-slate-500">
                        Odometer: {selectedBooking.current_odometer} {selectedBooking.odometer_unit || "mi"}
                      </span>
                    )}
                  </div>
                </div>

                {/* Appointment & Bay Slot */}
                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                    Scheduled Bay Slot
                  </span>
                  {selectedBooking.scheduled_appointment_start ? (
                    <div className="space-y-1">
                      <span className="font-bold text-emerald-800 text-sm block">
                        {new Date(selectedBooking.scheduled_appointment_start).toLocaleDateString("en-GB", {
                          weekday: "short",
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                        })}
                      </span>
                      <span className="text-slate-600 block">
                        {new Date(selectedBooking.scheduled_appointment_start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} &ndash;{" "}
                        {new Date(selectedBooking.scheduled_appointment_end || "").toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <span className="text-[11px] text-slate-500 block">
                        Technician: <strong className="text-slate-800">{selectedBooking.assigned_technician_name || "Bay lead"}</strong>
                      </span>
                    </div>
                  ) : (
                    <div className="space-y-1 text-slate-600">
                      <span className="font-bold block">Preferred: {selectedBooking.preferred_date}</span>
                      <span className="text-amber-700 block">Slot awaiting workshop bay allocation</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Requested Services */}
              <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-3">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                  Requested Commercial Services
                </span>
                {selectedBooking.service_items && selectedBooking.service_items.length > 0 ? (
                  <div className="divide-y divide-slate-200">
                    {selectedBooking.service_items.map((svc) => (
                      <div key={svc.id} className="py-2 flex items-center justify-between">
                        <span className="font-bold text-slate-900">{svc.service_name}</span>
                        <span className="font-mono font-bold text-slate-700">
                          {svc.currency} {svc.service_price}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <span className="text-slate-500 italic">Standard comprehensive workshop inspection requested.</span>
                )}
              </div>

              {/* Customer Notes & Fault Reports */}
              {(selectedBooking.customer_notes || selectedBooking.reported_faults) && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {selectedBooking.customer_notes && (
                    <div className="p-4 rounded-2xl bg-amber-50/70 border border-amber-200 text-amber-950 space-y-1">
                      <span className="text-[10px] font-bold text-amber-800 uppercase tracking-wider block">
                        Customer Instructions
                      </span>
                      <p className="mt-0.5">{selectedBooking.customer_notes}</p>
                    </div>
                  )}
                  {selectedBooking.reported_faults && (
                    <div className="p-4 rounded-2xl bg-rose-50/70 border border-rose-200 text-rose-950 space-y-1">
                      <span className="text-[10px] font-bold text-rose-800 uppercase tracking-wider block">
                        Reported Symptoms & Faults
                      </span>
                      <p className="mt-0.5">{selectedBooking.reported_faults}</p>
                    </div>
                  )}
                </div>
              )}

              {/* Quotations Lifecycle Breakdown */}
              <div className="p-5 rounded-2xl bg-slate-900 text-white space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-purple-400" />
                    <span className="font-bold text-sm">Quotation Lifecycle & Commercial Breakdown</span>
                  </div>
                  <span className="text-[11px] text-slate-400">
                    {selectedBooking.quotations?.length || 0} revision(s) recorded
                  </span>
                </div>

                {selectedBooking.quotations && selectedBooking.quotations.length > 0 ? (
                  <div className="space-y-4">
                    {selectedBooking.quotations.map((q) => (
                      <div key={q.id} className="p-4 rounded-xl bg-slate-800/80 border border-slate-700 space-y-3">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-slate-700">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-mono font-bold text-amber-400">
                                #{q.quotation_number} (Rev {q.version})
                              </span>
                              <span className={`px-2 py-0.5 rounded text-[10px] font-black border ${getQuotationStatusBadge(q.status)}`}>
                                {q.status}
                              </span>
                            </div>
                            <span className="text-[11px] text-slate-400 block mt-0.5">
                              Issued: {q.issued_at ? new Date(q.issued_at).toLocaleString("en-GB") : "Draft"}
                              {q.accepted_at && ` | Accepted: ${new Date(q.accepted_at).toLocaleString("en-GB")}`}
                              {q.rejected_at && ` | Declined: ${new Date(q.rejected_at).toLocaleString("en-GB")}`}
                            </span>
                          </div>

                          <div className="text-right">
                            <span className="text-[10px] text-slate-400 block uppercase font-bold">Authorized Total</span>
                            <span className="text-base font-black text-amber-400">
                              £{parseFloat(String(q.total_amount || 0)).toFixed(2)} {q.currency}
                            </span>
                          </div>
                        </div>

                        {/* Line items summary */}
                        {q.line_items && q.line_items.length > 0 && (
                          <div className="overflow-x-auto">
                            <table className="w-full text-left text-slate-300">
                              <thead>
                                <tr className="text-[10px] text-slate-500 uppercase border-b border-slate-700">
                                  <th className="pb-1">Item</th>
                                  <th className="pb-1">Description</th>
                                  <th className="pb-1 text-center">Qty</th>
                                  <th className="pb-1 text-right">Unit</th>
                                  <th className="pb-1 text-right">Total</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-slate-700/50">
                                {q.line_items.map((it) => (
                                  <tr key={it.id}>
                                    <td className="py-1 text-slate-400 font-mono text-[10px]">{it.item_type}</td>
                                    <td className="py-1">{it.description}</td>
                                    <td className="py-1 text-center">{it.quantity}</td>
                                    <td className="py-1 text-right font-mono">£{it.unit_price}</td>
                                    <td className="py-1 text-right font-mono font-bold text-white">£{it.line_total}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}

                        {/* Financial Subtotals */}
                        <div className="flex flex-wrap items-center justify-end gap-4 text-[11px] pt-2 border-t border-slate-700 text-slate-400">
                          <span>Labour: <strong className="text-slate-200">£{q.subtotal_labour}</strong></span>
                          <span>Parts: <strong className="text-slate-200">£{q.subtotal_parts}</strong></span>
                          <span>Tax ({q.tax_rate_percent}%): <strong className="text-slate-200">£{q.tax_amount}</strong></span>
                          <span>Total: <strong className="text-amber-400 font-bold">£{q.total_amount}</strong></span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <span className="text-slate-400 italic block py-2">
                    No quotation revisions issued for this booking request yet.
                  </span>
                )}
              </div>

              {/* Linked Work Order Execution & Tasks */}
              <div className="p-5 rounded-2xl bg-white border border-slate-200 space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <ClipboardList className="w-4 h-4 text-purple-600" />
                    <span className="font-bold text-sm text-slate-900">
                      Authorized Work Order Execution & Task Progress
                    </span>
                  </div>
                  {selectedBooking.work_order_number ? (
                    <span className={`px-2.5 py-1 rounded text-xs font-black border ${getWorkOrderStatusBadge(selectedBooking.work_order_status || "ASSIGNED")}`}>
                      {selectedBooking.work_order_status}
                    </span>
                  ) : (
                    <span className="text-xs text-slate-400 italic">No work order generated yet</span>
                  )}
                </div>

                {selectedBooking.work_order ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3 bg-slate-50 rounded-xl">
                      <div>
                        <span className="text-[10px] text-slate-400 block uppercase font-bold">Work Order Reference</span>
                        <span className="font-mono font-black text-slate-900">{selectedBooking.work_order.work_order_number}</span>
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-400 block uppercase font-bold">Lead Technician</span>
                        <span className="font-bold text-slate-900">{selectedBooking.work_order.lead_technician_name || "Unassigned"}</span>
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-400 block uppercase font-bold">Authorized Cap</span>
                        <span className="font-bold text-purple-900">£{parseFloat(String(selectedBooking.work_order.authorized_total_amount || 0)).toFixed(2)}</span>
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-400 block uppercase font-bold">Generated At</span>
                        <span className="text-slate-700">{new Date(selectedBooking.work_order.created_at).toLocaleDateString("en-GB")}</span>
                      </div>
                    </div>

                    {/* Task Progress */}
                    {selectedBooking.work_order.tasks && selectedBooking.work_order.tasks.length > 0 && (
                      <div className="space-y-2">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                          Execution Tasks ({selectedBooking.work_order.tasks.length})
                        </span>
                        <div className="divide-y divide-slate-100 border border-slate-200 rounded-xl overflow-hidden">
                          {selectedBooking.work_order.tasks.map((tsk) => (
                            <div key={tsk.id} className="p-3 flex items-center justify-between bg-white text-xs">
                              <div>
                                <span className="font-bold text-slate-900 block">{tsk.description}</span>
                                <span className="text-[11px] text-slate-400">
                                  Est: {tsk.estimated_labour_minutes} mins | Actual: {tsk.actual_labour_minutes} mins
                                </span>
                              </div>
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                tsk.status === "COMPLETED"
                                  ? "bg-emerald-100 text-emerald-800"
                                  : tsk.status === "IN_PROGRESS"
                                  ? "bg-purple-100 text-purple-800"
                                  : "bg-slate-100 text-slate-700"
                              }`}>
                                {tsk.status}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-slate-500 italic py-2">
                    Work orders are automatically spawned upon customer acceptance of an official workshop quotation.
                  </p>
                )}
              </div>

              {/* Operational Audit Stream */}
              <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200 space-y-3">
                <div className="flex items-center gap-2 pb-2 border-b border-slate-200">
                  <History className="w-4 h-4 text-purple-600" />
                  <span className="font-bold text-sm text-slate-900">Immutable Platform Audit History</span>
                </div>

                {selectedBooking.audit_logs && selectedBooking.audit_logs.length > 0 ? (
                  <div className="space-y-2">
                    {selectedBooking.audit_logs.map((log) => (
                      <div key={log.id} className="p-3 bg-white rounded-xl border border-slate-200 text-xs flex items-center justify-between">
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-bold text-purple-800">{log.event_type}</span>
                            <span className="px-1.5 py-0.2 rounded bg-slate-100 text-[10px] text-slate-600 font-mono">
                              {log.action}
                            </span>
                          </div>
                          <span className="text-[11px] text-slate-500 block">
                            {log.created_at ? new Date(log.created_at).toLocaleString("en-GB") : "Recorded"}
                          </span>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${log.status === "ALLOWED" ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"}`}>
                          {log.status}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <span className="text-slate-400 italic block">No audit log records attached yet.</span>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 bg-slate-50 border-t border-slate-200 flex items-center justify-end shrink-0">
              <button
                type="button"
                onClick={() => setSelectedBooking(null)}
                className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs rounded-xl transition"
              >
                Close Audit Inspection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
