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
  WorkOrderSummary,
  WorkOrderDetail,
  WorkOrderTaskItem,
  WorkshopTechnicianMember,
  ChangeOrder,
} from "@/lib/api/client";
import {
  Wrench,
  AlertCircle,
  AlertTriangle,
  FileCheck2,
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
  ClipboardList,
  CheckSquare,
  PackageCheck,
  UserCheck,
  PlayCircle,
  PauseCircle,
  ChevronRight,
} from "lucide-react";


function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message;
  if (err && typeof err === "object" && "message" in err && typeof err.message === "string") {
    return err.message;
  }
  return fallback;
}

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
  const [activeTab, setActiveTab] = useState<"bookings" | "work_orders" | "services" | "hours" | "profile">("bookings");

  // Core Data
  const [profile, setProfile] = useState<WorkshopProfilePublic | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [operatingHours, setOperatingHours] = useState<WorkshopOperatingHours[]>([]);
  const [services, setServices] = useState<WorkshopServiceItem[]>([]);
  const [categories, setCategories] = useState<WorkshopServiceCategory[]>([]);
  const [bookings, setBookings] = useState<WorkshopBooking[]>([]);

  // Work Orders State
  const [workOrders, setWorkOrders] = useState<WorkOrderSummary[]>([]);
  const [technicians, setTechnicians] = useState<WorkshopTechnicianMember[]>([]);
  const [workOrderFilter, setWorkOrderFilter] = useState<string>("ALL");
  const [workOrderSearchQuery, setWorkOrderSearchQuery] = useState("");

  // Work Order Detail Modal
  const [selectedWorkOrder, setSelectedWorkOrder] = useState<WorkOrderDetail | null>(null);
  const [workOrderDetailLoading, setWorkOrderDetailLoading] = useState(false);
  const [workOrderActionLoading, setWorkOrderActionLoading] = useState(false);
  const [workOrderModalError, setWorkOrderModalError] = useState<string | null>(null);

  // Status Action Modal State
  const [statusModalTarget, setStatusModalTarget] = useState<string | null>(null);
  const [statusModalNotes, setStatusModalNotes] = useState("");
  const [statusModalQualityNotes, setStatusModalQualityNotes] = useState("");
  const [statusModalCancelReason, setStatusModalCancelReason] = useState("");

  // Lead Technician Assignment
  const [selectedLeadTechId, setSelectedLeadTechId] = useState("");
  const [assignTechLoading, setAssignTechLoading] = useState(false);

  // New Task in Work Order
  const [newTaskDesc, setNewTaskDesc] = useState("");
  const [newTaskEstMinutes, setNewTaskEstMinutes] = useState("60");
  const [newTaskTechId, setNewTaskTechId] = useState("");
  const [newTaskLoading, setNewTaskLoading] = useState(false);

  // New Part Usage in Work Order
  const [newPartName, setNewPartName] = useState("");
  const [newPartNumber, setNewPartNumber] = useState("");
  const [newPartQty, setNewPartQty] = useState("1");
  const [newPartUnitCost, setNewPartUnitCost] = useState("0.00");
  const [newPartLoading, setNewPartLoading] = useState(false);

  // Change Orders in Work Order
  const [changeOrders, setChangeOrders] = useState<ChangeOrder[]>([]);
  const [loadingChangeOrders, setLoadingChangeOrders] = useState(false);
  const [newCoModalOpen, setNewCoModalOpen] = useState(false);
  const [coReason, setCoReason] = useState("");
  const [coDiscount, setCoDiscount] = useState("0.00");
  const [coTaxRate, setCoTaxRate] = useState("0.00");
  const [coWorkshopNotes, setCoWorkshopNotes] = useState("");
  const [coSubmitNow, setCoSubmitNow] = useState(true);
  const [coLineItems, setCoLineItems] = useState<Array<{
    item_type: "LABOUR" | "PART" | "DIAGNOSTIC" | "DISPOSAL" | "OTHER";
    description: string;
    part_number?: string;
    quantity: string;
    unit_price: string;
    estimated_labour_minutes?: number;
  }>>([
    { item_type: "LABOUR", description: "", quantity: "1", unit_price: "0.00", estimated_labour_minutes: 60 }
  ]);
  const [coActionLoading, setCoActionLoading] = useState(false);

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
  const [quoteTaxRate, setQuoteTaxRate] = useState<number>(0.0);
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

  // Platform tax collection authorization
  const canCollectTax = Boolean(profile?.can_collect_tax);

  // Quotation tax rate is initialized to 0.0% when canCollectTax is false

  // Show toast notification
  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  // Load All Workshop Data (called by user actions: refresh, save, etc.)
  const loadData = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);

    try {
      let profData: WorkshopProfilePublic | null = null;
      let profErr: string | null = null;
      try {
        profData = await api.workshops.manageProfile.get();
      } catch (err: unknown) {
        profErr = getErrorMessage(err, "Failed to load workshop profile.");
        console.warn("Workshop profile load failed:", err);
      }

      const [catsData, svcsData, bksData, woData, techsData] = await Promise.all([
        api.workshops.getCategories().catch(() => []),
        api.workshops.manageServices.list().catch(() => []),
        api.workshops.manageBookings.list().catch(() => ({ results: [], count: 0 })),
        api.workshops.manageWorkOrders.list().catch(() => ({ results: [], count: 0 })),
        api.workshops.manageTechnicians.list().catch(() => []),
      ]);

      setProfileError(profErr);

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
      setWorkOrders(woData?.results || []);
      setTechnicians(techsData || []);
    } catch (err: unknown) {
      console.error("Error loading workshop data:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    let ignore = false;
    Promise.all([
      api.workshops.manageProfile.get().catch((err: unknown) => {
        console.warn("Workshop profile load failed:", err);
        return null;
      }),
      api.workshops.getCategories().catch(() => []),
      api.workshops.manageServices.list().catch(() => []),
      api.workshops.manageBookings.list().catch(() => ({ results: [], count: 0 })),
      api.workshops.manageWorkOrders.list().catch(() => ({ results: [], count: 0 })),
      api.workshops.manageTechnicians.list().catch(() => []),
      api.workshops.manageHours.get().catch(() => []),
    ])
      .then(([profData, catsData, svcsData, bksData, woData, techsData, hoursData]) => {
        if (!ignore) {
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
            } else if (hoursData && hoursData.length > 0) {
              setOperatingHours(hoursData);
            } else {
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
          setWorkOrders(woData?.results || []);
          setTechnicians(techsData || []);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        console.error("Mount data load failed:", err);
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [user?.email]);

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

  // Filtered Work Orders
  const filteredWorkOrders = useMemo(() => {
    return workOrders.filter((wo) => {
      const matchesFilter =
        workOrderFilter === "ALL"
          ? true
          : wo.status.toUpperCase() === workOrderFilter.toUpperCase();

      const q = workOrderSearchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        wo.work_order_number.toLowerCase().includes(q) ||
        wo.booking_number.toLowerCase().includes(q) ||
        (wo.vehicle_registration_plate && wo.vehicle_registration_plate.toLowerCase().includes(q)) ||
        (wo.vehicle_make && wo.vehicle_make.toLowerCase().includes(q)) ||
        (wo.vehicle_model && wo.vehicle_model.toLowerCase().includes(q)) ||
        (wo.lead_technician_name && wo.lead_technician_name.toLowerCase().includes(q));

      return matchesFilter && matchesSearch;
    });
  }, [workOrders, workOrderFilter, workOrderSearchQuery]);

  // Work Order Action Handlers
  const handleOpenWorkOrder = async (id: string) => {
    setWorkOrderDetailLoading(true);
    setWorkOrderModalError(null);
    try {
      const detail = await api.workshops.manageWorkOrders.get(id);
      setSelectedWorkOrder(detail);
      setSelectedLeadTechId(detail.lead_technician || "");
      try {
        setLoadingChangeOrders(true);
        const coData = await api.workshops.manageWorkOrders.listChangeOrders(id);
        setChangeOrders(coData?.results || []);
      } catch {
        setChangeOrders([]);
      } finally {
        setLoadingChangeOrders(false);
      }
    } catch (err: unknown) {
      console.error("Failed to load work order detail:", err);
      showToast(getErrorMessage(err, "Failed to load work order detail"));
    } finally {
      setWorkOrderDetailLoading(false);
    }
  };

  const handleRefreshSelectedWorkOrder = async () => {
    if (!selectedWorkOrder) return;
    try {
      const detail = await api.workshops.manageWorkOrders.get(selectedWorkOrder.id);
      setSelectedWorkOrder(detail);
      setSelectedLeadTechId(detail.lead_technician || "");
      try {
        const coData = await api.workshops.manageWorkOrders.listChangeOrders(selectedWorkOrder.id);
        setChangeOrders(coData?.results || []);
      } catch {
        setChangeOrders([]);
      }
      const woData = await api.workshops.manageWorkOrders.list().catch(() => ({ results: [], count: 0 }));
      setWorkOrders(woData?.results || []);
    } catch (err) {
      console.error(err);
    }
  };

  const handleAssignLeadTechnician = async () => {
    if (!selectedWorkOrder || !selectedLeadTechId) return;
    setAssignTechLoading(true);
    setWorkOrderModalError(null);
    try {
      const updated = await api.workshops.manageWorkOrders.assignTechnician(selectedWorkOrder.id, selectedLeadTechId);
      setSelectedWorkOrder(updated);
      showToast("Lead technician assigned successfully.");
      await handleRefreshSelectedWorkOrder();
    } catch (err: unknown) {
      setWorkOrderModalError(getErrorMessage(err, "Failed to assign technician"));
    } finally {
      setAssignTechLoading(false);
    }
  };

  const handleExecuteStatusUpdate = async (targetStatus: string) => {
    if (!selectedWorkOrder) return;
    setWorkOrderActionLoading(true);
    setWorkOrderModalError(null);
    try {
      const res = await api.workshops.manageWorkOrders.updateStatus(selectedWorkOrder.id, {
        status: targetStatus as "ASSIGNED" | "IN_PROGRESS" | "AWAITING_PARTS" | "QUALITY_CHECK" | "COMPLETED" | "CANCELLED",
        internal_notes: statusModalNotes || undefined,
        quality_notes: statusModalQualityNotes || undefined,
        cancellation_reason: statusModalCancelReason || undefined,
      });
      const updated = res.work_order;
      setSelectedWorkOrder(updated);
      setStatusModalTarget(null);
      setStatusModalNotes("");
      setStatusModalQualityNotes("");
      setStatusModalCancelReason("");
      showToast(`Work order status updated to ${updated.status_display || updated.status}`);
      if (res.warnings && res.warnings.length > 0) {
        const odoWarn = res.warnings.find((w) => w.code === "ODOMETER_UNIT_MISMATCH");
        if (odoWarn) {
          setTimeout(() => showToast(`Notice: ${odoWarn.message}`), 4100);
        }
      }
      await handleRefreshSelectedWorkOrder();
    } catch (err: unknown) {
      setWorkOrderModalError(getErrorMessage(err, "Failed to update work order status"));
    } finally {
      setWorkOrderActionLoading(false);
    }
  };

  const handleToggleTaskStatus = async (task: WorkOrderTaskItem) => {
    if (!selectedWorkOrder) return;
    const nextStatus =
      task.status === "PENDING"
        ? "IN_PROGRESS"
        : task.status === "IN_PROGRESS"
        ? "COMPLETED"
        : "PENDING";

    try {
      await api.workshops.manageWorkOrders.updateTask(selectedWorkOrder.id, task.id, {
        status: nextStatus as "PENDING" | "IN_PROGRESS" | "COMPLETED",
      });
      await handleRefreshSelectedWorkOrder();
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to update task status"));
    }
  };

  const handleUpdateTaskLabour = async (task: WorkOrderTaskItem, newMinutes: number) => {
    if (!selectedWorkOrder || newMinutes < 0) return;
    try {
      await api.workshops.manageWorkOrders.updateTask(selectedWorkOrder.id, task.id, {
        actual_labour_minutes: newMinutes,
      });
      await handleRefreshSelectedWorkOrder();
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to update actual labour"));
    }
  };

  const handleAddNewTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedWorkOrder || !newTaskDesc.trim()) return;
    setNewTaskLoading(true);
    try {
      await api.workshops.manageWorkOrders.addTask(selectedWorkOrder.id, {
        description: newTaskDesc.trim(),
        estimated_labour_minutes: parseInt(newTaskEstMinutes, 10) || 60,
        assigned_technician_id: newTaskTechId || undefined,
      });
      setNewTaskDesc("");
      setNewTaskEstMinutes("60");
      setNewTaskTechId("");
      showToast("Task added to work order.");
      await handleRefreshSelectedWorkOrder();
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to add task"));
    } finally {
      setNewTaskLoading(false);
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    if (!selectedWorkOrder) return;
    if (!confirm("Are you sure you want to remove this task?")) return;
    try {
      await api.workshops.manageWorkOrders.deleteTask(selectedWorkOrder.id, taskId);
      showToast("Task removed.");
      await handleRefreshSelectedWorkOrder();
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to delete task"));
    }
  };

  const handleAddNewPartUsage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedWorkOrder || !newPartName.trim()) return;
    setNewPartLoading(true);
    try {
      await api.workshops.manageWorkOrders.recordPartUsage(selectedWorkOrder.id, {
        part_name: newPartName.trim(),
        part_number: newPartNumber.trim() || undefined,
        quantity: newPartQty,
        unit_cost: newPartUnitCost,
      });
      setNewPartName("");
      setNewPartNumber("");
      setNewPartQty("1");
      setNewPartUnitCost("0.00");
      showToast("Spare part recorded.");
      await handleRefreshSelectedWorkOrder();
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to record part usage"));
    } finally {
      setNewPartLoading(false);
    }
  };

  // Change Order Action Handlers
  const handleAddCoLineItem = () => {
    setCoLineItems((prev) => [
      ...prev,
      { item_type: "PART", description: "", quantity: "1", unit_price: "0.00" }
    ]);
  };

  const handleRemoveCoLineItem = (index: number) => {
    setCoLineItems((prev) => prev.filter((_, idx) => idx !== index));
  };

  const handleUpdateCoLineItem = (index: number, field: string, val: string | number) => {
    setCoLineItems((prev) =>
      prev.map((item, idx) => (idx === index ? { ...item, [field]: val } : item))
    );
  };

  const handleCreateChangeOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedWorkOrder || !coReason.trim()) return;
    if (coLineItems.length === 0 || !coLineItems.some(i => i.description.trim())) {
      showToast("Please provide at least one valid line item.");
      return;
    }

    setCoActionLoading(true);
    try {
      await api.workshops.manageWorkOrders.createChangeOrder(selectedWorkOrder.id, {
        reason: coReason.trim(),
        discount_amount: parseFloat(coDiscount) || 0,
        tax_rate_percent: canCollectTax ? (parseFloat(coTaxRate) || 0) : 0,
        workshop_notes: coWorkshopNotes.trim(),
        submit_for_approval: coSubmitNow,
        line_items: coLineItems.filter(i => i.description.trim()).map(i => ({
          item_type: i.item_type,
          description: i.description.trim(),
          part_number: i.part_number?.trim() || undefined,
          quantity: parseFloat(i.quantity) || 1,
          unit_price: parseFloat(i.unit_price) || 0,
          estimated_labour_minutes: i.estimated_labour_minutes,
        })),
      });

      showToast(coSubmitNow ? "Change order submitted for customer approval!" : "Change order draft saved.");
      setNewCoModalOpen(false);
      setCoReason("");
      setCoWorkshopNotes("");
      setCoLineItems([{ item_type: "LABOUR", description: "", quantity: "1", unit_price: "0.00", estimated_labour_minutes: 60 }]);
      await handleRefreshSelectedWorkOrder();
    } catch (err: unknown) {
      console.error(err);
      showToast(getErrorMessage(err, "Failed to create change order"));
    } finally {
      setCoActionLoading(false);
    }
  };

  const handleSubmitChangeOrder = async (coId: string) => {
    if (!selectedWorkOrder) return;
    setCoActionLoading(true);
    try {
      await api.workshops.manageWorkOrders.submitChangeOrder(coId);
      showToast("Change order dispatched to customer for approval!");
      await handleRefreshSelectedWorkOrder();
    } catch (err: unknown) {
      showToast(getErrorMessage(err, "Failed to submit change order"));
    } finally {
      setCoActionLoading(false);
    }
  };

  const handleCancelChangeOrder = async (coId: string) => {
    if (!selectedWorkOrder) return;
    setCoActionLoading(true);
    try {
      await api.workshops.manageWorkOrders.cancelChangeOrder(coId, "Cancelled by workshop");
      showToast("Change order cancelled.");
      await handleRefreshSelectedWorkOrder();
    } catch (err: unknown) {
      showToast(getErrorMessage(err, "Failed to cancel change order"));
    } finally {
      setCoActionLoading(false);
    }
  };

    const handleDeletePartUsage = async (partId: string) => {
    if (!selectedWorkOrder) return;
    if (!confirm("Are you sure you want to remove this part usage record?")) return;
    try {
      await api.workshops.manageWorkOrders.deletePartUsage(selectedWorkOrder.id, partId);
      showToast("Part usage removed.");
      await handleRefreshSelectedWorkOrder();
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to delete part usage"));
    }
  };

  const getWorkOrderStatusBadge = (status: string) => {
    switch (status) {
      case "ASSIGNED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-sky-50 text-sky-700 border border-sky-200">
            <UserCheck className="w-3.5 h-3.5" />
            Assigned
          </span>
        );
      case "IN_PROGRESS":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
            <Wrench className="w-3.5 h-3.5 animate-pulse" />
            In Progress
          </span>
        );
      case "AWAITING_PARTS":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-50 text-amber-700 border border-amber-200">
            <PackageCheck className="w-3.5 h-3.5" />
            Awaiting Parts
          </span>
        );
      case "QUALITY_CHECK":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-purple-50 text-purple-700 border border-purple-200">
            <ShieldCheck className="w-3.5 h-3.5" />
            Quality Check
          </span>
        );
      case "COMPLETED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Completed
          </span>
        );
      case "CANCELLED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-600 border border-slate-200">
            <XCircle className="w-3.5 h-3.5" />
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
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to accept booking"));
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
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to reject booking"));
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
    } catch (err: unknown) {
      console.error("Scheduling capacity error:", err);
      setScheduleError(getErrorMessage(err, "Unable to schedule appointment. Capacity may be exceeded for this timeslot."));
    } finally {
      setScheduleLoading(false);
    }
  };

  // Open Quotation Builder
  const handleOpenQuotation = (booking: WorkshopBooking, existingQuote?: WorkshopQuotation) => {
    setQuoteBooking(booking);
    setQuoteError(null);

    if (existingQuote) {
      // Respect existing quote's tax rate only if workshop is authorised to collect tax
      setQuoteTaxRate(canCollectTax ? parseFloat(String(existingQuote.tax_rate_percent || 0)) : 0.0);
      setQuoteDiscount(parseFloat(String(existingQuote.discount_amount || 0)));
      setQuoteNotes(existingQuote.workshop_notes || "");
      setQuoteTerms(existingQuote.terms_and_conditions || "");
      setQuoteValidUntil(existingQuote.valid_until || "");

      if (existingQuote.line_items && existingQuote.line_items.length > 0) {
        setQuoteLineItems(
          existingQuote.line_items.map((item, idx) => ({
            id: item.id || `item-${idx}`,
            item_type: (item.item_type as "LABOUR" | "PART" | "DIAGNOSTIC" | "FEE" | "DISCOUNT") || "LABOUR",
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
      // For new quotations: fixed 0% if unauthorised; default rate only if platform authorised
      setQuoteTaxRate(
        canCollectTax
          ? (profile?.default_tax_rate_percent ? parseFloat(profile.default_tax_rate_percent) : 20.0)
          : 0.0
      );
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
    if (!canCollectTax) return 0;
    const rate = Number(quoteTaxRate) || 0;
    const taxableBase = Math.max(0, quoteSubtotal - (Number(quoteDiscount) || 0));
    return (taxableBase * rate) / 100;
  }, [canCollectTax, quoteSubtotal, quoteTaxRate, quoteDiscount]);

  const quoteGrandTotal = useMemo(() => {
    const afterDiscount = Math.max(0, quoteSubtotal - (Number(quoteDiscount) || 0));
    return afterDiscount + quoteCalculatedTax;
  }, [quoteSubtotal, quoteDiscount, quoteCalculatedTax]);

  // Submit Quotation (Draft or Issue)
  const handleSaveQuotation = async (andIssue: boolean) => {
    if (!quoteBooking) return;

    // Prevent submission of non-zero tax rate when unauthorized
    if (!canCollectTax && Number(quoteTaxRate) > 0) {
      setQuoteError("Your workshop is not authorised to collect tax. Quotation tax rate must be 0.00%.");
      return;
    }

    setQuoteSaving(true);
    setQuoteError(null);

    try {
      const payload = {
        discount_amount: quoteDiscount.toFixed(2),
        tax_rate_percent: canCollectTax ? quoteTaxRate.toFixed(2) : "0.00",
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
    } catch (err: unknown) {
      console.error("Error saving quotation:", err);
      setQuoteError(getErrorMessage(err, "Failed to save quotation"));
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
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to issue quotation"));
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
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to save service"));
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
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to update service status"));
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
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to save operating hours"));
    } finally {
      setHoursSaving(false);
    }
  };

  // Save Profile Form
  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!profile) {
      alert(profileError || "Cannot save profile: Workshop organisation is not configured.");
      return;
    }
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
    } catch (err: unknown) {
      alert(getErrorMessage(err, "Failed to save profile"));
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

      {profileError && (
        <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-bold text-amber-300">Workshop Organisation Setup Incomplete</p>
            <p className="text-white/80">{profileError}</p>
            <p className="text-white/60">
              Your account has the Workshop role, but is not yet linked to an active workshop organisation. Please ensure your onboarding seller application has been approved by an administrator.
            </p>
          </div>
        </div>
      )}

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
          onClick={() => setActiveTab("work_orders")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition whitespace-nowrap ${
            activeTab === "work_orders"
              ? "bg-purple-600 text-white shadow-sm"
              : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200"
          }`}
        >
          <ClipboardList className="w-4 h-4" />
          <span>Work Orders</span>
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-black ${
            activeTab === "work_orders" ? "bg-purple-700 text-purple-100" : "bg-slate-200 text-slate-700"
          }`}>
            {workOrders.filter((w) => w.status !== "COMPLETED" && w.status !== "CANCELLED").length} active
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

                        {/* If Work Order exists -> Link to Work Order */}
                        {bk.work_order_id && (
                          <button
                            onClick={() => {
                              setActiveTab("work_orders");
                              handleOpenWorkOrder(bk.work_order_id!);
                            }}
                            className="px-4 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-sm"
                          >
                            <ClipboardList className="w-3.5 h-3.5" />
                            <span>View Work Order ({bk.work_order_number || "Active"})</span>
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
      {/* TAB: WORK ORDERS MANAGEMENT */}
      {/* ========================================================================= */}
      {activeTab === "work_orders" && (
        <div className="space-y-4">
          {/* Filter & Search Bar */}
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-2 overflow-x-auto pb-1">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1 mr-2">
                <Filter className="w-3.5 h-3.5" /> Filter:
              </span>
              {[
                { label: "All", value: "ALL" },
                { label: "Assigned", value: "ASSIGNED" },
                { label: "In Progress", value: "IN_PROGRESS" },
                { label: "Awaiting Parts", value: "AWAITING_PARTS" },
                { label: "Quality Check", value: "QUALITY_CHECK" },
                { label: "Completed", value: "COMPLETED" },
                { label: "Cancelled", value: "CANCELLED" },
              ].map((f) => (
                <button
                  key={f.value}
                  onClick={() => setWorkOrderFilter(f.value)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-bold transition whitespace-nowrap ${
                    workOrderFilter === f.value
                      ? "bg-purple-600 text-white shadow-sm"
                      : "bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200"
                  }`}
                >
                  {f.label}
                  <span className="ml-1.5 opacity-70">
                    (
                    {f.value === "ALL"
                      ? workOrders.length
                      : workOrders.filter((w) => w.status === f.value).length}
                    )
                  </span>
                </button>
              ))}
            </div>

            <div className="relative min-w-[240px]">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search work order #, vehicle, plate..."
                value={workOrderSearchQuery}
                onChange={(e) => setWorkOrderSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500 bg-slate-50 focus:bg-white"
              />
            </div>
          </div>

          {/* Work Orders List */}
          {filteredWorkOrders.length === 0 ? (
            <div className="bg-white rounded-3xl p-12 text-center border border-slate-200 shadow-sm space-y-3">
              <div className="w-14 h-14 rounded-2xl bg-purple-50 text-purple-600 flex items-center justify-center mx-auto">
                <ClipboardList className="w-7 h-7" />
              </div>
              <h3 className="text-base font-bold text-slate-900">No Work Orders Found</h3>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                Work orders are automatically generated as soon as a customer accepts an issued quotation.
                Once created, you can assign technicians, track repair tasks, log labour hours, and record spare parts consumption.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {filteredWorkOrders.map((wo) => {
                const hoursLogged = (wo.total_actual_labour_minutes / 60).toFixed(1);
                const estHours = (wo.total_estimated_labour_minutes / 60).toFixed(1);

                return (
                  <div
                    key={wo.id}
                    className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 hover:border-purple-300 transition space-y-4 flex flex-col justify-between"
                  >
                    {/* Header */}
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-black text-slate-900 tracking-tight">
                            {wo.work_order_number}
                          </span>
                          {getWorkOrderStatusBadge(wo.status)}
                        </div>
                        <span className="text-[11px] text-slate-400 block mt-0.5">
                          Created {new Date(wo.created_at).toLocaleDateString()} &bull; Booking: {wo.booking_number}
                        </span>
                      </div>

                      <div className="px-2.5 py-1 rounded-md bg-amber-300 text-slate-950 font-black text-xs font-mono tracking-wider border border-amber-400 shadow-xs">
                        {wo.vehicle_registration_plate || "NO PLATE"}
                      </div>
                    </div>

                    {/* Vehicle & Quotation Details */}
                    <div className="bg-slate-50 rounded-xl p-3 border border-slate-100 text-xs space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-800 flex items-center gap-1.5">
                          <Car className="w-3.5 h-3.5 text-purple-600" />
                          {wo.vehicle_make} {wo.vehicle_model} {wo.vehicle_year ? `(${wo.vehicle_year})` : ""}
                        </span>
                        <span className="text-[11px] text-slate-500 font-mono">
                          Quote: {wo.quotation_number}
                        </span>
                      </div>

                      <div className="flex items-center justify-between pt-1 border-t border-slate-200/60 text-[11px]">
                        <span className="text-slate-500 flex items-center gap-1">
                          <UserCheck className="w-3.5 h-3.5 text-slate-400" />
                          Lead Tech:
                          <strong className={wo.lead_technician_name ? "text-slate-800 font-semibold" : "text-amber-600 font-bold"}>
                            {wo.lead_technician_name || "Unassigned"}
                          </strong>
                        </span>
                        <span className="text-slate-600 font-bold">
                          {wo.task_count} Tasks
                        </span>
                      </div>
                    </div>

                    {/* Labour & Parts Metrics */}
                    <div className="grid grid-cols-2 gap-2 text-[11px]">
                      <div className="bg-purple-50/60 border border-purple-100 rounded-xl p-2.5 flex items-center justify-between">
                        <div>
                          <span className="text-slate-400 block text-[10px] uppercase font-bold">Labour Logged</span>
                          <span className="font-extrabold text-purple-900">{hoursLogged}h</span>
                          <span className="text-slate-400 text-[10px]"> / {estHours}h est</span>
                        </div>
                        <Clock className="w-4 h-4 text-purple-400" />
                      </div>

                      <div className="bg-emerald-50/60 border border-emerald-100 rounded-xl p-2.5 flex items-center justify-between">
                        <div>
                          <span className="text-slate-400 block text-[10px] uppercase font-bold">Parts Cost</span>
                          <span className="font-extrabold text-emerald-900">
                            £{parseFloat(wo.total_parts_cost || "0").toFixed(2)}
                          </span>
                        </div>
                        <PackageCheck className="w-4 h-4 text-emerald-400" />
                      </div>
                    </div>

                    {/* Action Button */}
                    <div className="pt-2 border-t border-slate-100 flex items-center justify-end">
                      <button
                        onClick={() => handleOpenWorkOrder(wo.id)}
                        className="w-full py-2 px-4 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-bold text-xs shadow-sm transition flex items-center justify-center gap-1.5"
                      >
                        <Wrench className="w-3.5 h-3.5" />
                        <span>Manage Work Order & Labour</span>
                        <ChevronRight className="w-3.5 h-3.5 ml-auto" />
                      </button>
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
              Org: {profile?.organisation_name || (profileError ? "Organisation Not Configured" : "Not Linked")}
            </span>
          </div>

          {profileError && (
            <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="font-bold">Workshop Setup Incomplete / Access Restricted</p>
                <p>{profileError}</p>
                <p className="text-amber-700">You must be an active Owner or Admin of an approved workshop organisation to update profile settings.</p>
              </div>
            </div>
          )}

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
                disabled={profileSaving || !canManageSettings || !profile}
                title={!profile ? (profileError || "Workshop organisation setup incomplete") : (!canManageSettings ? "Requires Workshop Owner or Admin permissions" : undefined)}
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
                          updated[idx].item_type = e.target.value as "LABOUR" | "PART" | "DIAGNOSTIC" | "FEE" | "DISCOUNT";
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
              {!canCollectTax && (
                <div className="flex items-center gap-2 p-2.5 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-300 text-xs font-medium">
                  <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
                  <span>Your workshop is not authorised to collect tax. Tax rate is fixed at 0%.</span>
                </div>
              )}

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
                    disabled={!canCollectTax}
                    value={canCollectTax ? quoteTaxRate : 0}
                    onChange={(e) => {
                      if (!canCollectTax) return;
                      setQuoteTaxRate(parseFloat(e.target.value) || 0);
                    }}
                    className={`w-16 px-1.5 py-0.5 rounded bg-slate-800 text-white border border-slate-700 text-xs font-mono ${
                      !canCollectTax ? "opacity-60 cursor-not-allowed bg-slate-800/50" : ""
                    }`}
                    title={!canCollectTax ? "Your workshop is not authorised to collect tax. Tax rate is fixed at 0%." : undefined}
                  />
                  <span>%</span>
                  {!canCollectTax && (
                    <span className="text-[10px] text-amber-400 font-semibold bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">
                      0% (Fixed)
                    </span>
                  )}
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

      {/* ========================================================================= */}
      {/* MODAL 5: WORK ORDER DETAIL & MANAGEMENT */}
      {/* ========================================================================= */}
      {selectedWorkOrder && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-3 md:p-6 overflow-y-auto">
          <div className="bg-white rounded-3xl max-w-5xl w-full max-h-[92vh] flex flex-col shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 overflow-hidden my-auto">
            {/* Top Modal Header */}
            <div className="p-5 border-b border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-50/50">
              <div className="space-y-1">
                <div className="flex items-center gap-2.5">
                  <span className="text-lg font-black text-slate-900 tracking-tight">
                    {selectedWorkOrder.work_order_number}
                  </span>
                  {getWorkOrderStatusBadge(selectedWorkOrder.status)}
                </div>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
                  <span>Booking: <strong className="text-slate-700 font-mono">{selectedWorkOrder.booking_number}</strong></span>
                  <span>Quote Ref: <strong className="text-slate-700 font-mono">{selectedWorkOrder.quotation_number}</strong></span>
                  <span>Base Quote: <strong className="text-slate-700 font-bold">£{parseFloat(selectedWorkOrder.quotation_total || "0").toFixed(2)}</strong></span>
                  {parseFloat(selectedWorkOrder.approved_change_orders_amount || "0") > 0 && (
                    <span className="text-emerald-700 font-bold">Approved Additions: +£{parseFloat(selectedWorkOrder.approved_change_orders_amount || "0").toFixed(2)}</span>
                  )}
                  <span>Authorized Scope Total: <strong className="text-purple-700 font-black">£{parseFloat(selectedWorkOrder.authorized_total_amount || selectedWorkOrder.quotation_total || "0").toFixed(2)}</strong></span>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="px-3 py-1.5 rounded-lg bg-amber-300 text-slate-950 font-black text-sm font-mono tracking-wider border border-amber-400 shadow-xs">
                  {selectedWorkOrder.vehicle_registration_plate || "NO PLATE"}
                </div>
                <button
                  onClick={() => setSelectedWorkOrder(null)}
                  className="p-2 text-slate-400 hover:text-slate-600 rounded-xl hover:bg-slate-100 transition"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Scrollable Content Body */}
            <div className="p-5 overflow-y-auto space-y-6 flex-1 text-xs">
              {/* Vehicle & Customer Info Strip */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-slate-50 rounded-2xl p-4 border border-slate-200/80">
                <div className="space-y-1.5">
                  <span className="text-[10px] font-black uppercase text-slate-400 tracking-wider flex items-center gap-1">
                    <Car className="w-3.5 h-3.5 text-purple-600" /> Vehicle Identification
                  </span>
                  <div className="text-sm font-bold text-slate-900">
                    {selectedWorkOrder.vehicle_make} {selectedWorkOrder.vehicle_model} {selectedWorkOrder.vehicle_year ? `(${selectedWorkOrder.vehicle_year})` : ""}
                  </div>
                  <div className="text-[11px] text-slate-500 font-mono">
                    Plate: {selectedWorkOrder.vehicle_registration_plate}
                  </div>
                </div>

                <div className="space-y-1.5">
                  <span className="text-[10px] font-black uppercase text-slate-400 tracking-wider flex items-center gap-1">
                    <UserCheck className="w-3.5 h-3.5 text-purple-600" /> Customer Information
                  </span>
                  <div className="text-sm font-bold text-slate-900">
                    {selectedWorkOrder.buyer_name}
                  </div>
                  <div className="text-[11px] text-slate-500">
                    Email: {selectedWorkOrder.buyer_email} {selectedWorkOrder.buyer_phone ? `| Tel: ${selectedWorkOrder.buyer_phone}` : ""}
                  </div>
                </div>
              </div>

              {/* Odometer Unit Mismatch Warning */}
              {selectedWorkOrder.odometer_unit_mismatch && (
                <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 flex items-start gap-3 text-amber-900 shadow-xs">
                  <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
                  <div className="space-y-0.5">
                    <span className="font-bold block text-xs">Odometer Unit Mismatch Notice</span>
                    <p className="text-[11px] text-amber-800 leading-relaxed">
                      Vehicle primary cluster is configured in <strong>{selectedWorkOrder.vehicle_odometer_unit || "mi"}</strong>, while this work order recorded telemetry in <strong>{selectedWorkOrder.odometer_unit || "km"}</strong>. Vehicle cluster mileage was preserved to prevent unit corruption.
                    </p>
                  </div>
                </div>
              )}

              {/* Status Progression Bar & Action Buttons */}
              <div className="bg-purple-50/50 rounded-2xl p-4 border border-purple-100 space-y-3">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
                  <div>
                    <span className="text-[11px] font-black uppercase text-purple-900 tracking-wider block">
                      Work Order Lifecycle Transitions
                    </span>
                    <span className="text-[11px] text-slate-500">
                      Current Phase: <strong className="text-purple-700 font-bold">{selectedWorkOrder.status_display || selectedWorkOrder.status}</strong>
                    </span>
                  </div>

                  {/* Contextual Action Buttons */}
                  <div className="flex flex-wrap items-center gap-2">
                    {/* ASSIGNED -> IN_PROGRESS */}
                    {selectedWorkOrder.status === "ASSIGNED" && (
                      <button
                        disabled={workOrderActionLoading}
                        onClick={() => handleExecuteStatusUpdate("IN_PROGRESS")}
                        className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold transition flex items-center gap-1.5 shadow-xs"
                      >
                        <PlayCircle className="w-3.5 h-3.5" />
                        <span>Start Diagnostics & Repair</span>
                      </button>
                    )}

                    {/* IN_PROGRESS -> AWAITING_PARTS or QUALITY_CHECK */}
                    {selectedWorkOrder.status === "IN_PROGRESS" && (
                      <>
                        <button
                          disabled={workOrderActionLoading}
                          onClick={() => handleExecuteStatusUpdate("AWAITING_PARTS")}
                          className="px-3.5 py-2 rounded-xl bg-amber-500 hover:bg-amber-600 text-white font-bold transition flex items-center gap-1.5 shadow-xs"
                        >
                          <PauseCircle className="w-3.5 h-3.5" />
                          <span>Hold: Awaiting Spare Parts</span>
                        </button>
                        <button
                          disabled={workOrderActionLoading}
                          onClick={() => {
                            setStatusModalTarget("QUALITY_CHECK");
                            setStatusModalNotes("");
                          }}
                          className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-bold transition flex items-center gap-1.5 shadow-xs"
                        >
                          <ShieldCheck className="w-3.5 h-3.5" />
                          <span>Submit for Quality Inspection</span>
                        </button>
                      </>
                    )}

                    {/* AWAITING_PARTS -> IN_PROGRESS */}
                    {selectedWorkOrder.status === "AWAITING_PARTS" && (
                      <button
                        disabled={workOrderActionLoading}
                        onClick={() => handleExecuteStatusUpdate("IN_PROGRESS")}
                        className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold transition flex items-center gap-1.5 shadow-xs"
                      >
                        <PlayCircle className="w-3.5 h-3.5" />
                        <span>Parts Received: Resume Work</span>
                      </button>
                    )}

                    {/* QUALITY_CHECK -> COMPLETED or IN_PROGRESS */}
                    {selectedWorkOrder.status === "QUALITY_CHECK" && (
                      <>
                        <button
                          disabled={workOrderActionLoading}
                          onClick={() => {
                            setStatusModalTarget("COMPLETED");
                            setStatusModalQualityNotes("");
                          }}
                          className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold transition flex items-center gap-1.5 shadow-xs"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>Pass Quality Inspection & Complete Job</span>
                        </button>
                        <button
                          disabled={workOrderActionLoading}
                          onClick={() => {
                            setStatusModalTarget("IN_PROGRESS");
                            setStatusModalQualityNotes("");
                          }}
                          className="px-3.5 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white font-bold transition flex items-center gap-1.5 shadow-xs"
                        >
                          <XCircle className="w-3.5 h-3.5" />
                          <span>Fail Inspection: Return for Rework</span>
                        </button>
                      </>
                    )}

                    {/* Cancel Action (if not already completed/cancelled) */}
                    {selectedWorkOrder.status !== "COMPLETED" && selectedWorkOrder.status !== "CANCELLED" && (
                      <button
                        disabled={workOrderActionLoading}
                        onClick={() => {
                          setStatusModalTarget("CANCELLED");
                          setStatusModalCancelReason("");
                        }}
                        className="px-3 py-2 rounded-xl text-rose-700 hover:bg-rose-100 border border-rose-200 font-bold transition"
                      >
                        Cancel Work Order
                      </button>
                    )}
                  </div>
                </div>

                {workOrderModalError && (
                  <div className="p-2.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-[11px] font-medium flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                    <span>{workOrderModalError}</span>
                  </div>
                )}
              </div>

              {/* Lead Technician Assignment Bar */}
              <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-purple-100 text-purple-700 flex items-center justify-center font-black">
                    <UserCheck className="w-5 h-5" />
                  </div>
                  <div>
                    <span className="text-xs font-bold text-slate-900 block">Lead Technician Assignment</span>
                    <span className="text-[11px] text-slate-500">
                      Currently assigned: <strong className="text-slate-800">{selectedWorkOrder.lead_technician_name || "None (Unassigned)"}</strong>
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <select
                    value={selectedLeadTechId}
                    onChange={(e) => setSelectedLeadTechId(e.target.value)}
                    className="px-3 py-1.5 rounded-xl border border-slate-200 bg-slate-50 focus:bg-white text-xs font-medium focus:outline-none focus:ring-2 focus:ring-purple-500"
                  >
                    <option value="">-- Select Workshop Technician --</option>
                    {technicians.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.full_name} ({t.role_display || t.role}) - {t.email}
                      </option>
                    ))}
                  </select>
                  <button
                    disabled={!selectedLeadTechId || assignTechLoading}
                    onClick={handleAssignLeadTechnician}
                    className="px-4 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-bold transition disabled:opacity-50 flex items-center gap-1.5 whitespace-nowrap shadow-xs"
                  >
                    {assignTechLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                    <span>Assign</span>
                  </button>
                </div>
              </div>

              {/* Two Column Split: Checklist & Labour (Left) vs Spare Parts (Right) */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* COLUMN 1: TASKS & LABOUR TIME TRACKING */}
                <div className="bg-slate-50/70 rounded-2xl p-4 border border-slate-200 space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-200">
                    <div className="flex items-center gap-2">
                      <CheckSquare className="w-4 h-4 text-purple-600" />
                      <h4 className="font-extrabold text-slate-900 text-xs">Work Order Tasks & Labour</h4>
                    </div>
                    <span className="text-[11px] font-bold text-slate-500">
                      {selectedWorkOrder.tasks.length} items &bull; {(selectedWorkOrder.total_actual_labour_minutes / 60).toFixed(1)}h logged
                    </span>
                  </div>

                  {/* Task List */}
                  <div className="space-y-2.5 max-h-[320px] overflow-y-auto pr-1">
                    {selectedWorkOrder.tasks.length === 0 ? (
                      <div className="text-center py-6 text-slate-400">No tasks defined yet. Add tasks below.</div>
                    ) : (
                      selectedWorkOrder.tasks.map((task) => {
                        const isDone = task.status === "COMPLETED";
                        const isInProg = task.status === "IN_PROGRESS";

                        return (
                          <div
                            key={task.id}
                            className={`p-3 rounded-xl border transition space-y-2 ${
                              isDone
                                ? "bg-emerald-50/60 border-emerald-200"
                                : isInProg
                                ? "bg-indigo-50/60 border-indigo-200"
                                : "bg-white border-slate-200"
                            }`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex items-start gap-2.5">
                                <button
                                  type="button"
                                  onClick={() => handleToggleTaskStatus(task)}
                                  className={`mt-0.5 w-4 h-4 rounded flex items-center justify-center transition border ${
                                    isDone
                                      ? "bg-emerald-600 border-emerald-600 text-white"
                                      : isInProg
                                      ? "bg-indigo-600 border-indigo-600 text-white"
                                      : "border-slate-300 hover:border-purple-500 bg-white"
                                  }`}
                                  title="Click to toggle status (Pending -> In Progress -> Completed)"
                                >
                                  {isDone && <Check className="w-3 h-3 stroke-[3]" />}
                                  {isInProg && <PlayCircle className="w-3 h-3 text-white" />}
                                </button>
                                <div>
                                  <span className={`font-bold block ${isDone ? "line-through text-slate-400" : "text-slate-800"}`}>
                                    {task.description}
                                  </span>
                                  {task.assigned_technician_name && (
                                    <span className="text-[10px] text-slate-500">
                                      Assigned: {task.assigned_technician_name}
                                    </span>
                                  )}
                                </div>
                              </div>

                              <button
                                type="button"
                                onClick={() => handleDeleteTask(task.id)}
                                className="text-slate-300 hover:text-rose-600 p-1 transition"
                                title="Delete task"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>

                            {/* Labour logger row */}
                            <div className="flex items-center justify-between pt-1 border-t border-slate-100 text-[11px]">
                              <span className="text-slate-500">
                                Labour: <strong>{task.actual_labour_minutes}m</strong> / {task.estimated_labour_minutes}m est
                              </span>
                              <div className="flex items-center gap-1">
                                <button
                                  type="button"
                                  onClick={() => handleUpdateTaskLabour(task, task.actual_labour_minutes + 15)}
                                  className="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-[10px] transition"
                                >
                                  +15m
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleUpdateTaskLabour(task, task.actual_labour_minutes + 30)}
                                  className="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-[10px] transition"
                                >
                                  +30m
                                </button>
                              </div>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>

                  {/* Add Task Form */}
                  <form onSubmit={handleAddNewTask} className="pt-2 border-t border-slate-200 space-y-2">
                    <span className="text-[11px] font-bold text-slate-700 block">Add Task to Work Order</span>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Inspect brake pads and rotors"
                      value={newTaskDesc}
                      onChange={(e) => setNewTaskDesc(e.target.value)}
                      className="w-full px-3 py-1.5 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        min="5"
                        step="5"
                        placeholder="Est Mins"
                        value={newTaskEstMinutes}
                        onChange={(e) => setNewTaskEstMinutes(e.target.value)}
                        className="w-24 px-3 py-1.5 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                        title="Estimated duration in minutes"
                      />
                      <select
                        value={newTaskTechId}
                        onChange={(e) => setNewTaskTechId(e.target.value)}
                        className="flex-1 px-3 py-1.5 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-purple-500 text-xs"
                      >
                        <option value="">Assign Tech (Optional)</option>
                        {technicians.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.full_name}
                          </option>
                        ))}
                      </select>
                      <button
                        type="submit"
                        disabled={newTaskLoading || !newTaskDesc.trim()}
                        className="px-3.5 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-bold transition flex items-center gap-1 disabled:opacity-50 shadow-xs"
                      >
                        {newTaskLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                        <span>Add</span>
                      </button>
                    </div>
                  </form>
                </div>

                {/* COLUMN 2: SPARE PARTS USAGE & COSTING */}
                <div className="bg-slate-50/70 rounded-2xl p-4 border border-slate-200 space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-200">
                    <div className="flex items-center gap-2">
                      <PackageCheck className="w-4 h-4 text-emerald-600" />
                      <h4 className="font-extrabold text-slate-900 text-xs">Spare Parts Consumed on Floor</h4>
                    </div>
                    <span className="text-[11px] font-extrabold text-emerald-700">
                      Total Cost: £{parseFloat(selectedWorkOrder.total_parts_cost || "0").toFixed(2)}
                    </span>
                  </div>

                  {/* Planned Quotation Parts Baseline */}
                  {selectedWorkOrder.planned_parts && selectedWorkOrder.planned_parts.length > 0 && (
                    <div className="bg-purple-50/60 rounded-xl p-2.5 border border-purple-100 space-y-1.5 text-[11px]">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-purple-900 flex items-center gap-1">
                          <FileText className="w-3.5 h-3.5 text-purple-600" />
                          Planned Parts in Quotation ({selectedWorkOrder.planned_parts.length})
                        </span>
                        <span className="text-[10px] text-purple-600">Estimate Reference</span>
                      </div>
                      <div className="space-y-1 max-h-28 overflow-y-auto pr-1">
                        {selectedWorkOrder.planned_parts.map((p) => (
                          <div key={p.id} className="flex items-center justify-between bg-white px-2 py-1 rounded border border-purple-100">
                            <span className="text-slate-800 font-medium truncate max-w-[180px]">{p.description}</span>
                            <div className="flex items-center gap-2">
                              <span className="text-slate-500 font-mono text-[10px]">{p.quantity} qty</span>
                              <button
                                type="button"
                                onClick={() => {
                                  setNewPartName(p.description);
                                  setNewPartNumber(p.part_number || "");
                                  setNewPartQty(String(p.quantity));
                                  setNewPartUnitCost(String(p.unit_price));
                                }}
                                className="text-[10px] px-1.5 py-0.5 rounded bg-purple-100 hover:bg-purple-200 text-purple-800 font-bold"
                              >
                                Log Usage
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Parts List */}
                  <div className="space-y-2.5 max-h-[320px] overflow-y-auto pr-1">
                    {selectedWorkOrder.parts_used.length === 0 ? (
                      <div className="text-center py-6 text-slate-400">No parts recorded yet. Log parts used below.</div>
                    ) : (
                      selectedWorkOrder.parts_used.map((part) => (
                        <div
                          key={part.id}
                          className="p-3 rounded-xl bg-white border border-slate-200 space-y-1.5 text-xs shadow-xs"
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <span className="font-bold text-slate-800 block">{part.part_name}</span>
                              {part.part_number && (
                                <span className="text-[10px] text-slate-400 font-mono">PN: {part.part_number}</span>
                              )}
                            </div>
                            <button
                              type="button"
                              onClick={() => handleDeletePartUsage(part.id)}
                              className="text-slate-300 hover:text-rose-600 p-1 transition"
                              title="Delete part entry"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>

                          <div className="flex items-center justify-between pt-1 border-t border-slate-100 text-[11px]">
                            <span className="text-slate-500">
                              {part.quantity} &times; £{parseFloat(part.unit_cost).toFixed(2)}
                            </span>
                            <span className="font-black text-emerald-700">
                              £{parseFloat(part.total_cost).toFixed(2)}
                            </span>
                          </div>
                        </div>
                      ))
                    )}
                  </div>

                  {/* Record Part Form */}
                  <form onSubmit={handleAddNewPartUsage} className="pt-2 border-t border-slate-200 space-y-2">
                    <span className="text-[11px] font-bold text-slate-700 block">Record Part Consumed</span>
                    <div className="grid grid-cols-2 gap-2">
                      <input
                        type="text"
                        required
                        placeholder="Part name (e.g. Oil Filter)"
                        value={newPartName}
                        onChange={(e) => setNewPartName(e.target.value)}
                        className="col-span-2 px-3 py-1.5 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-purple-500"
                      />
                      <input
                        type="text"
                        placeholder="Part # / SKU"
                        value={newPartNumber}
                        onChange={(e) => setNewPartNumber(e.target.value)}
                        className="px-3 py-1.5 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-purple-500 font-mono"
                      />
                      <div className="grid grid-cols-2 gap-1.5">
                        <input
                          type="number"
                          step="0.01"
                          min="0.01"
                          placeholder="Qty"
                          value={newPartQty}
                          onChange={(e) => setNewPartQty(e.target.value)}
                          className="px-2 py-1.5 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-purple-500 text-center"
                          title="Quantity"
                        />
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          placeholder="£ Unit"
                          value={newPartUnitCost}
                          onChange={(e) => setNewPartUnitCost(e.target.value)}
                          className="px-2 py-1.5 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-purple-500 text-right"
                          title="Unit Cost (£)"
                        />
                      </div>
                    </div>
                    <button
                      type="submit"
                      disabled={newPartLoading || !newPartName.trim()}
                      className="w-full py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold transition flex items-center justify-center gap-1.5 disabled:opacity-50 shadow-xs"
                    >
                      {newPartLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                      <span>Add Part Consumption</span>
                    </button>
                  </form>
                </div>
              </div>

              {/* Change Orders & Additional Repair Authorizations */}
              <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-xs space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-slate-200">
                  <div className="flex items-center gap-2">
                    <FileCheck2 className="w-4 h-4 text-purple-600" />
                    <div>
                      <h4 className="font-extrabold text-slate-900 text-xs">Change Orders & Additional Scope Authorizations</h4>
                      <p className="text-[11px] text-slate-500">
                        Formal requests for additional labour or spare parts identified during diagnosis. Requires explicit customer approval.
                      </p>
                    </div>
                  </div>
                  {selectedWorkOrder.status !== "COMPLETED" && selectedWorkOrder.status !== "CANCELLED" && (
                    <button
                      type="button"
                      onClick={() => setNewCoModalOpen(true)}
                      className="px-3 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-bold text-xs transition flex items-center gap-1.5 shadow-xs"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>Raise Change Order</span>
                    </button>
                  )}
                </div>

                {loadingChangeOrders ? (
                  <div className="text-center py-6 text-slate-400 text-xs flex items-center justify-center gap-2">
                    <RefreshCw className="w-4 h-4 animate-spin text-purple-600" />
                    <span>Loading change orders...</span>
                  </div>
                ) : changeOrders.length === 0 ? (
                  <div className="text-center py-6 text-slate-400 text-xs">
                    No change orders raised. If additional faults or parts are discovered, raise a change order for customer approval before starting work.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {changeOrders.map((co) => (
                      <div
                        key={co.id}
                        className={`p-3.5 rounded-xl border text-xs space-y-2.5 transition ${
                          co.status === "SUBMITTED"
                            ? "bg-amber-50/50 border-amber-200"
                            : co.status === "APPROVED"
                            ? "bg-emerald-50/40 border-emerald-200"
                            : co.status === "REJECTED"
                            ? "bg-rose-50/40 border-rose-200"
                            : "bg-slate-50 border-slate-200"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-mono font-black text-slate-900">{co.change_order_number}</span>
                              <span className="text-[10px] text-slate-500 font-bold">(Rev {co.version})</span>
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                                  co.status === "SUBMITTED"
                                    ? "bg-amber-200/70 text-amber-900 border border-amber-300"
                                    : co.status === "APPROVED"
                                    ? "bg-emerald-200/70 text-emerald-900 border border-emerald-300"
                                    : co.status === "REJECTED"
                                    ? "bg-rose-200/70 text-rose-900 border border-rose-300"
                                    : "bg-slate-200 text-slate-700 border border-slate-300"
                                }`}
                              >
                                {co.status === "SUBMITTED" ? "Awaiting Customer Approval" : co.status}
                              </span>
                            </div>
                            <p className="mt-1 text-slate-800 font-medium">
                              <span className="font-bold text-slate-900">Reason: </span>
                              {co.reason}
                            </p>
                          </div>
                          <div className="text-right shrink-0">
                            <span className="text-[10px] text-slate-500 block">Additional Cost</span>
                            <span className="font-black text-sm text-purple-700">
                              +£{parseFloat(co.additional_amount).toFixed(2)}
                            </span>
                            <span className="text-[10px] text-slate-400 block font-mono">
                              Revised: £{parseFloat(co.revised_authorized_total).toFixed(2)}
                            </span>
                          </div>
                        </div>

                        {/* Line Items Table */}
                        <div className="overflow-x-auto bg-white rounded-lg border border-slate-200">
                          <table className="w-full text-left text-[11px]">
                            <thead>
                              <tr className="bg-slate-50 text-slate-600 border-b border-slate-200">
                                <th className="px-2.5 py-1.5">Type</th>
                                <th className="px-2.5 py-1.5">Description</th>
                                <th className="px-2.5 py-1.5 text-center">Qty</th>
                                <th className="px-2.5 py-1.5 text-right">Unit</th>
                                <th className="px-2.5 py-1.5 text-right">Total</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {co.line_items.map((item) => (
                                <tr key={item.id} className="text-slate-800">
                                  <td className="px-2.5 py-1">
                                    <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-slate-100 text-slate-700">
                                      {item.item_type}
                                    </span>
                                  </td>
                                  <td className="px-2.5 py-1">
                                    <span className="font-medium">{item.description}</span>
                                    {item.part_number && (
                                      <span className="text-[10px] text-slate-400 font-mono block">PN: {item.part_number}</span>
                                    )}
                                  </td>
                                  <td className="px-2.5 py-1 text-center font-mono">{item.quantity}</td>
                                  <td className="px-2.5 py-1 text-right font-mono">£{parseFloat(item.unit_price).toFixed(2)}</td>
                                  <td className="px-2.5 py-1 text-right font-bold text-slate-900 font-mono">
                                    £{parseFloat(item.line_total).toFixed(2)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>

                        {/* Customer Decision / Status Audit */}
                        {co.status === "APPROVED" && (
                          <div className="flex items-center gap-2 text-[11px] text-emerald-800 bg-emerald-100/70 p-2 rounded-lg">
                            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                            <span>
                              Customer approved on {co.reviewed_at?.split("T")[0]}. Tasks spawned into work order list.
                              {co.buyer_notes && <em className="block text-emerald-900 mt-0.5">Note: &quot;{co.buyer_notes}&quot;</em>}
                            </span>
                          </div>
                        )}

                        {co.status === "REJECTED" && (
                          <div className="flex items-center gap-2 text-[11px] text-rose-800 bg-rose-100/70 p-2 rounded-lg">
                            <XCircle className="w-4 h-4 text-rose-600 shrink-0" />
                            <span>
                              Customer declined on {co.reviewed_at?.split("T")[0]}.
                              {co.buyer_notes && <em className="block text-rose-900 mt-0.5">Reason: &quot;{co.buyer_notes}&quot;</em>}
                            </span>
                          </div>
                        )}

                        {/* Actions for Draft and Submitted */}
                        <div className="flex items-center justify-end gap-2 pt-1 border-t border-slate-200">
                          {co.status === "DRAFT" && (
                            <button
                              type="button"
                              onClick={() => handleSubmitChangeOrder(co.id)}
                              disabled={coActionLoading}
                              className="px-3 py-1 rounded-lg bg-purple-600 hover:bg-purple-700 text-white font-bold text-[11px] transition shadow-xs flex items-center gap-1"
                            >
                              <Send className="w-3 h-3" />
                              <span>Submit to Customer</span>
                            </button>
                          )}
                          {(co.status === "DRAFT" || co.status === "SUBMITTED") && (
                            <button
                              type="button"
                              onClick={() => handleCancelChangeOrder(co.id)}
                              disabled={coActionLoading}
                              className="px-3 py-1 rounded-lg bg-slate-200 hover:bg-slate-300 text-slate-700 font-bold text-[11px] transition"
                            >
                              Cancel Request
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

                            {/* Notes & Quality Sign-Off Audit */}
              {(selectedWorkOrder.internal_notes || selectedWorkOrder.quality_notes || selectedWorkOrder.cancellation_reason) && (
                <div className="bg-slate-50 rounded-2xl p-4 border border-slate-200 space-y-2 text-xs">
                  <span className="text-[10px] font-black uppercase text-slate-400 tracking-wider block">
                    Notes & Quality Audit Trail
                  </span>
                  {selectedWorkOrder.quality_notes && (
                    <div className="p-2.5 rounded-xl bg-purple-50/80 border border-purple-200 text-purple-950">
                      <strong className="block font-bold text-[11px] text-purple-900">Quality Inspection Sign-Off:</strong>
                      <span>{selectedWorkOrder.quality_notes}</span>
                    </div>
                  )}
                  {selectedWorkOrder.internal_notes && (
                    <div className="p-2.5 rounded-xl bg-white border border-slate-200 text-slate-700">
                      <strong className="block font-bold text-[11px] text-slate-800">Internal Workshop Notes:</strong>
                      <span>{selectedWorkOrder.internal_notes}</span>
                    </div>
                  )}
                  {selectedWorkOrder.cancellation_reason && (
                    <div className="p-2.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800">
                      <strong className="block font-bold text-[11px] text-rose-900">Cancellation Reason:</strong>
                      <span>{selectedWorkOrder.cancellation_reason}</span>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Bottom Modal Actions */}
            <div className="p-4 border-t border-slate-200 bg-slate-50/50 flex items-center justify-between">
              <span className="text-[11px] text-slate-400 font-mono">
                Work Order ID: {selectedWorkOrder.id}
              </span>
              <button
                type="button"
                onClick={() => setSelectedWorkOrder(null)}
                className="px-5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs transition"
              >
                Close Work Order
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 6: WORK ORDER STATUS TRANSITION CONFIRMATION / NOTES */}
      {/* ========================================================================= */}
      {statusModalTarget && selectedWorkOrder && (
        <div className="fixed inset-0 z-60 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl border border-slate-200 space-y-4 animate-in fade-in zoom-in-95 text-xs">
            <div className="flex items-start justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-base font-black text-slate-900">
                  {statusModalTarget === "COMPLETED"
                    ? "Pass Quality Check & Complete"
                    : statusModalTarget === "QUALITY_CHECK"
                    ? "Submit for Quality Inspection"
                    : statusModalTarget === "IN_PROGRESS"
                    ? "Inspection Feedback & Return"
                    : "Cancel Work Order"}
                </h3>
                <span className="text-slate-500">
                  {statusModalTarget === "COMPLETED"
                    ? "Sign off inspection checklist before finishing work order"
                    : statusModalTarget === "CANCELLED"
                    ? "Provide mandatory cancellation reason"
                    : "Add notes for workshop audit logging"}
                </span>
              </div>
              <button
                onClick={() => setStatusModalTarget(null)}
                className="p-1 text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3">
              {statusModalTarget === "COMPLETED" && (
                <div className="space-y-1">
                  <label className="block font-bold text-slate-700">
                    Quality Inspection Sign-off Notes
                  </label>
                  <textarea
                    rows={3}
                    placeholder="e.g. Road tested, all safety checklist items verified and torque specs verified."
                    value={statusModalQualityNotes}
                    onChange={(e) => setStatusModalQualityNotes(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
              )}

              {statusModalTarget === "QUALITY_CHECK" && (
                <div className="space-y-1">
                  <label className="block font-bold text-slate-700">
                    Quality Inspection Request Notes
                  </label>
                  <textarea
                    rows={3}
                    placeholder="e.g. All labour items completed. Ready for lead tech road test and sign-off."
                    value={statusModalNotes}
                    onChange={(e) => setStatusModalNotes(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
              )}

              {statusModalTarget === "IN_PROGRESS" && (
                <div className="space-y-1">
                  <label className="block font-bold text-slate-700">
                    Inspection Feedback & Rework Required
                  </label>
                  <textarea
                    rows={3}
                    placeholder="e.g. Retorque suspension bolts and recheck steering alignment."
                    value={statusModalQualityNotes}
                    onChange={(e) => setStatusModalQualityNotes(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
              )}

              {statusModalTarget === "CANCELLED" && (
                <div className="space-y-1">
                  <label className="block font-bold text-slate-700">
                    Cancellation Reason (Required)
                  </label>
                  <textarea
                    rows={3}
                    required
                    placeholder="e.g. Customer requested cancellation due to vehicle transfer."
                    value={statusModalCancelReason}
                    onChange={(e) => setStatusModalCancelReason(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-rose-500"
                  />
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setStatusModalTarget(null)}
                className="px-4 py-2 rounded-xl text-slate-600 hover:bg-slate-100 font-bold"
              >
                Back
              </button>
              <button
                type="button"
                disabled={workOrderActionLoading || (statusModalTarget === "CANCELLED" && !statusModalCancelReason.trim())}
                onClick={() => handleExecuteStatusUpdate(statusModalTarget)}
                className={`px-5 py-2 rounded-xl text-white font-bold transition flex items-center gap-1.5 shadow-sm disabled:opacity-50 ${
                  statusModalTarget === "COMPLETED"
                    ? "bg-emerald-600 hover:bg-emerald-700"
                    : statusModalTarget === "CANCELLED"
                    ? "bg-rose-600 hover:bg-rose-700"
                    : "bg-purple-600 hover:bg-purple-700"
                }`}
              >
                {workOrderActionLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                <span>Confirm Transition</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 7: RAISE CHANGE ORDER (ADDITIONAL REPAIR WORK) */}
      {/* ========================================================================= */}
      {newCoModalOpen && selectedWorkOrder && (
        <div className="fixed inset-0 z-60 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 shadow-2xl border border-slate-200 space-y-4 animate-in fade-in zoom-in-95 text-xs my-8 max-h-[90vh] flex flex-col">
            <div className="flex items-start justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-base font-black text-slate-900">
                  Raise Change Order — Additional Repair Authorization
                </h3>
                <span className="text-slate-500">
                  Request customer approval for additional parts or labour identified during repair of {selectedWorkOrder.work_order_number}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setNewCoModalOpen(false)}
                className="p-1 text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateChangeOrder} className="space-y-4 overflow-y-auto flex-1 pr-1">
              <div className="space-y-1">
                <label className="block font-bold text-slate-700">Diagnosis / Reason for Additional Work *</label>
                <textarea
                  rows={2}
                  required
                  placeholder="e.g., During brake disc inspection, front calliper slide pins found seized requiring replacement."
                  value={coReason}
                  onChange={(e) => setCoReason(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              {/* Line items */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-700 uppercase tracking-wider text-[11px]">
                    Additional Line Items
                  </span>
                  <button
                    type="button"
                    onClick={handleAddCoLineItem}
                    className="text-purple-600 hover:text-purple-800 font-bold flex items-center gap-1 text-[11px]"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Add Item</span>
                  </button>
                </div>

                <div className="space-y-2">
                  {coLineItems.map((item, idx) => (
                    <div key={idx} className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
                      <div className="grid grid-cols-12 gap-2">
                        <div className="col-span-3">
                          <label className="block text-[10px] text-slate-500 font-bold">Type</label>
                          <select
                            value={item.item_type}
                            onChange={(e) => handleUpdateCoLineItem(idx, "item_type", e.target.value)}
                            className="w-full px-2 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-bold"
                          >
                            <option value="PART">Part</option>
                            <option value="LABOUR">Labour</option>
                            <option value="DIAGNOSTIC">Diagnostic</option>
                            <option value="DISPOSAL">Disposal</option>
                            <option value="OTHER">Other</option>
                          </select>
                        </div>
                        <div className="col-span-9">
                          <label className="block text-[10px] text-slate-500 font-bold">Description *</label>
                          <input
                            type="text"
                            required
                            placeholder="e.g. Front Calliper Guide Pin Set"
                            value={item.description}
                            onChange={(e) => handleUpdateCoLineItem(idx, "description", e.target.value)}
                            className="w-full px-2 py-1.5 rounded-lg border border-slate-200 bg-white text-xs"
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-12 gap-2 items-center">
                        <div className="col-span-4">
                          <label className="block text-[10px] text-slate-500 font-bold">Part Number (Opt)</label>
                          <input
                            type="text"
                            placeholder="e.g. OEM-11234"
                            value={item.part_number || ""}
                            onChange={(e) => handleUpdateCoLineItem(idx, "part_number", e.target.value)}
                            className="w-full px-2 py-1.5 rounded-lg border border-slate-200 bg-white text-xs"
                          />
                        </div>
                        <div className="col-span-3">
                          <label className="block text-[10px] text-slate-500 font-bold">Qty</label>
                          <input
                            type="number"
                            min="0.1"
                            step="any"
                            value={item.quantity}
                            onChange={(e) => handleUpdateCoLineItem(idx, "quantity", e.target.value)}
                            className="w-full px-2 py-1.5 rounded-lg border border-slate-200 bg-white text-xs"
                          />
                        </div>
                        <div className="col-span-3">
                          <label className="block text-[10px] text-slate-500 font-bold">Unit Price</label>
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={item.unit_price}
                            onChange={(e) => handleUpdateCoLineItem(idx, "unit_price", e.target.value)}
                            className="w-full px-2 py-1.5 rounded-lg border border-slate-200 bg-white text-xs"
                          />
                        </div>
                        <div className="col-span-2 flex justify-end pt-3">
                          {coLineItems.length > 1 && (
                            <button
                              type="button"
                              onClick={() => handleRemoveCoLineItem(idx)}
                              className="p-1.5 text-rose-500 hover:text-rose-700 hover:bg-rose-50 rounded-lg"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Discount, Tax, and Workshop Notes */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="block font-bold text-slate-700">Discount Amount</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={coDiscount}
                    onChange={(e) => setCoDiscount(e.target.value)}
                    className="w-full px-3 py-1.5 rounded-xl border border-slate-200 text-xs"
                  />
                </div>
                {canCollectTax && (
                  <div className="space-y-1">
                    <label className="block font-bold text-slate-700">Tax Rate %</label>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={coTaxRate}
                      onChange={(e) => setCoTaxRate(e.target.value)}
                      className="w-full px-3 py-1.5 rounded-xl border border-slate-200 text-xs"
                    />
                  </div>
                )}
              </div>

              <div className="space-y-1">
                <label className="block font-bold text-slate-700">Internal Workshop Notes (Optional)</label>
                <textarea
                  rows={2}
                  placeholder="Notes for technicians..."
                  value={coWorkshopNotes}
                  onChange={(e) => setCoWorkshopNotes(e.target.value)}
                  className="w-full px-3 py-1.5 rounded-xl border border-slate-200 text-xs"
                />
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="coSubmitNowCheckbox"
                  checked={coSubmitNow}
                  onChange={(e) => setCoSubmitNow(e.target.checked)}
                  className="rounded border-slate-300 text-purple-600 focus:ring-purple-500"
                />
                <label htmlFor="coSubmitNowCheckbox" className="text-xs text-slate-700 font-medium">
                  Submit immediately for customer approval (otherwise saves as draft)
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setNewCoModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-slate-600 hover:bg-slate-100 font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={coActionLoading}
                  className="px-5 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-bold transition flex items-center gap-1.5 shadow-sm"
                >
                  {coActionLoading && <RefreshCw className="w-4 h-4 animate-spin" />}
                  <span>{coSubmitNow ? "Submit to Customer" : "Save Draft"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Work Order Loading Indicator */}
      {workOrderDetailLoading && (
        <div className="fixed inset-0 z-60 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl p-
          4 shadow-xl flex items-center gap-3">
            <RefreshCw className="w-5 h-5 animate-spin text-purple-600" />
            <span className="text-xs font-bold text-slate-800">Loading work order details...</span>
          </div>
        </div>
      )}

    </div>
  );
}
