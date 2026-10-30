"use client";

import React, { useState, useEffect, useMemo } from "react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  api,
  WorkshopProfilePublic,
  WorkshopServiceCategory,
  WorkshopServiceItem,
  WorkshopOperatingHours,
  WorkshopBooking,
  WorkshopQuotation,
} from "@/lib/api/client";
import {
  Wrench,
  AlertCircle,
  ShieldCheck,
  CheckCircle2,
  Calendar,
  Clock,
  Plus,
  Trash2,
  FileText,
  Send,
  Car,
  Filter,
  Search,
  RefreshCw,
  Check,
  Layers,
  Settings,
  X,
  XCircle,
  CalendarCheck2,
} from "lucide-react";

const DAY_NAMES = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

export default function WorkshopLandingView() {
  const { user } = useAuth();

  // Active sub-tab in console
  const [activeTab, setActiveTab] = useState<"bookings" | "services" | "hours" | "profile">("bookings");

  // Core Data
  const [profile, setProfile] = useState<WorkshopProfilePublic | null>(null);
  const [operatingHours, setOperatingHours] = useState<WorkshopOperatingHours[]>([]);
  const [services, setServices] = useState<WorkshopServiceItem[]>([]);
  const [categories, setCategories] = useState<WorkshopServiceCategory[]>([]);
  const [bookings, setBookings] = useState<WorkshopBooking[]>([]);

  // State flags
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Booking filtering
  const [bookingFilter, setBookingFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  // Modals
  const [scheduleModalBooking, setScheduleModalBooking] = useState<WorkshopBooking | null>(null);
  const [scheduleDate, setScheduleDate] = useState("");
  const [scheduleStartTime, setScheduleStartTime] = useState("09:00");
  const [scheduleEndTime, setScheduleEndTime] = useState("11:00");
  const [scheduleNotes, setScheduleNotes] = useState("");
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [scheduleError, setScheduleError] = useState<string | null>(null);

  const [rejectModalBooking, setRejectModalBooking] = useState<WorkshopBooking | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectLoading, setRejectLoading] = useState(false);

  // Quotation Builder Modal
  const [quoteBooking, setQuoteBooking] = useState<WorkshopBooking | null>(null);
  const [quoteLineItems, setQuoteLineItems] = useState<Array<{
    id: string;
    item_type: "LABOUR" | "PART" | "DIAGNOSTIC" | "FEE" | "DISCOUNT";
    description: string;
    part_number: string;
    quantity: number;
    unit_price: number;
  }>>([
    { id: "1", item_type: "LABOUR", description: "Diagnostic Inspection & Health Check", part_number: "", quantity: 1, unit_price: 65 }
  ]);
  const [quoteTaxRate, setQuoteTaxRate] = useState<number>(20.0);
  const [quoteDiscount, setQuoteDiscount] = useState<number>(0);
  const [quoteNotes, setQuoteNotes] = useState("");
  const [quoteTerms, setQuoteTerms] = useState("Estimate valid for 30 days. All parts and labour covered by DriverXtra guarantee.");
  const [quoteValidUntil, setQuoteValidUntil] = useState("");
  const [quoteSaving, setQuoteSaving] = useState(false);
  const [quoteError, setQuoteError] = useState<string | null>(null);

  // Service Creation / Edit Modal
  const [serviceModalOpen, setServiceModalOpen] = useState(false);
  const [editingServiceId, setEditingServiceId] = useState<string | null>(null);
  const [serviceFormName, setServiceFormName] = useState("");
  const [serviceFormCategory, setServiceFormCategory] = useState("");
  const [serviceFormDescription, setServiceFormDescription] = useState("");
  const [serviceFormPrice, setServiceFormPrice] = useState("75.00");
  const [serviceFormDuration, setServiceFormDuration] = useState("60");
  const [serviceSaving, setServiceSaving] = useState(false);

  // Profile Form state
  const [profileForm, setProfileForm] = useState({
    business_name: "",
    description: "",
    contact_email: "",
    contact_phone: "",
    address_line1: "",
    address_line2: "",
    city: "",
    state_province: "",
    postal_code: "",
    country: "GB",
    bay_capacity: 2,
    default_tax_rate_percent: 20.0,
    is_accepting_bookings: true,
  });
  const [profileSaving, setProfileSaving] = useState(false);
  const [hoursSaving, setHoursSaving] = useState(false);

  // Role permissions
  const activeRole = user?.activeRole || (user?.rawRoles && user?.rawRoles[0]) || "BUYER";
  const orgs = user?.organisations || [];
  const isPlatformAdmin = activeRole === "ADMIN" || Boolean(user?.is_superuser || user?.rawRoles?.includes("ADMIN"));
  const isPlatformStaff = !isPlatformAdmin && (activeRole === "STAFF" || Boolean(user?.is_staff || user?.rawRoles?.includes("STAFF")));
  const isWorkshopOrgOwnerOrAdmin = orgs.some(
    (o) => o.organisation_type === "WORKSHOP" && (o.role === "OWNER" || o.role === "ADMIN")
  );
  const isTechnicianOrStaffMember = orgs.some(
    (o) => o.organisation_type === "WORKSHOP" && (o.role === "TECHNICIAN" || o.role === "MEMBER" || o.role === "STAFF")
  ) && !isWorkshopOrgOwnerOrAdmin;

  // Settings management (profile, operating hours, catalog services) requires Owner or Admin
  const canManageSettings =
    isPlatformAdmin ||
    isPlatformStaff ||
    isWorkshopOrgOwnerOrAdmin ||
    (!isTechnicianOrStaffMember && (activeRole === "WORKSHOP" || Boolean(user?.rawRoles?.includes("WORKSHOP"))));

  // Show toast notification
  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  // Load All Workshop Data
  const loadData = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);

    try {
      const [profData, catsData, svcsData, bksData] = await Promise.all([
        api.workshops.manageProfile.get().catch(() => null),
        api.workshops.getCategories().catch(() => []),
        api.workshops.manageServices.list().catch(() => []),
        api.workshops.manageBookings.list().catch(() => ({ results: [], count: 0 })),
      ]);

      if (profData) {
        setProfile(profData);
        setProfileForm({
          business_name: profData.business_name || profData.display_name || "",
          description: profData.description || "",
          contact_email: profData.contact_email || user?.email || "",
          contact_phone: profData.contact_phone || "",
          address_line1: profData.address_line1 || "",
          address_line2: profData.address_line2 || "",
          city: profData.city || "",
          state_province: profData.state_province || "",
          postal_code: profData.postal_code || "",
          country: profData.country || "GB",
          bay_capacity: profData.bay_capacity || 2,
          default_tax_rate_percent: profData.default_tax_rate_percent ? parseFloat(profData.default_tax_rate_percent) : 20.0,
          is_accepting_bookings: profData.is_accepting_bookings ?? true,
        });

        if (profData.operating_hours && profData.operating_hours.length > 0) {
          setOperatingHours(profData.operating_hours);
        } else {
          // Initialize standard 7-day default operating hours
          const defaults: WorkshopOperatingHours[] = DAY_NAMES.map((name, idx) => ({
            id: `init-${idx}`,
            day_of_week: idx,
            day_name: name,
            open_time: "08:30:00",
            close_time: "17:30:00",
            is_closed: idx === 6,
          }));
          setOperatingHours(defaults);
        }
      }

      setCategories(catsData || []);
      setServices(svcsData || []);
      setBookings(bksData?.results || []);
    } catch (err: any) {
      console.error("Error loading workshop data:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Filtered Bookings
  const filteredBookings = useMemo(() => {
    return bookings.filter((b) => {
      const matchesFilter =
        bookingFilter === "ALL"
          ? true
          : b.status.toUpperCase() === bookingFilter.toUpperCase();

      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        (b.booking_reference || b.booking_number).toLowerCase().includes(q) ||
        ((b.customer_name || b.buyer_name) && (b.customer_name || b.buyer_name).toLowerCase().includes(q)) ||
        ((b.vehicle_registration || b.vehicle_registration_plate) && (b.vehicle_registration || b.vehicle_registration_plate).toLowerCase().includes(q)) ||
        (b.vehicle_make && b.vehicle_make.toLowerCase().includes(q)) ||
        (b.vehicle_model && b.vehicle_model.toLowerCase().includes(q));

      return matchesFilter && matchesSearch;
    });
  }, [bookings, bookingFilter, searchQuery]);

  // Status Badge Helper
  const getStatusBadge = (status: string) => {
    switch (status) {
      case "CONFIRMED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CalendarCheck2 className="w-3 h-3" />
            Confirmed Appointment
          </span>
        );
      case "QUOTED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-purple-50 text-purple-700 border border-purple-200">
            <FileText className="w-3 h-3" />
            Quotation Issued
          </span>
        );
      case "ACCEPTED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200">
            <Check className="w-3 h-3" />
            Accepted (Pending Schedule)
          </span>
        );
      case "REQUESTED":
      case "UNDER_REVIEW":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-50 text-amber-700 border border-amber-200">
            <Clock className="w-3 h-3" />
            Booking Requested
          </span>
        );
      case "REJECTED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-50 text-rose-700 border border-rose-200">
            <XCircle className="w-3 h-3" />
            Rejected
          </span>
        );
      case "CANCELLED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-slate-50 text-slate-600 border border-slate-200">
            Cancelled
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded text-xs font-bold bg-slate-100 text-slate-700">
            {status}
          </span>
        );
    }
  };

  // Quick Accept Booking Action
  const handleAcceptBooking = async (booking: WorkshopBooking) => {
    try {
      await api.workshops.manageBookings.updateStatus(booking.id, { action: "ACCEPT" });
      showToast(`Booking ${(booking.booking_reference || booking.booking_number)} accepted.`);
      await loadData(true);
    } catch (err: any) {
      alert(err?.message || "Failed to accept booking");
    }
  };

  // Reject Booking Submit
  const handleRejectBookingSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rejectModalBooking) return;
    setRejectLoading(true);
    try {
      await api.workshops.manageBookings.updateStatus(rejectModalBooking.id, {
        action: "REJECT",
        rejection_reason: rejectReason || "Workshop capacity full for requested slot."
      });
      showToast(`Booking ${(rejectModalBooking.booking_reference || rejectModalBooking.booking_number)} rejected.`);
      setRejectModalBooking(null);
      setRejectReason("");
      await loadData(true);
    } catch (err: any) {
      alert(err?.message || "Failed to reject booking");
    } finally {
      setRejectLoading(false);
    }
  };

  // Schedule Appointment Submit with Capacity Check Feedback
  const handleScheduleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!scheduleModalBooking || !scheduleDate) return;
    setScheduleLoading(true);
    setScheduleError(null);

    try {
      const startIso = new Date(`${scheduleDate}T${scheduleStartTime}:00`).toISOString();
      const endIso = new Date(`${scheduleDate}T${scheduleEndTime}:00`).toISOString();

      await api.workshops.manageBookings.updateStatus(scheduleModalBooking.id, {
        action: "SCHEDULE",
        scheduled_appointment_start: startIso,
        scheduled_appointment_end: endIso,
        internal_notes: scheduleNotes || undefined
      });

      showToast(`Appointment scheduled for ${(scheduleModalBooking.booking_reference || scheduleModalBooking.booking_number)}. Bay capacity reserved.`);
      setScheduleModalBooking(null);
      setScheduleNotes("");
      await loadData(true);
    } catch (err: any) {
      console.error("Scheduling capacity error:", err);
      setScheduleError(err?.message || "Unable to schedule appointment. Capacity may be exceeded for this timeslot.");
    } finally {
      setScheduleLoading(false);
    }
  };

  // Open Quotation Builder
  const handleOpenQuotation = (booking: WorkshopBooking, existingQuote?: WorkshopQuotation) => {
    setQuoteBooking(booking);
    setQuoteError(null);

    if (existingQuote) {
      setQuoteTaxRate(parseFloat(String(existingQuote.tax_rate_percent || 20)));
      setQuoteDiscount(parseFloat(String(existingQuote.discount_amount || 0)));
      setQuoteNotes(existingQuote.workshop_notes || "");
      setQuoteTerms(existingQuote.terms_and_conditions || "");
      setQuoteValidUntil(existingQuote.valid_until || "");

      if (existingQuote.line_items && existingQuote.line_items.length > 0) {
        setQuoteLineItems(
          existingQuote.line_items.map((item, idx) => ({
            id: item.id || `item-${idx}`,
            item_type: item.item_type as any,
            description: item.description,
            part_number: item.part_number || "",
            quantity: parseFloat(String(item.quantity)),
            unit_price: parseFloat(String(item.unit_price))
          }))
        );
      } else {
        setQuoteLineItems([
          { id: "1", item_type: "LABOUR", description: "General Service Labour", part_number: "", quantity: 1, unit_price: 75 }
        ]);
      }
    } else {
      setQuoteTaxRate(profile?.default_tax_rate_percent ? parseFloat(profile.default_tax_rate_percent) : 20.0);
      setQuoteDiscount(0);
      setQuoteNotes("");
      setQuoteTerms("Estimate valid for 30 days. All parts and labour covered by DriverXtra guarantee.");
      if (booking.service_items && booking.service_items.length > 0) {
        setQuoteLineItems(
          booking.service_items.map((svc, idx) => ({
            id: `init-${idx}`,
            item_type: "LABOUR",
            description: svc.service_name,
            part_number: "",
            quantity: 1,
            unit_price: parseFloat(String(svc.quoted_price || 65))
          }))
        );
      } else {
        setQuoteLineItems([
          { id: "1", item_type: "LABOUR", description: "Vehicle Diagnostics & Safety Inspection", part_number: "", quantity: 1, unit_price: 65 },
          { id: "2", item_type: "PART", description: "Replacement Filter / Oil Element", part_number: "OEM-4401", quantity: 1, unit_price: 32 }
        ]);
      }
    }
  };

  // Live Quotation Calculations
  const quoteSubtotal = useMemo(() => {
    return quoteLineItems.reduce((acc, item) => {
      const qty = Number(item.quantity) || 0;
      const price = Number(item.unit_price) || 0;
      const total = qty * price;
      return item.item_type === "DISCOUNT" ? acc - total : acc + total;
    }, 0);
  }, [quoteLineItems]);

  const quoteCalculatedTax = useMemo(() => {
    const rate = Number(quoteTaxRate) || 0;
    const taxableBase = Math.max(0, quoteSubtotal - (Number(quoteDiscount) || 0));
    return (taxableBase * rate) / 100;
  }, [quoteSubtotal, quoteTaxRate, quoteDiscount]);

  const quoteGrandTotal = useMemo(() => {
    const afterDiscount = Math.max(0, quoteSubtotal - (Number(quoteDiscount) || 0));
    return afterDiscount + quoteCalculatedTax;
  }, [quoteSubtotal, quoteDiscount, quoteCalculatedTax]);

  // Submit Quotation (Draft or Issue)
  const handleSaveQuotation = async (andIssue: boolean) => {
    if (!quoteBooking) return;
    setQuoteSaving(true);
    setQuoteError(null);

    try {
      const payload = {
        discount_amount: quoteDiscount.toFixed(2),
        tax_rate_percent: quoteTaxRate.toFixed(2),
        valid_until: quoteValidUntil || null,
        workshop_notes: quoteNotes,
        terms_and_conditions: quoteTerms,
        line_items: quoteLineItems.map((item) => ({
          item_type: item.item_type,
          description: item.description,
          part_number: item.part_number || undefined,
          catalogue_part_id: null,
          quantity: Number(item.quantity) || 1,
          unit_price: Number(item.unit_price) || 0
        }))
      };

      const savedQuote = await api.workshops.manageQuotations.create(quoteBooking.id, payload);

      if (andIssue && savedQuote?.id) {
        await api.workshops.manageQuotations.issue(savedQuote.id);
        showToast(`Quotation #${(savedQuote.revision_number || savedQuote.version)} issued to customer.`);
      } else {
        showToast(`Quotation #${(savedQuote.revision_number || savedQuote.version)} saved as draft.`);
      }

      setQuoteBooking(null);
      await loadData(true);
    } catch (err: any) {
      console.error("Error saving quotation:", err);
      setQuoteError(err?.message || "Failed to save quotation");
    } finally {
      setQuoteSaving(false);
    }
  };

  // Direct Issue of Existing Draft Quote
  const handleIssueExistingQuote = async (quotationId: string) => {
    try {
      await api.workshops.manageQuotations.issue(quotationId);
      showToast("Quotation officially issued to buyer.");
      await loadData(true);
    } catch (err: any) {
      alert(err?.message || "Failed to issue quotation");
    }
  };

  // Add / Edit Service Submit
  const handleServiceFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setServiceSaving(true);
    try {
      const payload = {
        name: serviceFormName,
        category: serviceFormCategory || (categories[0]?.id ?? ""),
        description: serviceFormDescription,
        base_price: serviceFormPrice,
        estimated_duration_minutes: parseInt(serviceFormDuration) || 60,
        currency: profile?.currency || "GBP",
        is_active: true
      };

      if (editingServiceId) {
        await api.workshops.manageServices.update(editingServiceId, payload);
        showToast("Service updated successfully.");
      } else {
        await api.workshops.manageServices.create(payload);
        showToast("New service added to price book.");
      }

      setServiceModalOpen(false);
      setEditingServiceId(null);
      setServiceFormName("");
      setServiceFormDescription("");
      await loadData(true);
    } catch (err: any) {
      alert(err?.message || "Failed to save service");
    } finally {
      setServiceSaving(false);
    }
  };

  // Toggle Service Active Status
  const handleToggleServiceStatus = async (service: WorkshopServiceItem) => {
    try {
      await api.workshops.manageServices.update(service.id, {
        is_active: !service.is_active
      });
      showToast(`Service "${service.name}" ${service.is_active ? "disabled" : "activated"}.`);
      await loadData(true);
    } catch (err: any) {
      alert(err?.message || "Failed to update service status");
    }
  };

  // Save Operating Hours
  const handleSaveHours = async (e: React.FormEvent) => {
    e.preventDefault();
    setHoursSaving(true);
    try {
      await api.workshops.manageHours.update(operatingHours);
      await api.workshops.manageProfile.update({
        bay_capacity: profileForm.bay_capacity
      });
      showToast("Operating hours and bay capacity saved.");
      await loadData(true);
    } catch (err: any) {
      alert(err?.message || "Failed to save operating hours");
    } finally {
      setHoursSaving(false);
    }
  };

  // Save Profile Form
  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileSaving(true);
    try {
      await api.workshops.manageProfile.update({
        business_name: profileForm.business_name,
        description: profileForm.description,
        contact_email: profileForm.contact_email,
        contact_phone: profileForm.contact_phone,
        address_line1: profileForm.address_line1,
        address_line2: profileForm.address_line2,
        city: profileForm.city,
        state_province: profileForm.state_province,
        postal_code: profileForm.postal_code,
        country: profileForm.country,
        bay_capacity: profileForm.bay_capacity,
        default_tax_rate_percent: String(profileForm.default_tax_rate_percent),
        is_accepting_bookings: profileForm.is_accepting_bookings
      });
      showToast("Workshop profile settings updated successfully.");
      await loadData(true);
    } catch (err: any) {
      alert(err?.message || "Failed to save profile");
    } finally {
      setProfileSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-[500px] flex items-center justify-center p-8">
        <div className="flex flex-col items-center gap-3 text-slate-500">
          <RefreshCw className="w-8 h-8 animate-spin text-purple-600" />
          <span className="text-sm font-bold">Loading Workshop Partner Console...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed top-5 right-5 z-50 bg-slate-900 text-white px-5 py-3 rounded-2xl shadow-2xl border border-slate-700 flex items-center gap-3 animate-in fade-in slide-in-from-top-4">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
          <span className="text-sm font-bold">{toastMessage}</span>
        </div>
      )}

      {/* Role / Tech Access Notice */}
      {!canManageSettings && (
        <div className="bg-sky-50 border border-sky-200 rounded-2xl p-4 flex items-center justify-between text-xs text-sky-900">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-sky-600" />
            <span>
              <strong>Technician Mode:</strong> You have permissions for bookings, appointments and quotes. Workshop profile and bay settings are managed by Workshop Owners & Admins.
            </span>
          </div>
          <span className="px-2 py-0.5 rounded bg-sky-100 text-sky-800 font-bold uppercase text-[10px]">
            Role: {activeRole}
          </span>
        </div>
      )}

      {/* Header Banner */}
      <div className="bg-slate-950 text-white rounded-3xl p-6 shadow-sm border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-1.5">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-500/10 text-purple-400 text-xs font-bold border border-purple-500/20">
            <Wrench className="w-3.5 h-3.5" />
            <span>Commercial Workshop Partner Console</span>
          </div>
          <h1 className="text-2xl font-black tracking-tight text-white flex items-center gap-2">
            {profile?.business_name || profile?.display_name || user?.organizationName || "My Workshop Console"}
            <span className="text-xs font-normal text-slate-400 px-2.5 py-0.5 rounded-full bg-slate-800 border border-slate-700">
              {profile?.city || "UK"}
            </span>
          </h1>
          <p className="text-xs text-slate-400 max-w-2xl">
            Manage customer service bookings, allocate workshop bay capacity, generate verified repair quotes with itemised labour & parts, and issue official customer quotations.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="bg-slate-900 border border-slate-800 px-4 py-3 rounded-2xl flex items-center gap-3">
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <div className="text-xs">
              <span className="block text-slate-400 text-[10px] font-bold uppercase tracking-wider">Bay Capacity</span>
              <span className="font-bold text-white">{profile?.bay_capacity ?? 2} Service Bays Active</span>
            </div>
          </div>
          <button
            onClick={() => loadData(true)}
            disabled={refreshing}
            className="bg-slate-800 hover:bg-slate-700 text-white p-3 rounded-2xl border border-slate-700 transition flex items-center justify-center"
            title="Refresh Data"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin text-purple-400" : ""}`} />
          </button>
        </div>
      </div>

      {/* Console Tab Navigation */}
      <div className="flex items-center gap-2 border-b border-slate-200 pb-2 overflow-x-auto">
        <button
          onClick={() => setActiveTab("bookings")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition whitespace-nowrap ${
            activeTab === "bookings"
              ? "bg-purple-600 text-white shadow-sm"
              : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200"
          }`}
        >
          <CalendarCheck2 className="w-4 h-4" />
          <span>Bookings & Appointments</span>
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-black ${
            activeTab === "bookings" ? "bg-purple-700 text-purple-100" : "bg-slate-200 text-slate-700"
          }`}>
            {bookings.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab("services")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition whitespace-nowrap ${
            activeTab === "services"
              ? "bg-purple-600 text-white shadow-sm"
              : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200"
          }`}
        >
          <Layers className="w-4 h-4" />
          <span>Services & Price Book</span>
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-black ${
            activeTab === "services" ? "bg-purple-700 text-purple-100" : "bg-slate-200 text-slate-700"
          }`}>
            {services.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab("hours")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition whitespace-nowrap ${
            activeTab === "hours"
              ? "bg-purple-600 text-white shadow-sm"
              : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200"
          }`}
        >
          <Clock className="w-4 h-4" />
          <span>Operating Hours & Bays</span>
        </button>

        <button
          onClick={() => setActiveTab("profile")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition whitespace-nowrap ${
            activeTab === "profile"
              ? "bg-purple-600 text-white shadow-sm"
              : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200"
          }`}
        >
          <Settings className="w-4 h-4" />
          <span>Workshop Profile</span>
        </button>
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: BOOKINGS & APPOINTMENTS */}
      {/* ========================================================================= */}
      {activeTab === "bookings" && (
        <div className="space-y-4">
          {/* Filter Bar */}
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
                  onClick={() => setBookingFilter(f.value)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                    bookingFilter === f.value
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
                placeholder="Search ref, vehicle, customer..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-xs bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>

          {/* Bookings List */}
          {filteredBookings.length === 0 ? (
            <div className="bg-white rounded-2xl p-12 text-center border border-slate-200 space-y-3">
              <Calendar className="w-12 h-12 text-slate-300 mx-auto" />
              <h3 className="text-sm font-bold text-slate-700">No bookings found</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                {bookingFilter !== "ALL"
                  ? `There are currently no bookings with status "${bookingFilter}".`
                  : "Incoming customer booking requests will appear here once buyers schedule service appointments."}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {filteredBookings.map((bk) => {
                const latestQuote = bk.quotations && bk.quotations.length > 0 ? bk.quotations[0] : null;
                const isRequested = bk.status === "REQUESTED";
                const isAccepted = bk.status === "ACCEPTED";
                const isConfirmed = bk.status === "CONFIRMED";
                const isQuoted = bk.status === "QUOTED";

                return (
                  <div
                    key={bk.id}
                    className="bg-white rounded-2xl p-5 border border-slate-200 hover:border-slate-300 shadow-sm transition space-y-4"
                  >
                    {/* Top Row: Ref, Customer, Status */}
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-slate-100">
                      <div className="flex items-center gap-3">
                        <div className="p-2.5 rounded-xl bg-purple-50 text-purple-700 font-bold text-xs">
                          {(bk.booking_reference || bk.booking_number)}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-sm text-slate-900">
                              {(bk.customer_name || bk.buyer_name) || "Registered Driver"}
                            </span>
                            <span className="text-xs text-slate-400">&bull;</span>
                            <span className="text-xs text-slate-500">
                              Booked {new Date(bk.created_at).toLocaleDateString()}
                            </span>
                          </div>
                          <span className="text-xs text-slate-400 font-mono">
                            Buyer ID: {bk.buyer_id ? `${bk.buyer_id.slice(0, 8)}...` : "Registered User"}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-3">
                        {getStatusBadge(bk.status)}
                      </div>
                    </div>

                    {/* Middle Details: Vehicle, Preferred Date, Services */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs bg-slate-50 p-4 rounded-xl border border-slate-100">
                      {/* Vehicle details */}
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                          <Car className="w-3 h-3 text-purple-600" /> Vehicle Details
                        </span>
                        <div className="font-bold text-slate-900">
                          {bk.vehicle_year} {bk.vehicle_make} {bk.vehicle_model}
                        </div>
                        <div className="inline-block px-2 py-0.5 rounded bg-amber-100 text-amber-900 font-mono font-bold text-[11px]">
                          {(bk.vehicle_registration || bk.vehicle_registration_plate) || "Unregistered"}
                        </div>
                        {bk.vehicle_vin && (
                          <div className="text-[10px] text-slate-500 font-mono">
                            VIN: {bk.vehicle_vin}
                          </div>
                        )}
                      </div>

                      {/* Preferred / Scheduled Appointment */}
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                          <Clock className="w-3 h-3 text-blue-600" /> Appointment Schedule
                        </span>
                        {bk.scheduled_appointment_start ? (
                          <div className="space-y-0.5">
                            <span className="font-bold text-emerald-800 block">
                              {new Date(bk.scheduled_appointment_start).toLocaleDateString(undefined, {
                                weekday: "short",
                                day: "numeric",
                                month: "short",
                                year: "numeric"
                              })}
                            </span>
                            <span className="text-slate-600 text-[11px] block">
                              {new Date(bk.scheduled_appointment_start).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} &ndash; {new Date(bk.scheduled_appointment_end || "").toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                            </span>
                            <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded inline-block">
                              Bay Reserved
                            </span>
                          </div>
                        ) : (
                          <div className="space-y-0.5">
                            <span className="text-slate-800 font-medium block">
                              Preferred: {bk.preferred_date}
                            </span>
                            <span className="text-slate-500 block capitalize">
                              Slot: {bk.preferred_time_slot?.replace("_", " ") || "Any time"}
                            </span>
                            <span className="text-[10px] text-amber-700 font-bold block">
                              Awaiting workshop bay schedule
                            </span>
                          </div>
                        )}
                      </div>

                      {/* Services Requested */}
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                          <Wrench className="w-3 h-3 text-purple-600" /> Services Requested
                        </span>
                        {bk.service_items && bk.service_items.length > 0 ? (
                          <div className="flex flex-wrap gap-1.5 pt-0.5">
                            {bk.service_items.map((svc) => (
                              <span
                                key={svc.id}
                                className="px-2 py-0.5 rounded-md text-[11px] font-semibold bg-white border border-slate-200 text-slate-800"
                              >
                                {svc.service_name}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="text-slate-500 italic">Diagnostic / Inspection requested</span>
                        )}
                      </div>
                    </div>

                    {/* Reported Faults & Notes if present */}
                    {(bk.reported_faults || bk.customer_notes) && (
                      <div className="bg-amber-50/60 border border-amber-200/70 rounded-xl p-3 text-xs space-y-1">
                        {bk.reported_faults && (
                          <div>
                            <span className="font-bold text-amber-950 uppercase text-[10px] tracking-wider">Reported Faults: </span>
                            <span className="text-amber-900">{bk.reported_faults}</span>
                          </div>
                        )}
                        {bk.customer_notes && (
                          <div>
                            <span className="font-bold text-amber-950 uppercase text-[10px] tracking-wider">Customer Notes: </span>
                            <span className="text-amber-800">{bk.customer_notes}</span>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Quotation Status Strip (if quote exists) */}
                    {latestQuote && (
                      <div className="bg-purple-50/70 border border-purple-200 rounded-xl p-3 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-2">
                            <FileText className="w-4 h-4 text-purple-700" />
                            <span className="font-bold text-purple-950">
                              Quotation Rev #{(latestQuote.revision_number || latestQuote.version)} &ndash; Grand Total: £{parseFloat((latestQuote.grand_total || latestQuote.total_amount)).toFixed(2)}
                            </span>
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              latestQuote.status === "ACCEPTED"
                                ? "bg-emerald-100 text-emerald-800"
                                : latestQuote.status === "REJECTED"
                                ? "bg-rose-100 text-rose-800"
                                : latestQuote.status === "ISSUED"
                                ? "bg-indigo-100 text-indigo-800"
                                : "bg-slate-200 text-slate-700"
                            }`}>
                              Status: {latestQuote.status}
                            </span>
                          </div>
                          <span className="text-slate-500 text-[11px] block">
                            Subtotal: £{parseFloat((latestQuote.subtotal || latestQuote.total_amount)).toFixed(2)} | Tax ({latestQuote.tax_rate_percent}%): £{parseFloat(latestQuote.tax_amount).toFixed(2)}
                          </span>
                        </div>

                        <div className="flex items-center gap-2">
                          {latestQuote.status === "DRAFT" && (
                            <button
                              onClick={() => handleIssueExistingQuote(latestQuote.id)}
                              className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs flex items-center gap-1.5 transition"
                            >
                              <Send className="w-3.5 h-3.5" />
                              Issue to Buyer
                            </button>
                          )}
                          <button
                            onClick={() => handleOpenQuotation(bk, latestQuote)}
                            className="px-3 py-1.5 rounded-lg bg-white hover:bg-slate-100 text-purple-900 border border-purple-300 font-bold text-xs transition"
                          >
                            Edit Quote / Revise
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Action Bar */}
                    <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100">
                      <div className="text-[11px] text-slate-400">
                        {bk.internal_notes && (
                          <span>Internal note: <strong className="text-slate-600">{bk.internal_notes}</strong></span>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        {/* If REQUESTED -> Show Accept / Reject */}
                        {isRequested && (
                          <>
                            <button
                              onClick={() => {
                                setRejectModalBooking(bk);
                                setRejectReason("");
                              }}
                              className="px-3 py-1.5 rounded-xl text-rose-700 hover:bg-rose-50 border border-rose-200 text-xs font-bold transition"
                            >
                              Reject Request
                            </button>
                            <button
                              onClick={() => handleAcceptBooking(bk)}
                              className="px-4 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold transition flex items-center gap-1.5"
                            >
                              <Check className="w-3.5 h-3.5" />
                              Accept Booking
                            </button>
                          </>
                        )}

                        {/* If ACCEPTED or REQUESTED -> Allow Scheduling Appointment */}
                        {(isAccepted || isRequested) && (
                          <button
                            onClick={() => {
                              setScheduleModalBooking(bk);
                              setScheduleDate(bk.preferred_date || new Date().toISOString().split("T")[0]);
                              setScheduleStartTime("09:00");
                              setScheduleEndTime("11:00");
                              setScheduleError(null);
                            }}
                            className="px-4 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold transition flex items-center gap-1.5"
                          >
                            <Calendar className="w-3.5 h-3.5" />
                            Schedule Bay Appointment
                          </button>
                        )}

                        {/* If SCHEDULED or ACCEPTED -> Allow Creating / Revising Quotation */}
                        {(isAccepted || isConfirmed || isQuoted) && (
                          <button
                            onClick={() => handleOpenQuotation(bk, latestQuote || undefined)}
                            className="px-4 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition flex items-center gap-1.5"
                          >
                            <FileText className="w-3.5 h-3.5 text-purple-400" />
                            {latestQuote ? "Revise / Manage Quote" : "Create Itemised Quote"}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: SERVICES & PRICE BOOK */}
      {/* ========================================================================= */}
      {activeTab === "services" && (
        <div className="space-y-4">
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h2 className="text-base font-bold text-slate-900">Workshop Services & Price Book</h2>
              <p className="text-xs text-slate-500">
                Define your standardized labour packages, maintenance services, and diagnostic offerings.
              </p>
            </div>
            {canManageSettings ? (
              <button
                onClick={() => {
                  setEditingServiceId(null);
                  setServiceFormName("");
                  setServiceFormDescription("");
                  setServiceFormPrice("75.00");
                  setServiceFormDuration("60");
                  setServiceFormCategory(categories[0]?.id || "");
                  setServiceModalOpen(true);
                }}
                className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-bold text-xs flex items-center gap-1.5 shadow-sm transition"
              >
                <Plus className="w-4 h-4" />
                Add New Service
              </button>
            ) : (
              <span className="text-xs text-slate-500 font-bold bg-slate-100 px-3 py-1.5 rounded-xl border border-slate-200">
                Price Book Managed by Workshop Admin
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {services.map((svc) => (
              <div
                key={svc.id}
                className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm flex flex-col justify-between space-y-4"
              >
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <span className="px-2.5 py-0.5 rounded-md text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200 uppercase tracking-wide">
                      {svc.category_name || "Maintenance"}
                    </span>
                    <button
                      onClick={() => handleToggleServiceStatus(svc)}
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-full transition ${
                        svc.is_active
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                          : "bg-slate-100 text-slate-500 border border-slate-200"
                      }`}
                    >
                      {svc.is_active ? "Active" : "Disabled"}
                    </button>
                  </div>
                  <h3 className="text-sm font-bold text-slate-900">{svc.name}</h3>
                  <p className="text-xs text-slate-500 line-clamp-2 leading-relaxed">
                    {svc.description || "Standard workshop service package."}
                  </p>
                </div>

                <div className="pt-3 border-t border-slate-100 flex items-center justify-between">
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">Price</span>
                    <span className="text-base font-black text-slate-900">
                      £{parseFloat(svc.base_price).toFixed(2)}
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">Duration</span>
                    <span className="text-xs font-bold text-slate-600 flex items-center gap-1">
                      <Clock className="w-3 h-3 text-slate-400" /> {svc.estimated_duration_minutes} mins
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: OPERATING HOURS & BAY CAPACITY */}
      {/* ========================================================================= */}
      {activeTab === "hours" && (
        <form onSubmit={handleSaveHours} className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-6">
          <div>
            <h2 className="text-base font-bold text-slate-900">Operating Hours & Workshop Bay Capacity</h2>
            <p className="text-xs text-slate-500">
              DriverXtra enforces transaction-safe appointment booking against your workshop bay capacity.
            </p>
          </div>

          {/* Bay Capacity Setting */}
          <div className="bg-purple-50/70 border border-purple-200 rounded-2xl p-5 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="block text-xs font-bold text-purple-950 uppercase tracking-wider">
                Simultaneous Bay Capacity
              </label>
              <p className="text-xs text-purple-900/80">
                Maximum number of vehicles that can be booked for service concurrently at any given hour.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <input
                type="number"
                min="1"
                max="50"
                value={profileForm.bay_capacity}
                onChange={(e) => setProfileForm({ ...profileForm, bay_capacity: parseInt(e.target.value) || 1 })}
                className="w-24 px-3 py-2 rounded-xl border border-purple-300 text-sm font-bold text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <span className="text-xs font-bold text-purple-950">Active Vehicle Service Bays</span>
            </div>
          </div>

          {/* Days Grid */}
          <div className="space-y-2">
            <span className="text-xs font-bold text-slate-700 uppercase tracking-wider block">
              Weekly Schedule
            </span>
            <div className="divide-y divide-slate-100 border border-slate-200 rounded-2xl overflow-hidden">
              {operatingHours.map((hour, idx) => (
                <div
                  key={hour.day_of_week}
                  className={`p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 transition ${
                    hour.is_closed ? "bg-slate-50 opacity-70" : "bg-white"
                  }`}
                >
                  <div className="w-36 flex items-center gap-2">
                    <span className="font-bold text-sm text-slate-900">{hour.day_name}</span>
                  </div>

                  <div className="flex items-center gap-3">
                    <label className="flex items-center gap-2 text-xs font-bold text-slate-600 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={hour.is_closed}
                        onChange={(e) => {
                          const updated = [...operatingHours];
                          updated[idx] = { ...updated[idx], is_closed: e.target.checked };
                          setOperatingHours(updated);
                        }}
                        className="rounded border-slate-300 text-purple-600 focus:ring-purple-500 w-4 h-4"
                      />
                      <span>Closed</span>
                    </label>
                  </div>

                  {!hour.is_closed && (
                    <div className="flex items-center gap-3 text-xs">
                      <div className="flex items-center gap-1.5">
                        <span className="text-slate-400 font-bold uppercase text-[10px]">Open:</span>
                        <input
                          type="time"
                          value={hour.open_time?.slice(0, 5) || "08:30"}
                          onChange={(e) => {
                            const updated = [...operatingHours];
                            updated[idx] = { ...updated[idx], open_time: `${e.target.value}:00` };
                            setOperatingHours(updated);
                          }}
                          className="px-2 py-1 rounded-lg border border-slate-200 text-xs font-mono font-bold"
                        />
                      </div>
                      <span className="text-slate-400">&ndash;</span>
                      <div className="flex items-center gap-1.5">
                        <span className="text-slate-400 font-bold uppercase text-[10px]">Close:</span>
                        <input
                          type="time"
                          value={hour.close_time?.slice(0, 5) || "17:30"}
                          onChange={(e) => {
                            const updated = [...operatingHours];
                            updated[idx] = { ...updated[idx], close_time: `${e.target.value}:00` };
                            setOperatingHours(updated);
                          }}
                          className="px-2 py-1 rounded-lg border border-slate-200 text-xs font-mono font-bold"
                        />
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {!canManageSettings && (
            <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-xl p-3 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
              <span>Read-Only: Bay capacity and operating schedule can only be modified by Workshop Owners and Admins.</span>
            </div>
          )}

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={hoursSaving || !canManageSettings}
              title={!canManageSettings ? "Requires Workshop Owner or Admin permissions" : undefined}
              className="px-6 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-bold text-xs flex items-center gap-2 shadow-sm transition disabled:opacity-50"
            >
              {hoursSaving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
              <span>Save Schedule & Capacity</span>
            </button>
          </div>
        </form>
      )}

      {/* ========================================================================= */}
      {/* TAB 4: WORKSHOP PROFILE */}
      {/* ========================================================================= */}
      {activeTab === "profile" && (
        <form onSubmit={handleSaveProfile} className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-6">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <h2 className="text-base font-bold text-slate-900">Workshop Legal Profile & Contact Details</h2>
              <p className="text-xs text-slate-500">
                Trading information shown to buyers when booking services.
              </p>
            </div>
            <span className="text-xs text-slate-500 font-bold bg-slate-100 px-3 py-1 rounded-full">
              Org: {profile?.organisation_name || "Independent Workshop"}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div className="space-y-1">
              <label className="block font-bold text-slate-700">Trading / Business Name</label>
              <input
                type="text"
                value={profileForm.business_name}
                onChange={(e) => setProfileForm({ ...profileForm, business_name: e.target.value })}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            <div className="space-y-1">
              <label className="block font-bold text-slate-700">Contact Email</label>
              <input
                type="email"
                value={profileForm.contact_email}
                onChange={(e) => setProfileForm({ ...profileForm, contact_email: e.target.value })}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            <div className="space-y-1">
              <label className="block font-bold text-slate-700">Contact Phone</label>
              <input
                type="tel"
                value={profileForm.contact_phone}
                onChange={(e) => setProfileForm({ ...profileForm, contact_phone: e.target.value })}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            <div className="space-y-1">
              <label className="block font-bold text-slate-700">Default Tax / VAT Rate (%)</label>
              <input
                type="number"
                step="0.1"
                value={profileForm.default_tax_rate_percent}
                onChange={(e) => setProfileForm({ ...profileForm, default_tax_rate_percent: parseFloat(e.target.value) || 0 })}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            <div className="md:col-span-2 space-y-1">
              <label className="block font-bold text-slate-700">Workshop Overview & Specialisms</label>
              <textarea
                rows={3}
                value={profileForm.description}
                onChange={(e) => setProfileForm({ ...profileForm, description: e.target.value })}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            <div className="space-y-1">
              <label className="block font-bold text-slate-700">Address Line 1</label>
              <input
                type="text"
                value={profileForm.address_line1}
                onChange={(e) => setProfileForm({ ...profileForm, address_line1: e.target.value })}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            <div className="space-y-1">
              <label className="block font-bold text-slate-700">Address Line 2 (Optional)</label>
              <input
                type="text"
                value={profileForm.address_line2}
                onChange={(e) => setProfileForm({ ...profileForm, address_line2: e.target.value })}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            <div className="space-y-1">
              <label className="block font-bold text-slate-700">City</label>
              <input
                type="text"
                value={profileForm.city}
                onChange={(e) => setProfileForm({ ...profileForm, city: e.target.value })}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>

            <div className="space-y-1">
              <label className="block font-bold text-slate-700">Postal Code</label>
              <input
                type="text"
                value={profileForm.postal_code}
                onChange={(e) => setProfileForm({ ...profileForm, postal_code: e.target.value })}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>

          <div className="pt-3 border-t border-slate-100 flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={profileForm.is_accepting_bookings}
                onChange={(e) => setProfileForm({ ...profileForm, is_accepting_bookings: e.target.checked })}
                className="w-4 h-4 rounded text-purple-600 focus:ring-purple-500"
              />
              <span className="text-xs font-bold text-slate-800">Currently accepting online bookings from buyers</span>
            </label>

            <div className="flex items-center gap-3">
              {!canManageSettings && (
                <span className="text-xs text-amber-700 bg-amber-50 px-2.5 py-1 rounded-lg border border-amber-200 font-medium">
                  Read-Only (Owner/Admin required)
                </span>
              )}
              <button
                type="submit"
                disabled={profileSaving || !canManageSettings}
                title={!canManageSettings ? "Requires Workshop Owner or Admin permissions" : undefined}
                className="px-6 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-bold text-xs flex items-center gap-2 shadow-sm transition disabled:opacity-50"
              >
                {profileSaving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                <span>Save Profile Changes</span>
              </button>
            </div>
          </div>
        </form>
      )}

      {/* ========================================================================= */}
      {/* MODAL 1: SCHEDULE APPOINTMENT (WITH CAPACITY CHECK) */}
      {/* ========================================================================= */}
      {scheduleModalBooking && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl border border-slate-200 space-y-5 animate-in fade-in zoom-in-95">
            <div className="flex items-start justify-between pb-3 border-b border-slate-100">
              <div>
                <span className="text-[10px] uppercase font-bold text-purple-600 tracking-wider">Bay Capacity Check</span>
                <h3 className="text-base font-black text-slate-900">Schedule Service Appointment</h3>
                <span className="text-xs text-slate-500 font-mono">Ref: {(scheduleModalBooking.booking_reference || scheduleModalBooking.booking_number)}</span>
              </div>
              <button
                onClick={() => setScheduleModalBooking(null)}
                className="p-1 text-slate-400 hover:text-slate-600 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {scheduleError && (
              <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-xl p-3 text-xs flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                <div>
                  <span className="font-bold block">Bay Allocation Failed</span>
                  <span>{scheduleError}</span>
                </div>
              </div>
            )}

            <form onSubmit={handleScheduleSubmit} className="space-y-4 text-xs">
              <div className="space-y-1">
                <label className="block font-bold text-slate-700">Appointment Date</label>
                <input
                  type="date"
                  required
                  value={scheduleDate}
                  onChange={(e) => setScheduleDate(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="block font-bold text-slate-700">Start Time</label>
                  <input
                    type="time"
                    required
                    value={scheduleStartTime}
                    onChange={(e) => setScheduleStartTime(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block font-bold text-slate-700">End Time</label>
                  <input
                    type="time"
                    required
                    value={scheduleEndTime}
                    onChange={(e) => setScheduleEndTime(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="block font-bold text-slate-700">Internal Notes / Bay Allocation</label>
                <textarea
                  rows={2}
                  placeholder="e.g. Assigned to Bay 1. Technician: Dave."
                  value={scheduleNotes}
                  onChange={(e) => setScheduleNotes(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setScheduleModalBooking(null)}
                  className="px-4 py-2 rounded-xl text-slate-600 hover:bg-slate-100 font-bold transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={scheduleLoading}
                  className="px-5 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-bold transition flex items-center gap-1.5 disabled:opacity-50"
                >
                  {scheduleLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                  <span>Confirm Schedule</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 2: REJECT BOOKING WITH REASON */}
      {/* ========================================================================= */}
      {rejectModalBooking && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl border border-slate-200 space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-start justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-base font-black text-rose-950">Reject Booking Request</h3>
                <span className="text-xs text-slate-500 font-mono">Ref: {(rejectModalBooking.booking_reference || rejectModalBooking.booking_number)}</span>
              </div>
              <button onClick={() => setRejectModalBooking(null)} className="p-1 text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleRejectBookingSubmit} className="space-y-4 text-xs">
              <div className="space-y-1">
                <label className="block font-bold text-slate-700">Reason for Rejection</label>
                <textarea
                  rows={3}
                  required
                  placeholder="Please explain why this booking cannot be accepted (e.g. bay fully booked, parts unavailable)..."
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-rose-500"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setRejectModalBooking(null)}
                  className="px-4 py-2 rounded-xl text-slate-600 hover:bg-slate-100 font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={rejectLoading}
                  className="px-5 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white font-bold transition flex items-center gap-1.5"
                >
                  {rejectLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <XCircle className="w-4 h-4" />}
                  <span>Confirm Rejection</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 3: COMPREHENSIVE QUOTATION BUILDER */}
      {/* ========================================================================= */}
      {quoteBooking && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white rounded-3xl max-w-3xl w-full p-6 shadow-2xl border border-slate-200 space-y-5 my-8 animate-in fade-in zoom-in-95">
            {/* Header */}
            <div className="flex items-start justify-between pb-3 border-b border-slate-100">
              <div>
                <div className="flex items-center gap-2">
                  <FileText className="w-5 h-5 text-purple-600" />
                  <h3 className="text-lg font-black text-slate-900">Itemised Workshop Quotation Builder</h3>
                </div>
                <div className="text-xs text-slate-500 flex items-center gap-2 mt-0.5">
                  <span>Booking Ref: <strong className="text-slate-800 font-mono">{(quoteBooking.booking_reference || quoteBooking.booking_number)}</strong></span>
                  <span>&bull;</span>
                  <span>Vehicle: <strong className="text-slate-800">{quoteBooking.vehicle_make} {quoteBooking.vehicle_model} [{(quoteBooking.vehicle_registration || quoteBooking.vehicle_registration_plate)}]</strong></span>
                </div>
              </div>
              <button onClick={() => setQuoteBooking(null)} className="p-1 text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            {quoteError && (
              <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-xl p-3 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>{quoteError}</span>
              </div>
            )}

            {/* Line Items Table */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                  Line Items & Parts Breakdown
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setQuoteLineItems([
                      ...quoteLineItems,
                      {
                        id: String(Date.now()),
                        item_type: "LABOUR",
                        description: "",
                        part_number: "",
                        quantity: 1,
                        unit_price: 60
                      }
                    ]);
                  }}
                  className="text-xs font-bold text-purple-600 hover:text-purple-800 flex items-center gap-1"
                >
                  <Plus className="w-3.5 h-3.5" /> Add Item
                </button>
              </div>

              <div className="space-y-2">
                {quoteLineItems.map((item, idx) => (
                  <div
                    key={item.id}
                    className="grid grid-cols-12 gap-2 items-center bg-slate-50 p-2.5 rounded-xl border border-slate-200 text-xs"
                  >
                    <div className="col-span-3">
                      <select
                        value={item.item_type}
                        onChange={(e) => {
                          const updated = [...quoteLineItems];
                          updated[idx].item_type = e.target.value as any;
                          setQuoteLineItems(updated);
                        }}
                        className="w-full px-2 py-1.5 rounded-lg border border-slate-200 text-[11px] font-bold bg-white"
                      >
                        <option value="LABOUR">Labour</option>
                        <option value="PART">Part</option>
                        <option value="DIAGNOSTIC">Diagnostic</option>
                        <option value="FEE">Fee / Surcharge</option>
                        <option value="DISCOUNT">Discount</option>
                      </select>
                    </div>

                    <div className="col-span-4">
                      <input
                        type="text"
                        placeholder="Description..."
                        value={item.description}
                        onChange={(e) => {
                          const updated = [...quoteLineItems];
                          updated[idx].description = e.target.value;
                          setQuoteLineItems(updated);
                        }}
                        className="w-full px-2 py-1.5 rounded-lg border border-slate-200 text-xs bg-white"
                      />
                    </div>

                    <div className="col-span-2">
                      <input
                        type="number"
                        min="1"
                        placeholder="Qty"
                        value={item.quantity}
                        onChange={(e) => {
                          const updated = [...quoteLineItems];
                          updated[idx].quantity = parseFloat(e.target.value) || 0;
                          setQuoteLineItems(updated);
                        }}
                        className="w-full px-2 py-1.5 rounded-lg border border-slate-200 text-xs text-center bg-white"
                      />
                    </div>

                    <div className="col-span-2">
                      <div className="relative">
                        <span className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400">£</span>
                        <input
                          type="number"
                          step="0.01"
                          placeholder="Price"
                          value={item.unit_price}
                          onChange={(e) => {
                            const updated = [...quoteLineItems];
                            updated[idx].unit_price = parseFloat(e.target.value) || 0;
                            setQuoteLineItems(updated);
                          }}
                          className="w-full pl-5 pr-2 py-1.5 rounded-lg border border-slate-200 text-xs bg-white font-mono"
                        />
                      </div>
                    </div>

                    <div className="col-span-1 text-right">
                      <button
                        type="button"
                        disabled={quoteLineItems.length <= 1}
                        onClick={() => {
                          setQuoteLineItems(quoteLineItems.filter((_, i) => i !== idx));
                        }}
                        className="p-1 text-slate-400 hover:text-rose-600 disabled:opacity-30"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Calculations & Discounts */}
            <div className="bg-slate-900 text-white p-4 rounded-2xl space-y-2 text-xs">
              <div className="flex justify-between text-slate-300">
                <span>Subtotal (Net)</span>
                <span className="font-mono font-bold">£{quoteSubtotal.toFixed(2)}</span>
              </div>

              <div className="flex justify-between items-center text-slate-300">
                <div className="flex items-center gap-2">
                  <span>Tax Rate:</span>
                  <input
                    type="number"
                    step="0.5"
                    value={quoteTaxRate}
                    onChange={(e) => setQuoteTaxRate(parseFloat(e.target.value) || 0)}
                    className="w-16 px-1.5 py-0.5 rounded bg-slate-800 text-white border border-slate-700 text-xs font-mono"
                  />
                  <span>%</span>
                </div>
                <span className="font-mono font-bold">£{quoteCalculatedTax.toFixed(2)}</span>
              </div>

              <div className="flex justify-between items-center text-slate-300">
                <div className="flex items-center gap-2">
                  <span>Special Discount (£):</span>
                  <input
                    type="number"
                    step="1"
                    value={quoteDiscount}
                    onChange={(e) => setQuoteDiscount(parseFloat(e.target.value) || 0)}
                    className="w-20 px-1.5 py-0.5 rounded bg-slate-800 text-white border border-slate-700 text-xs font-mono"
                  />
                </div>
                <span className="font-mono text-emerald-400 font-bold">-£{Number(quoteDiscount || 0).toFixed(2)}</span>
              </div>

              <div className="pt-2 border-t border-slate-800 flex justify-between items-center text-base font-black text-white">
                <span>Total Quotation Amount</span>
                <span className="font-mono text-emerald-400 text-lg">£{quoteGrandTotal.toFixed(2)}</span>
              </div>
            </div>

            {/* Terms and Notes */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div className="space-y-1">
                <label className="block font-bold text-slate-700">Workshop Notes / Diagnostics</label>
                <textarea
                  rows={2}
                  placeholder="Specific fault analysis or technician recommendations..."
                  value={quoteNotes}
                  onChange={(e) => setQuoteNotes(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              <div className="space-y-1">
                <label className="block font-bold text-slate-700">Terms & Guarantee</label>
                <textarea
                  rows={2}
                  value={quoteTerms}
                  onChange={(e) => setQuoteTerms(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
            </div>

            {/* Buttons */}
            <div className="pt-3 border-t border-slate-100 flex items-center justify-between">
              <button
                type="button"
                onClick={() => setQuoteBooking(null)}
                className="px-4 py-2 rounded-xl text-slate-600 hover:bg-slate-100 font-bold text-xs"
              >
                Cancel
              </button>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={quoteSaving}
                  onClick={() => handleSaveQuotation(false)}
                  className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold text-xs transition disabled:opacity-50"
                >
                  Save as Draft
                </button>
                <button
                  type="button"
                  disabled={quoteSaving}
                  onClick={() => handleSaveQuotation(true)}
                  className="px-5 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-bold text-xs shadow-sm transition flex items-center gap-1.5 disabled:opacity-50"
                >
                  {quoteSaving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  <span>Save & Issue to Customer</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 4: ADD / EDIT SERVICE */}
      {/* ========================================================================= */}
      {serviceModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl border border-slate-200 space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-start justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-base font-black text-slate-900">
                  {editingServiceId ? "Edit Workshop Service" : "Add New Workshop Service"}
                </h3>
                <span className="text-xs text-slate-500">Add standardized service to your commercial catalog</span>
              </div>
              <button onClick={() => setServiceModalOpen(false)} className="p-1 text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleServiceFormSubmit} className="space-y-4 text-xs">
              <div className="space-y-1">
                <label className="block font-bold text-slate-700">Service Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Major Engine Service"
                  value={serviceFormName}
                  onChange={(e) => setServiceFormName(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              <div className="space-y-1">
                <label className="block font-bold text-slate-700">Category</label>
                <select
                  value={serviceFormCategory}
                  onChange={(e) => setServiceFormCategory(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                >
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1">
                <label className="block font-bold text-slate-700">Description</label>
                <textarea
                  rows={2}
                  placeholder="Details of labour, checks, or included items..."
                  value={serviceFormDescription}
                  onChange={(e) => setServiceFormDescription(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="block font-bold text-slate-700">Base Price (£)</label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    value={serviceFormPrice}
                    onChange={(e) => setServiceFormPrice(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block font-bold text-slate-700">Duration (Mins)</label>
                  <input
                    type="number"
                    step="15"
                    min="15"
                    required
                    value={serviceFormDuration}
                    onChange={(e) => setServiceFormDuration(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setServiceModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-slate-600 hover:bg-slate-100 font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={serviceSaving}
                  className="px-5 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-bold transition flex items-center gap-1.5"
                >
                  {serviceSaving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                  <span>Save Service</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
