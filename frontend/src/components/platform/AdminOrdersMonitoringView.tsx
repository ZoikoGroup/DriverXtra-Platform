"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  api,
  AdminOrderItem,
} from "@/lib/api/client";
import {
  Search,
  RefreshCw,
  Eye,
  ShoppingBag,
  Package,
  CreditCard,
  Mail,
  ChevronLeft,
  ChevronRight,
  X,
  Clock,
  CheckCircle2,
  AlertCircle,
  Truck,
  Building2,
  AlertTriangle,
  Car,
  Wrench,
} from "lucide-react";

export default function AdminOrdersMonitoringView() {
  const [orders, setOrders] = useState<AdminOrderItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(20);

  const [searchQuery, setSearchQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [orderTypeFilter, setOrderTypeFilter] = useState<string>("ALL");
  const [ordering, setOrdering] = useState<string>("-created_at");

  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Detail Drawer state
  const [selectedOrder, setSelectedOrder] = useState<AdminOrderItem | null>(null);

  const fetchOrders = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const res = await api.admin.orders.list({
        page: currentPage,
        page_size: pageSize,
        q: searchQuery.trim() || undefined,
        status: statusFilter !== "ALL" ? statusFilter : undefined,
        order_type: orderTypeFilter !== "ALL" ? orderTypeFilter : undefined,
        ordering,
      });

      setOrders(res.results || []);
      setTotalCount(res.count || 0);
      setTotalPages(res.total_pages || 1);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load orders monitoring data from backend.");
      setOrders([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [currentPage, pageSize, searchQuery, statusFilter, orderTypeFilter, ordering]);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

  const getOrderStatusBadge = (status: string) => {
    const s = (status || "").toUpperCase();
    switch (s) {
      case "DELIVERED":
      case "COMPLETED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5" />
            {s === "DELIVERED" ? "Delivered" : "Completed"}
          </span>
        );
      case "SHIPPED":
      case "READY_FOR_HANDOVER":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
            <Truck className="w-3.5 h-3.5" />
            {s === "SHIPPED" ? "Shipped" : "Ready for Handover"}
          </span>
        );
      case "PAID":
      case "CONFIRMED":
      case "PAYMENT_CONFIRMED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-cyan-50 text-cyan-800 border border-cyan-200">
            <CreditCard className="w-3.5 h-3.5" />
            Confirmed
          </span>
        );
      case "PENDING":
      case "PENDING_CONFIRMATION":
      case "PAYMENT_PENDING":
      case "DOCUMENTS_PENDING":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-300">
            <Clock className="w-3.5 h-3.5" />
            {s.replace(/_/g, " ")}
          </span>
        );
      case "CANCELLED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <AlertCircle className="w-3.5 h-3.5" />
            Cancelled
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            {status}
          </span>
        );
    }
  };

  const getOrderTypeBadge = (orderType: string) => {
    const isVehicle = (orderType || "").toUpperCase().includes("VEHICLE");
    if (isVehicle) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-bold uppercase tracking-wider bg-indigo-50 text-indigo-700 border border-indigo-200">
          <Car className="w-3 h-3 text-indigo-600" />
          Vehicle
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-bold uppercase tracking-wider bg-amber-50 text-amber-800 border border-amber-200">
        <Wrench className="w-3 h-3 text-amber-600" />
        Spare Part
      </span>
    );
  };

  const getPaymentStatusBadge = (status: string) => {
    const s = (status || "").toUpperCase();
    if (s === "PAID" || s === "COMPLETED") {
      return (
        <span className="font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded text-[11px] border border-emerald-200">
          Paid
        </span>
      );
    }
    if (s === "REFUNDED") {
      return (
        <span className="font-semibold text-purple-700 bg-purple-50 px-2 py-0.5 rounded text-[11px] border border-purple-200">
          Refunded
        </span>
      );
    }
    if (s === "SUBMITTED") {
      return (
        <span className="font-semibold text-blue-700 bg-blue-50 px-2 py-0.5 rounded text-[11px] border border-blue-200">
          Submitted
        </span>
      );
    }
    return (
      <span className="font-semibold text-amber-800 bg-amber-50 px-2 py-0.5 rounded text-[11px] border border-amber-300">
        {status || "Pending"}
      </span>
    );
  };

  return (
    <div className="p-6 md:p-8 space-y-6 max-w-7xl mx-auto text-slate-900 bg-slate-100 min-h-screen">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-slate-900">
            Customer Orders Monitoring
          </h1>
          <p className="text-sm font-medium text-slate-600 mt-1">
            Platform-wide governance view of motor vehicle orders, spare part purchases, fulfillment tracking, and seller breakdowns.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchOrders(true)}
            disabled={refreshing}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-slate-800 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 shadow-sm hover:border-slate-400 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin text-amber-600" : "text-slate-600"}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error Alert Banner */}
      {error && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-300 text-red-900 text-sm flex items-center justify-between shadow-sm">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-600 shrink-0" />
            <div>
              <p className="font-bold text-red-900">Unable to load customer orders</p>
              <p className="text-xs text-red-700 mt-0.5">{error}</p>
            </div>
          </div>
          <button
            onClick={() => fetchOrders()}
            className="px-3 py-1.5 text-xs font-semibold bg-red-600 text-white rounded-lg hover:bg-red-700 shadow-sm transition-colors"
          >
            Try Again
          </button>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
          {/* Search */}
          <div className="md:col-span-5 relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
            <input
              type="text"
              placeholder="Search by order #, buyer, seller, product, or VIN/MPN..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full pl-9 pr-4 py-2 text-xs bg-slate-50 border border-slate-300 rounded-lg text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-amber-500 font-medium"
            />
          </div>

          {/* Order Type Filter */}
          <div className="md:col-span-2">
            <select
              value={orderTypeFilter}
              onChange={(e) => {
                setOrderTypeFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full px-3 py-2 text-xs font-semibold bg-slate-50 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              <option value="ALL">All Order Types</option>
              <option value="VEHICLE">Motor Vehicles</option>
              <option value="SPARE_PART">Spare Parts</option>
            </select>
          </div>

          {/* Status Filter */}
          <div className="md:col-span-2">
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full px-3 py-2 text-xs font-semibold bg-slate-50 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              <option value="ALL">All Statuses</option>
              <option value="PENDING">Pending</option>
              <option value="CONFIRMED">Confirmed</option>
              <option value="PAID">Paid</option>
              <option value="SHIPPED">Shipped</option>
              <option value="DELIVERED">Delivered</option>
              <option value="CANCELLED">Cancelled</option>
            </select>
          </div>

          {/* Sorter */}
          <div className="md:col-span-3">
            <select
              value={ordering}
              onChange={(e) => {
                setOrdering(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full px-3 py-2 text-xs font-semibold bg-slate-50 border border-slate-300 rounded-lg text-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              <option value="-created_at">Date: Newest First</option>
              <option value="created_at">Date: Oldest First</option>
              <option value="-total_amount">Amount: Highest First</option>
              <option value="total_amount">Amount: Lowest First</option>
            </select>
          </div>
        </div>

        {/* Page size and counter */}
        <div className="flex flex-wrap items-center justify-between text-xs text-slate-600 pt-2 border-t border-slate-100">
          <div className="flex items-center gap-2 font-medium">
            <span>Showing records:</span>
            <span className="font-bold text-slate-900">
              {totalCount > 0 ? (currentPage - 1) * pageSize + 1 : 0} -{" "}
              {Math.min(currentPage * pageSize, totalCount)}
            </span>
            <span>of</span>
            <span className="font-bold text-slate-900">{totalCount}</span>
            <span>platform orders</span>
          </div>

          <div className="flex items-center gap-2">
            <span className="font-medium">Rows per page:</span>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setCurrentPage(1);
              }}
              className="px-2 py-1 text-xs font-semibold bg-slate-50 border border-slate-300 rounded text-slate-800 focus:outline-none"
            >
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>
        </div>
      </div>

      {/* Table Section */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-700">
            <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wider text-slate-600 border-b border-slate-200">
              <tr>
                <th scope="col" className="px-5 py-3.5">
                  Order & Type
                </th>
                <th scope="col" className="px-5 py-3.5">
                  Buyer Information
                </th>
                <th scope="col" className="px-5 py-3.5">
                  Fulfilling Seller
                </th>
                <th scope="col" className="px-5 py-3.5">
                  Product Details
                </th>
                <th scope="col" className="px-5 py-3.5">
                  Amount
                </th>
                <th scope="col" className="px-5 py-3.5">
                  Status & Payment
                </th>
                <th scope="col" className="px-5 py-3.5">
                  Date
                </th>
                <th scope="col" className="px-5 py-3.5 text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 font-medium">
              {loading && orders.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-14 text-center text-slate-500">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-amber-500" />
                    <span className="text-xs font-semibold">Loading platform customer orders...</span>
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td colSpan={8} className="px-6 py-14 text-center text-red-600">
                    <AlertTriangle className="w-8 h-8 mx-auto mb-2 text-red-500" />
                    <div className="text-sm font-bold text-slate-900">Failed to load orders data</div>
                    <p className="text-xs text-slate-500 mt-1">{error}</p>
                    <button
                      onClick={() => fetchOrders()}
                      className="mt-3 px-3 py-1 text-xs font-semibold bg-red-600 text-white rounded-lg hover:bg-red-700 shadow-sm transition"
                    >
                      Retry Loading
                    </button>
                  </td>
                </tr>
              ) : orders.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-14 text-center text-slate-500">
                    <ShoppingBag className="w-8 h-8 mx-auto mb-2 text-slate-300" />
                    <div className="text-sm font-bold text-slate-900">No customer orders found</div>
                    <p className="text-xs text-slate-500 mt-1">Try clearing search or adjusting your status/type filters.</p>
                  </td>
                </tr>
              ) : (
                orders.map((ord) => (
                  <tr
                    key={ord.id}
                    className="hover:bg-slate-50 transition-colors"
                  >
                    {/* Order Number & Type */}
                    <td className="px-5 py-4">
                      <div className="font-extrabold text-slate-900 text-sm">
                        {ord.order_number}
                      </div>
                      <div className="mt-1">
                        {getOrderTypeBadge(ord.order_type)}
                      </div>
                    </td>

                    {/* Buyer Information */}
                    <td className="px-5 py-4">
                      <div className="font-bold text-slate-900 text-xs">
                        {ord.buyer.full_name || "Customer"}
                      </div>
                      <div className="text-xs text-slate-500 flex items-center gap-1 mt-0.5">
                        <Mail className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span className="truncate max-w-[150px]">{ord.buyer.email}</span>
                      </div>
                    </td>

                    {/* Fulfilling Seller */}
                    <td className="px-5 py-4">
                      <div className="font-semibold text-slate-900 text-xs">
                        {ord.seller?.full_name || ord.items_preview?.[0]?.seller_name || "Multiple / Direct"}
                      </div>
                      <div className="text-[11px] text-slate-500 truncate max-w-[150px] mt-0.5">
                        {ord.seller?.email || ord.items_preview?.[0]?.seller_email || "Platform"}
                      </div>
                    </td>

                    {/* Product Details */}
                    <td className="px-5 py-4">
                      <div className="text-xs max-w-[220px]">
                        <div className="font-bold text-slate-900 truncate">
                          {ord.items_preview?.[0]?.title || "Product Purchase"}
                        </div>
                        <div className="text-[11px] text-slate-500 mt-0.5 flex items-center gap-1">
                          {ord.items_preview?.[0]?.part_number && (
                            <span className="font-mono bg-slate-100 px-1 py-0.5 rounded text-[10px] text-slate-700">
                              {ord.items_preview[0].part_number}
                            </span>
                          )}
                          {ord.item_count > 1 && (
                            <span className="text-blue-600 font-semibold text-[10px]">
                              +{ord.item_count - 1} more items
                            </span>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Amount */}
                    <td className="px-5 py-4">
                      <div className="font-extrabold text-slate-900 text-sm">
                        {ord.currency} {ord.total_amount}
                      </div>
                    </td>

                    {/* Status & Payment */}
                    <td className="px-5 py-4">
                      <div className="space-y-1">
                        <div>{getOrderStatusBadge(ord.status)}</div>
                        <div className="text-[11px] text-slate-500 flex items-center gap-1">
                          Payment: {getPaymentStatusBadge(ord.payment_status)}
                        </div>
                      </div>
                    </td>

                    {/* Date */}
                    <td className="px-5 py-4 text-xs font-medium text-slate-600">
                      {ord.created_at ? (
                        new Date(ord.created_at).toLocaleDateString("en-US", {
                          year: "numeric",
                          month: "short",
                          day: "numeric",
                        })
                      ) : (
                        "—"
                      )}
                    </td>

                    {/* Actions */}
                    <td className="px-5 py-4 text-right">
                      <button
                        onClick={() => setSelectedOrder(ord)}
                        className="px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-300 rounded-lg shadow-sm hover:border-slate-400 transition-colors inline-flex items-center gap-1"
                        title="Inspect Complete Order Breakdown"
                      >
                        <Eye className="w-3.5 h-3.5 text-slate-600" />
                        <span>Inspect</span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Server-Side Pagination Bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 border-t border-slate-200 bg-slate-50 text-xs text-slate-600">
          <div>
            Page <span className="font-bold text-slate-900">{currentPage}</span> of{" "}
            <span className="font-bold text-slate-900">{totalPages}</span> ({totalCount} total orders)
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage <= 1 || loading}
              className="px-3 py-1.5 font-semibold text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors inline-flex items-center gap-1"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              Previous
            </button>

            {Array.from({ length: Math.min(5, totalPages) }, (_, idx) => {
              let pageNum = idx + 1;
              if (totalPages > 5 && currentPage > 3) {
                pageNum = Math.min(currentPage - 3 + idx + 1, totalPages);
              }
              return (
                <button
                  key={pageNum}
                  onClick={() => setCurrentPage(pageNum)}
                  disabled={loading}
                  className={`w-8 h-8 font-bold rounded-lg transition-colors ${
                    currentPage === pageNum
                      ? "bg-amber-500 text-slate-950 shadow-sm"
                      : "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  {pageNum}
                </button>
              );
            })}

            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage >= totalPages || loading}
              className="px-3 py-1.5 font-semibold text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors inline-flex items-center gap-1"
            >
              Next
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Inspect Order Detail Drawer */}
      {selectedOrder && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-slate-900/60 backdrop-blur-sm flex justify-end">
          <div className="w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col border-l border-slate-200">
            {/* Drawer Header */}
            <div className="p-6 border-b border-slate-200 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xl font-extrabold text-slate-900 flex items-center gap-2">
                    <ShoppingBag className="w-5 h-5 text-amber-500" />
                    Order #{selectedOrder.order_number}
                  </h3>
                  {getOrderTypeBadge(selectedOrder.order_type)}
                </div>
                <p className="text-xs font-mono text-slate-500 mt-1">
                  ID: {selectedOrder.id}
                </p>
              </div>
              <button
                onClick={() => setSelectedOrder(null)}
                className="p-2 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Order summary banner */}
              <div className="p-5 rounded-xl bg-slate-50 border border-slate-200 space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div>
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-500 block">Total Order Amount</span>
                    <span className="text-2xl font-extrabold text-slate-900">
                      {selectedOrder.currency} {selectedOrder.total_amount}
                    </span>
                  </div>
                  <div>{getOrderStatusBadge(selectedOrder.status)}</div>
                </div>

                <div className="grid grid-cols-2 gap-4 text-xs pt-3 border-t border-slate-200">
                  <div>
                    <span className="text-slate-500 font-semibold block">Buyer Name:</span>
                    <span className="font-bold text-slate-900 text-sm">
                      {selectedOrder.buyer.full_name || "Guest Customer"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 font-semibold block">Buyer Contact:</span>
                    <span className="font-bold text-slate-900">
                      {selectedOrder.buyer.email}
                    </span>
                    {selectedOrder.buyer.phone_number && (
                      <span className="text-slate-500 block text-[11px] mt-0.5">
                        {selectedOrder.buyer.phone_number}
                      </span>
                    )}
                  </div>
                  <div>
                    <span className="text-slate-500 font-semibold block">Fulfilling Seller:</span>
                    <span className="font-bold text-slate-900">
                      {selectedOrder.seller?.full_name || selectedOrder.items_preview?.[0]?.seller_name || "Direct Marketplace"}
                    </span>
                    <span className="text-slate-500 block text-[11px] mt-0.5">
                      {selectedOrder.seller?.email || selectedOrder.items_preview?.[0]?.seller_email || "Direct"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 font-semibold block">Payment & Fulfilment:</span>
                    <div className="flex items-center gap-1.5 mt-1">
                      {getPaymentStatusBadge(selectedOrder.payment_status)}
                      <span className="text-slate-400 font-bold">·</span>
                      <span className="text-slate-700 font-semibold text-xs">
                        {selectedOrder.fulfilment_status || selectedOrder.status}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="text-xs text-slate-500 pt-2 border-t border-slate-200 flex items-center justify-between">
                  <span>Order Placed: {selectedOrder.created_at ? new Date(selectedOrder.created_at).toLocaleString() : "—"}</span>
                  <span className="font-mono bg-white px-2 py-0.5 rounded border border-slate-200 text-[11px]">
                    Method: {selectedOrder.payment_method || "ONLINE"}
                  </span>
                </div>
              </div>

              {/* Order Items Breakdown */}
              <div className="space-y-3">
                <h4 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <Package className="w-4 h-4 text-blue-600" />
                  Product Breakdown ({selectedOrder.item_count} {selectedOrder.item_count === 1 ? "item" : "items"})
                </h4>

                <div className="space-y-3">
                  {selectedOrder.items_preview && selectedOrder.items_preview.length > 0 ? (
                    selectedOrder.items_preview.map((item, idx) => (
                      <div
                        key={item.id || idx}
                        className="p-4 rounded-xl border border-slate-200 bg-white shadow-sm space-y-3"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="font-bold text-slate-900 text-sm">
                              {item.title}
                            </div>
                            <div className="text-xs text-slate-500 mt-1 flex items-center gap-2 flex-wrap">
                              {item.brand && (
                                <span className="font-semibold text-slate-700 bg-slate-100 px-2 py-0.5 rounded text-[11px]">
                                  {item.brand}
                                </span>
                              )}
                              {item.part_number && (
                                <span className="font-mono text-slate-600 bg-slate-50 px-2 py-0.5 rounded border border-slate-200 text-[11px]">
                                  Ref / MPN: {item.part_number}
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="text-right shrink-0">
                            <div className="font-extrabold text-slate-900 text-base">
                              {selectedOrder.currency} {item.total_price}
                            </div>
                            <div className="text-xs font-medium text-slate-500 mt-0.5">
                              {item.quantity} × {selectedOrder.currency} {item.unit_price}
                            </div>
                          </div>
                        </div>

                        <div className="pt-2.5 border-t border-slate-100 flex items-center justify-between text-xs text-slate-600">
                          <span className="flex items-center gap-1 font-medium">
                            <Building2 className="w-3.5 h-3.5 text-slate-400" />
                            Fulfilling Seller:
                          </span>
                          <span className="font-bold text-slate-900">
                            {item.seller_email || selectedOrder.seller?.email || "Platform Managed"}
                          </span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="p-6 text-center text-slate-500 text-xs bg-slate-50 rounded-xl border border-slate-200">
                      No line items preview available for this order.
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Drawer Footer Actions */}
            <div className="p-4 border-t border-slate-200 bg-slate-50 flex items-center justify-end gap-3">
              <button
                onClick={() => setSelectedOrder(null)}
                className="px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-200 bg-white border border-slate-300 rounded-lg shadow-sm transition-colors"
              >
                Close Drawer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
