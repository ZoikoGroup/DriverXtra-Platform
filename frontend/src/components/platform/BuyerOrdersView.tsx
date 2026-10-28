"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  api,
  PlatformOrder,
  PlatformOrderItem,
  PlatformShipment,
  PlatformTrackingEvent,
  PlatformReturnRequest,
  PlatformRefund,
  PlatformDispute,
  PlatformDisputeEvent,
  OrderReturnEligibilityResponse,
  ReturnReason,
  ReturnRequestType,
  DisputeCategory,
  DisputePriority,
  resolveMediaUrl,
} from "@/lib/api/client";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  Package,
  Clock,
  CheckCircle2,
  XCircle,
  Truck,
  RotateCcw,
  ShoppingBag,
  Building2,
  User,
  AlertTriangle,
  Mail,
  Phone,
  Copy,
  Check,
  Calendar,
  Search,
  ChevronRight,
  MapPin,
  Receipt,
  FileText,
  AlertCircle,
  X,
  Loader2,
  ShieldAlert,
  CreditCard,
  Banknote,
  ExternalLink,
  Navigation,
  Scale,
  MessageSquare,
  UploadCloud,
  Send,
  HelpCircle,
} from "lucide-react";

interface BuyerOrdersViewProps {
  onNavigateToBrowse?: () => void;
  initialOrderId?: string;
}

type OrderStatusFilter =
  | "ALL"
  | "PENDING_CONFIRMATION"
  | "CONFIRMED"
  | "PROCESSING"
  | "COMPLETED"
  | "CANCELLED";

