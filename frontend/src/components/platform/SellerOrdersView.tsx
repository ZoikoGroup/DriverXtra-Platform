"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  api,
  SellerOrder,
  PlatformOrderItem,
  PlatformShipment,
  CarrierOption,
  PlatformReturnRequest,
  PlatformRefund,
  PlatformDispute,
  PlatformDisputeEvent,
} from "@/lib/api/client";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  Package,
  Clock,
  CheckCircle2,
  XCircle,
  Truck,
  RotateCcw,
  AlertTriangle,
  Phone,
  Copy,
  Check,
  Calendar,
  Search,
  MapPin,
  Receipt,
  FileText,
  AlertCircle,
  X,
  Loader2,
  Boxes,
  CreditCard,
  Banknote,
  Plus,
  ExternalLink,
  Navigation,
  Send,
  Scale,
  MessageSquare,
} from "lucide-react";

interface SellerOrdersViewProps {
  initialOrderId?: string;
  initialMainTab?: "orders" | "returns" | "disputes";
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
  initialMainTab,
}: SellerOrdersViewProps) {
  const { user } = useAuth();
  const activeRole = user?.activeRole || (user?.rawRoles && user?.rawRoles[0]) || "BUYER";
  const isAdmin = activeRole === "ADMIN" || activeRole === "STAFF" || Boolean(user?.is_staff || user?.is_superuser);
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

  // Shipment creation state
  const [createShipmentOrder, setCreateShipmentOrder] = useState<SellerOrder | null>(null);
  const [carriers, setCarriers] = useState<CarrierOption[]>([]);
  const [loadingCarriers, setLoadingCarriers] = useState(false);
  const [carrierCode, setCarrierCode] = useState("");
  const [customCarrierName, setCustomCarrierName] = useState("");
  const [trackingNumberInput, setTrackingNumberInput] = useState("");
  const [trackingUrlInput, setTrackingUrlInput] = useState("");
  const [estimatedDeliveryInput, setEstimatedDeliveryInput] = useState("");
  const [deliveryNotesInput, setDeliveryNotesInput] = useState("");
  const [dispatchImmediatelyInput, setDispatchImmediatelyInput] = useState(true);
  const [itemQuantitiesToShip, setItemQuantitiesToShip] = useState<Record<string, number>>({});
  const [isSubmittingShipment, setIsSubmittingShipment] = useState(false);
  const [createShipmentError, setCreateShipmentError] = useState<string | null>(null);

  // Shipment status update state
  const [shipmentStatusTarget, setShipmentStatusTarget] = useState<{
    shipment: PlatformShipment;
    targetStatus: string;
  } | null>(null);
  const [shipmentLocation, setShipmentLocation] = useState("");
  const [shipmentDescription, setShipmentDescription] = useState("");
  const [isUpdatingShipmentStatus, setIsUpdatingShipmentStatus] = useState(false);
  const [shipmentUpdateError, setShipmentUpdateError] = useState<string | null>(null);

  // Add Tracking Event state
  const [trackingEventShipment, setTrackingEventShipment] = useState<PlatformShipment | null>(null);
  const [trackingEventStatus, setTrackingEventStatus] = useState("");
  const [trackingEventLocation, setTrackingEventLocation] = useState("");
  const [trackingEventDescription, setTrackingEventDescription] = useState("");
  const [isAddingTrackingEvent, setIsAddingTrackingEvent] = useState(false);
  const [trackingEventError, setTrackingEventError] = useState<string | null>(null);

  // Main Tab Navigation
  const [activeMainTab, setActiveMainTab] = useState<"orders" | "returns" | "disputes">(initialMainTab || "orders");

  useEffect(() => {
    if (initialMainTab) {
      setActiveMainTab(initialMainTab);
    }
  }, [initialMainTab]);

  // Returns & RMAs State
  const [sellerReturns, setSellerReturns] = useState<PlatformReturnRequest[]>([]);
  const [loadingReturns, setLoadingReturns] = useState(false);
  const [returnsError, setReturnsError] = useState<string | null>(null);
  const [returnStatusFilter, setReturnStatusFilter] = useState<string>("ALL");
  const [selectedReturnForReview, setSelectedReturnForReview] = useState<{
    returnReq: PlatformReturnRequest;
    action: "APPROVE" | "REJECT";
  } | null>(null);
  const [rejectionReasonInput, setRejectionReasonInput] = useState("");
  const [isReviewingReturn, setIsReviewingReturn] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [completeReturnModal, setCompleteReturnModal] = useState<PlatformReturnRequest | null>(null);
  const [returnTrackingNumberInput, setReturnTrackingNumberInput] = useState("");
  const [isCompletingReturn, setIsCompletingReturn] = useState(false);
  const [completeReturnError, setCompleteReturnError] = useState<string | null>(null);

  // Disputes State
  const [sellerDisputes, setSellerDisputes] = useState<PlatformDispute[]>([]);
  const [loadingDisputes, setLoadingDisputes] = useState(false);
  const [disputesError, setDisputesError] = useState<string | null>(null);
  const [disputeStatusFilter, setDisputeStatusFilter] = useState<string>("ALL");
  const [activeDisputeDrawer, setActiveDisputeDrawer] = useState<PlatformDispute | null>(null);
  const [disputeEvents, setDisputeEvents] = useState<PlatformDisputeEvent[]>([]);
  const [loadingDisputeEvents, setLoadingDisputeEvents] = useState(false);
  const [sellerReplyMessage, setSellerReplyMessage] = useState("");
  const [isPostingDisputeReply, setIsPostingDisputeReply] = useState(false);
  const [disputeReplyError, setDisputeReplyError] = useState<string | null>(null);

  const getItemShippedQuantity = (item: PlatformOrderItem, shipments?: PlatformShipment[]): number => {
    return (shipments || [])
      .filter((s) => s.status !== "CANCELLED")
      .flatMap((s) => s.items)
      .filter((si) => si.order_item_id === item.id || si.order_item === item.id)
      .reduce((sum, si) => sum + Number(si.quantity || 0), 0);
  };

  const getItemRemainingQuantity = (item: PlatformOrderItem, shipments?: PlatformShipment[]): number => {
    const shipped = getItemShippedQuantity(item, shipments);
    return Math.max(0, item.quantity - shipped);
  };

  const openCreateShipmentModal = async (order: SellerOrder) => {
    setCreateShipmentOrder(order);
    setCarrierCode("");
    setCustomCarrierName("");
    setTrackingNumberInput("");
    setTrackingUrlInput("");
    setEstimatedDeliveryInput("");
    setDeliveryNotesInput("");
    setDispatchImmediatelyInput(true);
    setCreateShipmentError(null);

    const initialQtys: Record<string, number> = {};
    order.items.forEach((item) => {
      initialQtys[item.id] = getItemRemainingQuantity(item, order.shipments);
    });
    setItemQuantitiesToShip(initialQtys);

    setLoadingCarriers(true);
    try {
      const res = await api.marketplace.getAvailableCarriers(order.shipping_country);
      setCarriers(res.carriers || []);
      if (res.carriers && res.carriers.length > 0) {
        setCarrierCode(res.carriers[0].code);
      }
    } catch {
      setCarriers([
        { code: "BLUE_DART", name: "Blue Dart Express" },
        { code: "DELHIVERY", name: "Delhivery Logistics" },
        { code: "ROYAL_MAIL", name: "Royal Mail UK" },
        { code: "OTHER", name: "Other / Manual Logistics" },
      ]);
      setCarrierCode("OTHER");
    } finally {
      setLoadingCarriers(false);
    }
  };

  const handleCreateShipment = async () => {
    if (!createShipmentOrder) return;
    setIsSubmittingShipment(true);
    setCreateShipmentError(null);

    const itemsPayload = Object.entries(itemQuantitiesToShip)
      .filter(([, qty]) => Number(qty) > 0)
      .map(([order_item_id, qty]) => ({
        order_item_id,
        quantity: Number(qty),
      }));

    if (itemsPayload.length === 0) {
      setCreateShipmentError("Please select at least 1 unit of an item to include in this shipment.");
      setIsSubmittingShipment(false);
      return;
    }

    try {
      const res = await api.marketplace.createShipment(createShipmentOrder.id, {
        carrier: carrierCode || "OTHER",
        carrier_name: carrierCode === "OTHER" ? customCarrierName : undefined,
        tracking_number: trackingNumberInput.trim(),
        tracking_url: trackingUrlInput.trim() || undefined,
        estimated_delivery_at: estimatedDeliveryInput || undefined,
        delivery_notes: deliveryNotesInput.trim() || undefined,
        dispatch_immediately: dispatchImmediatelyInput,
        items: itemsPayload,
      });

      if (res.status === "success" && res.shipment) {
        await loadSellerOrders();
        if (selectedOrder) {
          try {
            const updatedOrder = await api.marketplace.getSellerOrder(selectedOrder.id);
            setSelectedOrder(updatedOrder);
          } catch {
            setSelectedOrder((prev) =>
              prev ? { ...prev, shipments: [...(prev.shipments || []), res.shipment] } : null
            );
          }
        }
        setSuccessBanner(`Shipment ${res.shipment.shipment_number} created successfully.`);
        setCreateShipmentOrder(null);
      } else {
        throw new Error(res.message || "Failed to create shipment.");
      }
    } catch (err: unknown) {
      setCreateShipmentError(
        err instanceof Error ? err.message : "Failed to create shipment."
      );
    } finally {
      setIsSubmittingShipment(false);
    }
  };

  const handleUpdateShipmentStatus = async () => {
    if (!shipmentStatusTarget) return;
    setIsUpdatingShipmentStatus(true);
    setShipmentUpdateError(null);
    try {
      const res = await api.marketplace.updateShipmentStatus(
        shipmentStatusTarget.shipment.id,
        {
          status: shipmentStatusTarget.targetStatus,
          location: shipmentLocation.trim() || undefined,
          description: shipmentDescription.trim() || undefined,
        }
      );
      if (res.status === "success" && res.shipment) {
        await loadSellerOrders();
        if (selectedOrder) {
          const updatedOrder = await api.marketplace.getSellerOrder(selectedOrder.id);
          setSelectedOrder(updatedOrder);
        }
        setSuccessBanner(
          `Shipment ${res.shipment.shipment_number} status updated to ${shipmentStatusTarget.targetStatus}.`
        );
        setShipmentStatusTarget(null);
        setShipmentLocation("");
        setShipmentDescription("");
      } else {
        throw new Error(res.message || "Failed to update shipment status.");
      }
    } catch (err: unknown) {
      setShipmentUpdateError(
        err instanceof Error ? err.message : "Failed to update shipment status."
      );
    } finally {
      setIsUpdatingShipmentStatus(false);
    }
  };

  const handleAddTrackingEvent = async () => {
    if (!trackingEventShipment) return;
    setIsAddingTrackingEvent(true);
    setTrackingEventError(null);
    try {
      const res = await api.marketplace.addTrackingEvent(
        trackingEventShipment.id,
        {
          status: trackingEventStatus || trackingEventShipment.status,
          location: trackingEventLocation.trim() || undefined,
          description: trackingEventDescription.trim(),
        }
      );
      if (res.status === "success" && res.shipment) {
        await loadSellerOrders();
        if (selectedOrder) {
          const updatedOrder = await api.marketplace.getSellerOrder(selectedOrder.id);
          setSelectedOrder(updatedOrder);
        }
        setSuccessBanner(
          `Tracking checkpoint recorded for shipment ${res.shipment.shipment_number}.`
        );
        setTrackingEventShipment(null);
        setTrackingEventDescription("");
        setTrackingEventLocation("");
      } else {
        throw new Error(res.message || "Failed to record tracking event.");
      }
    } catch (err: unknown) {
      setTrackingEventError(
        err instanceof Error ? err.message : "Failed to record tracking event."
      );
    } finally {
      setIsAddingTrackingEvent(false);
    }
  };

  const getShipmentStatusBadge = (status: string) => {
    switch (status) {
      case "CREATED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-800 border border-slate-300">
            <Package className="w-3 h-3 text-slate-600" />
            Label Created
          </span>
        );
      case "DISPATCHED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-100 text-blue-800 border border-blue-300">
            <Truck className="w-3 h-3 text-blue-600" />
            Dispatched
          </span>
        );
      case "IN_TRANSIT":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-indigo-100 text-indigo-800 border border-indigo-300">
            <Navigation className="w-3 h-3 text-indigo-600" />
            In Transit
          </span>
        );
      case "OUT_FOR_DELIVERY":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
            <Truck className="w-3 h-3 text-amber-600 animate-pulse" />
            Out for Delivery
          </span>
        );
      case "DELIVERED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
            Delivered
          </span>
        );
      case "FAILED_DELIVERY":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-100 text-rose-800 border border-rose-300">
            <AlertTriangle className="w-3 h-3 text-rose-600" />
            Delivery Failed
          </span>
        );
      case "RETURNED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-purple-100 text-purple-800 border border-purple-300">
            <RotateCcw className="w-3 h-3 text-purple-600" />
            Returned
          </span>
        );
      case "CANCELLED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-500 border border-slate-200">
            <XCircle className="w-3 h-3 text-slate-400" />
            Cancelled
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-800">
            {status}
          </span>
        );
    }
  };

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

  const getPaymentBadge = (order: SellerOrder) => {
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

  const loadSellerReturns = useCallback(async () => {
    if (!user) return;
    setLoadingReturns(true);
    setReturnsError(null);
    try {
      const res = await api.marketplace.listSellerReturnRequests(
        returnStatusFilter === "ALL" ? undefined : { status: returnStatusFilter }
      );
      setSellerReturns(res.return_requests || []);
    } catch (err: unknown) {
      setReturnsError(
        err instanceof Error ? err.message : "Failed to load return requests."
      );
    } finally {
      setLoadingReturns(false);
    }
  }, [user, returnStatusFilter]);

  const loadSellerDisputes = useCallback(async () => {
    if (!user) return;
    setLoadingDisputes(true);
    setDisputesError(null);
    try {
      const data = await api.marketplace.listSellerDisputes();
      const filtered = disputeStatusFilter === "ALL"
        ? data
        : (data || []).filter((d) => d.status === disputeStatusFilter);
      setSellerDisputes(filtered || []);
    } catch (err: unknown) {
      setDisputesError(
        err instanceof Error ? err.message : "Failed to load seller disputes."
      );
    } finally {
      setLoadingDisputes(false);
    }
  }, [user, disputeStatusFilter]);

  // Initial fetch for count badges
  useEffect(() => {
    if (user) {
      api.marketplace.listSellerReturnRequests().then((res) => {
        if (res?.return_requests) setSellerReturns(res.return_requests);
      }).catch(() => {});
      api.marketplace.listSellerDisputes().then((data) => {
        if (data) setSellerDisputes(data);
      }).catch(() => {});
    }
  }, [user]);

  useEffect(() => {
    if (activeMainTab === "returns") {
      loadSellerReturns();
    } else if (activeMainTab === "disputes") {
      loadSellerDisputes();
    }
  }, [activeMainTab, loadSellerReturns, loadSellerDisputes]);

  const pendingReturnsCount = useMemo(() => {
    return sellerReturns.filter((r) => r.status === "PENDING").length;
  }, [sellerReturns]);

  const openDisputesCount = useMemo(() => {
    return sellerDisputes.filter((d) => d.status === "OPEN" || d.status === "UNDER_REVIEW").length;
  }, [sellerDisputes]);

  const handleReviewReturn = async () => {
    if (!selectedReturnForReview) return;
    setIsReviewingReturn(true);
    setReviewError(null);
    try {
      const res = await api.marketplace.reviewSellerReturnRequest(selectedReturnForReview.returnReq.id, {
        action: selectedReturnForReview.action,
        rejection_reason: selectedReturnForReview.action === "REJECT" ? rejectionReasonInput.trim() : undefined,
      });
      setSuccessBanner(res.message || `Return request ${selectedReturnForReview.action === "APPROVE" ? "approved" : "rejected"} successfully.`);
      setSelectedReturnForReview(null);
      setRejectionReasonInput("");
      loadSellerReturns();
      loadSellerOrders();
      if (selectedOrder) {
        try {
          const updated = await api.marketplace.getSellerOrder(selectedOrder.id);
          setSelectedOrder(updated);
        } catch {}
      }
    } catch (err: unknown) {
      setReviewError(err instanceof Error ? err.message : "Failed to review return request.");
    } finally {
      setIsReviewingReturn(false);
    }
  };

  const handleCompleteReturn = async () => {
    if (!completeReturnModal) return;
    setIsCompletingReturn(true);
    setCompleteReturnError(null);
    try {
      const res = await api.marketplace.completeSellerReturnRequest(completeReturnModal.id, {
        return_tracking_number: returnTrackingNumberInput.trim() || undefined,
      });
      setSuccessBanner(res.message || "Return marked as completed and inventory restocked.");
      setCompleteReturnModal(null);
      setReturnTrackingNumberInput("");
      loadSellerReturns();
      loadSellerOrders();
      if (selectedOrder) {
        try {
          const updated = await api.marketplace.getSellerOrder(selectedOrder.id);
          setSelectedOrder(updated);
        } catch {}
      }
    } catch (err: unknown) {
      setCompleteReturnError(err instanceof Error ? err.message : "Failed to complete return request.");
    } finally {
      setIsCompletingReturn(false);
    }
  };

  const openDisputeDrawer = async (dispute: PlatformDispute) => {
    setActiveDisputeDrawer(dispute);
    setLoadingDisputeEvents(true);
    setDisputeReplyError(null);
    setSellerReplyMessage("");
    try {
      const res = await api.marketplace.getDisputeDetail(dispute.id);
      setActiveDisputeDrawer(res.dispute);
      setDisputeEvents(res.events || []);
    } catch (err: unknown) {
      setDisputeReplyError(err instanceof Error ? err.message : "Failed to load dispute conversation.");
    } finally {
      setLoadingDisputeEvents(false);
    }
  };

  const handlePostSellerDisputeReply = async () => {
    if (!activeDisputeDrawer || !sellerReplyMessage.trim()) return;
    setIsPostingDisputeReply(true);
    setDisputeReplyError(null);
    try {
      const res = await api.marketplace.postDisputeMessage(activeDisputeDrawer.id, {
        message: sellerReplyMessage.trim(),
      });
      setDisputeEvents((prev) => [...prev, res.event]);
      setSellerReplyMessage("");
    } catch (err: unknown) {
      setDisputeReplyError(err instanceof Error ? err.message : "Failed to send message.");
    } finally {
      setIsPostingDisputeReply(false);
    }
  };

  const getReturnStatusBadge = (status: string) => {
    switch (status) {
      case "PENDING":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
            <Clock className="w-3 h-3 text-amber-600" />
            Pending Seller Review
          </span>
        );
      case "APPROVED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-100 text-blue-800 border border-blue-300">
            <CheckCircle2 className="w-3 h-3 text-blue-600" />
            Approved · Awaiting Return
          </span>
        );
      case "COMPLETED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
            <Check className="w-3 h-3 text-emerald-600" />
            Completed & Restocked
          </span>
        );
      case "REJECTED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-100 text-rose-800 border border-rose-300">
            <XCircle className="w-3 h-3 text-rose-600" />
            Rejected
          </span>
        );
      case "CANCELLED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-700 border border-slate-300">
            <X className="w-3 h-3" />
            Withdrawn by Buyer
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-800 border border-slate-300">
            {status}
          </span>
        );
    }
  };

  const getDisputeStatusBadge = (status: string) => {
    switch (status) {
      case "OPEN":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-100 text-rose-800 border border-rose-300">
            <AlertTriangle className="w-3 h-3 text-rose-600" />
            Open Dispute
          </span>
        );
      case "UNDER_REVIEW":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
            <Clock className="w-3 h-3 text-amber-600" />
            Under Adjudication
          </span>
        );
      case "RESOLVED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
            Resolved
          </span>
        );
      case "REJECTED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-800 border border-slate-300">
            <XCircle className="w-3 h-3 text-slate-500" />
            Dismissed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-800 border border-slate-300">
            {status}
          </span>
        );
    }
  };

  const getDisputePriorityBadge = (priority: string) => {
    switch (priority) {
      case "HIGH":
      case "URGENT":
        return (
          <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded bg-rose-100 text-rose-700 border border-rose-200">
            {priority}
          </span>
        );
      case "MEDIUM":
        return (
          <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded bg-amber-100 text-amber-700 border border-amber-200">
            MEDIUM
          </span>
        );
      default:
        return (
          <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
            {priority || "LOW"}
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

      {/* Admin View-Only Informational Alert */}
      {isAdmin && (
        <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 flex items-center gap-3 shadow-xs">
          <AlertCircle className="w-5 h-5 text-amber-600 shrink-0" />
          <p className="text-xs">
            <span className="font-bold">Admin Notice:</span> Customer Orders, fulfillment actions, shipping dispatch, and returns/disputes are managed strictly by Sellers. Fulfillment actions are disabled for Admin users.
          </p>
        </div>
      )}

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

      {/* Main Tab Navigation */}
      <div className="flex border-b border-slate-200 gap-8">
        <button
          onClick={() => setActiveMainTab("orders")}
          className={`pb-3 text-sm font-bold flex items-center gap-2 border-b-2 transition-all ${
            activeMainTab === "orders"
              ? "border-amber-500 text-slate-900"
              : "border-transparent text-slate-400 hover:text-slate-600"
          }`}
        >
          <Boxes className="w-4 h-4" />
          <span>Customer Orders</span>
          <span className="px-2 py-0.5 rounded-full text-[10px] bg-slate-100 text-slate-700 font-mono">
            {orders.length}
          </span>
        </button>

        <button
          onClick={() => setActiveMainTab("returns")}
          className={`pb-3 text-sm font-bold flex items-center gap-2 border-b-2 transition-all ${
            activeMainTab === "returns"
              ? "border-amber-500 text-slate-900"
              : "border-transparent text-slate-400 hover:text-slate-600"
          }`}
        >
          <RotateCcw className="w-4 h-4" />
          <span>Returns & RMAs</span>
          {pendingReturnsCount > 0 ? (
            <span className="px-2 py-0.5 rounded-full text-[10px] bg-amber-500 text-slate-950 font-bold font-mono">
              {pendingReturnsCount} pending review
            </span>
          ) : (
            <span className="px-2 py-0.5 rounded-full text-[10px] bg-slate-100 text-slate-700 font-mono">
              {sellerReturns.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveMainTab("disputes")}
          className={`pb-3 text-sm font-bold flex items-center gap-2 border-b-2 transition-all ${
            activeMainTab === "disputes"
              ? "border-amber-500 text-slate-900"
              : "border-transparent text-slate-400 hover:text-slate-600"
          }`}
        >
          <Scale className="w-4 h-4" />
          <span>Customer Disputes</span>
          {openDisputesCount > 0 ? (
            <span className="px-2 py-0.5 rounded-full text-[10px] bg-rose-500 text-white font-bold font-mono">
              {openDisputesCount} active
            </span>
          ) : (
            <span className="px-2 py-0.5 rounded-full text-[10px] bg-slate-100 text-slate-700 font-mono">
              {sellerDisputes.length}
            </span>
          )}
        </button>
      </div>

      {activeMainTab === "orders" && (
        <div className="space-y-6">
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

                <div className="flex flex-wrap items-center gap-2">
                  {getStatusBadge(order.status)}
                  {getPaymentBadge(order)}
                  {order.return_requests && order.return_requests.length > 0 && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
                      <RotateCcw className="w-3 h-3 text-amber-600" />
                      Return ({order.return_requests.length})
                    </span>
                  )}
                  {order.disputes && order.disputes.length > 0 && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-300">
                      <Scale className="w-3 h-3 text-rose-600" />
                      Dispute ({order.disputes.length})
                    </span>
                  )}
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
                    {!isAdmin && order.status === "PENDING_CONFIRMATION" && (
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

                    {!isAdmin && order.status === "CONFIRMED" && (
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

                    {!isAdmin && order.status === "PROCESSING" && (
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
        </div>
      )}

      {/* ========================================================= */}
      {/* RETURNS & RMAS VIEW                                       */}
      {/* ========================================================= */}
      {activeMainTab === "returns" && (
        <div className="space-y-6">
          {/* Sub Header & Filters */}
          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
            <div className="flex flex-wrap gap-2">
              {[
                { id: "ALL", label: "All Returns" },
                { id: "PENDING", label: "Pending Review" },
                { id: "APPROVED", label: "Approved" },
                { id: "COMPLETED", label: "Completed & Restocked" },
                { id: "REJECTED", label: "Rejected" },
                { id: "CANCELLED", label: "Withdrawn" },
              ].map((f) => (
                <button
                  key={f.id}
                  onClick={() => setReturnStatusFilter(f.id)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all border ${
                    returnStatusFilter === f.id
                      ? "bg-slate-900 text-white border-slate-900 shadow-xs"
                      : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>

            <button
              onClick={loadSellerReturns}
              disabled={loadingReturns}
              className="px-3.5 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold flex items-center gap-2 transition-colors shadow-xs disabled:opacity-50"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${loadingReturns ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>

          {/* Returns List */}
          {loadingReturns ? (
            <div className="py-20 flex flex-col items-center justify-center space-y-3 bg-white rounded-2xl border border-slate-200">
              <Loader2 className="w-8 h-8 text-amber-500 animate-spin" />
              <span className="text-xs font-bold text-slate-600">Loading customer return requests...</span>
            </div>
          ) : returnsError ? (
            <div className="p-8 bg-rose-50 border border-rose-200 rounded-2xl text-center space-y-3">
              <AlertCircle className="w-10 h-10 text-rose-500 mx-auto" />
              <h3 className="text-sm font-bold text-rose-900">Failed to Load Returns</h3>
              <p className="text-xs text-rose-700 max-w-md mx-auto">{returnsError}</p>
              <button
                onClick={loadSellerReturns}
                className="px-4 py-2 bg-rose-600 text-white text-xs font-bold rounded-xl hover:bg-rose-700 transition-colors"
              >
                Try Again
              </button>
            </div>
          ) : sellerReturns.length === 0 ? (
            <div className="py-20 bg-white rounded-2xl border border-slate-200 text-center space-y-4 p-6">
              <div className="w-16 h-16 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
                <RotateCcw className="w-8 h-8" />
              </div>
              <div className="space-y-1 max-w-sm mx-auto">
                <h3 className="text-base font-black text-slate-900">No Return Requests</h3>
                <p className="text-xs text-slate-500">
                  {returnStatusFilter !== "ALL"
                    ? `No return requests match the "${returnStatusFilter}" filter.`
                    : "There are currently no customer return or cancellation requests for your items."}
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {sellerReturns.map((ret) => (
                <div
                  key={ret.id}
                  className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-xs hover:border-slate-300 transition-all space-y-4"
                >
                  {/* Top Bar */}
                  <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100">
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="font-mono font-black text-sm text-slate-900">
                        {ret.request_number}
                      </span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-100 text-slate-700 border border-slate-200">
                        {ret.request_type_display || ret.request_type}
                      </span>
                      <span className="text-xs text-slate-500">
                        Order Ref: <strong className="font-mono text-slate-800">{ret.order_number}</strong>
                      </span>
                      <span className="text-[11px] text-slate-400">
                        {new Date(ret.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      {getReturnStatusBadge(ret.status)}
                    </div>
                  </div>

                  {/* Buyer & Reason */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div className="p-3 bg-slate-50 rounded-xl space-y-1.5">
                      <span className="text-[10px] uppercase font-bold text-slate-400 block">Customer Information</span>
                      <p className="font-bold text-slate-900">{ret.buyer_name || "Customer"}</p>
                      <p className="text-slate-500">{ret.buyer_email}</p>
                    </div>

                    <div className="p-3 bg-slate-50 rounded-xl space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] uppercase font-bold text-slate-400 block">Reason</span>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-100 text-amber-800">
                          {ret.reason_display || ret.reason}
                        </span>
                      </div>
                      <p className="text-slate-700 italic">&ldquo;{ret.description}&rdquo;</p>
                      {ret.rejection_reason && (
                        <p className="text-rose-700 font-semibold pt-1">Rejection Reason: {ret.rejection_reason}</p>
                      )}
                      {ret.return_tracking_number && (
                        <p className="text-indigo-700 font-mono text-[11px] pt-1">Return Waybill: {ret.return_tracking_number}</p>
                      )}
                    </div>
                  </div>

                  {/* Supporting Evidence Thumbnails */}
                  {ret.evidence_urls && ret.evidence_urls.length > 0 && (
                    <div className="space-y-1.5">
                      <span className="text-[10px] uppercase font-bold text-slate-400 block">Customer Evidence ({ret.evidence_urls.length})</span>
                      <div className="flex flex-wrap gap-2">
                        {ret.evidence_urls.map((url, eIdx) => (
                          <a
                            key={eIdx}
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="w-14 h-14 rounded-xl border border-slate-200 overflow-hidden bg-slate-100 hover:opacity-80 transition-opacity block shrink-0"
                            title="Click to view full image"
                          >
                            <img src={url} alt={`Evidence ${eIdx + 1}`} className="w-full h-full object-cover" />
                          </a>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Requested Items */}
                  <div className="space-y-2">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">
                      Requested Part Allocation
                    </span>
                    <div className="border border-slate-200 rounded-xl divide-y divide-slate-100 overflow-hidden">
                      <div className="p-3 flex items-center justify-between gap-3 text-xs bg-white">
                        <div className="space-y-0.5">
                          <p className="font-bold text-slate-900">{ret.item_title || `Order Items (${ret.order_number})`}</p>
                          {ret.item_brand && (
                            <p className="text-[11px] text-slate-400">Brand: {ret.item_brand}</p>
                          )}
                        </div>
                        <div className="text-right">
                          <span className="text-slate-500 text-[11px] block">
                            Requested Qty: {ret.requested_quantity}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Actions & Refund Estimate */}
                  <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3 bg-slate-50/50 -mx-5 -mb-5 p-4 rounded-b-2xl">
                    <div className="text-xs">
                      <span className="text-[10px] uppercase font-bold text-slate-400 block">Calculated Refund Value</span>
                      <span className="font-mono font-black text-base text-slate-900">
                        {ret.refund_amount ? `${Number(ret.refund_amount).toFixed(2)}` : "Pending Calculation"}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      {!isAdmin && ret.status === "PENDING" && (
                        <>
                          <button
                            onClick={() => {
                              setReviewError(null);
                              setRejectionReasonInput("");
                              setSelectedReturnForReview({ returnReq: ret, action: "APPROVE" });
                            }}
                            className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5"
                          >
                            <Check className="w-3.5 h-3.5" />
                            <span>Approve Return</span>
                          </button>
                          <button
                            onClick={() => {
                              setReviewError(null);
                              setRejectionReasonInput("");
                              setSelectedReturnForReview({ returnReq: ret, action: "REJECT" });
                            }}
                            className="px-3.5 py-2 rounded-xl border border-rose-300 text-rose-700 bg-white hover:bg-rose-50 text-xs font-bold transition-colors flex items-center gap-1.5"
                          >
                            <X className="w-3.5 h-3.5" />
                            <span>Reject</span>
                          </button>
                        </>
                      )}

                      {!isAdmin && ret.status === "APPROVED" && ret.request_type === "RETURN" && (
                        <button
                          onClick={() => {
                            setCompleteReturnError(null);
                            setReturnTrackingNumberInput("");
                            setCompleteReturnModal(ret);
                          }}
                          className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5"
                        >
                          <Boxes className="w-3.5 h-3.5" />
                          <span>Confirm Receipt & Restock</span>
                        </button>
                      )}

                      {ret.status === "COMPLETED" && (
                        <span className="text-xs font-bold text-emerald-700 flex items-center gap-1.5 bg-emerald-50 px-3 py-1.5 rounded-xl border border-emerald-200">
                          <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                          <span>Goods Received & Inventory Restocked</span>
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ========================================================= */}
      {/* DISPUTES VIEW                                             */}
      {/* ========================================================= */}
      {activeMainTab === "disputes" && (
        <div className="space-y-6">
          {/* Sub Header & Filters */}
          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
            <div className="flex flex-wrap gap-2">
              {[
                { id: "ALL", label: "All Disputes" },
                { id: "OPEN", label: "Open" },
                { id: "UNDER_REVIEW", label: "Under Review" },
                { id: "RESOLVED", label: "Resolved" },
                { id: "REJECTED", label: "Dismissed" },
              ].map((f) => (
                <button
                  key={f.id}
                  onClick={() => setDisputeStatusFilter(f.id)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all border ${
                    disputeStatusFilter === f.id
                      ? "bg-slate-900 text-white border-slate-900 shadow-xs"
                      : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>

            <button
              onClick={loadSellerDisputes}
              disabled={loadingDisputes}
              className="px-3.5 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold flex items-center gap-2 transition-colors shadow-xs disabled:opacity-50"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${loadingDisputes ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>

          {/* Disputes List */}
          {loadingDisputes ? (
            <div className="py-20 flex flex-col items-center justify-center space-y-3 bg-white rounded-2xl border border-slate-200">
              <Loader2 className="w-8 h-8 text-amber-500 animate-spin" />
              <span className="text-xs font-bold text-slate-600">Loading order disputes...</span>
            </div>
          ) : disputesError ? (
            <div className="p-8 bg-rose-50 border border-rose-200 rounded-2xl text-center space-y-3">
              <AlertCircle className="w-10 h-10 text-rose-500 mx-auto" />
              <h3 className="text-sm font-bold text-rose-900">Failed to Load Disputes</h3>
              <p className="text-xs text-rose-700 max-w-md mx-auto">{disputesError}</p>
              <button
                onClick={loadSellerDisputes}
                className="px-4 py-2 bg-rose-600 text-white text-xs font-bold rounded-xl hover:bg-rose-700 transition-colors"
              >
                Try Again
              </button>
            </div>
          ) : sellerDisputes.length === 0 ? (
            <div className="py-20 bg-white rounded-2xl border border-slate-200 text-center space-y-4 p-6">
              <div className="w-16 h-16 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
                <Scale className="w-8 h-8" />
              </div>
              <div className="space-y-1 max-w-sm mx-auto">
                <h3 className="text-base font-black text-slate-900">No Customer Disputes</h3>
                <p className="text-xs text-slate-500">
                  {disputeStatusFilter !== "ALL"
                    ? `No disputes match the "${disputeStatusFilter}" filter.`
                    : "No order disputes have been filed against orders containing your items."}
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {sellerDisputes.map((disp) => (
                <div
                  key={disp.id}
                  className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-xs hover:border-slate-300 transition-all space-y-4"
                >
                  {/* Top Bar */}
                  <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100">
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="font-mono font-black text-sm text-slate-900">
                        {disp.dispute_number}
                      </span>
                      {getDisputePriorityBadge(disp.priority)}
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-100 text-slate-700 border border-slate-200">
                        {disp.category_display || disp.category}
                      </span>
                      <span className="text-xs text-slate-500">
                        Order: <strong className="font-mono text-slate-800">{disp.order_number}</strong>
                      </span>
                      <span className="text-[11px] text-slate-400">
                        {new Date(disp.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      {getDisputeStatusBadge(disp.status)}
                    </div>
                  </div>

                  {/* Buyer & Description */}
                  <div className="space-y-2 text-xs">
                    <div className="flex items-center gap-2 text-slate-600">
                      <span>Buyer: <strong>{disp.buyer_name || disp.buyer_email}</strong></span>
                    </div>
                    <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-100 space-y-2">
                      <span className="text-[10px] uppercase font-bold text-slate-400 block">Buyer Statement</span>
                      <p className="text-slate-800 leading-relaxed">{disp.description}</p>
                    </div>

                    {disp.resolution_summary && (
                      <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl space-y-1 text-emerald-900">
                        <span className="text-[10px] uppercase font-bold text-emerald-700 block">Resolution Decided</span>
                        <p className="font-bold">{disp.resolution_summary}</p>
                        {disp.resolution_notes && (
                          <p className="text-[11px] text-emerald-800">{disp.resolution_notes}</p>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Evidence Thumbnails */}
                  {disp.evidence_urls && disp.evidence_urls.length > 0 && (
                    <div className="space-y-1.5">
                      <span className="text-[10px] uppercase font-bold text-slate-400 block">Evidence Attachments ({disp.evidence_urls.length})</span>
                      <div className="flex flex-wrap gap-2">
                        {disp.evidence_urls.map((url, eIdx) => (
                          <a
                            key={eIdx}
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="w-14 h-14 rounded-xl border border-slate-200 overflow-hidden bg-slate-100 hover:opacity-80 transition-opacity block shrink-0"
                            title="Click to view full image"
                          >
                            <img src={url} alt={`Evidence ${eIdx + 1}`} className="w-full h-full object-cover" />
                          </a>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Footer */}
                  <div className="pt-3 border-t border-slate-100 flex items-center justify-between gap-3 bg-slate-50/50 -mx-5 -mb-5 p-4 rounded-b-2xl">
                    <span className="text-[11px] text-slate-500">
                      Adjudicated by platform support staff.
                    </span>

                    <button
                      onClick={() => openDisputeDrawer(disp)}
                      className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-all shadow-xs flex items-center gap-1.5"
                    >
                      <MessageSquare className="w-3.5 h-3.5 text-amber-400" />
                      <span>View Thread & Reply</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
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

              {/* Shipments & Logistics Tracking */}
              <div className="p-4 sm:p-5 rounded-2xl bg-white border border-slate-200 shadow-xs space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100">
                  <div className="space-y-0.5">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-2">
                      <Truck className="w-4 h-4 text-indigo-600" />
                      <span>Fulfillment Shipments & Tracking</span>
                    </h4>
                    <p className="text-[11px] text-slate-500">
                      Manage package consignments, courier tracking numbers, and delivery milestones.
                    </p>
                  </div>

                  {!isAdmin && selectedOrder.status !== "CANCELLED" && (
                    <button
                      onClick={() => openCreateShipmentModal(selectedOrder)}
                      className="px-3.5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>Create Shipment</span>
                    </button>
                  )}
                </div>

                {selectedOrder.shipments && selectedOrder.shipments.length > 0 ? (
                  <div className="space-y-3">
                    {selectedOrder.shipments.map((shp) => (
                      <div
                        key={shp.id}
                        className="p-4 rounded-xl border border-slate-200 bg-slate-50/60 space-y-3"
                      >
                        {/* Shipment Top Bar */}
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono font-black text-xs text-slate-900">
                              {shp.shipment_number}
                            </span>
                            <button
                              onClick={() => handleCopy(shp.shipment_number)}
                              className="p-1 text-slate-400 hover:text-slate-700 rounded"
                              title="Copy Shipment Number"
                            >
                              {copiedId === shp.shipment_number ? (
                                <Check className="w-3 h-3 text-emerald-600" />
                              ) : (
                                <Copy className="w-3 h-3" />
                              )}
                            </button>
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-200 text-slate-700 uppercase">
                              {shp.carrier_display || shp.carrier_name || shp.carrier}
                            </span>
                            {shp.tracking_number && (
                              <div className="flex items-center gap-1 text-[11px] font-mono text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                                <span>Ref: {shp.tracking_number}</span>
                                <button
                                  onClick={() => handleCopy(shp.tracking_number)}
                                  className="text-indigo-500 hover:text-indigo-800"
                                  title="Copy Tracking Number"
                                >
                                  {copiedId === shp.tracking_number ? (
                                    <Check className="w-2.5 h-2.5 text-emerald-600" />
                                  ) : (
                                    <Copy className="w-2.5 h-2.5" />
                                  )}
                                </button>
                                {shp.tracking_url && (
                                  <a
                                    href={shp.tracking_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-indigo-600 hover:text-indigo-900 ml-0.5"
                                    title="Open Carrier Tracking URL"
                                  >
                                    <ExternalLink className="w-2.5 h-2.5" />
                                  </a>
                                )}
                              </div>
                            )}
                          </div>

                          <div className="flex items-center gap-2">
                            {getShipmentStatusBadge(shp.status)}
                          </div>
                        </div>

                        {/* Shipment Timestamps */}
                        <div className="flex flex-wrap items-center gap-4 text-[11px] text-slate-500">
                          {shp.dispatched_at && (
                            <span>
                              Dispatched: <strong>{new Date(shp.dispatched_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</strong>
                            </span>
                          )}
                          {shp.delivered_at && (
                            <span className="text-emerald-700">
                              Delivered: <strong>{new Date(shp.delivered_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</strong>
                            </span>
                          )}
                          {shp.estimated_delivery_at && !shp.delivered_at && (
                            <span className="text-amber-800">
                              Est. Delivery: <strong>{new Date(shp.estimated_delivery_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}</strong>
                            </span>
                          )}
                          {shp.delivery_notes && (
                            <span className="italic text-slate-600">
                              Note: {shp.delivery_notes}
                            </span>
                          )}
                        </div>

                        {/* Items in this shipment */}
                        <div className="p-2.5 bg-white rounded-lg border border-slate-200 text-xs space-y-1">
                          <span className="text-[10px] uppercase font-bold text-slate-400 block">
                            Allocated Items:
                          </span>
                          <div className="flex flex-wrap gap-2">
                            {shp.items.map((si) => (
                              <span
                                key={si.id}
                                className="px-2 py-1 rounded bg-slate-100 text-slate-800 text-[11px] font-medium"
                              >
                                {si.quantity}x {si.listing_title} ({si.listing_brand})
                              </span>
                            ))}
                          </div>
                        </div>

                        {/* Tracking Milestones */}
                        <div className="space-y-1.5 pt-1">
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] uppercase font-bold text-slate-400">
                              Tracking Timeline ({shp.tracking_events?.length || 0})
                            </span>
                            {shp.status !== "DELIVERED" && shp.status !== "CANCELLED" && (
                              <button
                                onClick={() => {
                                  setTrackingEventError(null);
                                  setTrackingEventStatus(shp.status);
                                  setTrackingEventLocation("");
                                  setTrackingEventDescription("");
                                  setTrackingEventShipment(shp);
                                }}
                                className="text-[11px] text-indigo-600 hover:text-indigo-800 font-bold flex items-center gap-1"
                              >
                                <Plus className="w-3 h-3" />
                                <span>Add Checkpoint</span>
                              </button>
                            )}
                          </div>

                          {shp.tracking_events && shp.tracking_events.length > 0 ? (
                            <div className="relative pl-4 space-y-2 before:absolute before:left-1.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
                              {shp.tracking_events.map((evt, eIdx) => (
                                <div key={evt.id || eIdx} className="relative text-[11px]">
                                  <div className="absolute -left-4 top-1.5 w-2 h-2 rounded-full bg-indigo-500 ring-2 ring-white" />
                                  <div className="flex flex-wrap items-baseline gap-2">
                                    <span className="font-bold text-slate-900">
                                      {evt.status_display || evt.status}
                                    </span>
                                    {evt.location && (
                                      <span className="text-slate-500">· {evt.location}</span>
                                    )}
                                    <span className="text-[10px] text-slate-400">
                                      {new Date(evt.event_timestamp).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" })}
                                    </span>
                                  </div>
                                  <p className="text-slate-600 text-xs mt-0.5">{evt.description}</p>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="text-[11px] text-slate-400 italic">
                              No tracking checkpoints recorded yet.
                            </p>
                          )}
                        </div>

                        {/* Shipment Action Transitions */}
                        {shp.status !== "DELIVERED" && shp.status !== "CANCELLED" && (
                          <div className="pt-2 border-t border-slate-200 flex flex-wrap items-center gap-2">
                            <span className="text-[10px] uppercase font-bold text-slate-400 mr-1">
                              Advance Shipment:
                            </span>

                            {shp.status === "CREATED" && (
                              <button
                                onClick={() => {
                                  setShipmentUpdateError(null);
                                  setShipmentLocation("");
                                  setShipmentDescription("Package dispatched from seller warehouse.");
                                  setShipmentStatusTarget({ shipment: shp, targetStatus: "DISPATCHED" });
                                }}
                                className="px-2.5 py-1 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-[11px] font-bold transition-colors"
                              >
                                Mark Dispatched
                              </button>
                            )}

                            {shp.status === "DISPATCHED" && (
                              <button
                                onClick={() => {
                                  setShipmentUpdateError(null);
                                  setShipmentLocation("");
                                  setShipmentDescription("Consignment handed over to courier and in transit.");
                                  setShipmentStatusTarget({ shipment: shp, targetStatus: "IN_TRANSIT" });
                                }}
                                className="px-2.5 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-[11px] font-bold transition-colors"
                              >
                                Mark In Transit
                              </button>
                            )}

                            {(shp.status === "DISPATCHED" || shp.status === "IN_TRANSIT") && (
                              <button
                                onClick={() => {
                                  setShipmentUpdateError(null);
                                  setShipmentLocation("");
                                  setShipmentDescription("Courier out for delivery to recipient address.");
                                  setShipmentStatusTarget({ shipment: shp, targetStatus: "OUT_FOR_DELIVERY" });
                                }}
                                className="px-2.5 py-1 rounded-lg bg-amber-500 hover:bg-amber-600 text-slate-950 text-[11px] font-bold transition-colors"
                              >
                                Mark Out for Delivery
                              </button>
                            )}

                            {shp.status !== "CREATED" && (
                              <button
                                onClick={() => {
                                  setShipmentUpdateError(null);
                                  setShipmentLocation("");
                                  setShipmentDescription("Package successfully delivered and signed for.");
                                  setShipmentStatusTarget({ shipment: shp, targetStatus: "DELIVERED" });
                                }}
                                className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-bold transition-colors"
                              >
                                Mark Delivered
                              </button>
                            )}

                            <button
                              onClick={() => {
                                setShipmentUpdateError(null);
                                setShipmentLocation("");
                                setShipmentDescription("Shipment cancelled by seller.");
                                setShipmentStatusTarget({ shipment: shp, targetStatus: "CANCELLED" });
                              }}
                              className="px-2.5 py-1 rounded-lg border border-rose-300 text-rose-700 hover:bg-rose-50 text-[11px] font-bold transition-colors"
                            >
                              Cancel Shipment
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="py-6 px-4 bg-slate-50 rounded-xl text-center space-y-2 border border-slate-100">
                    <Package className="w-8 h-8 text-slate-300 mx-auto" />
                    <p className="text-xs font-bold text-slate-700">No shipments created for this order yet.</p>
                    <p className="text-[11px] text-slate-400 max-w-sm mx-auto">
                      Click &ldquo;Create Shipment&rdquo; above to assign courier tracking numbers and allocate purchased item quantities.
                    </p>
                  </div>
                )}
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

              {/* Payment & Settlement Details */}
              <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-xs space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                    <CreditCard className="w-3.5 h-3.5 text-amber-500" />
                    <span>Payment & Settlement Tracking</span>
                  </h4>
                  {getPaymentBadge(selectedOrder)}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                  <div className="p-2.5 bg-slate-50 rounded-xl">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">Method</span>
                    <span className="font-bold text-slate-900">
                      {selectedOrder.payment_method === "COD" ? "Cash on Delivery (COD)" : "Online Payment"}
                    </span>
                  </div>

                  <div className="p-2.5 bg-slate-50 rounded-xl">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">Payment Status</span>
                    <span className="font-bold text-slate-900">
                      {selectedOrder.payment_status}
                    </span>
                  </div>

                  <div className="p-2.5 bg-slate-50 rounded-xl">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">Reference</span>
                    <span className="font-mono text-slate-700 truncate block" title={selectedOrder.payment_reference || "N/A"}>
                      {selectedOrder.payment_reference || "None"}
                    </span>
                  </div>
                </div>

                {selectedOrder.payment_method === "COD" && (
                  <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-xl text-xs text-amber-900 space-y-1">
                    <p className="font-bold flex items-center gap-1">
                      <Banknote className="w-3.5 h-3.5 text-amber-600" />
                      COD Collection Status: {selectedOrder.cod_collection_status}
                    </p>
                    <p className="text-[11px] text-amber-800">
                      Payment collection is handled by courier personnel on delivery and verified by platform operations staff. Sellers cannot directly mark COD as collected.
                    </p>
                  </div>
                )}
              </div>

              {/* Returns, Refunds & Disputes Section for this Order */}
              {((selectedOrder.return_requests && selectedOrder.return_requests.length > 0) ||
                (selectedOrder.refunds && selectedOrder.refunds.length > 0) ||
                (selectedOrder.disputes && selectedOrder.disputes.length > 0)) && (
                <div className="p-4 sm:p-5 rounded-2xl bg-white border border-slate-200 shadow-xs space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center gap-1.5">
                      <RotateCcw className="w-3.5 h-3.5 text-amber-500" />
                      <span>Returns, Refunds & Dispute Cases</span>
                    </h4>
                  </div>

                  {/* Return Requests on this Order */}
                  {selectedOrder.return_requests && selectedOrder.return_requests.length > 0 && (
                    <div className="space-y-2">
                      <span className="text-[10px] uppercase font-bold text-slate-400 block">
                        Return Requests ({selectedOrder.return_requests.length})
                      </span>
                      <div className="space-y-2">
                        {selectedOrder.return_requests.map((ret) => (
                          <div key={ret.id} className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="font-mono font-bold text-slate-900">{ret.request_number}</span>
                              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">
                                {ret.status}
                              </span>
                            </div>
                            <p className="text-slate-600 text-[11px]">Reason: {ret.description || ret.buyer_reason || ret.reason}</p>
                            <div className="flex items-center justify-between text-[11px] pt-1 border-t border-slate-200 text-slate-500">
                              <span>Amount: {selectedOrder.currency} {Number(ret.refund_amount || 0).toFixed(2)}</span>
                              {ret.status === "PENDING" && (
                                <div className="flex gap-2">
                                  <button
                                    onClick={() => setSelectedReturnForReview({ returnReq: ret, action: "APPROVE" })}
                                    className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-[10px] rounded-lg"
                                  >
                                    Approve
                                  </button>
                                  <button
                                    onClick={() => setSelectedReturnForReview({ returnReq: ret, action: "REJECT" })}
                                    className="px-2.5 py-1 border border-rose-300 text-rose-700 hover:bg-rose-50 font-bold text-[10px] rounded-lg"
                                  >
                                    Reject
                                  </button>
                                </div>
                              )}
                              {ret.status === "APPROVED" && ret.request_type === "RETURN" && (
                                <button
                                  onClick={() => setCompleteReturnModal(ret)}
                                  className="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-[10px] rounded-lg"
                                >
                                  Confirm Return & Restock
                                </button>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Refunds on this Order */}
                  {selectedOrder.refunds && selectedOrder.refunds.length > 0 && (
                    <div className="space-y-2">
                      <span className="text-[10px] uppercase font-bold text-slate-400 block">
                        Refund Transactions ({selectedOrder.refunds.length})
                      </span>
                      <div className="space-y-1.5">
                        {selectedOrder.refunds.map((ref) => (
                          <div key={ref.id} className="p-2.5 bg-slate-50 rounded-xl flex items-center justify-between text-xs">
                            <div>
                              <span className="font-mono font-bold text-slate-900">{ref.refund_number}</span>
                              <span className="text-[10px] text-slate-500 ml-2">Reason: {ref.reason || ref.reason_category}</span>
                            </div>
                            <div className="text-right">
                              <span className="font-mono font-bold text-slate-900">
                                {selectedOrder.currency} {Number(ref.amount).toFixed(2)}
                              </span>
                              <span className="block text-[10px] font-bold text-emerald-700 uppercase">{ref.status}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Disputes on this Order */}
                  {selectedOrder.disputes && selectedOrder.disputes.length > 0 && (
                    <div className="space-y-2">
                      <span className="text-[10px] uppercase font-bold text-slate-400 block">
                        Commercial Disputes ({selectedOrder.disputes.length})
                      </span>
                      <div className="space-y-2">
                        {selectedOrder.disputes.map((disp) => (
                          <div key={disp.id} className="p-3 bg-rose-50/50 rounded-xl border border-rose-200 text-xs flex items-center justify-between">
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-mono font-bold text-slate-900">{disp.dispute_number}</span>
                                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-rose-100 text-rose-800">
                                  {disp.status}
                                </span>
                              </div>
                              <p className="text-[11px] text-slate-600 mt-0.5 line-clamp-1">{disp.description}</p>
                            </div>
                            <button
                              onClick={() => openDisputeDrawer(disp)}
                              className="px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white text-[11px] font-bold rounded-lg shrink-0"
                            >
                              View Thread
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Modal Footer Actions */}
            <div className="p-4 sm:p-5 bg-slate-50 border-t border-slate-200 flex flex-wrap items-center justify-between gap-3 shrink-0">
              <div className="flex items-center gap-2">
                {!isAdmin && selectedOrder.status === "PENDING_CONFIRMATION" && (
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

                {!isAdmin && selectedOrder.status === "CONFIRMED" && (
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

                {!isAdmin && selectedOrder.status === "PROCESSING" && (
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

      {/* ========================================================= */}
      {/* CREATE SHIPMENT MODAL                                     */}
      {/* ========================================================= */}
      {createShipmentOrder && (
        <div className="fixed inset-0 z-60 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
          <div className="bg-white rounded-3xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            {/* Header */}
            <div className="p-5 sm:p-6 bg-slate-900 text-white flex items-center justify-between shrink-0">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-indigo-500 text-white flex items-center justify-center">
                    <Truck className="w-4 h-4" />
                  </div>
                  <h3 className="text-base font-black text-white">Create Consignment Shipment</h3>
                </div>
                <p className="text-xs text-slate-400">
                  Order {createShipmentOrder.order_number} · Destination: {createShipmentOrder.shipping_city}, {createShipmentOrder.shipping_country}
                </p>
              </div>
              <button
                onClick={() => setCreateShipmentOrder(null)}
                className="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-slate-800 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Form Body */}
            <div className="p-5 sm:p-6 overflow-y-auto space-y-5">
              {/* Carrier Selection */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[11px] font-bold text-slate-700 block">
                    Logistics Carrier <span className="text-rose-500">*</span>
                  </label>
                  {loadingCarriers ? (
                    <div className="p-2.5 rounded-xl border border-slate-200 bg-slate-50 flex items-center gap-2 text-xs text-slate-500">
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-500" />
                      <span>Loading available carriers...</span>
                    </div>
                  ) : (
                    <select
                      value={carrierCode}
                      onChange={(e) => setCarrierCode(e.target.value)}
                      className="w-full p-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 bg-white focus:outline-hidden focus:ring-2 focus:ring-indigo-500 transition-all font-medium"
                    >
                      {carriers.map((c) => (
                        <option key={c.code} value={c.code}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                {carrierCode === "OTHER" ? (
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-bold text-slate-700 block">
                      Custom Carrier / Courier Name
                    </label>
                    <input
                      type="text"
                      value={customCarrierName}
                      onChange={(e) => setCustomCarrierName(e.target.value)}
                      placeholder="e.g. Local Courier Express, Direct Van..."
                      className="w-full p-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 transition-all"
                    />
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-bold text-slate-700 block">
                      Tracking / Consignment Number
                    </label>
                    <input
                      type="text"
                      value={trackingNumberInput}
                      onChange={(e) => setTrackingNumberInput(e.target.value)}
                      placeholder="e.g. TRK-9876543210"
                      className="w-full p-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 transition-all font-mono"
                    />
                  </div>
                )}
              </div>

              {carrierCode === "OTHER" && (
                <div className="space-y-1.5">
                  <label className="text-[11px] font-bold text-slate-700 block">
                    Tracking / Consignment Number
                  </label>
                  <input
                    type="text"
                    value={trackingNumberInput}
                    onChange={(e) => setTrackingNumberInput(e.target.value)}
                    placeholder="e.g. TRK-9876543210"
                    className="w-full p-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 transition-all font-mono"
                  />
                </div>
              )}

              {/* Tracking URL & Est. Delivery */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[11px] font-bold text-slate-700 block">
                    Carrier Tracking URL (Optional)
                  </label>
                  <input
                    type="url"
                    value={trackingUrlInput}
                    onChange={(e) => setTrackingUrlInput(e.target.value)}
                    placeholder="https://carrier.com/track/..."
                    className="w-full p-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 transition-all"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-[11px] font-bold text-slate-700 block">
                    Estimated Delivery Date (Optional)
                  </label>
                  <input
                    type="date"
                    value={estimatedDeliveryInput}
                    onChange={(e) => setEstimatedDeliveryInput(e.target.value)}
                    className="w-full p-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 transition-all"
                  />
                </div>
              </div>

              {/* Delivery Notes */}
              <div className="space-y-1.5">
                <label className="text-[11px] font-bold text-slate-700 block">
                  Delivery Notes / Package Memo (Optional)
                </label>
                <input
                  type="text"
                  value={deliveryNotesInput}
                  onChange={(e) => setDeliveryNotesInput(e.target.value)}
                  placeholder="e.g. Box 1 of 1, fragile automotive glass, left with warehouse..."
                  className="w-full p-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 transition-all"
                />
              </div>

              {/* Immediate Dispatch Checkbox */}
              <label className="p-3 bg-indigo-50/60 border border-indigo-100 rounded-xl flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={dispatchImmediatelyInput}
                  onChange={(e) => setDispatchImmediatelyInput(e.target.checked)}
                  className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 border-slate-300"
                />
                <div className="text-xs">
                  <span className="font-bold text-slate-900">Mark as Dispatched immediately</span>
                  <p className="text-[11px] text-slate-500">
                    If checked, the shipment status will start at DISPATCHED instead of CREATED.
                  </p>
                </div>
              </label>

              {/* Item Quantity Allocation */}
              <div className="space-y-2">
                <label className="text-[11px] font-bold text-slate-700 block uppercase tracking-wider">
                  Select Item Quantities to Include in this Shipment
                </label>
                <div className="border border-slate-200 rounded-2xl divide-y divide-slate-100 overflow-hidden">
                  {createShipmentOrder.items.map((item) => {
                    const remaining = getItemRemainingQuantity(item, createShipmentOrder.shipments);
                    const shipped = getItemShippedQuantity(item, createShipmentOrder.shipments);
                    const currentAlloc = itemQuantitiesToShip[item.id] || 0;

                    return (
                      <div
                        key={item.id}
                        className="p-3.5 flex items-center justify-between gap-3 text-xs bg-white"
                      >
                        <div className="space-y-0.5 flex-1 min-w-0">
                          <p className="font-bold text-slate-900 truncate">{item.title}</p>
                          <p className="text-[11px] text-slate-400">
                            Brand: {item.brand} {item.mpn ? `· MPN: ${item.mpn}` : ""}
                          </p>
                          <p className="text-[10px] text-slate-500 font-medium">
                            Ordered: {item.quantity} · Already Shipped: {shipped} · Remaining:{" "}
                            <strong className={remaining > 0 ? "text-indigo-600" : "text-slate-400"}>
                              {remaining}
                            </strong>
                          </p>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-[11px] text-slate-500 font-medium">Pack Qty:</span>
                          <input
                            type="number"
                            min={0}
                            max={remaining}
                            value={currentAlloc}
                            onChange={(e) => {
                              const val = Math.max(0, Math.min(remaining, parseInt(e.target.value) || 0));
                              setItemQuantitiesToShip((prev) => ({ ...prev, [item.id]: val }));
                            }}
                            disabled={remaining === 0}
                            className="w-16 p-2 rounded-lg border border-slate-200 text-center text-xs font-bold text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-100 disabled:text-slate-400"
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {createShipmentError && (
                <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs font-medium">
                  {createShipmentError}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="p-4 sm:p-5 bg-slate-50 border-t border-slate-200 flex items-center justify-between gap-3 shrink-0">
              <button
                type="button"
                onClick={() => setCreateShipmentOrder(null)}
                disabled={isSubmittingShipment}
                className="px-4 py-2.5 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-bold transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCreateShipment}
                disabled={isSubmittingShipment}
                className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition-all shadow-md flex items-center gap-2 disabled:opacity-50"
              >
                {isSubmittingShipment ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Creating Consignment...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" />
                    <span>Create & Assign Shipment</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* UPDATE SHIPMENT STATUS MODAL                              */}
      {/* ========================================================= */}
      {shipmentStatusTarget && (
        <div className="fixed inset-0 z-60 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
                <Truck className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-black text-slate-900">
                  Update Shipment to {shipmentStatusTarget.targetStatus}
                </h3>
                <p className="text-xs text-slate-500 font-mono">
                  {shipmentStatusTarget.shipment.shipment_number}
                </p>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              Advancing shipment status records an automatic tracking milestone and updates order fulfillment progress.
            </p>

            <div className="space-y-3">
              <div className="space-y-1">
                <label className="text-[11px] font-bold text-slate-700 block">
                  Location (Optional)
                </label>
                <input
                  type="text"
                  value={shipmentLocation}
                  onChange={(e) => setShipmentLocation(e.target.value)}
                  placeholder="e.g. Birmingham Hub, Mumbai Sorting Center..."
                  className="w-full p-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 transition-all"
                />
              </div>

              <div className="space-y-1">
                <label className="text-[11px] font-bold text-slate-700 block">
                  Status Description / Notes (Optional)
                </label>
                <textarea
                  value={shipmentDescription}
                  onChange={(e) => setShipmentDescription(e.target.value)}
                  placeholder="e.g. Handed over to courier driver, signed by recipient..."
                  rows={2}
                  className="w-full p-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 transition-all"
                />
              </div>
            </div>

            {shipmentUpdateError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs">
                {shipmentUpdateError}
              </div>
            )}

            <div className="flex items-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShipmentStatusTarget(null)}
                disabled={isUpdatingShipmentStatus}
                className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-bold transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleUpdateShipmentStatus}
                disabled={isUpdatingShipmentStatus}
                className="flex-1 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {isUpdatingShipmentStatus ? (
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

      {/* ========================================================= */}
      {/* ADD TRACKING CHECKPOINT MODAL                             */}
      {/* ========================================================= */}
      {trackingEventShipment && (
        <div className="fixed inset-0 z-60 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
                <Navigation className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-black text-slate-900">
                  Log Tracking Checkpoint
                </h3>
                <p className="text-xs text-slate-500 font-mono">
                  {trackingEventShipment.shipment_number}
                </p>
              </div>
            </div>

            <div className="space-y-3">
              <div className="space-y-1">
                <label className="text-[11px] font-bold text-slate-700 block">
                  Milestone Status
                </label>
                <select
                  value={trackingEventStatus}
                  onChange={(e) => setTrackingEventStatus(e.target.value)}
                  className="w-full p-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 bg-white focus:outline-hidden focus:ring-2 focus:ring-indigo-500 transition-all font-medium"
                >
                  <option value={trackingEventShipment.status}>
                    Current ({trackingEventShipment.status})
                  </option>
                  <option value="IN_TRANSIT">IN_TRANSIT (In Transit)</option>
                  <option value="OUT_FOR_DELIVERY">OUT_FOR_DELIVERY (Out for Delivery)</option>
                  <option value="DELIVERED">DELIVERED (Delivered)</option>
                  <option value="FAILED_DELIVERY">FAILED_DELIVERY (Delivery Failed)</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-[11px] font-bold text-slate-700 block">
                  Checkpoint Description <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  value={trackingEventDescription}
                  onChange={(e) => setTrackingEventDescription(e.target.value)}
                  placeholder="e.g. Arrived at Regional Sorting Hub"
                  className="w-full p-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 transition-all"
                />
              </div>

              <div className="space-y-1">
                <label className="text-[11px] font-bold text-slate-700 block">
                  Location (Optional)
                </label>
                <input
                  type="text"
                  value={trackingEventLocation}
                  onChange={(e) => setTrackingEventLocation(e.target.value)}
                  placeholder="e.g. Heathrow Distribution Center"
                  className="w-full p-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 transition-all"
                />
              </div>
            </div>

            {trackingEventError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs">
                {trackingEventError}
              </div>
            )}

            <div className="flex items-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => setTrackingEventShipment(null)}
                disabled={isAddingTrackingEvent}
                className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-bold transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleAddTrackingEvent}
                disabled={isAddingTrackingEvent || !trackingEventDescription.trim()}
                className="flex-1 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {isAddingTrackingEvent ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Recording...</span>
                  </>
                ) : (
                  <span>Record Checkpoint</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* SELLER RETURN REVIEW MODAL                                */}
      {/* ========================================================= */}
      {selectedReturnForReview && (
        <div className="fixed inset-0 z-60 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center gap-3">
              <div
                className={`w-10 h-10 rounded-2xl flex items-center justify-center shrink-0 ${
                  selectedReturnForReview.action === "APPROVE"
                    ? "bg-emerald-100 text-emerald-600"
                    : "bg-rose-100 text-rose-600"
                }`}
              >
                {selectedReturnForReview.action === "APPROVE" ? (
                  <Check className="w-5 h-5" />
                ) : (
                  <X className="w-5 h-5" />
                )}
              </div>
              <div>
                <h3 className="text-base font-black text-slate-900">
                  {selectedReturnForReview.action === "APPROVE"
                    ? "Approve Return Request"
                    : "Reject Return Request"}
                </h3>
                <p className="text-xs text-slate-500 font-mono">
                  {selectedReturnForReview.returnReq.request_number} · Order: {selectedReturnForReview.returnReq.order_number}
                </p>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              {selectedReturnForReview.action === "APPROVE"
                ? "Approving this request authorizes the buyer to return the items to your facility. Once you receive and verify the returned goods, you will complete the return to restock inventory and trigger the refund."
                : "Rejecting this request will close the return request. Please provide a clear, factual justification for rejecting the customer's request."}
            </p>

            {selectedReturnForReview.action === "REJECT" && (
              <div className="space-y-1.5">
                <label className="text-[11px] font-bold text-slate-700 block">
                  Rejection Reason <span className="text-rose-500">*</span>
                </label>
                <textarea
                  value={rejectionReasonInput}
                  onChange={(e) => setRejectionReasonInput(e.target.value)}
                  placeholder="e.g. Return window expired, item damaged by customer, part installed incorrectly..."
                  rows={3}
                  className="w-full p-3 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-rose-500 transition-all"
                />
              </div>
            )}

            {reviewError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs">
                {reviewError}
              </div>
            )}

            <div className="flex items-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => setSelectedReturnForReview(null)}
                disabled={isReviewingReturn}
                className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-bold transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleReviewReturn}
                disabled={
                  isReviewingReturn ||
                  (selectedReturnForReview.action === "REJECT" && !rejectionReasonInput.trim())
                }
                className={`flex-1 py-2.5 rounded-xl text-white text-xs font-bold transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50 ${
                  selectedReturnForReview.action === "APPROVE"
                    ? "bg-emerald-600 hover:bg-emerald-700"
                    : "bg-rose-600 hover:bg-rose-700"
                }`}
              >
                {isReviewingReturn ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Processing...</span>
                  </>
                ) : (
                  <span>
                    {selectedReturnForReview.action === "APPROVE" ? "Confirm Approval" : "Confirm Rejection"}
                  </span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* SELLER COMPLETE RETURN (RECEIPT & RESTOCK) MODAL           */}
      {/* ========================================================= */}
      {completeReturnModal && (
        <div className="fixed inset-0 z-60 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
                <Boxes className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-black text-slate-900">
                  Confirm Item Receipt & Restock
                </h3>
                <p className="text-xs text-slate-500 font-mono">
                  {completeReturnModal.request_number} · Order: {completeReturnModal.order_number}
                </p>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              Confirming delivery acknowledges that you have physically received the returned items back in satisfactory condition. This action will automatically restock the returned quantities back into your inventory catalogue and generate the refund record for settlement.
            </p>

            <div className="space-y-1.5">
              <label className="text-[11px] font-bold text-slate-700 block">
                Return Courier Waybill / Tracking (Optional)
              </label>
              <input
                type="text"
                value={returnTrackingNumberInput}
                onChange={(e) => setReturnTrackingNumberInput(e.target.value)}
                placeholder="e.g. RET-TRK-123456"
                className="w-full p-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 transition-all font-mono"
              />
            </div>

            {completeReturnError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs">
                {completeReturnError}
              </div>
            )}

            <div className="flex items-center gap-3 pt-2">
              <button
                type="button"
                onClick={() => setCompleteReturnModal(null)}
                disabled={isCompletingReturn}
                className="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-bold transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCompleteReturn}
                disabled={isCompletingReturn}
                className="flex-1 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {isCompletingReturn ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Restocking...</span>
                  </>
                ) : (
                  <span>Confirm & Restock</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* DISPUTE THREAD DRAWER                                      */}
      {/* ========================================================= */}
      {activeDisputeDrawer && (
        <div className="fixed inset-0 z-60 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
          <div className="bg-white rounded-3xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            {/* Header */}
            <div className="p-5 sm:p-6 bg-slate-900 text-white flex items-center justify-between shrink-0">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Scale className="w-5 h-5 text-amber-400" />
                  <span className="font-mono font-black text-base text-amber-400">
                    {activeDisputeDrawer.dispute_number}
                  </span>
                  {getDisputePriorityBadge(activeDisputeDrawer.priority)}
                </div>
                <p className="text-xs text-slate-400">
                  Order {activeDisputeDrawer.order_number} · Category: {activeDisputeDrawer.category_display || activeDisputeDrawer.category}
                </p>
              </div>

              <div className="flex items-center gap-2">
                {getDisputeStatusBadge(activeDisputeDrawer.status)}
                <button
                  onClick={() => setActiveDisputeDrawer(null)}
                  className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors ml-2"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Conversation Timeline */}
            <div className="p-5 sm:p-6 overflow-y-auto space-y-4 flex-1 bg-slate-50/50">
              {/* Buyer Initial Description */}
              <div className="p-4 bg-white rounded-2xl border border-slate-200 shadow-xs space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-900">
                    {activeDisputeDrawer.buyer_name || activeDisputeDrawer.buyer_email} (Buyer Claim)
                  </span>
                  <span className="text-[10px] text-slate-400">
                    {new Date(activeDisputeDrawer.created_at).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" })}
                  </span>
                </div>
                <p className="text-xs text-slate-700 leading-relaxed">{activeDisputeDrawer.description}</p>
                {activeDisputeDrawer.evidence_urls && activeDisputeDrawer.evidence_urls.length > 0 && (
                  <div className="flex flex-wrap gap-2 pt-2">
                    {activeDisputeDrawer.evidence_urls.map((url, idx) => (
                      <a
                        key={idx}
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="w-14 h-14 rounded-lg border border-slate-200 overflow-hidden block bg-slate-100 shrink-0"
                      >
                        <img src={url} alt="Evidence" className="w-full h-full object-cover" />
                      </a>
                    ))}
                  </div>
                )}
              </div>

              {/* Event Timeline */}
              {loadingDisputeEvents ? (
                <div className="py-8 text-center text-xs text-slate-500 flex items-center justify-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin text-amber-500" />
                  <span>Loading dispute timeline...</span>
                </div>
              ) : disputeEvents.length > 0 ? (
                <div className="space-y-3">
                  {disputeEvents.map((evt) => (
                    <div
                      key={evt.id}
                      className={`p-3.5 rounded-2xl text-xs space-y-1.5 border shadow-xs ${
                        evt.actor_role === "STAFF" || evt.actor_role === "ADMIN"
                          ? "bg-purple-50 border-purple-200"
                          : evt.actor_role === "SELLER"
                          ? "bg-blue-50 border-blue-200 ml-6"
                          : "bg-white border-slate-200 mr-6"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-slate-900">
                            {evt.actor_name || evt.actor_email}
                          </span>
                          <span
                            className={`text-[9px] font-black uppercase px-1.5 py-0.5 rounded ${
                              evt.actor_role === "STAFF" || evt.actor_role === "ADMIN"
                                ? "bg-purple-200 text-purple-900"
                                : evt.actor_role === "SELLER"
                                ? "bg-blue-200 text-blue-900"
                                : "bg-slate-200 text-slate-800"
                            }`}
                          >
                            {evt.actor_role}
                          </span>
                        </div>
                        <span className="text-[10px] text-slate-400">
                          {new Date(evt.created_at).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" })}
                        </span>
                      </div>
                      <p className="text-slate-800">{evt.message}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-center text-xs text-slate-400 italic py-4">
                  No additional communication recorded yet.
                </p>
              )}
            </div>

            {/* Reply Input Form */}
            <div className="p-4 sm:p-5 bg-white border-t border-slate-200 space-y-3 shrink-0">
              <div className="space-y-1">
                <label className="text-[11px] font-bold text-slate-700 block">
                  Add Seller Response / Evidence Explanation
                </label>
                <textarea
                  value={sellerReplyMessage}
                  onChange={(e) => setSellerReplyMessage(e.target.value)}
                  placeholder="Provide clarification, dispatch proof, or agreement with claim..."
                  rows={2}
                  disabled={isPostingDisputeReply}
                  className="w-full p-2.5 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 transition-all"
                />
              </div>

              {disputeReplyError && (
                <div className="p-2.5 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs">
                  {disputeReplyError}
                </div>
              )}

              <div className="flex items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={() => setActiveDisputeDrawer(null)}
                  className="px-4 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-bold transition-colors"
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={handlePostSellerDisputeReply}
                  disabled={isPostingDisputeReply || !sellerReplyMessage.trim()}
                  className="px-5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-2 disabled:opacity-50"
                >
                  {isPostingDisputeReply ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Sending...</span>
                    </>
                  ) : (
                    <>
                      <Send className="w-3.5 h-3.5 text-amber-400" />
                      <span>Post Response</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
