"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  api,
  SellerOrder,
  PlatformOrderItem,
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
  ShieldCheck,
  ArrowRight,
  Boxes,
} from "lucide-react";

interface SellerOrdersViewProps {
  initialOrderId?: string;
}

type OrderStatusFilter =
  | "ALL"
  | "PENDING_CONFIRMATION"
  | "CONFIRMED"
  | "PROCESSING"
  | "COMPLETED"
  | "CANCELLED";

export default function SellerOrdersView({
  initialOrderId,
}: SellerOrdersViewProps) {
  const { user } = useAuth();
  const [orders, setOrders] = useState<SellerOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<OrderStatusFilter>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedOrder, setSelectedOrder] = useState<SellerOrder | null>(null);

  // Status update modal & state
  const [statusModalOrder, setStatusModalOrder] = useState<{
    order: SellerOrder;
    targetStatus: string;
  } | null>(null);
  const [statusNotes, setStatusNotes] = useState("");
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  // Copy feedback
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const loadSellerOrders = useCallback(async () => {
    if (!user) {
      setOrders([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await api.marketplace.listSellerOrders(statusFilter, searchQuery);
      setOrders(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      console.error("Failed to load seller orders", err);
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to load seller orders. Please check your network connection.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [user, statusFilter, searchQuery]);

  useEffect(() => {
    let ignore = false;
    Promise.resolve().then(() => {
      if (!ignore) {
        loadSellerOrders();
      }
    });
    return () => {
      ignore = true;
    };
  }, [loadSellerOrders]);

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

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleStatusUpdate = async () => {
    if (!statusModalOrder) return;
    setIsUpdatingStatus(true);
    setUpdateError(null);
    try {
      const { order, targetStatus } = statusModalOrder;
      const res = await api.marketplace.updateSellerOrderStatus(
        order.id,
        targetStatus,
        statusNotes
      );
      if (res.status === "success" && res.order) {
        // Update local orders list
        setOrders((prev) =>
          prev.map((o) => (o.id === res.order.id ? res.order : o))
        );
        if (selectedOrder?.id === res.order.id) {
          setSelectedOrder(res.order);
        }
        setSuccessBanner(
          `Order ${res.order.order_number} has been updated to ${targetStatus}.`
        );
        setStatusModalOrder(null);
        setStatusNotes("");
      } else {
        throw new Error(res.message || "Failed to update order status.");
      }
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to update order status. Please verify permissions and valid transitions.";
      setUpdateError(msg);
    } finally {
      setIsUpdatingStatus(false);
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
    };
  }, [orders]);

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

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-950 text-white rounded-2xl p-6 sm:p-8 shadow-xl relative overflow-hidden border border-slate-800">
        <div className="relative z-10 space-y-2">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-amber-400 text-slate-950 flex items-center justify-center font-black">
              <Boxes className="w-4 h-4" />
            </div>
            <span className="text-xs font-bold text-amber-400 tracking-wider uppercase">
              Seller Fulfillment & Orders
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white">
            Customer Orders & Fulfillment
          </h1>
          <p className="text-xs sm:text-sm text-slate-300 max-w-2xl leading-relaxed">
            Manage purchase orders containing your inventory items. Confirm incoming orders, advance fulfillment through processing, access shipping addresses, and maintain strict multi-seller privacy.
          </p>
        </div>
        <div className="absolute right-0 top-0 bottom-0 w-80 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-amber-500/10 via-transparent to-transparent pointer-events-none" />
      </div>

      {/* Success Banner */}
      {successBanner && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-900 flex items-start justify-between gap-3 shadow-xs">
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

      {/* Metric Tabs */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {[
          { id: "ALL", label: "All Orders", count: counts.all, color: "hover:border-slate-400" },
          { id: "PENDING_CONFIRMATION", label: "Needs Confirmation", count: counts.pending, color: "hover:border-amber-400" },
          { id: "CONFIRMED", label: "Confirmed", count: counts.confirmed, color: "hover:border-blue-400" },
          { id: "PROCESSING", label: "In Processing", count: counts.processing, color: "hover:border-indigo-400" },
          { id: "COMPLETED", label: "Completed", count: counts.completed, color: "hover:border-emerald-400" },
          { id: "CANCELLED", label: "Cancelled", count: counts.cancelled, color: "hover:border-rose-400" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setStatusFilter(tab.id as OrderStatusFilter)}
            className={`p-3.5 rounded-xl border text-left transition-all ${
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

      {/* Search & Actions Bar */}
      <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by order #, buyer email, or recipient..."
            className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 bg-white text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-amber-400 focus:border-transparent transition-all shadow-xs"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadSellerOrders}
            disabled={loading}
            className="px-3.5 py-2.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold flex items-center gap-2 transition-colors shadow-xs disabled:opacity-50"
            title="Refresh orders list"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Content Area */}
      {loading ? (
        <div className="py-20 flex flex-col items-center justify-center space-y-3 bg-white rounded-2xl border border-slate-200">
          <Loader2 className="w-8 h-8 text-amber-500 animate-spin" />
          <span className="text-xs font-bold text-slate-600">Loading incoming seller orders...</span>
        </div>
      ) : error ? (
        <div className="p-8 bg-rose-50 border border-rose-200 rounded-2xl text-center space-y-3">
          <AlertCircle className="w-10 h-10 text-rose-500 mx-auto" />
          <h3 className="text-sm font-bold text-rose-900">Failed to Load Orders</h3>
          <p className="text-xs text-rose-700 max-w-md mx-auto">{error}</p>
          <button
            onClick={loadSellerOrders}
            className="px-4 py-2 bg-rose-600 text-white text-xs font-bold rounded-xl hover:bg-rose-700 transition-colors"
          >
            Try Again
          </button>
        </div>
      ) : orders.length === 0 ? (
        <div className="py-20 bg-white rounded-2xl border border-slate-200 text-center space-y-4 p-6">
          <div className="w-16 h-16 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
            <Boxes className="w-8 h-8" />
          </div>
          <div className="space-y-1 max-w-sm mx-auto">
            <h3 className="text-base font-black text-slate-900">No Orders Found</h3>
            <p className="text-xs text-slate-500">
              {searchQuery || statusFilter !== "ALL"
                ? "No customer orders match your active filter and search criteria."
                : "No customer orders have been received for your listings yet. Ensure your spare parts listings are active and competitive."}
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {orders.map((order) => (
            <div
              key={order.id}
              className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-xs hover:border-slate-300 hover:shadow-md transition-all space-y-4"
            >
              {/* Order Header Row */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-black text-sm text-slate-900 tracking-wide">
                      {order.order_number}
                    </span>
                    <button
                      onClick={() => handleCopy(order.order_number)}
                      className="p-1 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded transition-colors"
                      title="Copy Order Number"
                    >
                      {copiedId === order.order_number ? (
                        <Check className="w-3.5 h-3.5 text-emerald-600" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                  <div className="text-[11px] text-slate-400 flex items-center gap-1">
                    <Calendar className="w-3 h-3" />
                    <span>{new Date(order.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                  </div>
                  <div className="text-[11px] text-slate-600 font-medium">
                    Buyer: <span className="font-semibold text-slate-900">{order.buyer_name || order.buyer_email}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {getStatusBadge(order.status)}
                </div>
              </div>

              {/* Items Preview (Isolated to this Seller Only) */}
              <div className="space-y-2">
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                  <span>Your Ordered Items ({order.items.length})</span>
                  <span className="text-amber-700 font-semibold lowercase">
                    {order.seller_item_count} total units
                  </span>
                </div>
                <div className="divide-y divide-slate-100">
                  {order.items.map((item, idx) => (
                    <div
                      key={item.id || idx}
                      className="py-2 flex items-center justify-between gap-4 text-xs"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-slate-900 truncate">
                            {item.title}
                          </span>
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

              {/* Footer & Action Controls */}
              <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-4 bg-slate-50/50 -mx-5 -mb-5 p-4 rounded-b-2xl">
                <div className="text-xs text-slate-600 flex items-center gap-2">
                  <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <span className="truncate max-w-xs sm:max-w-md">
                    Ship to: <strong>{order.shipping_name}</strong> ({order.shipping_phone}) · {order.shipping_city}, {order.shipping_state}
                  </span>
                </div>

                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">
                      Your Revenue (Incl. GST)
                    </span>
                    <span className="font-mono font-black text-base text-slate-900">
                      {order.currency} {Number(order.seller_total_amount).toFixed(2)}
                    </span>
                  </div>

                  {/* Permitted Status Transition Buttons */}
                  <div className="flex items-center gap-2">
                    {order.status === "PENDING_CONFIRMATION" && (
                      <>
                        <button
                          onClick={() => {
                            setUpdateError(null);
                            setStatusNotes("");
                            setStatusModalOrder({ order, targetStatus: "CONFIRMED" });
                          }}
                          className="px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>Confirm Order</span>
                        </button>
                        <button
                          onClick={() => {
                            setUpdateError(null);
                            setStatusNotes("");
                            setStatusModalOrder({ order, targetStatus: "CANCELLED" });
                          }}
                          className="px-3 py-2 rounded-xl border border-rose-300 text-rose-700 bg-white hover:bg-rose-50 text-xs font-bold transition-colors"
                        >
                          Cancel
                        </button>
                      </>
                    )}

                    {order.status === "CONFIRMED" && (
                      <>
                        <button
                          onClick={() => {
                            setUpdateError(null);
                            setStatusNotes("");
                            setStatusModalOrder({ order, targetStatus: "PROCESSING" });
                          }}
                          className="px-3.5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5"
                        >
                          <Truck className="w-3.5 h-3.5" />
                          <span>Mark Processing</span>
                        </button>
                        <button
                          onClick={() => {
                            setUpdateError(null);
                            setStatusNotes("");
                            setStatusModalOrder({ order, targetStatus: "CANCELLED" });
                          }}
                          className="px-3 py-2 rounded-xl border border-rose-300 text-rose-700 bg-white hover:bg-rose-50 text-xs font-bold transition-colors"
                        >
                          Cancel
                        </button>
                      </>
                    )}

                    {order.status === "PROCESSING" && (
                      <>
                        <button
                          onClick={() => {
                            setUpdateError(null);
                            setStatusNotes("");
                            setStatusModalOrder({ order, targetStatus: "COMPLETED" });
                          }}
                          className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>Mark Completed</span>
                        </button>
                        <button
                          onClick={() => {
                            setUpdateError(null);
                            setStatusNotes("");
                            setStatusModalOrder({ order, targetStatus: "CANCELLED" });
                          }}
                          className="px-3 py-2 rounded-xl border border-rose-300 text-rose-700 bg-white hover:bg-rose-50 text-xs font-bold transition-colors"
                        >
                          Cancel
                        </button>
                      </>
                    )}

                    <button
                      onClick={() => setSelectedOrder(order)}
                      className="px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5"
                    >
                      <FileText className="w-3.5 h-3.5 text-amber-400" />
                      <span>Details</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ========================================================= */}
      {/* SELLER ORDER DETAILS MODAL                                */}
      {/* ========================================================= */}
      {selectedOrder && (
        <div className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
          <div className="bg-white rounded-3xl max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-200">
            {/* Header */}
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
                  Buyer: {selectedOrder.buyer_name} ({selectedOrder.buyer_email}) · Ordered on {new Date(selectedOrder.created_at).toLocaleString("en-GB", { dateStyle: "full", timeStyle: "short" })}
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

            {/* Modal Body */}
            <div className="p-5 sm:p-6 overflow-y-auto space-y-6">
              {/* Order Workflow Progression Banner */}
              <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    Order Fulfillment Lifecycle
                  </span>
                  <span className="text-xs font-bold text-slate-800">
                    Current: {selectedOrder.status}
                  </span>
                </div>

                <div className="grid grid-cols-4 gap-2 pt-1">
                  {[
                    { step: "PENDING_CONFIRMATION", label: "1. Pending" },
                    { step: "CONFIRMED", label: "2. Confirmed" },
                    { step: "PROCESSING", label: "3. Processing" },
                    { step: "COMPLETED", label: "4. Completed" },
                  ].map((s, idx) => {
                    const stepOrder = ["PENDING_CONFIRMATION", "CONFIRMED", "PROCESSING", "COMPLETED"];
                    const currentIdx = stepOrder.indexOf(selectedOrder.status);
                    const thisIdx = idx;
                    const isPassed = currentIdx >= thisIdx && selectedOrder.status !== "CANCELLED";
                    const isCurrent = selectedOrder.status === s.step;

                    return (
                      <div
                        key={s.step}
                        className={`p-2 rounded-xl text-center border text-[11px] font-bold transition-all ${
                          selectedOrder.status === "CANCELLED"
                            ? "bg-slate-100 text-slate-400 border-slate-200"
                            : isCurrent
                            ? "bg-amber-400 text-slate-950 border-amber-400 shadow-sm"
                            : isPassed
                            ? "bg-emerald-50 text-emerald-800 border-emerald-300"
                            : "bg-white text-slate-400 border-slate-200"
                        }`}
                      >
                        {s.label}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Items Breakdown (Seller items only) */}
              <div className="space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <Receipt className="w-3.5 h-3.5" />
                    <span>Your Allocated Items ({selectedOrder.items.length})</span>
                  </span>
                  <span className="text-emerald-700 font-semibold text-[11px]">
                    Multi-Seller Privacy Protected
                  </span>
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
                            {item.hsn_code && (
                              <span className="text-[10px] font-mono text-slate-400">
                                HSN: {item.hsn_code}
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

                      <div className="p-2.5 bg-slate-50 rounded-xl text-[11px] text-slate-600 flex flex-wrap items-center justify-between gap-2">
                        <span>Taxable: {selectedOrder.currency} {Number(item.taxable_amount).toFixed(2)}</span>
                        <span>GST: {Number(item.gst_rate)}%</span>
                        {Number(item.igst_amount) > 0 ? (
                          <span>IGST: +{selectedOrder.currency} {Number(item.igst_amount).toFixed(2)}</span>
                        ) : (
                          <span>CGST: +{selectedOrder.currency} {Number(item.cgst_amount).toFixed(2)} | SGST: +{selectedOrder.currency} {Number(item.sgst_amount).toFixed(2)}</span>
                        )}
                        <span className="font-semibold text-slate-800">
                          Tax Amount: {selectedOrder.currency} {Number(item.tax_amount).toFixed(2)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Delivery Destination & Seller Revenue Summary */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Shipping Details */}
                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                    <MapPin className="w-3.5 h-3.5 text-amber-500" />
                    <span>Customer Shipping Details</span>
                  </h4>
                  <div className="text-xs text-slate-700 space-y-1">
                    <p className="font-black text-slate-900">{selectedOrder.shipping_name}</p>
                    <p className="flex items-center gap-1.5 text-slate-600">
                      <Phone className="w-3 h-3 text-slate-400" />
                      <span>{selectedOrder.shipping_phone}</span>
                    </p>
                    <p className="text-slate-600 pt-1">
                      {selectedOrder.shipping_address_line1}
                      {selectedOrder.shipping_address_line2 && `, ${selectedOrder.shipping_address_line2}`}
                      <br />
                      {selectedOrder.shipping_city}, {selectedOrder.shipping_state} - {selectedOrder.shipping_postal_code}
                      <br />
                      {selectedOrder.shipping_country}
                    </p>
                  </div>
                </div>

                {/* Seller Revenue Summary */}
                <div className="p-4 rounded-2xl bg-slate-900 text-white space-y-2.5">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                    <Receipt className="w-3.5 h-3.5" />
                    <span>Your Allocated Revenue</span>
                  </h4>
                  <div className="space-y-1.5 text-xs text-slate-300">
                    <div className="flex justify-between">
                      <span>Your Taxable Subtotal:</span>
                      <span className="font-mono text-white">
                        {selectedOrder.currency} {Number(selectedOrder.seller_subtotal_taxable_amount).toFixed(2)}
                      </span>
                    </div>

                    {Number(selectedOrder.seller_cgst_amount) > 0 && (
                      <div className="flex justify-between text-slate-400">
                        <span>CGST (Your Items):</span>
                        <span className="font-mono">
                          +{selectedOrder.currency} {Number(selectedOrder.seller_cgst_amount).toFixed(2)}
                        </span>
                      </div>
                    )}
                    {Number(selectedOrder.seller_sgst_amount) > 0 && (
                      <div className="flex justify-between text-slate-400">
                        <span>SGST (Your Items):</span>
                        <span className="font-mono">
                          +{selectedOrder.currency} {Number(selectedOrder.seller_sgst_amount).toFixed(2)}
                        </span>
                      </div>
                    )}
                    {Number(selectedOrder.seller_igst_amount) > 0 && (
                      <div className="flex justify-between text-slate-400">
                        <span>IGST (Your Items):</span>
                        <span className="font-mono">
                          +{selectedOrder.currency} {Number(selectedOrder.seller_igst_amount).toFixed(2)}
                        </span>
                      </div>
                    )}

                    <div className="flex justify-between text-amber-400 font-semibold pt-1 border-t border-slate-800">
                      <span>Total Statutory GST:</span>
                      <span className="font-mono">
                        +{selectedOrder.currency} {Number(selectedOrder.seller_total_tax_amount).toFixed(2)}
                      </span>
                    </div>

                    <div className="flex justify-between items-baseline pt-2 border-t border-slate-800">
                      <span className="text-sm font-black text-white">Your Net Total:</span>
                      <span className="text-xl font-black text-amber-400 font-mono">
                        {selectedOrder.currency} {Number(selectedOrder.seller_total_amount).toFixed(2)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Footer Actions */}
            <div className="p-4 sm:p-5 bg-slate-50 border-t border-slate-200 flex flex-wrap items-center justify-between gap-3 shrink-0">
              <div className="flex items-center gap-2">
                {selectedOrder.status === "PENDING_CONFIRMATION" && (
                  <>
                    <button
                      onClick={() => {
                        setUpdateError(null);
                        setStatusNotes("");
                        setStatusModalOrder({ order: selectedOrder, targetStatus: "CONFIRMED" });
                      }}
                      className="px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Confirm Order</span>
                    </button>
                    <button
                      onClick={() => {
                        setUpdateError(null);
                        setStatusNotes("");
                        setStatusModalOrder({ order: selectedOrder, targetStatus: "CANCELLED" });
                      }}
                      className="px-4 py-2.5 rounded-xl border border-rose-300 text-rose-700 bg-white hover:bg-rose-50 text-xs font-bold transition-colors"
                    >
                      Cancel Order
                    </button>
                  </>
                )}

                {selectedOrder.status === "CONFIRMED" && (
                  <>
                    <button
                      onClick={() => {
                        setUpdateError(null);
                        setStatusNotes("");
                        setStatusModalOrder({ order: selectedOrder, targetStatus: "PROCESSING" });
                      }}
                      className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5"
                    >
                      <Truck className="w-3.5 h-3.5" />
                      <span>Start Processing / Dispatch</span>
                    </button>
                    <button
                      onClick={() => {
                        setUpdateError(null);
                        setStatusNotes("");
                        setStatusModalOrder({ order: selectedOrder, targetStatus: "CANCELLED" });
                      }}
                      className="px-4 py-2.5 rounded-xl border border-rose-300 text-rose-700 bg-white hover:bg-rose-50 text-xs font-bold transition-colors"
                    >
                      Cancel Order
                    </button>
                  </>
                )}

                {selectedOrder.status === "PROCESSING" && (
                  <>
                    <button
                      onClick={() => {
                        setUpdateError(null);
                        setStatusNotes("");
                        setStatusModalOrder({ order: selectedOrder, targetStatus: "COMPLETED" });
                      }}
                      className="px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Mark Delivered / Completed</span>
                    </button>
                    <button
                      onClick={() => {
                        setUpdateError(null);
                        setStatusNotes("");
                        setStatusModalOrder({ order: selectedOrder, targetStatus: "CANCELLED" });
                      }}
                      className="px-4 py-2.5 rounded-xl border border-rose-300 text-rose-700 bg-white hover:bg-rose-50 text-xs font-bold transition-colors"
                    >
                      Cancel Order
                    </button>
                  </>
                )}
              </div>

              <button
                onClick={() => setSelectedOrder(null)}
                className="px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-all shadow-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* STATUS TRANSITION CONFIRMATION MODAL                      */}
      {/* ========================================================= */}
      {statusModalOrder && (
        <div className="fixed inset-0 z-60 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center gap-3">
              <div
                className={`w-10 h-10 rounded-2xl flex items-center justify-center shrink-0 ${
                  statusModalOrder.targetStatus === "CANCELLED"
                    ? "bg-rose-100 text-rose-600"
                    : statusModalOrder.targetStatus === "COMPLETED"
                    ? "bg-emerald-100 text-emerald-600"
                    : "bg-blue-100 text-blue-600"
                }`}
              >
                {statusModalOrder.targetStatus === "CANCELLED" ? (
                  <AlertTriangle className="w-5 h-5" />
                ) : (
                  <CheckCircle2 className="w-5 h-5" />
                )}
              </div>
              <div>
                <h3 className="text-base font-black text-slate-900">
                  {statusModalOrder.targetStatus === "CANCELLED"
                    ? `Cancel Order ${statusModalOrder.order.order_number}?`
                    : `Update Status to ${statusModalOrder.targetStatus}`}
                </h3>
                <p className="text-xs text-slate-500">
                  Order: {statusModalOrder.order.order_number}
                </p>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              {statusModalOrder.targetStatus === "CONFIRMED" &&
                "Confirming this order locks the allocation and signals the buyer that the order has been accepted."}
              {statusModalOrder.targetStatus === "PROCESSING" &&
                "Advancing to Processing indicates package preparation and pending courier dispatch."}
              {statusModalOrder.targetStatus === "COMPLETED" &&
                "Marking as Completed finalizes the order fulfillment process."}
              {statusModalOrder.targetStatus === "CANCELLED" &&
                "Cancelling will abort this order and automatically restock all allocated items back to your inventory."}
            </p>

            <div className="space-y-1.5">
              <label className="text-[11px] font-bold text-slate-700 block">
                Fulfillment Notes (Optional)
              </label>
              <textarea
                value={statusNotes}
                onChange={(e) => setStatusNotes(e.target.value)}
                placeholder="Add optional dispatch tracking or cancellation reason..."
                rows={2}
                className="w-full p-3 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-amber-400 focus:border-transparent transition-all"
              />
            </div>

            {updateError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs">
                {updateError}
              </div>
            )}

            <div className="flex items-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => setStatusModalOrder(null)}
                disabled={isUpdatingStatus}
                className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-bold transition-colors"
              >
                Dismiss
              </button>
              <button
                type="button"
                onClick={handleStatusUpdate}
                disabled={isUpdatingStatus}
                className={`flex-1 py-2.5 rounded-xl text-white text-xs font-bold transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50 ${
                  statusModalOrder.targetStatus === "CANCELLED"
                    ? "bg-rose-600 hover:bg-rose-700"
                    : statusModalOrder.targetStatus === "COMPLETED"
                    ? "bg-emerald-600 hover:bg-emerald-700"
                    : "bg-slate-900 hover:bg-slate-800"
                }`}
              >
                {isUpdatingStatus ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Updating...</span>
                  </>
                ) : (
                  <span>Confirm Status</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
