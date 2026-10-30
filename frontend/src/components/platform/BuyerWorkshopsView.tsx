"use client";

import React, { useState, useEffect } from "react";
import {
  api,
  WorkshopProfilePublic,
  WorkshopBooking,
  WorkshopQuotation,
  GarageVehicle,
  WorkshopServiceCategory,
} from "@/lib/api/client";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  Wrench,
  Search,
  MapPin,
  Calendar,
  Clock,
  Car,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ChevronRight,
  FileText,
  DollarSign,
  Filter,
  Plus,
  RefreshCw,
  Shield,
  Layers,
  Sparkles,
} from "lucide-react";

export default function BuyerWorkshopsView({ onNavigateToGarage }: { onNavigateToGarage?: () => void }) {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<"browse" | "my_bookings">("browse");

  // Workshop Browsing State
  const [workshops, setWorkshops] = useState<WorkshopProfilePublic[]>([]);
  const [categories, setCategories] = useState<WorkshopServiceCategory[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [cityFilter, setCityFilter] = useState("");
  const [loadingWorkshops, setLoadingWorkshops] = useState(true);
  const [selectedWorkshop, setSelectedWorkshop] = useState<WorkshopProfilePublic | null>(null);

  // Garage Vehicles
  const [vehicles, setVehicles] = useState<GarageVehicle[]>([]);
  const [loadingVehicles, setLoadingVehicles] = useState(false);

  // Booking Modal State
  const [bookingModalOpen, setBookingModalOpen] = useState(false);
  const [targetWorkshop, setTargetWorkshop] = useState<WorkshopProfilePublic | null>(null);
  const [selectedVehicleId, setSelectedVehicleId] = useState<string>("");
  const [selectedServiceIds, setSelectedServiceIds] = useState<string[]>([]);
  const [preferredDate, setPreferredDate] = useState<string>("");
  const [preferredTimeSlot, setPreferredTimeSlot] = useState<string>("09:00 - 11:00");
  const [customerNotes, setCustomerNotes] = useState("");
  const [reportedFaults, setReportedFaults] = useState("");
  const [submittingBooking, setSubmittingBooking] = useState(false);
  const [bookingError, setBookingError] = useState<string | null>(null);
  const [bookingSuccessNumber, setBookingSuccessNumber] = useState<string | null>(null);

  // My Bookings State
  const [myBookings, setMyBookings] = useState<WorkshopBooking[]>([]);
  const [loadingBookings, setLoadingBookings] = useState(false);
  const [selectedBooking, setSelectedBooking] = useState<WorkshopBooking | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");

  // Quotation Response State
  const [respondingQuoteId, setRespondingQuoteId] = useState<string | null>(null);
  const [rejectReasonModal, setRejectReasonModal] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [actionSuccessMessage, setActionSuccessMessage] = useState<string | null>(null);

  // Load workshops & categories
  useEffect(() => {
    fetchWorkshops();
    api.workshops.getCategories().then(setCategories).catch(() => {});
  }, [searchQuery, cityFilter]);

  // Load vehicles and my bookings when tab changes
  useEffect(() => {
    if (activeTab === "my_bookings") {
      fetchMyBookings();
    }
  }, [activeTab, statusFilter]);

  useEffect(() => {
    fetchGarageVehicles();
  }, []);

  const fetchWorkshops = async () => {
    setLoadingWorkshops(true);
    try {
      const res = await api.workshops.list({
        q: searchQuery || undefined,
        city: cityFilter || undefined,
        accepting_only: true,
      });
      setWorkshops(res.results || []);
    } catch (err) {
      console.error("Failed to load workshops:", err);
    } finally {
      setLoadingWorkshops(false);
    }
  };

  const fetchGarageVehicles = async () => {
    setLoadingVehicles(true);
    try {
      const res = await api.garage.listVehicles();
      const active = (res || []).filter((v: GarageVehicle) => !v.is_archived);
      setVehicles(active);
      if (active.length > 0 && !selectedVehicleId) {
        setSelectedVehicleId(active[0].id);
      }
    } catch (err) {
      console.error("Failed to load garage vehicles:", err);
    } finally {
      setLoadingVehicles(false);
    }
  };

  const fetchMyBookings = async () => {
    setLoadingBookings(true);
    try {
      const res = await api.workshops.listMyBookings({ status: statusFilter || undefined });
      setMyBookings(res.results || []);
    } catch (err) {
      console.error("Failed to load my bookings:", err);
    } finally {
      setLoadingBookings(false);
    }
  };

  const openBookingModal = (ws: WorkshopProfilePublic) => {
    setTargetWorkshop(ws);
    setSelectedServiceIds([]);
    setPreferredDate(new Date(Date.now() + 86400000 * 2).toISOString().split("T")[0]);
    setPreferredTimeSlot("09:00 - 11:00");
    setCustomerNotes("");
    setReportedFaults("");
    setBookingError(null);
    setBookingSuccessNumber(null);
    setBookingModalOpen(true);
  };

  const handleToggleService = (serviceId: string) => {
    setSelectedServiceIds((prev) =>
      prev.includes(serviceId) ? prev.filter((id) => id !== serviceId) : [...prev, serviceId]
    );
  };

  const handleCreateBooking = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetWorkshop) return;
    if (!selectedVehicleId) {
      setBookingError("Please select a registered garage vehicle.");
      return;
    }
    if (!preferredDate) {
      setBookingError("Please select a preferred appointment date.");
      return;
    }

    setSubmittingBooking(true);
    setBookingError(null);

    try {
      const booking = await api.workshops.createBooking({
        workshop_id: targetWorkshop.id,
        vehicle_id: selectedVehicleId,
        service_ids: selectedServiceIds,
        preferred_date: preferredDate,
        preferred_time_slot: preferredTimeSlot,
        customer_notes: customerNotes,
        reported_faults: reportedFaults,
      });

      setBookingSuccessNumber(booking.booking_number);
      fetchMyBookings();
    } catch (err: any) {
      setBookingError(err.message || "Failed to submit booking request.");
    } finally {
      setSubmittingBooking(false);
    }
  };

  const handleAcceptQuotation = async (quoteId: string) => {
    setRespondingQuoteId(quoteId);
    try {
      await api.workshops.acceptQuotation(quoteId);
      setActionSuccessMessage("Quotation accepted successfully! Your appointment is confirmed.");
      fetchMyBookings();
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err: any) {
      alert(err.message || "Failed to accept quotation.");
    } finally {
      setRespondingQuoteId(null);
    }
  };

  const handleRejectQuotation = async () => {
    if (!rejectReasonModal) return;
    setRespondingQuoteId(rejectReasonModal);
    try {
      await api.workshops.rejectQuotation(rejectReasonModal, rejectReason);
      setActionSuccessMessage("Quotation rejected. The workshop has been notified.");
      setRejectReasonModal(null);
      setRejectReason("");
      fetchMyBookings();
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err: any) {
      alert(err.message || "Failed to reject quotation.");
    } finally {
      setRespondingQuoteId(null);
    }
  };

  const handleCancelBooking = async (bookingId: string) => {
    const reason = prompt("Please provide a reason for cancelling this booking:");
    if (!reason || !reason.trim()) return;

    try {
      await api.workshops.cancelMyBooking(bookingId, reason);
      setActionSuccessMessage("Booking cancelled successfully.");
      fetchMyBookings();
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err: any) {
      alert(err.message || "Failed to cancel booking.");
    }
  };

  // Status helper colors
  const getStatusBadge = (status: string) => {
    switch (status) {
      case "CONFIRMED":
        return "bg-emerald-50 text-emerald-700 border-emerald-200";
      case "ACCEPTED":
        return "bg-blue-50 text-blue-700 border-blue-200";
      case "QUOTED":
        return "bg-purple-50 text-purple-700 border-purple-200";
      case "REQUESTED":
      case "UNDER_REVIEW":
        return "bg-amber-50 text-amber-700 border-amber-200";
      case "CANCELLED":
      case "REJECTED":
        return "bg-rose-50 text-rose-700 border-rose-200";
      default:
        return "bg-slate-50 text-slate-700 border-slate-200";
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Top Banner */}
      <div className="bg-slate-950 text-white rounded-3xl p-6 shadow-sm border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-amber-400/10 text-amber-400 text-xs font-bold border border-amber-400/20 mb-2">
            <Wrench className="w-3.5 h-3.5" />
            <span>DriverXtra Verified Service Network</span>
          </div>
          <h1 className="text-2xl font-black tracking-tight text-white">Workshop Services & Bookings</h1>
          <p className="text-xs text-slate-400 max-w-xl mt-1">
            Browse verified automotive service centres, request bookings with your garage vehicle, and review certified quotations with transparent pricing.
          </p>
        </div>

        {/* Tab Controls */}
        <div className="flex items-center gap-2 bg-slate-900 p-1.5 rounded-2xl border border-slate-800 self-start md:self-auto">
          <button
            onClick={() => setActiveTab("browse")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              activeTab === "browse"
                ? "bg-amber-400 text-slate-950 shadow-sm"
                : "text-slate-400 hover:text-white"
            }`}
          >
            Find Workshops
          </button>
          <button
            onClick={() => setActiveTab("my_bookings")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 ${
              activeTab === "my_bookings"
                ? "bg-amber-400 text-slate-950 shadow-sm"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <span>My Bookings</span>
            {myBookings.length > 0 && (
              <span className="w-5 h-5 rounded-full bg-slate-950 text-amber-400 text-[10px] font-black flex items-center justify-center">
                {myBookings.length}
              </span>
            )}
          </button>
        </div>
      </div>

      {actionSuccessMessage && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-2xl text-xs font-bold flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{actionSuccessMessage}</span>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 1: BROWSE WORKSHOPS */}
      {/* ========================================================================= */}
      {activeTab === "browse" && (
        <div className="space-y-6">
          {/* Search & Filter Bar */}
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-3 items-center">
            <div className="relative flex-1 w-full">
              <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search by workshop name, service, or keyword..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
              />
            </div>
            <div className="relative w-full md:w-56">
              <MapPin className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Filter by city (e.g. London)"
                value={cityFilter}
                onChange={(e) => setCityFilter(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
              />
            </div>
          </div>

          {/* Workshop Cards Grid */}
          {loadingWorkshops ? (
            <div className="p-12 text-center text-xs text-slate-500 bg-white rounded-2xl border border-slate-200">
              <RefreshCw className="w-6 h-6 animate-spin mx-auto text-amber-500 mb-2" />
              <span>Locating verified service centres...</span>
            </div>
          ) : workshops.length === 0 ? (
            <div className="p-12 text-center bg-white rounded-2xl border border-slate-200 space-y-2">
              <Wrench className="w-8 h-8 text-slate-400 mx-auto" />
              <h3 className="text-sm font-black text-slate-900">No workshops match your criteria</h3>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                Try removing city filters or search terms. Only verified workshops currently accepting bookings are displayed.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {workshops.map((ws) => (
                <div
                  key={ws.id}
                  className="bg-white rounded-2xl border border-slate-200 shadow-sm hover:shadow-md transition-all p-5 flex flex-col justify-between"
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-1.5">
                          <h3 className="text-sm font-black text-slate-950">{ws.display_name}</h3>
                          {ws.is_verified && (
                            <span title="Verified Workshop"><Shield className="w-3.5 h-3.5 text-emerald-600 shrink-0" /></span>
                          )}
                        </div>
                        <div className="flex items-center gap-1 text-[11px] text-slate-500 mt-0.5">
                          <MapPin className="w-3 h-3 text-slate-400" />
                          <span>{ws.city || "UK"}, {ws.country}</span>
                        </div>
                      </div>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200">
                        {ws.bay_capacity} Bays
                      </span>
                    </div>

                    {ws.description && (
                      <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                        {ws.description}
                      </p>
                    )}

                    {/* Services Preview */}
                    <div className="space-y-1.5 pt-2 border-t border-slate-100">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                        Popular Services ({ws.services?.length || 0})
                      </span>
                      {ws.services && ws.services.length > 0 ? (
                        <div className="space-y-1">
                          {ws.services.slice(0, 3).map((srv) => (
                            <div key={srv.id} className="flex items-center justify-between text-xs">
                              <span className="text-slate-700 font-medium truncate max-w-[180px]">{srv.name}</span>
                              <span className="text-slate-900 font-bold">{srv.currency} {srv.base_price}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400 italic">Price upon inspection / quotation</span>
                      )}
                    </div>
                  </div>

                  <div className="pt-4 mt-4 border-t border-slate-100 flex items-center gap-2">
                    <button
                      onClick={() => openBookingModal(ws)}
                      className="flex-1 py-2.5 px-3 bg-slate-950 hover:bg-slate-900 text-white font-bold text-xs rounded-xl transition-all flex items-center justify-center gap-1.5 shadow-sm"
                    >
                      <span>Book Service</span>
                      <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: MY BOOKINGS & QUOTATIONS */}
      {/* ========================================================================= */}
      {activeTab === "my_bookings" && (
        <div className="space-y-6">
          {/* Status Filter Tabs */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            {["", "REQUESTED", "ACCEPTED", "CONFIRMED", "QUOTED", "CANCELLED"].map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold whitespace-nowrap transition-all border ${
                  statusFilter === st
                    ? "bg-slate-950 text-white border-slate-950"
                    : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
                }`}
              >
                {st === "" ? "All Bookings" : st.replace("_", " ")}
              </button>
            ))}
          </div>

          {loadingBookings ? (
            <div className="p-12 text-center text-xs text-slate-500 bg-white rounded-2xl border border-slate-200">
              <RefreshCw className="w-6 h-6 animate-spin mx-auto text-amber-500 mb-2" />
              <span>Loading your booking history...</span>
            </div>
          ) : myBookings.length === 0 ? (
            <div className="p-12 text-center bg-white rounded-2xl border border-slate-200 space-y-3">
              <Calendar className="w-8 h-8 text-slate-400 mx-auto" />
              <h3 className="text-sm font-black text-slate-900">No bookings found</h3>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                You haven&apos;t booked any workshop appointments yet. Browse verified centres to schedule your service.
              </p>
              <button
                onClick={() => setActiveTab("browse")}
                className="mt-2 px-4 py-2 bg-amber-400 text-slate-950 font-bold text-xs rounded-xl hover:bg-amber-500 transition-all"
              >
                Find a Workshop
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {myBookings.map((bk) => (
                <div
                  key={bk.id}
                  className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4"
                >
                  {/* Top Line */}
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-slate-100">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-purple-50 text-purple-700 flex items-center justify-center font-black text-xs shrink-0">
                        <Wrench className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-black text-slate-900">{bk.booking_number}</span>
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${getStatusBadge(
                              bk.status
                            )}`}
                          >
                            {bk.status}
                          </span>
                        </div>
                        <h4 className="text-sm font-black text-slate-950 mt-0.5">{bk.workshop_name}</h4>
                      </div>
                    </div>

                    <div className="text-right text-xs">
                      <span className="text-slate-400 block text-[11px]">Preferred Date</span>
                      <span className="font-bold text-slate-900">
                        {bk.preferred_date} {bk.preferred_time_slot && `(${bk.preferred_time_slot})`}
                      </span>
                    </div>
                  </div>

                  {/* Vehicle & Fault Details */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs bg-slate-50 p-4 rounded-xl">
                    <div>
                      <span className="text-slate-400 text-[11px] font-bold uppercase block">Vehicle</span>
                      <span className="font-bold text-slate-900">
                        {bk.vehicle_make} {bk.vehicle_model} ({bk.vehicle_year || "N/A"})
                      </span>
                      <span className="block text-slate-600 font-mono mt-0.5">{bk.vehicle_registration_plate}</span>
                    </div>

                    <div>
                      <span className="text-slate-400 text-[11px] font-bold uppercase block">Scheduled Appointment</span>
                      {bk.scheduled_appointment_start ? (
                        <div className="text-emerald-700 font-bold flex items-center gap-1.5 mt-0.5">
                          <Clock className="w-3.5 h-3.5" />
                          <span>
                            {new Date(bk.scheduled_appointment_start).toLocaleDateString("en-GB", {
                              weekday: "short",
                              day: "numeric",
                              month: "short",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        </div>
                      ) : (
                        <span className="text-slate-500 italic mt-0.5 block">Awaiting workshop confirmation</span>
                      )}
                    </div>

                    <div>
                      <span className="text-slate-400 text-[11px] font-bold uppercase block">Contact Workshop</span>
                      <span className="text-slate-700 block font-medium">{bk.workshop_phone || bk.workshop_email || "N/A"}</span>
                      <span className="text-slate-500 text-[11px]">{bk.workshop_city}</span>
                    </div>
                  </div>

                  {bk.reported_faults && (
                    <div className="text-xs text-slate-700 bg-amber-50/60 border border-amber-200/60 p-3 rounded-xl">
                      <span className="font-bold text-amber-900 block">Reported Faults & Symptoms:</span>
                      <p className="mt-0.5">{bk.reported_faults}</p>
                    </div>
                  )}

                  {/* Quotation Review Card (If Quotation Available) */}
                  {bk.active_quotation && (
                    <div className="p-5 rounded-2xl bg-gradient-to-br from-slate-900 to-purple-950 text-white space-y-4 shadow-sm border border-slate-800">
                      <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 pb-3 border-b border-white/10">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-black uppercase tracking-wider text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded border border-amber-400/20">
                              Official Workshop Quotation
                            </span>
                            <span className="text-xs text-slate-300">
                              #{bk.active_quotation.quotation_number} (v{bk.active_quotation.version})
                            </span>
                          </div>
                          <h4 className="text-base font-black mt-1">Estimate Breakdown & Scope of Work</h4>
                        </div>
                        <div className="text-right">
                          <span className="text-xs text-slate-400 block">Final Quoted Total</span>
                          <span className="text-xl font-black text-amber-400">
                            {bk.active_quotation.currency} {bk.active_quotation.total_amount}
                          </span>
                        </div>
                      </div>

                      {/* Quotation Line Items Table */}
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead>
                            <tr className="text-slate-400 border-b border-white/10 text-[11px] uppercase tracking-wider">
                              <th className="pb-2">Type</th>
                              <th className="pb-2">Description / Part</th>
                              <th className="pb-2 text-center">Qty</th>
                              <th className="pb-2 text-right">Unit Price</th>
                              <th className="pb-2 text-right">Line Total</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-white/5">
                            {bk.active_quotation.line_items.map((item) => (
                              <tr key={item.id} className="text-slate-200">
                                <td className="py-2">
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-white/10 text-slate-300">
                                    {item.item_type_display}
                                  </span>
                                </td>
                                <td className="py-2">
                                  <span className="font-bold">{item.description}</span>
                                  {item.part_number && (
                                    <span className="block text-[10px] text-slate-400 font-mono">
                                      PN: {item.part_number}
                                    </span>
                                  )}
                                </td>
                                <td className="py-2 text-center">{item.quantity}</td>
                                <td className="py-2 text-right">
                                  {bk.active_quotation?.currency} {item.unit_price}
                                </td>
                                <td className="py-2 text-right font-bold text-white">
                                  {bk.active_quotation?.currency} {item.line_total}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      {/* Financial Totals Summary */}
                      <div className="pt-3 border-t border-white/10 flex flex-col md:flex-row justify-between text-xs gap-3">
                        <div className="text-slate-400 text-[11px] space-y-1">
                          {bk.active_quotation?.workshop_notes && (
                            <p>
                              <span className="text-slate-300 font-bold">Notes: </span>
                              {bk.active_quotation?.workshop_notes}
                            </p>
                          )}
                          {bk.active_quotation.valid_until && (
                            <p>
                              <span className="text-slate-300 font-bold">Quote Valid Until: </span>
                              {bk.active_quotation.valid_until}
                            </p>
                          )}
                        </div>

                        <div className="w-full md:w-64 space-y-1 text-slate-300">
                          <div className="flex justify-between">
                            <span>Labour Subtotal:</span>
                            <span className="font-medium">
                              {bk.active_quotation.currency} {bk.active_quotation.subtotal_labour}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span>Parts Subtotal:</span>
                            <span className="font-medium">
                              {bk.active_quotation.currency} {bk.active_quotation.subtotal_parts}
                            </span>
                          </div>
                          {parseFloat(bk.active_quotation.subtotal_other) > 0 && (
                            <div className="flex justify-between">
                              <span>Diagnostics / Fees:</span>
                              <span className="font-medium">
                                {bk.active_quotation.currency} {bk.active_quotation.subtotal_other}
                              </span>
                            </div>
                          )}
                          {parseFloat(bk.active_quotation.discount_amount) > 0 && (
                            <div className="flex justify-between text-emerald-400">
                              <span>Discount Applied:</span>
                              <span>
                                -{bk.active_quotation.currency} {bk.active_quotation.discount_amount}
                              </span>
                            </div>
                          )}
                          <div className="flex justify-between">
                            <span>VAT / Tax ({bk.active_quotation.tax_rate_percent}%):</span>
                            <span>
                              {bk.active_quotation.currency} {bk.active_quotation.tax_amount}
                            </span>
                          </div>
                          <div className="flex justify-between text-sm font-black text-amber-400 pt-1 border-t border-white/10">
                            <span>Total Quote:</span>
                            <span>
                              {bk.active_quotation.currency} {bk.active_quotation.total_amount}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Quotation Actions */}
                      {bk.active_quotation.status === "ISSUED" && (
                        <div className="pt-3 border-t border-white/10 flex items-center justify-end gap-3">
                          <button
                            onClick={() => setRejectReasonModal(bk.active_quotation!.id)}
                            disabled={respondingQuoteId === bk.active_quotation.id}
                            className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white font-bold text-xs rounded-xl transition-all"
                          >
                            Decline Quotation
                          </button>
                          <button
                            onClick={() => handleAcceptQuotation(bk.active_quotation!.id)}
                            disabled={respondingQuoteId === bk.active_quotation.id}
                            className="px-5 py-2 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-black text-xs rounded-xl transition-all shadow-sm flex items-center gap-1.5"
                          >
                            <CheckCircle2 className="w-4 h-4" />
                            <span>Accept & Confirm Service</span>
                          </button>
                        </div>
                      )}

                      {bk.active_quotation.status === "ACCEPTED" && (
                        <div className="pt-2 text-xs text-emerald-400 font-bold flex items-center gap-1.5">
                          <CheckCircle2 className="w-4 h-4" />
                          <span>You accepted this quotation on {bk.active_quotation.accepted_at?.split("T")[0]}.</span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Booking Cancel option */}
                  {bk.status !== "CANCELLED" && bk.status !== "REJECTED" && (
                    <div className="flex justify-end pt-2">
                      <button
                        onClick={() => handleCancelBooking(bk.id)}
                        className="text-xs text-rose-600 hover:text-rose-800 font-semibold"
                      >
                        Cancel Booking Request
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: SUBMIT BOOKING REQUEST */}
      {/* ========================================================================= */}
      {bookingModalOpen && targetWorkshop && (
        <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 shadow-2xl space-y-6 my-8 border border-slate-200">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <span className="text-[10px] font-black uppercase tracking-wider text-amber-600 bg-amber-50 px-2 py-0.5 rounded">
                  Service Booking Request
                </span>
                <h3 className="text-lg font-black text-slate-950 mt-1">{targetWorkshop.display_name}</h3>
                <p className="text-xs text-slate-500">{targetWorkshop.city}, {targetWorkshop.country}</p>
              </div>
              <button
                onClick={() => setBookingModalOpen(false)}
                className="w-8 h-8 rounded-full bg-slate-100 text-slate-500 hover:text-slate-900 flex items-center justify-center font-bold"
              >
                ✕
              </button>
            </div>

            {bookingSuccessNumber ? (
              <div className="p-6 text-center space-y-4">
                <div className="w-12 h-12 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mx-auto">
                  <CheckCircle2 className="w-6 h-6" />
                </div>
                <h4 className="text-lg font-black text-slate-950">Booking Request Submitted!</h4>
                <p className="text-xs text-slate-600 max-w-md mx-auto">
                  Your booking reference is <strong className="text-slate-900 font-mono">{bookingSuccessNumber}</strong>. The workshop has been notified and will review your appointment request and prepare a quotation.
                </p>
                <div className="pt-2 flex justify-center gap-3">
                  <button
                    onClick={() => {
                      setBookingModalOpen(false);
                      setActiveTab("my_bookings");
                    }}
                    className="px-5 py-2.5 bg-slate-950 text-white font-bold text-xs rounded-xl"
                  >
                    View My Bookings
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleCreateBooking} className="space-y-4">
                {bookingError && (
                  <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs font-bold flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                    <span>{bookingError}</span>
                  </div>
                )}

                {/* 1. Vehicle Selection */}
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-900 block flex items-center justify-between">
                    <span>Select Vehicle from My Garage</span>
                    {onNavigateToGarage && (
                      <button
                        type="button"
                        onClick={onNavigateToGarage}
                        className="text-[11px] text-amber-600 hover:underline font-bold"
                      >
                        + Add new vehicle in Garage
                      </button>
                    )}
                  </label>
                  {vehicles.length === 0 ? (
                    <div className="p-3 bg-amber-50 border border-amber-200 text-amber-900 rounded-xl text-xs">
                      No vehicles found in your garage. Please register a vehicle in My Garage before booking workshop services.
                    </div>
                  ) : (
                    <select
                      value={selectedVehicleId}
                      onChange={(e) => setSelectedVehicleId(e.target.value)}
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
                    >
                      {vehicles.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.make} {v.model} ({v.year || "N/A"}) — {v.registration_plate || "No Plate"}
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                {/* 2. Select Services */}
                {targetWorkshop.services && targetWorkshop.services.length > 0 && (
                  <div className="space-y-1.5">
                    <label className="text-xs font-bold text-slate-900 block">Select Required Services (Optional)</label>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-40 overflow-y-auto p-1">
                      {targetWorkshop.services.map((srv) => {
                        const checked = selectedServiceIds.includes(srv.id);
                        return (
                          <div
                            key={srv.id}
                            onClick={() => handleToggleService(srv.id)}
                            className={`p-3 rounded-xl border text-xs cursor-pointer transition-all flex items-center justify-between ${
                              checked
                                ? "bg-purple-50 border-purple-400 text-purple-950 font-bold"
                                : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"
                            }`}
                          >
                            <span className="truncate pr-2">{srv.name}</span>
                            <span className="text-slate-900 shrink-0 font-bold">
                              {srv.currency} {srv.base_price}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* 3. Preferred Date & Time */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs font-bold text-slate-900 block">Preferred Date</label>
                    <input
                      type="date"
                      min={new Date().toISOString().split("T")[0]}
                      value={preferredDate}
                      onChange={(e) => setPreferredDate(e.target.value)}
                      required
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-bold text-slate-900 block">Preferred Time Slot</label>
                    <select
                      value={preferredTimeSlot}
                      onChange={(e) => setPreferredTimeSlot(e.target.value)}
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
                    >
                      <option value="08:00 - 10:00">Early Morning (08:00 - 10:00)</option>
                      <option value="10:00 - 12:00">Late Morning (10:00 - 12:00)</option>
                      <option value="12:00 - 14:00">Early Afternoon (12:00 - 14:00)</option>
                      <option value="14:00 - 17:00">Late Afternoon (14:00 - 17:00)</option>
                    </select>
                  </div>
                </div>

                {/* 4. Customer Fault Notes */}
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-900 block">
                    Symptoms or Fault Descriptions (Optional)
                  </label>
                  <textarea
                    rows={2}
                    value={reportedFaults}
                    onChange={(e) => setReportedFaults(e.target.value)}
                    placeholder="Describe any unusual noises, warning lights, vibrations, or leaks..."
                    className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-900 block">Additional Notes / Instructions</label>
                  <textarea
                    rows={2}
                    value={customerNotes}
                    onChange={(e) => setCustomerNotes(e.target.value)}
                    placeholder="E.g., Please check rear tyres while vehicle is on ramp..."
                    className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
                  />
                </div>

                {/* Submit Buttons */}
                <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setBookingModalOpen(false)}
                    className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl transition-all"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submittingBooking || vehicles.length === 0}
                    className="px-6 py-2.5 bg-slate-950 hover:bg-slate-900 disabled:opacity-50 text-white font-black text-xs rounded-xl transition-all shadow-sm flex items-center gap-2"
                  >
                    {submittingBooking && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                    <span>Submit Booking Request</span>
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: DECLINE QUOTATION REASON */}
      {/* ========================================================================= */}
      {rejectReasonModal && (
        <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl space-y-4 border border-slate-200">
            <h3 className="text-base font-black text-slate-950">Decline Quotation</h3>
            <p className="text-xs text-slate-600">
              Please share why this quotation was declined so the workshop can provide an adjusted estimate if desired.
            </p>
            <textarea
              rows={3}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="E.g., Labour cost higher than expected, prefer aftermarket parts instead of OEM..."
              className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
            />
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setRejectReasonModal(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl"
              >
                Go Back
              </button>
              <button
                onClick={handleRejectQuotation}
                disabled={respondingQuoteId !== null}
                className="px-5 py-2 bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs rounded-xl"
              >
                Confirm Decline
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

