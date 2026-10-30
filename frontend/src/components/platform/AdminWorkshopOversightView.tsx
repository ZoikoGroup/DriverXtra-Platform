"use client";

import React, { useState, useEffect } from "react";
import { api, WorkshopBooking } from "@/lib/api/client";
import {
  Calendar,
  Clock,
  Filter,
  Search,
  RefreshCw,
  Car,
  FileText,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  Building2,
} from "lucide-react";

export default function AdminWorkshopOversightView() {
  const [bookings, setBookings] = useState<WorkshopBooking[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  const loadOversightBookings = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const res = await api.workshops.adminBookings.list(
        statusFilter !== "ALL" ? { status: statusFilter } : undefined
      );
      setBookings(res.results || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load platform workshop bookings.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadOversightBookings();
  }, [statusFilter]);

  const filteredBookings = bookings.filter((b) => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return true;
    const ref = (b.booking_reference || b.booking_number || "").toLowerCase();
    const ws = (b.workshop_name || "").toLowerCase();
    const buyer = (b.customer_name || b.buyer_name || "").toLowerCase();
    const plate = (b.vehicle_registration || b.vehicle_registration_plate || "").toLowerCase();
    return ref.includes(q) || ws.includes(q) || buyer.includes(q) || plate.includes(q);
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

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Banner */}
      <div className="bg-slate-950 text-white rounded-3xl p-6 shadow-sm border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-purple-500/10 text-purple-400 text-xs font-bold border border-purple-500/20">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Platform Governance & Audit</span>
          </div>
          <h1 className="text-2xl font-black tracking-tight text-white">
            Workshop Operations Oversight
          </h1>
          <p className="text-xs text-slate-400 max-w-2xl">
            Live platform audit stream of all commercial workshop service requests, appointments, bay schedules, and customer quotation lifecycle records across all registered workshop tenants.
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
            { label: "All", value: "ALL" },
            { label: "Requested", value: "REQUESTED" },
            { label: "Accepted", value: "ACCEPTED" },
            { label: "Confirmed", value: "CONFIRMED" },
            { label: "Quoted", value: "QUOTED" },
            { label: "Rejected", value: "REJECTED" },
            { label: "Cancelled", value: "CANCELLED" },
          ].map((f) => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                statusFilter === f.value
                  ? "bg-purple-100 text-purple-900 font-extrabold border border-purple-300"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="relative w-full md:w-72">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search ref, workshop, buyer, reg..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-xs bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>
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
            {statusFilter !== "ALL"
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
              const latestQuote = b.quotations && b.quotations.length > 0 ? b.quotations[0] : null;
              return (
                <div key={b.id} className="p-5 hover:bg-slate-50/70 transition space-y-3">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="px-3 py-1.5 rounded-xl bg-purple-50 text-purple-800 font-mono font-bold text-xs">
                        {b.booking_reference || b.booking_number}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <Building2 className="w-3.5 h-3.5 text-purple-600" />
                          <span className="font-bold text-sm text-slate-950">{b.workshop_name}</span>
                        </div>
                        <span className="text-xs text-slate-500">
                          Customer: <strong className="text-slate-800">{b.customer_name || b.buyer_name}</strong> ({b.buyer_email})
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className={`px-2.5 py-1 rounded-full text-xs font-bold border ${getStatusBadge(b.status)}`}>
                        {b.status}
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs bg-slate-50 p-3.5 rounded-xl border border-slate-100">
                    <div>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Vehicle</span>
                      <span className="font-bold text-slate-900 block">
                        {b.vehicle_year} {b.vehicle_make} {b.vehicle_model}
                      </span>
                      <span className="inline-block px-1.5 py-0.5 rounded bg-amber-100 text-amber-900 font-mono text-[10px] font-bold mt-0.5">
                        {b.vehicle_registration || b.vehicle_registration_plate || "N/A"}
                      </span>
                    </div>

                    <div>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Appointment Slot</span>
                      {b.scheduled_appointment_start ? (
                        <div className="text-emerald-700 font-bold space-y-0.5">
                          <span>{new Date(b.scheduled_appointment_start).toLocaleDateString()}</span>
                          <span className="block text-[11px] text-slate-600 font-normal">
                            {new Date(b.scheduled_appointment_start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} &ndash; {new Date(b.scheduled_appointment_end || "").toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                          </span>
                        </div>
                      ) : (
                        <div className="text-slate-600">
                          <span>Preferred: {b.preferred_date}</span>
                          <span className="block text-[10px] text-amber-700 font-medium">Awaiting bay schedule</span>
                        </div>
                      )}
                    </div>

                    <div>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Services & Quotations</span>
                      <span className="text-slate-700 block">
                        {b.service_items && b.service_items.length > 0
                          ? b.service_items.map((s) => s.service_name).join(", ")
                          : "Inspection / Diagnostics"}
                      </span>
                      {latestQuote && (
                        <span className="text-[11px] font-bold text-purple-700 block mt-0.5">
                          Quote Rev #{latestQuote.revision_number || latestQuote.version} ({latestQuote.status}) &ndash; £{parseFloat(String(latestQuote.grand_total || latestQuote.total_amount || 0)).toFixed(2)}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