export default function BuyerOrdersView({
  onNavigateToBrowse,
  initialOrderId,
}: BuyerOrdersViewProps) {
  const { user } = useAuth();

  // Navigation: Orders / Returns / Disputes
  const [activeSection, setActiveSection] = useState<"orders" | "returns" | "disputes">("orders");

  // Orders State
  const [orders, setOrders] = useState<PlatformOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<OrderStatusFilter>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedOrder, setSelectedOrder] = useState<PlatformOrder | null>(null);

  // Cancellation state (pre-confirmation direct cancel)
  const [cancelModalOrder, setCancelModalOrder] = useState<PlatformOrder | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  // Copy feedback
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Phase 5 Task 3: Returns & Cancellations State
  const [buyerReturns, setBuyerReturns] = useState<PlatformReturnRequest[]>([]);
  const [loadingReturns, setLoadingReturns] = useState(false);
  const [returnStatusFilter, setReturnStatusFilter] = useState<string>("ALL");

  const [returnModalOrder, setReturnModalOrder] = useState<PlatformOrder | null>(null);
  const [returnEligibility, setReturnEligibility] = useState<OrderReturnEligibilityResponse | null>(null);
  const [checkingEligibility, setCheckingEligibility] = useState(false);
  const [selectedItemForReturn, setSelectedItemForReturn] = useState<string>("ORDER");
  const [returnRequestType, setReturnRequestType] = useState<ReturnRequestType>("RETURN");
  const [returnReason, setReturnReason] = useState<ReturnReason>("DEFECTIVE_ITEM");
  const [returnQuantity, setReturnQuantity] = useState(1);
  const [returnDescription, setReturnDescription] = useState("");
  const [returnEvidenceUrls, setReturnEvidenceUrls] = useState<string[]>([]);
  const [isUploadingReturnImage, setIsUploadingReturnImage] = useState(false);
  const [isSubmittingReturn, setIsSubmittingReturn] = useState(false);
  const [returnModalError, setReturnModalError] = useState<string | null>(null);

  // Phase 5 Task 3: Disputes State
  const [buyerDisputes, setBuyerDisputes] = useState<PlatformDispute[]>([]);
  const [loadingDisputes, setLoadingDisputes] = useState(false);

  const [disputeModalOrder, setDisputeModalOrder] = useState<PlatformOrder | null>(null);
  const [disputeCategory, setDisputeCategory] = useState<DisputeCategory>("ITEM_NOT_RECEIVED");
  const [disputePriority, setDisputePriority] = useState<DisputePriority>("MEDIUM");
  const [disputeDescription, setDisputeDescription] = useState("");
  const [disputeEvidenceUrls, setDisputeEvidenceUrls] = useState<string[]>([]);
  const [isUploadingDisputeImage, setIsUploadingDisputeImage] = useState(false);
  const [isSubmittingDispute, setIsSubmittingDispute] = useState(false);
  const [disputeModalError, setDisputeModalError] = useState<string | null>(null);

  // Active Dispute Thread Drawer
  const [activeDisputeThread, setActiveDisputeThread] = useState<PlatformDispute | null>(null);
  const [disputeReplyMessage, setDisputeReplyMessage] = useState("");
  const [isSendingDisputeReply, setIsSendingDisputeReply] = useState(false);
  const [disputeReplyError, setDisputeReplyError] = useState<string | null>(null);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Load orders
  const loadOrders = useCallback(async () => {
    if (!user) {
      setOrders([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await api.marketplace.listOrders();
      setOrders(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      console.error("Failed to load buyer orders", err);
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to load orders. Please check your network connection.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [user]);

  // Load returns
  const loadBuyerReturns = useCallback(async () => {
    if (!user) return;
    setLoadingReturns(true);
    try {
      const res = await api.marketplace.listBuyerReturns(
        undefined,
        returnStatusFilter !== "ALL" ? returnStatusFilter : undefined
      );
      setBuyerReturns(Array.isArray(res) ? res : []);
    } catch (err) {
      console.error("Failed to load returns", err);
    } finally {
      setLoadingReturns(false);
    }
  }, [user, returnStatusFilter]);

  // Load disputes
  const loadBuyerDisputes = useCallback(async () => {
    if (!user) return;
    setLoadingDisputes(true);
    try {
      const res = await api.marketplace.listBuyerDisputes();
      setBuyerDisputes(Array.isArray(res) ? res : []);
    } catch (err) {
      console.error("Failed to load disputes", err);
    } finally {
      setLoadingDisputes(false);
    }
  }, [user]);

  useEffect(() => {
    let ignore = false;
    Promise.resolve().then(() => {
      if (!ignore) {
        loadOrders();
        loadBuyerReturns();
        loadBuyerDisputes();
      }
    });
    return () => {
      ignore = true;
    };
  }, [loadOrders, loadBuyerReturns, loadBuyerDisputes]);

  // Initial order navigation
  useEffect(() => {
    if (initialOrderId && orders.length > 0) {
      const found = orders.find(
        (o) => o.id === initialOrderId || o.order_number === initialOrderId
      );
      if (found) {
        setSelectedOrder(found);
      }
    }
  }, [initialOrderId, orders]);

  // Direct cancel order (before confirmation)
  const handleCancelOrder = async () => {
    if (!cancelModalOrder) return;
    setIsCancelling(true);
    setCancelError(null);
    try {
      const res = await api.marketplace.cancelBuyerOrder(cancelModalOrder.id);
      if (res.status === "success" && res.order) {
        setOrders((prev) =>
          prev.map((o) => (o.id === res.order.id ? res.order : o))
        );
        if (selectedOrder?.id === res.order.id) {
          setSelectedOrder(res.order);
        }
        setSuccessBanner(
          `Order ${res.order.order_number} has been cancelled successfully and stock has been restocked.`
        );
        setCancelModalOrder(null);
      } else {
        throw new Error(res.message || "Failed to cancel order.");
      }
    } catch (err: unknown) {
      setCancelError(err instanceof Error ? err.message : "Failed to cancel order.");
    } finally {
      setIsCancelling(false);
    }
  };

  // Check eligibility and open return modal
  const handleOpenReturnModal = async (order: PlatformOrder) => {
    setReturnModalOrder(order);
    setReturnModalError(null);
    setCheckingEligibility(true);
    setSelectedItemForReturn("ORDER");
    setReturnDescription("");
    setReturnEvidenceUrls([]);
    try {
      const eligibility = await api.marketplace.getReturnEligibility(order.order_number);
      setReturnEligibility(eligibility);
      // Default request type based on eligibility
      if (eligibility.order_cancellation.eligible) {
        setReturnRequestType("CANCELLATION");
        setReturnReason("BUYER_CANCEL");
      } else {
        setReturnRequestType("RETURN");
        setReturnReason("DEFECTIVE_ITEM");
      }
    } catch (err: unknown) {
      setReturnModalError(err instanceof Error ? err.message : "Unable to evaluate return eligibility.");
    } finally {
      setCheckingEligibility(false);
    }
  };

  // Upload evidence image for return
  const handleUploadReturnImage = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const files = Array.from(e.target.files);
    setIsUploadingReturnImage(true);
    setReturnModalError(null);
    try {
      const res = await api.marketplace.uploadMultipleImages(files, { listingType: "part" });
      if (res.images && res.images.length > 0) {
        const urls = res.images.map((img) => img.relative_url || img.url);
        setReturnEvidenceUrls((prev) => [...prev, ...urls]);
      }
    } catch (err: unknown) {
      setReturnModalError(err instanceof Error ? err.message : "Failed to upload evidence.");
    } finally {
      setIsUploadingReturnImage(false);
    }
  };

  // Submit return or cancellation request
  const handleSubmitReturnRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!returnModalOrder) return;
    setIsSubmittingReturn(true);
    setReturnModalError(null);

    const isItemLevel = selectedItemForReturn !== "ORDER";
    const itemId = isItemLevel ? selectedItemForReturn : undefined;

    try {
      const res = await api.marketplace.createReturnRequest(returnModalOrder.order_number, {
        order_item_id: itemId,
        request_type: returnRequestType,
        reason: returnReason,
        requested_quantity: returnQuantity,
        description: returnDescription.trim(),
        evidence_urls: returnEvidenceUrls,
      });

      if (res.status === "success" && res.return_request) {
        setSuccessBanner(
          `${res.return_request.request_type_display || res.return_request.request_type} request ${res.return_request.request_number} submitted successfully.`
        );
        setReturnModalOrder(null);
        loadBuyerReturns();
        loadOrders();
      }
    } catch (err: unknown) {
      setReturnModalError(err instanceof Error ? err.message : "Failed to submit return request.");
    } finally {
      setIsSubmittingReturn(false);
    }
  };

  // Withdraw pending return request
  const handleWithdrawReturnRequest = async (requestNumber: string) => {
    if (!confirm(`Are you sure you want to withdraw return request ${requestNumber}?`)) return;
    try {
      const res = await api.marketplace.cancelBuyerReturn(requestNumber);
      if (res.status === "success") {
        setSuccessBanner(`Return request ${requestNumber} has been withdrawn.`);
        loadBuyerReturns();
        loadOrders();
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to withdraw return request.");
    }
  };

  // Open dispute modal
  const handleOpenDisputeModal = (order: PlatformOrder) => {
    setDisputeModalOrder(order);
    setDisputeCategory("ITEM_NOT_RECEIVED");
    setDisputePriority("MEDIUM");
    setDisputeDescription("");
    setDisputeEvidenceUrls([]);
    setDisputeModalError(null);
  };

  // Upload evidence image for dispute
  const handleUploadDisputeImage = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const files = Array.from(e.target.files);
    setIsUploadingDisputeImage(true);
    setDisputeModalError(null);
    try {
      const res = await api.marketplace.uploadMultipleImages(files, { listingType: "part" });
      if (res.images && res.images.length > 0) {
        const urls = res.images.map((img) => img.relative_url || img.url);
        setDisputeEvidenceUrls((prev) => [...prev, ...urls]);
      }
    } catch (err: unknown) {
      setDisputeModalError(err instanceof Error ? err.message : "Failed to upload evidence.");
    } finally {
      setIsUploadingDisputeImage(false);
    }
  };

  // Submit dispute
  const handleSubmitDispute = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!disputeModalOrder) return;
    setIsSubmittingDispute(true);
    setDisputeModalError(null);
    try {
      const res = await api.marketplace.createDispute(disputeModalOrder.order_number, {
        category: disputeCategory,
        priority: disputePriority,
        description: disputeDescription.trim(),
        evidence_urls: disputeEvidenceUrls,
      });

      if (res.status === "success" && res.dispute) {
        setSuccessBanner(`Dispute ${res.dispute.dispute_number} created successfully.`);
        setDisputeModalOrder(null);
        loadBuyerDisputes();
        loadOrders();
      }
    } catch (err: unknown) {
      setDisputeModalError(err instanceof Error ? err.message : "Failed to create dispute.");
    } finally {
      setIsSubmittingDispute(false);
    }
  };

  // Send message in active dispute thread
  const handleSendDisputeReply = async () => {
    if (!activeDisputeThread || !disputeReplyMessage.trim()) return;
    setIsSendingDisputeReply(true);
    setDisputeReplyError(null);
    try {
      const res = await api.marketplace.addDisputeMessage(activeDisputeThread.dispute_number, {
        message: disputeReplyMessage.trim(),
      });
      if (res.status === "success") {
        const updated = await api.marketplace.getDispute(activeDisputeThread.dispute_number);
        setActiveDisputeThread(updated);
        setBuyerDisputes((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
        setDisputeReplyMessage("");
      }
    } catch (err: unknown) {
      setDisputeReplyError(err instanceof Error ? err.message : "Failed to send message.");
    } finally {
      setIsSendingDisputeReply(false);
    }
  };

  // Status Metrics
  const counts = useMemo(() => {
    return {
      all: orders.length,
      pending: orders.filter((o) => o.status === "PENDING_CONFIRMATION").length,
      confirmed: orders.filter((o) => o.status === "CONFIRMED").length,
      processing: orders.filter((o) => o.status === "PROCESSING").length,
      completed: orders.filter((o) => o.status === "COMPLETED").length,
      cancelled: orders.filter((o) => o.status === "CANCELLED").length,
      returns: buyerReturns.length,
      disputes: buyerDisputes.length,
    };
  }, [orders, buyerReturns, buyerDisputes]);

  // Filtered orders
  const filteredOrders = useMemo(() => {
    return orders.filter((order) => {
      const matchesStatus =
        statusFilter === "ALL" || order.status === statusFilter;
      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        order.order_number.toLowerCase().includes(q) ||
        order.shipping_name.toLowerCase().includes(q) ||
        order.shipping_city.toLowerCase().includes(q) ||
        order.items.some(
          (item) =>
            item.title.toLowerCase().includes(q) ||
            item.brand.toLowerCase().includes(q) ||
            (item.mpn && item.mpn.toLowerCase().includes(q))
        );
      return matchesStatus && matchesSearch;
    });
  }, [orders, statusFilter, searchQuery]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "PENDING_CONFIRMATION":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
            <Clock className="w-3 h-3 text-amber-600" />
            Pending Confirmation
          </span>
        );
      case "CONFIRMED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-blue-100 text-blue-800 border border-blue-300">
            <CheckCircle2 className="w-3 h-3 text-blue-600" />
            Confirmed
          </span>
        );
      case "PROCESSING":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-indigo-100 text-indigo-800 border border-indigo-300">
            <Truck className="w-3 h-3 text-indigo-600" />
            Processing & Dispatching
          </span>
        );
      case "COMPLETED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
            Completed
          </span>
        );
      case "CANCELLED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-rose-100 text-rose-800 border border-rose-300">
            <XCircle className="w-3 h-3 text-rose-600" />
            Cancelled
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-slate-100 text-slate-800 border border-slate-300">
            {status}
          </span>
        );
    }
  };

  const getReturnStatusBadge = (status: string) => {
    switch (status) {
      case "PENDING":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">Pending Review</span>;
      case "APPROVED":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 border border-blue-300">Approved</span>;
      case "COMPLETED":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">Completed & Restocked</span>;
      case "REJECTED":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-300">Rejected</span>;
      case "CANCELLED":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-300">Withdrawn</span>;
      default:
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-800">{status}</span>;
    }
  };

  const getDisputeStatusBadge = (status: string) => {
    switch (status) {
      case "OPEN":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">Open</span>;
      case "UNDER_REVIEW":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 border border-blue-300">Under Review</span>;
      case "RESOLVED":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">Resolved</span>;
      case "REJECTED":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-300">Rejected</span>;
      case "ESCALATED":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-purple-100 text-purple-800 border border-purple-300">Escalated</span>;
      default:
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-800">{status}</span>;
    }
  };

  const getPaymentBadge = (order: PlatformOrder) => {
    if (order.payment_status === "REFUNDED") {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-purple-100 text-purple-800 border border-purple-300">
          <RotateCcw className="w-3 h-3 text-purple-600" />
          Refunded
        </span>
      );
    }
    if (order.payment_method === "COD") {
      const isCollected = order.cod_collection_status === "COLLECTED" || order.payment_status === "PAID";
      return (
        <span
          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold border ${
            isCollected
              ? "bg-emerald-100 text-emerald-800 border-emerald-300"
              : "bg-blue-100 text-blue-800 border-blue-300"
          }`}
        >
          <Banknote className="w-3 h-3 text-blue-600" />
          {isCollected ? "COD: Collected" : "COD: Pending Delivery"}
        </span>
      );
    }
    const isPaid = order.payment_status === "PAID";
    return (
      <span
        className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold border ${
          isPaid
            ? "bg-emerald-100 text-emerald-800 border-emerald-300"
            : order.payment_status === "FAILED"
            ? "bg-rose-100 text-rose-800 border-rose-300"
            : "bg-amber-100 text-amber-800 border-amber-300"
        }`}
      >
        <CreditCard className="w-3 h-3 text-slate-600" />
        {isPaid ? "Paid" : `Payment ${order.payment_status || "Pending"}`}
      </span>
    );
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-amber-950 text-white rounded-3xl p-6 sm:p-8 shadow-xl relative overflow-hidden border border-slate-800">
        <div className="relative z-10 space-y-2">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-amber-400 text-slate-950 flex items-center justify-center font-black">
              <Package className="w-4 h-4" />
            </div>
            <span className="text-xs font-bold text-amber-400 tracking-wider uppercase">
              Phase 5 Marketplace
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white">
            My Orders, Returns & Dispute Management
          </h1>
          <p className="text-xs sm:text-sm text-slate-300 max-w-2xl leading-relaxed">
            Track order delivery, manage pre-dispatch cancellations and physical returns, inspect refunds, and communicate in active commercial dispute cases.
          </p>
        </div>
        <div className="absolute right-0 top-0 bottom-0 w-80 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-amber-500/10 via-transparent to-transparent pointer-events-none" />
      </div>

      {/* Success Banner */}
      {successBanner && (
        <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-900 flex items-start justify-between gap-3 shadow-xs">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
            <p className="text-xs font-bold">{successBanner}</p>
          </div>
          <button
            onClick={() => setSuccessBanner(null)}
            className="text-emerald-700 hover:text-emerald-900"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Primary Section Switcher */}
      <div className="flex items-center gap-2 p-1 bg-white rounded-2xl border border-slate-200 shadow-xs max-w-lg">
        <button
          onClick={() => setActiveSection("orders")}
          className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2 ${
            activeSection === "orders"
              ? "bg-slate-900 text-white shadow-md"
              : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
          }`}
        >
          <Package className="w-4 h-4 text-amber-400" />
          <span>Purchased Orders ({counts.all})</span>
        </button>

        <button
          onClick={() => setActiveSection("returns")}
          className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2 ${
            activeSection === "returns"
              ? "bg-slate-900 text-white shadow-md"
              : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
          }`}
        >
          <RotateCcw className="w-4 h-4 text-indigo-400" />
          <span>Returns & Cancellations ({counts.returns})</span>
        </button>

        <button
          onClick={() => setActiveSection("disputes")}
          className={`flex-1 py-2.5 px-4 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-2 ${
            activeSection === "disputes"
              ? "bg-slate-900 text-white shadow-md"
              : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
          }`}
        >
          <Scale className="w-4 h-4 text-rose-400" />
          <span>Disputes ({counts.disputes})</span>
        </button>
      </div>

      {/* ========================================================= */}
      {/* SECTION 1: PURCHASES & ORDERS                             */}
      {/* ========================================================= */}
      {activeSection === "orders" && (
        <div className="space-y-6">
          {/* Metric Tabs */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {[
              { id: "ALL", label: "All Orders", count: counts.all, color: "hover:border-slate-400" },
              { id: "PENDING_CONFIRMATION", label: "Pending", count: counts.pending, color: "hover:border-amber-400" },
              { id: "CONFIRMED", label: "Confirmed", count: counts.confirmed, color: "hover:border-blue-400" },
              { id: "PROCESSING", label: "Processing", count: counts.processing, color: "hover:border-indigo-400" },
              { id: "COMPLETED", label: "Completed", count: counts.completed, color: "hover:border-emerald-400" },
              { id: "CANCELLED", label: "Cancelled", count: counts.cancelled, color: "hover:border-rose-400" },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setStatusFilter(tab.id as OrderStatusFilter)}
                className={`p-3.5 rounded-2xl border text-left transition-all ${
                  statusFilter === tab.id
                    ? "bg-slate-900 text-white border-slate-900 shadow-md ring-2 ring-slate-900/20"
                    : `bg-white text-slate-700 border-slate-200 ${tab.color} hover:bg-slate-50`
                }`}
              >
                <div className="text-[10px] uppercase font-bold tracking-wider opacity-70">
                  {tab.label}
                </div>
                <div className="text-xl font-black mt-1 font-mono">
                  {tab.count}
                </div>
              </button>
            ))}
          </div>

          {/* Search Bar */}
          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by order #, part title, brand, or city..."
                className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 bg-white text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-amber-400 focus:border-transparent transition-all shadow-xs"
              />
            </div>
          </div>

          {/* Orders List */}
          {loading ? (
            <div className="p-12 text-center text-slate-400 text-xs">
              <Loader2 className="w-6 h-6 animate-spin mx-auto text-amber-500 mb-2" />
              <span>Loading purchase history...</span>
            </div>
          ) : filteredOrders.length === 0 ? (
            <div className="bg-white rounded-3xl border border-slate-200/80 p-12 text-center space-y-4">
              <Package className="w-12 h-12 text-slate-300 mx-auto" />
              <h3 className="text-base font-black text-slate-900">No Orders Found</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                {searchQuery || statusFilter !== "ALL"
                  ? "No orders match your filter. Try adjusting criteria."
                  : "You haven't placed any orders yet. Browse our verified catalogue to start."}
              </p>
              {onNavigateToBrowse && (
                <button
                  onClick={onNavigateToBrowse}
                  className="px-5 py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-black rounded-xl transition-all shadow-md inline-flex items-center gap-2"
                >
                  <ShoppingBag className="w-4 h-4" />
                  <span>Start Shopping</span>
                </button>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              {filteredOrders.map((order) => (
                <div
                  key={order.id}
                  className="bg-white rounded-3xl border border-slate-200/80 p-5 sm:p-6 shadow-xs hover:border-slate-300 hover:shadow-md transition-all space-y-4"
                >
                  {/* Order Header */}
                  <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100">
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="font-mono font-black text-sm text-slate-900">
                        {order.order_number}
                      </span>
                      <button
                        onClick={() => handleCopy(order.order_number)}
                        className="p-1 text-slate-400 hover:text-slate-700"
                        title="Copy Order #"
                      >
                        {copiedId === order.order_number ? (
                          <Check className="w-3.5 h-3.5 text-emerald-600" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                      </button>

                      <div className="text-[11px] text-slate-400 flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        <span>{new Date(order.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      {getStatusBadge(order.status)}
                      {getPaymentBadge(order)}

                      {/* Active Return Badges */}
                      {order.return_requests && order.return_requests.length > 0 && (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-indigo-100 text-indigo-900 border border-indigo-200">
                          <RotateCcw className="w-3 h-3 text-indigo-600" />
                          <span>Return: {order.return_requests[0].status}</span>
                        </span>
                      )}

                      {/* Active Dispute Badges */}
                      {order.disputes && order.disputes.length > 0 && (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-rose-100 text-rose-900 border border-rose-200">
                          <Scale className="w-3 h-3 text-rose-600" />
                          <span>Dispute: {order.disputes[0].status}</span>
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Items Preview */}
                  <div className="space-y-2">
                    <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Items ({order.items.length})
                    </div>
                    <div className="divide-y divide-slate-100">
                      {order.items.map((item, idx) => (
                        <div key={item.id || idx} className="py-2 flex items-center justify-between gap-4 text-xs">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-slate-900 truncate">{item.title}</span>
                              <span className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded font-semibold shrink-0 uppercase">
                                {item.brand}
                              </span>
                            </div>
                            {item.mpn && (
                              <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                                MPN: {item.mpn} · GST: {Number(item.gst_rate)}%
                              </div>
                            )}
                          </div>
                          <div className="text-right shrink-0">
                            <span className="text-slate-500 text-[11px] block">
                              Qty: {item.quantity} × {order.currency} {Number(item.unit_price).toFixed(2)}
                            </span>
                            <span className="font-mono font-bold text-slate-900">
                              {order.currency} {Number(item.total_amount).toFixed(2)}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Order Footer & Actions */}
                  <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-4 bg-slate-50/50 -mx-5 -mb-5 sm:-mx-6 sm:-mb-6 p-4 rounded-b-3xl">
                    <div className="text-xs text-slate-600 flex items-center gap-2">
                      <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span className="truncate max-w-xs sm:max-w-md">
                        Deliver to: <strong>{order.shipping_name}</strong> · {order.shipping_city}, {order.shipping_state}
                      </span>
                    </div>

                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <span className="text-[10px] uppercase font-bold text-slate-400 block">Total</span>
                        <span className="font-mono font-black text-base text-slate-900">
                          {order.currency} {Number(order.total_amount).toFixed(2)}
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        {/* Return or Cancel Action */}
                        {order.status !== "CANCELLED" && (
                          <button
                            type="button"
                            onClick={() => handleOpenReturnModal(order)}
                            className="px-3 py-2 rounded-xl border border-slate-300 hover:border-slate-400 bg-white text-slate-800 text-xs font-bold transition-all shadow-2xs flex items-center gap-1.5"
                          >
                            <RotateCcw className="w-3.5 h-3.5 text-indigo-600" />
                            <span>Return / Cancel</span>
                          </button>
                        )}

                        {/* Raise Dispute Action */}
                        <button
                          type="button"
                          onClick={() => handleOpenDisputeModal(order)}
                          className="px-3 py-2 rounded-xl border border-slate-300 hover:border-slate-400 bg-white text-slate-800 text-xs font-bold transition-all shadow-2xs flex items-center gap-1.5"
                        >
                          <Scale className="w-3.5 h-3.5 text-rose-600" />
                          <span>Dispute</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => setSelectedOrder(order)}
                          className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5"
                        >
                          <FileText className="w-3.5 h-3.5 text-amber-400" />
                          <span>Order Details</span>
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ========================================================= */}
      {/* SECTION 2: BUYER RETURNS & CANCELLATIONS                  */}
      {/* ========================================================= */}
      {activeSection === "returns" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
            <h3 className="text-xs font-black uppercase tracking-wider text-slate-800 flex items-center gap-2">
              <RotateCcw className="w-4 h-4 text-indigo-600" />
              <span>Return & Cancellation Requests ({buyerReturns.length})</span>
            </h3>

            <div className="flex items-center gap-2">
              <select
                value={returnStatusFilter}
                onChange={(e) => setReturnStatusFilter(e.target.value)}
                className="px-3 py-1.5 rounded-xl border border-slate-200 text-xs text-slate-800 font-bold bg-white"
              >
                <option value="ALL">All Statuses</option>
                <option value="PENDING">Pending</option>
                <option value="APPROVED">Approved</option>
                <option value="COMPLETED">Completed</option>
                <option value="REJECTED">Rejected</option>
                <option value="CANCELLED">Withdrawn</option>
              </select>
            </div>
          </div>

          {loadingReturns ? (
            <div className="p-12 text-center text-slate-400 text-xs">
              <Loader2 className="w-6 h-6 animate-spin mx-auto text-indigo-500 mb-2" />
              <span>Loading return requests...</span>
            </div>
          ) : buyerReturns.length === 0 ? (
            <div className="bg-white rounded-3xl border border-slate-200 p-12 text-center space-y-2">
              <RotateCcw className="w-10 h-10 text-slate-300 mx-auto" />
              <h4 className="text-sm font-black text-slate-900">No Return Requests</h4>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                You haven&apos;t created any return or cancellation requests. Eligible orders can be returned from the &quot;Purchased Orders&quot; tab.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {buyerReturns.map((ret) => (
                <div key={ret.id} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono font-black text-sm text-slate-900">
                        {ret.request_number}
                      </span>
                      <span className="text-slate-300">·</span>
                      <span className="text-xs text-slate-600 font-mono">
                        Order #{ret.order_number}
                      </span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-slate-100 text-slate-700">
                        {ret.request_type_display || ret.request_type}
                      </span>
                      {getReturnStatusBadge(ret.status)}
                    </div>

                    <div className="text-xs text-slate-400">
                      Requested {new Date(ret.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                    </div>
                  </div>

                  <div className="text-xs space-y-1">
                    <div>
                      <span className="font-bold text-slate-800">Reason: </span>
                      <span>{ret.reason_display || ret.reason}</span>
                    </div>
                    {ret.item_title && (
                      <div>
                        <span className="font-bold text-slate-800">Item: </span>
                        <span>{ret.item_title} (Qty: {ret.requested_quantity})</span>
                      </div>
                    )}
                    <div className="p-3 rounded-xl bg-slate-50 text-slate-700 leading-relaxed mt-1">
                      <span className="font-bold text-slate-900">Description: </span>
                      {ret.description}
                    </div>
                  </div>

                  {/* Seller Notes / Rejection Reason */}
                  {ret.seller_notes && (
                    <div className="p-3 rounded-xl bg-blue-50 border border-blue-200 text-xs text-blue-900">
                      <strong>Seller Feedback: </strong>
                      {ret.seller_notes}
                    </div>
                  )}

                  {ret.rejection_reason && (
                    <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-900">
                      <strong>Rejection Rationale: </strong>
                      {ret.rejection_reason}
                    </div>
                  )}

                  {/* Evidence Images */}
                  {ret.evidence_urls && ret.evidence_urls.length > 0 && (
                    <div className="space-y-1 pt-1">
                      <span className="text-[10px] uppercase font-bold text-slate-400 block">Uploaded Evidence</span>
                      <div className="flex flex-wrap gap-2">
                        {ret.evidence_urls.map((url, i) => (
                          <a
                            key={i}
                            href={resolveMediaUrl(url)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="w-14 h-14 rounded-xl border border-slate-200 overflow-hidden bg-slate-100 hover:opacity-80 transition-opacity"
                          >
                            <img src={resolveMediaUrl(url)} alt={`Evidence ${i + 1}`} className="w-full h-full object-cover" />
                          </a>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Actions */}
                  {ret.status === "PENDING" && (
                    <div className="pt-2 flex justify-end">
                      <button
                        type="button"
                        onClick={() => handleWithdrawReturnRequest(ret.request_number)}
                        className="px-3 py-1.5 rounded-xl border border-rose-200 hover:bg-rose-50 text-rose-700 text-xs font-bold transition-colors"
                      >
                        Withdraw Request
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ========================================================= */}
      {/* SECTION 3: COMMERCIAL DISPUTES                            */}
      {/* ========================================================= */}
      {activeSection === "disputes" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
            <h3 className="text-xs font-black uppercase tracking-wider text-slate-800 flex items-center gap-2">
              <Scale className="w-4 h-4 text-rose-600" />
              <span>Commercial Dispute Cases ({buyerDisputes.length})</span>
            </h3>
          </div>

          {loadingDisputes ? (
            <div className="p-12 text-center text-slate-400 text-xs">
              <Loader2 className="w-6 h-6 animate-spin mx-auto text-rose-500 mb-2" />
              <span>Loading dispute cases...</span>
            </div>
          ) : buyerDisputes.length === 0 ? (
            <div className="bg-white rounded-3xl border border-slate-200 p-12 text-center space-y-2">
              <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto" />
              <h4 className="text-sm font-black text-slate-900">No Open Disputes</h4>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                You have no active disputes. If you experience order fulfillment or refund issues, you can raise a dispute directly from any order.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {buyerDisputes.map((disp) => (
                <div key={disp.id} className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono font-black text-sm text-slate-900">
                        {disp.dispute_number}
                      </span>
                      <span className="text-slate-300">·</span>
                      <span className="text-xs text-slate-600 font-mono">
                        Order #{disp.order_number}
                      </span>
                      {getDisputeStatusBadge(disp.status)}
                    </div>

                    <div className="text-xs text-slate-400">
                      Opened {new Date(disp.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                    </div>
                  </div>

                  <div className="text-xs space-y-1">
                    <div>
                      <span className="font-bold text-slate-800">Category: </span>
                      <span>{disp.category_display || disp.category}</span>
                    </div>
                    <div className="p-3 rounded-xl bg-slate-50 text-slate-700 leading-relaxed">
                      <span className="font-bold text-slate-900">Description: </span>
                      {disp.description}
                    </div>
                  </div>

                  {disp.resolution && (
                    <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-950 space-y-1">
                      <div className="flex items-center gap-1.5 font-bold">
                        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                        <span>Resolution: {disp.resolution}</span>
                      </div>
                      {disp.resolution_notes && <p className="text-emerald-800">{disp.resolution_notes}</p>}
                    </div>
                  )}

                  <div className="pt-2 flex items-center justify-between gap-3">
                    <span className="text-[11px] text-slate-400 flex items-center gap-1">
                      <MessageSquare className="w-3.5 h-3.5" />
                      <span>{disp.events?.length || 0} messages in thread</span>
                    </span>

                    <button
                      type="button"
                      onClick={() => setActiveDisputeThread(disp)}
                      className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5"
                    >
                      <MessageSquare className="w-3.5 h-3.5 text-amber-400" />
                      <span>Open Dispute Conversation</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ========================================================= */}
      {/* RETURN OR CANCELLATION REQUEST MODAL                      */}
      {/* ========================================================= */}
      {returnModalOrder && (
        <div className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
          <div className="bg-white rounded-3xl max-w-xl w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="p-5 sm:p-6 bg-slate-900 text-white flex items-center justify-between shrink-0">
              <div className="space-y-0.5">
                <h3 className="font-mono font-black text-amber-400 text-base flex items-center gap-2">
                  <RotateCcw className="w-4 h-4" />
                  <span>Request Return / Cancellation</span>
                </h3>
                <p className="text-xs text-slate-300">
                  Order #{returnModalOrder.order_number}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setReturnModalOrder(null)}
                className="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmitReturnRequest} className="p-5 sm:p-6 overflow-y-auto space-y-4 text-xs">
              {checkingEligibility ? (
                <div className="p-8 text-center text-slate-400">
                  <Loader2 className="w-6 h-6 animate-spin mx-auto text-amber-500 mb-2" />
                  <span>Checking return policy and eligibility rules...</span>
                </div>
              ) : (
                <>
                  {returnModalError && (
                    <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800">
                      {returnModalError}
                    </div>
                  )}

                  {returnEligibility && (
                    <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-2xl space-y-2">
                      <span className="text-[10px] uppercase font-bold text-slate-400 block">Policy Eligibility</span>
                      <div className="grid grid-cols-2 gap-2 text-[11px]">
                        <div className={`p-2 rounded-xl border ${returnEligibility.order_cancellation.eligible ? "bg-emerald-50 border-emerald-200 text-emerald-900" : "bg-slate-100 border-slate-200 text-slate-600"}`}>
                          <span className="font-bold block">Pre-dispatch Cancellation</span>
                          <span>{returnEligibility.order_cancellation.eligible ? "Eligible" : returnEligibility.order_cancellation.reason || "Not permitted"}</span>
                        </div>
                        <div className={`p-2 rounded-xl border ${returnEligibility.order_return.eligible ? "bg-emerald-50 border-emerald-200 text-emerald-900" : "bg-slate-100 border-slate-200 text-slate-600"}`}>
                          <span className="font-bold block">Physical Return</span>
                          <span>{returnEligibility.order_return.eligible ? "Eligible (14-day window)" : returnEligibility.order_return.reason || "Not permitted"}</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Request Type Selector */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Request Type *</label>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => setReturnRequestType("CANCELLATION")}
                        className={`p-3 rounded-xl border text-left font-bold ${
                          returnRequestType === "CANCELLATION"
                            ? "bg-slate-900 text-white border-slate-900 shadow-sm"
                            : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
                        }`}
                      >
                        Cancellation (Pre-Dispatch)
                      </button>
                      <button
                        type="button"
                        onClick={() => setReturnRequestType("RETURN")}
                        className={`p-3 rounded-xl border text-left font-bold ${
                          returnRequestType === "RETURN"
                            ? "bg-slate-900 text-white border-slate-900 shadow-sm"
                            : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
                        }`}
                      >
                        Physical Return (Delivered)
                      </button>
                    </div>
                  </div>

                  {/* Item Selection */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Return Scope *</label>
                    <select
                      value={selectedItemForReturn}
                      onChange={(e) => setSelectedItemForReturn(e.target.value)}
                      className="w-full px-3 py-2.5 rounded-xl border border-slate-200 bg-white font-semibold text-slate-800"
                    >
                      <option value="ORDER">Entire Order (All Items)</option>
                      {returnModalOrder.items.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.title} ({item.quantity}x)
                        </option>
                      ))}
                    </select>
                  </div>

                  {selectedItemForReturn !== "ORDER" && (
                    <div>
                      <label className="block font-bold text-slate-700 mb-1">Quantity to Return</label>
                      <input
                        type="number"
                        min={1}
                        max={returnModalOrder.items.find((i) => i.id === selectedItemForReturn)?.quantity || 1}
                        value={returnQuantity}
                        onChange={(e) => setReturnQuantity(parseInt(e.target.value) || 1)}
                        className="w-24 px-3 py-2 rounded-xl border border-slate-200 font-mono"
                      />
                    </div>
                  )}

                  {/* Reason Dropdown */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Reason for Return / Cancellation *</label>
                    <select
                      value={returnReason}
                      onChange={(e) => setReturnReason(e.target.value as ReturnReason)}
                      className="w-full px-3 py-2.5 rounded-xl border border-slate-200 bg-white font-semibold text-slate-800"
                    >
                      <option value="DEFECTIVE_ITEM">Defective / Damaged Item</option>
                      <option value="INCORRECT_ITEM">Wrong / Incorrect Item Received</option>
                      <option value="NOT_AS_DESCRIBED">Item Not As Described in Listing</option>
                      <option value="ORDERED_BY_MISTAKE">Ordered By Mistake</option>
                      <option value="DELIVERY_DELAY">Severe Delivery Delay</option>
                      <option value="BUYER_CANCEL">Buyer Requested Cancellation</option>
                      <option value="OTHER">Other Reason</option>
                    </select>
                  </div>

                  {/* Description */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Detailed Explanation *</label>
                    <textarea
                      rows={3}
                      value={returnDescription}
                      onChange={(e) => setReturnDescription(e.target.value)}
                      placeholder="Please explain the issue in detail (min 10 characters)..."
                      required
                      minLength={10}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-400"
                    />
                  </div>

                  {/* Supporting Evidence Image Upload */}
                  <div className="space-y-2">
                    <label className="block font-bold text-slate-700">Supporting Evidence Photos (Optional)</label>
                    <div className="flex items-center gap-2">
                      <label className="px-3 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 cursor-pointer text-slate-700 font-bold inline-flex items-center gap-1.5 shadow-2xs">
                        <UploadCloud className="w-4 h-4 text-indigo-600" />
                        <span>Upload Images</span>
                        <input
                          type="file"
                          accept="image/*"
                          multiple
                          onChange={handleUploadReturnImage}
                          className="hidden"
                          disabled={isUploadingReturnImage}
                        />
                      </label>
                      {isUploadingReturnImage && (
                        <span className="text-[11px] text-slate-400 flex items-center gap-1">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          <span>Uploading...</span>
                        </span>
                      )}
                    </div>

                    {returnEvidenceUrls.length > 0 && (
                      <div className="flex flex-wrap gap-2 pt-1">
                        {returnEvidenceUrls.map((url, idx) => (
                          <div key={idx} className="relative w-14 h-14 rounded-xl border border-slate-300 overflow-hidden group">
                            <img src={resolveMediaUrl(url)} alt={`Evidence ${idx}`} className="w-full h-full object-cover" />
                            <button
                              type="button"
                              onClick={() => setReturnEvidenceUrls((prev) => prev.filter((_, i) => i !== idx))}
                              className="absolute inset-0 bg-slate-950/60 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                            >
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="pt-2 flex items-center justify-end gap-3">
                    <button
                      type="button"
                      onClick={() => setReturnModalOrder(null)}
                      className="px-4 py-2.5 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 font-bold"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isSubmittingReturn || returnDescription.trim().length < 10}
                      className="px-5 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-black shadow-md flex items-center gap-2 disabled:opacity-40"
                    >
                      {isSubmittingReturn ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          <span>Submitting Request...</span>
                        </>
                      ) : (
                        <span>Submit Request</span>
                      )}
                    </button>
                  </div>
                </>
              )}
            </form>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* RAISE DISPUTE MODAL                                       */}
      {/* ========================================================= */}
      {disputeModalOrder && (
        <div className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
          <div className="bg-white rounded-3xl max-w-xl w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="p-5 sm:p-6 bg-slate-900 text-white flex items-center justify-between shrink-0">
              <div className="space-y-0.5">
                <h3 className="font-mono font-black text-rose-400 text-base flex items-center gap-2">
                  <Scale className="w-4 h-4" />
                  <span>Raise Commercial Dispute</span>
                </h3>
                <p className="text-xs text-slate-300">
                  Order #{disputeModalOrder.order_number}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setDisputeModalOrder(null)}
                className="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmitDispute} className="p-5 sm:p-6 overflow-y-auto space-y-4 text-xs">
              {disputeModalError && (
                <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800">
                  {disputeModalError}
                </div>
              )}

              <div>
                <label className="block font-bold text-slate-700 mb-1">Dispute Category *</label>
                <select
                  value={disputeCategory}
                  onChange={(e) => setDisputeCategory(e.target.value as DisputeCategory)}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-200 bg-white font-semibold text-slate-800"
                >
                  <option value="ITEM_NOT_RECEIVED">Item Not Received</option>
                  <option value="SIGNIFICANTLY_NOT_AS_DESCRIBED">Significantly Not As Described</option>
                  <option value="DAMAGED_OR_DEFECTIVE">Damaged or Defective Part</option>
                  <option value="UNAUTHORIZED_TRANSACTION">Unauthorized Transaction</option>
                  <option value="REFUND_NOT_PROCESSED">Refund Not Processed / Delayed</option>
                  <option value="CANCELLATION_ISSUE">Cancellation Issue</option>
                  <option value="OTHER">Other Issue</option>
                </select>
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">Priority Level</label>
                <select
                  value={disputePriority}
                  onChange={(e) => setDisputePriority(e.target.value as DisputePriority)}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-200 bg-white font-semibold text-slate-800"
                >
                  <option value="LOW">Low</option>
                  <option value="MEDIUM">Medium</option>
                  <option value="HIGH">High</option>
                  <option value="URGENT">Urgent</option>
                </select>
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">Detailed Description of Claim *</label>
                <textarea
                  rows={4}
                  value={disputeDescription}
                  onChange={(e) => setDisputeDescription(e.target.value)}
                  placeholder="Explain the background, timeline, courier issues, or defect details (min 15 characters)..."
                  required
                  minLength={15}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-rose-400"
                />
              </div>

              {/* Evidence Upload */}
              <div className="space-y-2">
                <label className="block font-bold text-slate-700">Supporting Evidence Photos (Optional)</label>
                <div className="flex items-center gap-2">
                  <label className="px-3 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 cursor-pointer text-slate-700 font-bold inline-flex items-center gap-1.5 shadow-2xs">
                    <UploadCloud className="w-4 h-4 text-rose-600" />
                    <span>Upload Images</span>
                    <input
                      type="file"
                      accept="image/*"
                      multiple
                      onChange={handleUploadDisputeImage}
                      className="hidden"
                      disabled={isUploadingDisputeImage}
                    />
                  </label>
                  {isUploadingDisputeImage && (
                    <span className="text-[11px] text-slate-400 flex items-center gap-1">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      <span>Uploading...</span>
                    </span>
                  )}
                </div>

                {disputeEvidenceUrls.length > 0 && (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {disputeEvidenceUrls.map((url, idx) => (
                      <div key={idx} className="relative w-14 h-14 rounded-xl border border-slate-300 overflow-hidden group">
                        <img src={resolveMediaUrl(url)} alt={`Evidence ${idx}`} className="w-full h-full object-cover" />
                        <button
                          type="button"
                          onClick={() => setDisputeEvidenceUrls((prev) => prev.filter((_, i) => i !== idx))}
                          className="absolute inset-0 bg-slate-950/60 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="pt-2 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setDisputeModalOrder(null)}
                  className="px-4 py-2.5 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingDispute || disputeDescription.trim().length < 15}
                  className="px-5 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-black shadow-md flex items-center gap-2 disabled:opacity-40"
                >
                  {isSubmittingDispute ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Opening Dispute...</span>
                    </>
                  ) : (
                    <span>Submit Dispute Case</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* ACTIVE DISPUTE CONVERSATION THREAD MODAL                  */}
      {/* ========================================================= */}
      {activeDisputeThread && (
        <div className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
          <div className="bg-white rounded-3xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="p-5 sm:p-6 bg-slate-900 text-white flex items-center justify-between shrink-0">
              <div className="space-y-0.5">
                <h3 className="font-mono font-black text-rose-400 text-base flex items-center gap-2">
                  <Scale className="w-4 h-4" />
                  <span>Dispute {activeDisputeThread.dispute_number}</span>
                </h3>
                <p className="text-xs text-slate-300">
                  Order #{activeDisputeThread.order_number} · Category: {activeDisputeThread.category_display || activeDisputeThread.category}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {getDisputeStatusBadge(activeDisputeThread.status)}
                <button
                  type="button"
                  onClick={() => setActiveDisputeThread(null)}
                  className="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-slate-800"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            <div className="p-5 sm:p-6 overflow-y-auto space-y-4 text-xs">
              {/* Claim Description */}
              <div className="p-3.5 rounded-2xl bg-slate-50 border border-slate-200 text-slate-800 space-y-1">
                <span className="font-bold text-slate-900 block">Original Claim:</span>
                <p className="leading-relaxed">{activeDisputeThread.description}</p>
              </div>

              {activeDisputeThread.resolution && (
                <div className="p-3.5 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-950 space-y-1">
                  <span className="font-bold block">Adjudicated Decision: {activeDisputeThread.resolution}</span>
                  {activeDisputeThread.resolution_notes && <p>{activeDisputeThread.resolution_notes}</p>}
                </div>
              )}

              {/* Message thread */}
              <div className="space-y-3">
                <span className="text-[10px] uppercase font-bold text-slate-400 block">
                  Messages & Events ({activeDisputeThread.events?.length || 0})
                </span>

                <div className="space-y-2.5 max-h-64 overflow-y-auto pr-1">
                  {activeDisputeThread.events && activeDisputeThread.events.length > 0 ? (
                    activeDisputeThread.events.map((evt) => (
                      <div
                        key={evt.id}
                        className={`p-3 rounded-2xl border text-xs space-y-1 ${
                          evt.actor_role === "BUYER"
                            ? "bg-amber-50/80 border-amber-200 mr-8"
                            : evt.actor_role === "SELLER"
                            ? "bg-indigo-50/80 border-indigo-200 ml-8"
                            : "bg-slate-50 border-slate-200 ml-8"
                        }`}
                      >
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="font-bold text-slate-900">
                            {evt.actor_name || "User"} ({evt.actor_role || "PARTY"})
                          </span>
                          <span className="text-slate-400 font-mono text-[10px]">
                            {new Date(evt.created_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}
                          </span>
                        </div>
                        <p className="text-slate-700 leading-relaxed">{evt.message}</p>
                      </div>
                    ))
                  ) : (
                    <div className="p-4 text-center text-slate-400">No events yet.</div>
                  )}
                </div>

                {/* Reply box */}
                {activeDisputeThread.status !== "RESOLVED" && activeDisputeThread.status !== "REJECTED" && (
                  <div className="pt-2 border-t border-slate-200 space-y-2">
                    {disputeReplyError && <div className="text-rose-600 text-xs">{disputeReplyError}</div>}
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={disputeReplyMessage}
                        onChange={(e) => setDisputeReplyMessage(e.target.value)}
                        placeholder="Reply to seller or staff..."
                        className="flex-1 px-3.5 py-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-rose-400"
                      />
                      <button
                        type="button"
                        onClick={handleSendDisputeReply}
                        disabled={isSendingDisputeReply || !disputeReplyMessage.trim()}
                        className="px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-bold transition-all disabled:opacity-40 flex items-center gap-1.5"
                      >
                        {isSendingDisputeReply ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5 text-amber-400" />}
                        <span>Send</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* ORDER DETAILS MODAL / DRAWER                              */}
      {/* ========================================================= */}
      {selectedOrder && (
        <div className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
          <div className="bg-white rounded-3xl max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="p-5 sm:p-6 bg-slate-900 text-white flex items-center justify-between shrink-0">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-black text-lg text-amber-400">
                    {selectedOrder.order_number}
                  </span>
                  <button
                    onClick={() => handleCopy(selectedOrder.order_number)}
                    className="p-1 text-slate-400 hover:text-white rounded transition-colors"
                    title="Copy Order Number"
                  >
                    {copiedId === selectedOrder.order_number ? (
                      <Check className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <Copy className="w-4 h-4" />
                    )}
                  </button>
                </div>
                <p className="text-xs text-slate-400">
                  Placed on {new Date(selectedOrder.created_at).toLocaleString("en-GB", { dateStyle: "full", timeStyle: "short" })}
                </p>
              </div>

              <div className="flex items-center gap-3">
                {getStatusBadge(selectedOrder.status)}
                <button
                  onClick={() => setSelectedOrder(null)}
                  className="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-slate-800 transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Modal Scrollable Body */}
            <div className="p-5 sm:p-6 overflow-y-auto space-y-6">
              {/* Status Banner */}
              <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 flex items-start gap-3">
                <div className="p-2 rounded-xl bg-amber-100 text-amber-800 shrink-0">
                  <Clock className="w-5 h-5" />
                </div>
                <div className="space-y-0.5 text-xs">
                  <h4 className="font-bold text-slate-900">
                    Order Status: {selectedOrder.status}
                  </h4>
                  <p className="text-slate-500 leading-relaxed">
                    {selectedOrder.status === "PENDING_CONFIRMATION" &&
                      "Your order has been recorded and is currently awaiting seller confirmation."}
                    {selectedOrder.status === "CONFIRMED" &&
                      "The seller has confirmed your order. Inventory has been allocated."}
                    {selectedOrder.status === "PROCESSING" &&
                      "Your order is currently processing for shipping and dispatch."}
                    {selectedOrder.status === "COMPLETED" &&
                      "Your order has been completed and delivered."}
                    {selectedOrder.status === "CANCELLED" &&
                      "This order has been cancelled and its inventory items have been returned to active stock."}
                  </p>
                </div>
              </div>

              {/* Items Breakdown */}
              <div className="space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <Receipt className="w-3.5 h-3.5" />
                  <span>Purchased Spare Parts & Items ({selectedOrder.items.length})</span>
                </h4>
                <div className="border border-slate-200 rounded-2xl overflow-hidden divide-y divide-slate-100">
                  {selectedOrder.items.map((item, idx) => (
                    <div key={item.id || idx} className="p-4 space-y-2 bg-white">
                      <div className="flex items-start justify-between gap-3">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-[10px] font-bold px-2 py-0.5 bg-amber-100 text-amber-800 rounded uppercase">
                              {item.brand}
                            </span>
                            {item.mpn && (
                              <span className="text-[10px] font-mono font-medium text-slate-500">
                                MPN: {item.mpn}
                              </span>
                            )}
                          </div>
                          <h5 className="text-sm font-bold text-slate-900">{item.title}</h5>
                        </div>
                        <div className="text-right shrink-0">
                          <div className="text-xs text-slate-400">
                            {item.quantity} × {selectedOrder.currency} {Number(item.unit_price).toFixed(2)}
                          </div>
                          <div className="font-mono font-black text-sm text-slate-900 mt-0.5">
                            {selectedOrder.currency} {Number(item.total_amount).toFixed(2)}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Returns, Refunds & Disputes Status Section */}
              {((selectedOrder.return_requests && selectedOrder.return_requests.length > 0) ||
                (selectedOrder.refunds && selectedOrder.refunds.length > 0) ||
                (selectedOrder.disputes && selectedOrder.disputes.length > 0)) && (
                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-3 text-xs">
                  <h4 className="font-bold text-slate-900 flex items-center gap-2">
                    <RotateCcw className="w-4 h-4 text-indigo-600" />
                    <span>Returns, Refunds & Disputes Record</span>
                  </h4>

                  {selectedOrder.return_requests && selectedOrder.return_requests.length > 0 && (
                    <div className="space-y-1">
                      <span className="text-[10px] uppercase font-bold text-slate-500 block">Return Requests:</span>
                      {selectedOrder.return_requests.map((rr) => (
                        <div key={rr.id} className="p-2.5 rounded-xl bg-white border border-slate-200 flex items-center justify-between">
                          <div>
                            <span className="font-mono font-bold text-slate-900">{rr.request_number}</span>
                            <span className="text-slate-500"> · {rr.request_type} ({rr.reason})</span>
                          </div>
                          {getReturnStatusBadge(rr.status)}
                        </div>
                      ))}
                    </div>
                  )}

                  {selectedOrder.refunds && selectedOrder.refunds.length > 0 && (
                    <div className="space-y-1">
                      <span className="text-[10px] uppercase font-bold text-slate-500 block">Issued Refunds:</span>
                      {selectedOrder.refunds.map((rf) => (
                        <div key={rf.id} className="p-2.5 rounded-xl bg-white border border-slate-200 flex items-center justify-between">
                          <div>
                            <span className="font-mono font-bold text-slate-900">{rf.refund_number}</span>
                            <span className="text-slate-600"> · {rf.currency} {Number(rf.amount).toFixed(2)} ({rf.refund_method})</span>
                          </div>
                          <span className="font-bold text-emerald-700">{rf.status}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Delivery Details & Financial Recap */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-2 text-xs">
                  <h4 className="font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                    <MapPin className="w-3.5 h-3.5 text-amber-500" />
                    <span>Shipping Destination</span>
                  </h4>
                  <p className="font-black text-slate-900">{selectedOrder.shipping_name}</p>
                  <p className="text-slate-600">
                    {selectedOrder.shipping_address_line1}, {selectedOrder.shipping_city}, {selectedOrder.shipping_state} - {selectedOrder.shipping_postal_code}
                  </p>
                </div>

                <div className="p-4 rounded-2xl bg-slate-900 text-white space-y-2 text-xs">
                  <h4 className="font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                    <Receipt className="w-3.5 h-3.5" />
                    <span>Total Financial Summary</span>
                  </h4>
                  <div className="flex justify-between">
                    <span>Taxable Subtotal:</span>
                    <span className="font-mono">{selectedOrder.currency} {Number(selectedOrder.subtotal_taxable_amount).toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Total Taxes:</span>
                    <span className="font-mono">+{selectedOrder.currency} {Number(selectedOrder.total_tax_amount).toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between text-base font-black text-amber-400 pt-1 border-t border-slate-800">
                    <span>Grand Total:</span>
                    <span className="font-mono">{selectedOrder.currency} {Number(selectedOrder.total_amount).toFixed(2)}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 sm:p-5 bg-slate-50 border-t border-slate-200 flex items-center justify-between gap-3 shrink-0">
              <div className="flex items-center gap-2">
                {selectedOrder.status !== "CANCELLED" && (
                  <button
                    type="button"
                    onClick={() => {
                      const ord = selectedOrder;
                      setSelectedOrder(null);
                      handleOpenReturnModal(ord);
                    }}
                    className="px-3.5 py-2 rounded-xl border border-slate-300 bg-white hover:bg-slate-50 text-slate-800 text-xs font-bold transition-colors"
                  >
                    Request Return / Cancellation
                  </button>
                )}

                <button
                  type="button"
                  onClick={() => {
                    const ord = selectedOrder;
                    setSelectedOrder(null);
                    handleOpenDisputeModal(ord);
                  }}
                  className="px-3.5 py-2 rounded-xl border border-slate-300 bg-white hover:bg-slate-50 text-rose-700 text-xs font-bold transition-colors"
                >
                  Raise Dispute
                </button>
              </div>

              <button
                type="button"
                onClick={() => setSelectedOrder(null)}
                className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-all shadow-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Cancel Order Confirmation */}
      {cancelModalOrder && (
        <div className="fixed inset-0 z-60 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-200">
            <div className="w-12 h-12 rounded-2xl bg-rose-100 text-rose-600 flex items-center justify-center mx-auto">
              <AlertTriangle className="w-6 h-6" />
            </div>

            <div className="text-center space-y-1">
              <h3 className="text-base font-black text-slate-900">
                Cancel Order {cancelModalOrder.order_number}?
              </h3>
              <p className="text-xs text-slate-500">
                Are you sure you want to cancel this order? Cancelling will release the order and automatically return all reserved spare parts to active inventory.
              </p>
            </div>

            {cancelError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs">
                {cancelError}
              </div>
            )}

            <div className="flex items-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => setCancelModalOrder(null)}
                disabled={isCancelling}
                className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-bold transition-colors"
              >
                Keep Order
              </button>
              <button
                type="button"
                onClick={handleCancelOrder}
                disabled={isCancelling}
                className="flex-1 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {isCancelling ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Cancelling...</span>
                  </>
                ) : (
                  <span>Yes, Cancel Order</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
