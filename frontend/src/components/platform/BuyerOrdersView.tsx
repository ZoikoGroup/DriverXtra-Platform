"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  api,
  PlatformOrder,
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
  ShieldAlert,
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
  const [orders, setOrders] = useState<PlatformOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<OrderStatusFilter>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedOrder, setSelectedOrder] = useState<PlatformOrder | null>(null);

  // Cancellation state
  const [cancelModalOrder, setCancelModalOrder] = useState<PlatformOrder | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  // Copy feedback
  const [copiedId, setCopiedId] = useState<string | null>(null);

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

  useEffect(() => {
    let ignore = false;
    Promise.resolve().then(() => {
      if (!ignore) {
        loadOrders();
      }
    });
    return () => {
      ignore = true;
    };
  }, [loadOrders]);

  // Set initial selected order if supplied
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

  const handleCancelOrder = async () => {
    if (!cancelModalOrder) return;
    setIsCancelling(true);
    setCancelError(null);
    try {
      const res = await api.marketplace.cancelBuyerOrder(cancelModalOrder.id);
      if (res.status === "success" && res.order) {
        // Update local orders list
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
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to cancel order. Please try again.";
      setCancelError(msg);
    } finally {
      setIsCancelling(false);
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

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-amber-950 text-white rounded-2xl p-6 sm:p-8 shadow-xl relative overflow-hidden border border-slate-800">
        <div className="relative z-10 space-y-2">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-amber-400 text-slate-950 flex items-center justify-center font-black">
              <Package className="w-4 h-4" />
            </div>
            <span className="text-xs font-bold text-amber-400 tracking-wider uppercase">
              Phase 4 Marketplace
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white">
            My Orders & Purchase History
          </h1>
          <p className="text-xs sm:text-sm text-slate-300 max-w-2xl leading-relaxed">
            Track your order statuses, review line items with statutory tax breakdowns, inspect shipping addresses, and manage cancellations before dispatch.
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
          { id: "PENDING_CONFIRMATION", label: "Pending", count: counts.pending, color: "hover:border-amber-400" },
          { id: "CONFIRMED", label: "Confirmed", count: counts.confirmed, color: "hover:border-blue-400" },
          { id: "PROCESSING", label: "Processing", count: counts.processing, color: "hover:border-indigo-400" },
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
            placeholder="Search by order #, part title, brand, or city..."
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
            onClick={loadOrders}
            disabled={loading}
            className="px-3.5 py-2.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold flex items-center gap-2 transition-colors shadow-xs disabled:opacity-50"
            title="Refresh orders list"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
          {onNavigateToBrowse && (
            <button
              onClick={onNavigateToBrowse}
              className="px-4 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-black flex items-center gap-1.5 transition-all shadow-md"
            >
              <ShoppingBag className="w-3.5 h-3.5" />
              <span>Browse Marketplace</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Content Area */}
      {loading ? (
        <div className="py-20 flex flex-col items-center justify-center space-y-3 bg-white rounded-2xl border border-slate-200">
          <Loader2 className="w-8 h-8 text-amber-500 animate-spin" />
          <span className="text-xs font-bold text-slate-600">Loading your purchase history...</span>
        </div>
      ) : error ? (
        <div className="p-8 bg-rose-50 border border-rose-200 rounded-2xl text-center space-y-3">
          <AlertCircle className="w-10 h-10 text-rose-500 mx-auto" />
          <h3 className="text-sm font-bold text-rose-900">Failed to Load Orders</h3>
          <p className="text-xs text-rose-700 max-w-md mx-auto">{error}</p>
          <button
            onClick={loadOrders}
            className="px-4 py-2 bg-rose-600 text-white text-xs font-bold rounded-xl hover:bg-rose-700 transition-colors"
          >
            Try Again
          </button>
        </div>
      ) : filteredOrders.length === 0 ? (
        <div className="py-20 bg-white rounded-2xl border border-slate-200 text-center space-y-4 p-6">
          <div className="w-16 h-16 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
            <Package className="w-8 h-8" />
          </div>
          <div className="space-y-1 max-w-sm mx-auto">
            <h3 className="text-base font-black text-slate-900">No Orders Found</h3>
            <p className="text-xs text-slate-500">
              {searchQuery || statusFilter !== "ALL"
                ? "No orders match your active filter and search criteria. Try resetting filters."
                : "You have not placed any orders yet. Browse our verified spare parts catalogue to make your first purchase."}
            </p>
          </div>
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
                </div>

                <div className="flex items-center gap-2">
                  {getStatusBadge(order.status)}
                </div>
              </div>

              {/* Order Items Preview */}
              <div className="space-y-2">
                <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Items ({order.items.length})
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
                          {item.seller_name && (
                            <span className="text-[10px] text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded font-medium shrink-0">
                              Seller: {item.seller_name}
                            </span>
                          )}
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
              <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-4 bg-slate-50/50 -mx-5 -mb-5 p-4 rounded-b-2xl">
                <div className="text-xs text-slate-600 flex items-center gap-2">
                  <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <span className="truncate max-w-xs sm:max-w-md">
                    Deliver to: <strong>{order.shipping_name}</strong> · {order.shipping_city}, {order.shipping_state}
                  </span>
                </div>

                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">
                      Total (Incl. GST)
                    </span>
                    <span className="font-mono font-black text-base text-slate-900">
                      {order.currency} {Number(order.total_amount).toFixed(2)}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    {order.status === "PENDING_CONFIRMATION" && (
                      <button
                        onClick={() => {
                          setCancelError(null);
                          setCancelModalOrder(order);
                        }}
                        className="px-3 py-2 rounded-xl border border-rose-200 text-rose-700 hover:bg-rose-50 text-xs font-bold transition-colors"
                      >
                        Cancel
                      </button>
                    )}
                    <button
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
                      "Your order has been recorded and is currently awaiting seller confirmation. You may cancel this order at any time before it is confirmed."}
                    {selectedOrder.status === "CONFIRMED" &&
                      "The seller has confirmed your order. Inventory has been allocated and the package is being prepped."}
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
                            {item.hsn_code && (
                              <span className="text-[10px] font-mono text-slate-400">
                                HSN: {item.hsn_code}
                              </span>
                            )}
                          </div>
                          <h5 className="text-sm font-bold text-slate-900">{item.title}</h5>
                          {item.seller_name && (
                            <p className="text-xs text-slate-500">
                              Fulfilled by seller: <strong className="text-slate-800">{item.seller_name}</strong>
                            </p>
                          )}
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

                      {/* Tax Details Line */}
                      <div className="p-2.5 bg-slate-50 rounded-xl text-[11px] text-slate-600 flex flex-wrap items-center justify-between gap-2">
                        <span>Taxable Value: {selectedOrder.currency} {Number(item.taxable_amount).toFixed(2)}</span>
                        <span>GST Rate: {Number(item.gst_rate)}%</span>
                        {Number(item.igst_amount) > 0 ? (
                          <span>IGST: +{selectedOrder.currency} {Number(item.igst_amount).toFixed(2)}</span>
                        ) : (
                          <span>CGST: +{selectedOrder.currency} {Number(item.cgst_amount).toFixed(2)} | SGST: +{selectedOrder.currency} {Number(item.sgst_amount).toFixed(2)}</span>
                        )}
                        <span className="font-semibold text-slate-800">
                          Total Tax: {selectedOrder.currency} {Number(item.tax_amount).toFixed(2)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Delivery Details & Financial Recap */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Shipping Card */}
                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                    <MapPin className="w-3.5 h-3.5 text-amber-500" />
                    <span>Shipping & Delivery Destination</span>
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
                    {selectedOrder.place_of_supply && (
                      <p className="text-[10px] text-slate-400 pt-1 font-mono">
                        Place of supply: {selectedOrder.place_of_supply}
                      </p>
                    )}
                  </div>
                </div>

                {/* Financial Summary Card */}
                <div className="p-4 rounded-2xl bg-slate-900 text-white space-y-2.5">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                    <Receipt className="w-3.5 h-3.5" />
                    <span>Statutory Financial Summary</span>
                  </h4>
                  <div className="space-y-1.5 text-xs text-slate-300">
                    <div className="flex justify-between">
                      <span>Subtotal (Taxable):</span>
                      <span className="font-mono text-white">
                        {selectedOrder.currency} {Number(selectedOrder.subtotal_taxable_amount).toFixed(2)}
                      </span>
                    </div>

                    {Number(selectedOrder.cgst_amount) > 0 && (
                      <div className="flex justify-between text-slate-400">
                        <span>Central GST (CGST):</span>
                        <span className="font-mono">
                          +{selectedOrder.currency} {Number(selectedOrder.cgst_amount).toFixed(2)}
                        </span>
                      </div>
                    )}
                    {Number(selectedOrder.sgst_amount) > 0 && (
                      <div className="flex justify-between text-slate-400">
                        <span>State GST (SGST):</span>
                        <span className="font-mono">
                          +{selectedOrder.currency} {Number(selectedOrder.sgst_amount).toFixed(2)}
                        </span>
                      </div>
                    )}
                    {Number(selectedOrder.igst_amount) > 0 && (
                      <div className="flex justify-between text-slate-400">
                        <span>Integrated GST (IGST):</span>
                        <span className="font-mono">
                          +{selectedOrder.currency} {Number(selectedOrder.igst_amount).toFixed(2)}
                        </span>
                      </div>
                    )}

                    <div className="flex justify-between text-amber-400 font-semibold pt-1 border-t border-slate-800">
                      <span>Total Statutory Taxes:</span>
                      <span className="font-mono">
                        +{selectedOrder.currency} {Number(selectedOrder.total_tax_amount).toFixed(2)}
                      </span>
                    </div>

                    <div className="flex justify-between items-baseline pt-2 border-t border-slate-800">
                      <span className="text-sm font-black text-white">Grand Total:</span>
                      <span className="text-xl font-black text-amber-400 font-mono">
                        {selectedOrder.currency} {Number(selectedOrder.total_amount).toFixed(2)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 sm:p-5 bg-slate-50 border-t border-slate-200 flex items-center justify-between gap-3 shrink-0">
              <div>
                {selectedOrder.status === "PENDING_CONFIRMATION" && (
                  <button
                    onClick={() => {
                      setCancelError(null);
                      setCancelModalOrder(selectedOrder);
                    }}
                    className="px-4 py-2.5 rounded-xl border border-rose-300 text-rose-700 bg-white hover:bg-rose-50 text-xs font-bold transition-colors shadow-xs"
                  >
                    Cancel Order
                  </button>
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
      {/* CANCELLATION CONFIRMATION MODAL                           */}
      {/* ========================================================= */}
      {cancelModalOrder && (
        <div className="fixed inset-0 z-60 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
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
