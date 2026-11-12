"use client";

import React, { useState, useEffect, useCallback } from "react";
import Image from "next/image";
import {
  api,
  VehiclePurchaseOffer,
  VehicleOrder,
  resolveMediaUrl,
} from "@/lib/api/client";
import {
  Car,
  Tag,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Building2,
  Check,
  RefreshCw,
  FileText,
  ShieldCheck,
  Receipt,
  CreditCard,
} from "lucide-react";

interface BuyerVehicleOrdersOffersSectionProps {
  onNavigateToBrowse?: () => void;
}

export default function BuyerVehicleOrdersOffersSection({
  onNavigateToBrowse,
}: BuyerVehicleOrdersOffersSectionProps) {
  const [subTab, setSubTab] = useState<"offers" | "orders">("offers");
  const [offers, setOffers] = useState<VehiclePurchaseOffer[]>([]);
  const [orders, setOrders] = useState<VehicleOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Counter Modal State (Buyer countering dealer)
  const [counterModalOffer, setCounterModalOffer] = useState<VehiclePurchaseOffer | null>(null);
  const [counterPrice, setCounterPrice] = useState<string>("");
  const [counterNotes, setCounterNotes] = useState<string>("");
  const [actionLoading, setActionLoading] = useState(false);

  // Selected Detail Modal
  const [selectedOffer, setSelectedOffer] = useState<VehiclePurchaseOffer | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<VehicleOrder | null>(null);

  // Payment Reporting Modal State (Phase 2)
  const [reportPaymentOrder, setReportPaymentOrder] = useState<VehicleOrder | null>(null);
  const [paymentRef, setPaymentRef] = useState<string>("");
  const [paymentPaidAt, setPaymentPaidAt] = useState<string>("");
  const [paymentNotes, setPaymentNotes] = useState<string>("");
  const [paymentReporting, setPaymentReporting] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [offersData, ordersData] = await Promise.all([
        api.marketplace.listBuyerVehicleOffers(),
        api.marketplace.listBuyerVehicleOrders(),
      ]);
      setOffers(offersData);
      setOrders(ordersData);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load vehicle offers and orders.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => {
      void loadData();
    });
  }, [loadData]);

  // Buyer accepts dealer counteroffer
  const handleAcceptCounteroffer = async (offer: VehiclePurchaseOffer) => {
    if (!confirm(`Are you sure you want to accept the dealer's terms of £${Number(offer.proposals[offer.proposals.length - 1]?.offered_price || offer.agreed_price).toLocaleString()}? This will reserve the vehicle and create your Vehicle Purchase Order.`)) {
      return;
    }
    setActionLoading(true);
    setError(null);
    try {
      const order = await api.marketplace.acceptBuyerVehicleOffer(offer.id);
      setActionSuccess(`Counteroffer accepted! Vehicle reserved under Order #${order.order_number}.`);
      setSubTab("orders");
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to accept counteroffer.";
      setError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  // Buyer rejects dealer counteroffer
  const handleRejectCounteroffer = async (offer: VehiclePurchaseOffer) => {
    const reason = prompt("Optional reason for declining this counteroffer:") || "";
    setActionLoading(true);
    setError(null);
    try {
      await api.marketplace.rejectBuyerVehicleOffer(offer.id, reason);
      setActionSuccess("Counteroffer rejected.");
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to reject counteroffer.";
      setError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  // Buyer withdraws pending offer
  const handleWithdrawOffer = async (offer: VehiclePurchaseOffer) => {
    if (!confirm("Are you sure you want to withdraw this purchase offer?")) return;
    setActionLoading(true);
    setError(null);
    try {
      await api.marketplace.withdrawBuyerVehicleOffer(offer.id, "Buyer withdrew offer prior to review.");
      setActionSuccess("Offer successfully withdrawn.");
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to withdraw offer.";
      setError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  // Submit buyer counteroffer
  const handleSubmitCounter = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!counterModalOffer) return;
    const num = parseFloat(counterPrice);
    if (isNaN(num) || num <= 0) {
      alert("Please enter a valid counteroffer price.");
      return;
    }
    setActionLoading(true);
    setError(null);
    try {
      await api.marketplace.counterBuyerVehicleOffer(counterModalOffer.id, {
        counter_price: num,
        notes: counterNotes.trim(),
      });
      setActionSuccess(`Counteroffer of £${num.toLocaleString()} submitted to dealer.`);
      setCounterModalOffer(null);
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to submit counteroffer.";
      setError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const handleOpenReportPayment = (order: VehicleOrder) => {
    setReportPaymentOrder(order);
    setPaymentRef("");
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    setPaymentPaidAt(now.toISOString().slice(0, 16));
    setPaymentNotes("");
  };

  const handleSubmitPaymentReport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reportPaymentOrder) return;
    if (!paymentRef.trim() || paymentRef.trim().length < 3) {
      setError("Please provide a valid transaction reference (at least 3 characters).");
      return;
    }
    if (!paymentPaidAt) {
      setError("Please select the date and time of payment.");
      return;
    }

    setPaymentReporting(true);
    setError(null);
    try {
      await api.marketplace.reportBuyerVehicleOrderPayment(reportPaymentOrder.id, {
        amount_paid: reportPaymentOrder.agreed_price,
        currency: reportPaymentOrder.currency,
        payment_reference: paymentRef.trim(),
        paid_at: new Date(paymentPaidAt).toISOString(),
        payment_notes: paymentNotes.trim(),
      });
      setActionSuccess(`Payment report submitted for Order #${reportPaymentOrder.order_number}! Awaiting dealer verification.`);
      setReportPaymentOrder(null);
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to submit offline payment report.";
      setError(msg);
    } finally {
      setPaymentReporting(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "PENDING_DEALER":
        return <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">Pending Dealer Review</span>;
      case "PENDING_BUYER":
        return <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200 animate-pulse">Dealer Countered (Action Required)</span>;
      case "ACCEPTED":
        return <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">Offer Accepted</span>;
      case "REJECTED":
        return <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">Offer Rejected</span>;
      case "SUPERSEDED":
        return <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">Superseded</span>;
      case "WITHDRAWN":
        return <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-500 border border-slate-200">Withdrawn</span>;
      case "EXPIRED":
        return <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-500 border border-slate-200">Expired</span>;
      default:
        return <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600">{status}</span>;
    }
  };

  const getOrderStatusBadge = (order: VehicleOrder) => {
    switch (order.status) {
      case "PAYMENT_PENDING":
        return (
          <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${
            order.is_payment_overdue
              ? "bg-rose-50 text-rose-700 border-rose-300"
              : "bg-amber-50 text-amber-700 border-amber-300"
          }`}>
            {order.is_payment_overdue ? "Payment Overdue (Deadline Expired)" : "Payment Pending (5-Day Window)"}
          </span>
        );
      case "PAYMENT_SUBMITTED":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">Payment Submitted (Awaiting Dealer Confirmation)</span>;
      case "PAYMENT_CONFIRMED":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">Payment Confirmed</span>;
      case "DOCUMENTS_PENDING":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200">Registration Docs Pending</span>;
      case "READY_FOR_HANDOVER":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-cyan-50 text-cyan-700 border border-cyan-200">Ready for Handover</span>;
      case "COMPLETED":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">Transaction Completed</span>;
      case "CANCELLED":
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">Cancelled</span>;
      default:
        return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600">{order.status}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Subtab Navigation */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setSubTab("offers")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 ${
              subTab === "offers"
                ? "bg-slate-900 text-white shadow-sm"
                : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
            }`}
          >
            <Tag className="w-3.5 h-3.5 text-amber-400" />
            <span>Purchase Offers ({offers.length})</span>
          </button>
          <button
            onClick={() => setSubTab("orders")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 ${
              subTab === "orders"
                ? "bg-slate-900 text-white shadow-sm"
                : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
            }`}
          >
            <Car className="w-3.5 h-3.5 text-emerald-400" />
            <span>Vehicle Orders & Reservations ({orders.length})</span>
          </button>
        </div>

        <button
          onClick={loadData}
          disabled={loading}
          className="p-2 text-slate-500 hover:text-slate-800 rounded-lg hover:bg-slate-100 text-xs font-medium flex items-center gap-1"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Success / Error Alerts */}
      {actionSuccess && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-800 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            <span>{actionSuccess}</span>
          </div>
          <button onClick={() => setActionSuccess(null)} className="text-emerald-700 font-bold hover:underline">
            Dismiss
          </button>
        </div>
      )}

      {error && (
        <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-600" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="text-rose-700 font-bold hover:underline">
            Dismiss
          </button>
        </div>
      )}

      {/* SECTION 1: OFFERS */}
      {subTab === "offers" && (
        <div className="space-y-4">
          {offers.length === 0 ? (
            <div className="p-10 bg-white rounded-2xl border border-slate-200 text-center space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-amber-50 text-amber-600 mx-auto flex items-center justify-center">
                <Tag className="w-6 h-6" />
              </div>
              <h4 className="text-sm font-black text-slate-900">No Vehicle Purchase Offers Yet</h4>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                When you browse vehicles on the marketplace, click &quot;Make an Offer&quot; to begin a formal price negotiation.
              </p>
              {onNavigateToBrowse && (
                <button
                  onClick={onNavigateToBrowse}
                  className="px-4 py-2 bg-slate-900 text-white rounded-xl text-xs font-bold hover:bg-slate-800"
                >
                  Browse Vehicles
                </button>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {offers.map((offer) => {
                const latestProp = offer.proposals[offer.proposals.length - 1];
                const isDealerTurn = offer.status === "PENDING_DEALER";
                const isBuyerTurn = offer.status === "PENDING_BUYER";

                return (
                  <div
                    key={offer.id}
                    className="p-5 bg-white rounded-2xl border border-slate-200 shadow-xs hover:border-slate-300 transition-all space-y-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className="w-14 h-14 rounded-xl bg-slate-100 overflow-hidden relative flex-shrink-0 border border-slate-200 flex items-center justify-center">
                          <Car className="w-6 h-6 text-slate-400" />
                          {Boolean(offer.listing_image_url) && (
                            <Image
                              src={resolveMediaUrl(offer.listing_image_url)}
                              alt={offer.listing_title}
                              fill
                              sizes="56px"
                              className="object-cover"
                              onError={(e) => {
                                (e.target as HTMLElement).style.display = "none";
                              }}
                            />
                          )}
                        </div>
                        <div>
                          <h4 className="text-sm font-black text-slate-900">{offer.listing_title}</h4>
                          <p className="text-xs text-slate-500 flex items-center gap-1.5 mt-0.5">
                            <Building2 className="w-3.5 h-3.5 text-slate-400" />
                            <span>Dealer: {offer.organisation_name || offer.seller_name}</span>
                            <span>·</span>
                            <span>Round {offer.current_round}</span>
                          </p>
                        </div>
                      </div>

                      <div className="flex flex-col items-end gap-1">
                        {getStatusBadge(offer.status)}
                        <span className="text-[10px] text-slate-400">
                          Expires: {new Date(offer.expires_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>

                    {/* Proposal Summary Box */}
                    <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 flex flex-wrap items-center justify-between gap-3 text-xs">
                      <div>
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                          Current Offer Terms (Round {offer.current_round})
                        </span>
                        <div className="text-base font-black text-slate-900 mt-0.5">
                          {offer.currency} {Number(latestProp?.offered_price || 0).toLocaleString()}
                        </div>
                        <span className="text-[11px] text-slate-500">
                          Proposed by: <strong>{latestProp?.proposed_by_role === "DEALER" ? "Dealership" : "You (Buyer)"}</strong>
                          {latestProp?.handover_preference && ` · ${latestProp.handover_preference === "COLLECTION" ? "Dealership Collection" : "Dealer Delivery"}`}
                        </span>
                      </div>

                      {latestProp?.notes && (
                        <div className="max-w-md text-xs text-slate-600 bg-white p-2.5 rounded-lg border border-slate-200">
                          <span className="text-[10px] font-bold text-slate-400 block mb-0.5">Notes:</span>
                          &quot;{latestProp.notes}&quot;
                        </div>
                      )}
                    </div>

                    {/* Action Bar */}
                    <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100">
                      <button
                        onClick={() => setSelectedOffer(offer)}
                        className="text-xs font-bold text-slate-600 hover:text-slate-900 flex items-center gap-1"
                      >
                        <FileText className="w-3.5 h-3.5 text-slate-400" />
                        <span>View History ({offer.proposals.length} rounds)</span>
                      </button>

                      <div className="flex items-center gap-2">
                        {isBuyerTurn && (
                          <>
                            <button
                              onClick={() => handleRejectCounteroffer(offer)}
                              disabled={actionLoading}
                              className="px-3 py-1.5 text-xs font-bold text-rose-600 hover:bg-rose-50 rounded-xl border border-rose-200 transition-colors"
                            >
                              Decline
                            </button>
                            <button
                              onClick={() => {
                                setCounterModalOffer(offer);
                                setCounterPrice(String(latestProp?.offered_price || ""));
                                setCounterNotes("");
                              }}
                              disabled={actionLoading}
                              className="px-3 py-1.5 text-xs font-bold text-slate-800 hover:bg-slate-100 rounded-xl border border-slate-300 transition-colors"
                            >
                              Counteroffer
                            </button>
                            <button
                              onClick={() => handleAcceptCounteroffer(offer)}
                              disabled={actionLoading}
                              className="px-4 py-1.5 text-xs font-black bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl shadow-xs transition-colors flex items-center gap-1"
                            >
                              <Check className="w-3.5 h-3.5" />
                              <span>Accept Terms</span>
                            </button>
                          </>
                        )}

                        {isDealerTurn && (
                          <button
                            onClick={() => handleWithdrawOffer(offer)}
                            disabled={actionLoading}
                            className="px-3 py-1.5 text-xs font-bold text-slate-500 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition-colors"
                          >
                            Withdraw Offer
                          </button>
                        )}

                        {offer.status === "ACCEPTED" && offer.order_id && (
                          <button
                            onClick={() => setSubTab("orders")}
                            className="px-3 py-1.5 text-xs font-bold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-xl border border-emerald-200 flex items-center gap-1"
                          >
                            <Car className="w-3.5 h-3.5" />
                            <span>View Vehicle Order</span>
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

      {/* SECTION 2: ORDERS */}
      {subTab === "orders" && (
        <div className="space-y-4">
          {orders.length === 0 ? (
            <div className="p-10 bg-white rounded-2xl border border-slate-200 text-center space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-emerald-50 text-emerald-600 mx-auto flex items-center justify-center">
                <Car className="w-6 h-6" />
              </div>
              <h4 className="text-sm font-black text-slate-900">No Vehicle Orders Yet</h4>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                When a dealer accepts your purchase offer, a dedicated Vehicle Order is placed and the vehicle is reserved.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {orders.map((order) => {
                const deadlineDate = new Date(order.payment_deadline);
                const isOverdue = order.is_payment_overdue;

                return (
                  <div
                    key={order.id}
                    className="p-5 bg-white rounded-2xl border border-slate-200 shadow-xs space-y-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className="w-16 h-16 rounded-xl bg-slate-100 overflow-hidden relative flex-shrink-0 border border-slate-200 flex items-center justify-center">
                          <Car className="w-6 h-6 text-slate-400" />
                          {Boolean(order.listing_image_url) && (
                            <Image
                              src={resolveMediaUrl(order.listing_image_url)}
                              alt={order.listing_title}
                              fill
                              sizes="64px"
                              className="object-cover"
                              onError={(e) => {
                                (e.target as HTMLElement).style.display = "none";
                              }}
                            />
                          )}
                        </div>
                        <div>
                          <span className="text-[10px] font-mono font-bold text-slate-400">#{order.order_number}</span>
                          <h4 className="text-sm font-black text-slate-900">{order.listing_title}</h4>
                          <p className="text-xs text-slate-500 flex items-center gap-1.5 mt-0.5">
                            <Building2 className="w-3.5 h-3.5 text-slate-400" />
                            <span>Dealership: {order.organisation_name || order.seller_name}</span>
                          </p>
                        </div>
                      </div>

                      <div className="flex flex-col items-end gap-1">
                        {getOrderStatusBadge(order)}
                        <span className="text-base font-black text-slate-900">
                          {order.currency} {Number(order.agreed_price).toLocaleString()}
                        </span>
                      </div>
                    </div>

                    {/* Payment Deadline Callout */}
                    {order.status === "PAYMENT_PENDING" && (
                      <div className={`p-4 rounded-xl border flex flex-wrap items-center justify-between gap-3 text-xs ${
                        isOverdue
                          ? "bg-rose-50 border-rose-200 text-rose-900"
                          : "bg-amber-50 border-amber-200 text-amber-900"
                      }`}>
                        <div className="space-y-0.5">
                          <div className="font-bold flex items-center gap-1.5">
                            <Clock className={`w-4 h-4 ${isOverdue ? "text-rose-600" : "text-amber-600"}`} />
                            <span>5-Business-Day Payment Deadline</span>
                          </div>
                          <p className="text-[11px] opacity-90">
                            {isOverdue
                              ? "The statutory payment deadline has elapsed. Order is pending release."
                              : `Please submit your offline bank transfer reference before ${deadlineDate.toLocaleString()} (${order.market_timezone}).`}
                          </p>
                        </div>

                        <div className="text-right">
                          <span className="text-[10px] uppercase font-bold tracking-wider opacity-75 block">Deadline</span>
                          <span className="font-mono font-black text-xs">{deadlineDate.toLocaleDateString()} {deadlineDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                        </div>
                      </div>
                    )}

                    {/* Payment Submitted Callout */}
                    {order.status === "PAYMENT_SUBMITTED" && (
                      <div className="p-4 rounded-xl border border-blue-200 bg-blue-50 text-blue-950 space-y-2 text-xs">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2 font-bold text-blue-900">
                            <Clock className="w-4 h-4 text-blue-600" />
                            <span>Payment Submitted — Awaiting Dealership Verification</span>
                          </div>
                          {order.latest_payment_report?.status === "FLAGGED" ? (
                            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-black bg-amber-100 text-amber-900 border border-amber-300">
                              Discrepancy Flagged by Dealership
                            </span>
                          ) : order.latest_payment_report?.escalation_level === "ESCALATED_120H" ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-rose-100 text-rose-800 border border-rose-300">
                              Escalated to Operations (&gt;120h)
                            </span>
                          ) : order.latest_payment_report?.escalation_level === "OVERDUE_72H" ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-amber-100 text-amber-800 border border-amber-300">
                              Verification Overdue (&gt;72h)
                            </span>
                          ) : order.latest_payment_report?.escalation_level === "WARNING_48H" ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                              Verification Pending (&gt;48h)
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 border border-blue-200">
                              Standard 72h Verification Window
                            </span>
                          )}
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-2 border-t border-blue-200/60 text-[11px]">
                          <div>
                            <span className="text-blue-700 font-medium block">Reported Amount:</span>
                            <span className="font-bold">{order.currency} {Number(order.agreed_price).toLocaleString()}</span>
                          </div>
                          <div>
                            <span className="text-blue-700 font-medium block">Bank Reference:</span>
                            <span className="font-mono font-bold">{order.latest_payment_report?.payment_reference || "Direct Bank Transfer"}</span>
                          </div>
                          <div>
                            <span className="text-blue-700 font-medium block">Transfer Date:</span>
                            <span>{order.latest_payment_report?.paid_at ? new Date(order.latest_payment_report.paid_at).toLocaleString() : (order.payment_submitted_at ? new Date(order.payment_submitted_at).toLocaleString() : "Recently")}</span>
                          </div>
                        </div>

                        {order.latest_payment_report?.status === "FLAGGED" ? (
                          <div className="p-2.5 rounded-lg bg-amber-100/80 border border-amber-300 text-amber-950 text-xs">
                            <strong>Notice:</strong> The dealership flagged an issue with your payment report. Your vehicle remains reserved while dealership staff completes verification or resolution.
                          </div>
                        ) : (
                          <p className="text-[11px] text-blue-800 pt-1">
                            Vehicle remains securely reserved under your order while the dealership confirms receipt in their bank account.
                          </p>
                        )}
                      </div>
                    )}

                    {/* Payment Confirmed Callout */}
                    {order.status === "PAYMENT_CONFIRMED" && (
                      <div className="p-4 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-950 space-y-1.5 text-xs">
                        <div className="flex items-center gap-2 font-bold text-emerald-900">
                          <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                          <span>Payment Verified & Confirmed</span>
                        </div>
                        <p className="text-[11px] text-emerald-800">
                          The dealership has confirmed receipt of your payment {order.payment_confirmed_at ? `on ${new Date(order.payment_confirmed_at).toLocaleDateString()}` : ""}. Your vehicle is fully secured. Registration and handover preparations are now active.
                        </p>
                      </div>
                    )}

                    {/* Order Details Footer */}
                    <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100 text-xs text-slate-500">
                      <div className="flex items-center gap-3">
                        <span>Handover: <strong>{order.handover_type === "COLLECTION" ? "Dealership Collection" : "Dealer Delivery"}</strong></span>
                        <span>·</span>
                        <span>Market: {order.market_timezone}</span>
                      </div>

                      <div className="flex items-center gap-2">
                        {order.status === "PAYMENT_PENDING" && (
                          <button
                            onClick={() => handleOpenReportPayment(order)}
                            className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black text-xs flex items-center gap-1.5 shadow-xs transition-colors"
                          >
                            <CreditCard className="w-3.5 h-3.5" />
                            <span>Report Offline Payment</span>
                          </button>
                        )}
                        <button
                          onClick={() => setSelectedOrder(order)}
                          className="font-bold text-slate-700 hover:text-slate-950 flex items-center gap-1 px-3 py-1.5 hover:bg-slate-50 rounded-xl"
                        >
                          <Receipt className="w-3.5 h-3.5 text-slate-400" />
                          <span>View Contract Summary</span>
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* MODAL: BUYER COUNTEROFFER */}
      {counterModalOffer && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-base font-black text-slate-900">Counter Dealership Offer</h3>
              <button onClick={() => setCounterModalOffer(null)} className="p-1 text-slate-400 hover:text-slate-700">
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmitCounter} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Your New Counter Price ({counterModalOffer.currency})
                </label>
                <input
                  type="number"
                  step="1"
                  min="1"
                  value={counterPrice}
                  onChange={(e) => setCounterPrice(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Notes to Dealership (Optional)
                </label>
                <textarea
                  rows={3}
                  value={counterNotes}
                  onChange={(e) => setCounterNotes(e.target.value)}
                  placeholder="Explain your price reasoning..."
                  className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-400 resize-none"
                />
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setCounterModalOffer(null)}
                  className="px-4 py-2 text-xs font-bold text-slate-600 hover:text-slate-900 rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-5 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-black rounded-xl text-xs transition-colors"
                >
                  {actionLoading ? "Submitting..." : "Send Counteroffer"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: OFFER PROPOSAL REVISION HISTORY */}
      {selectedOffer && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl max-h-[85vh] overflow-y-auto space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-base font-black text-slate-900">Offer Negotiation History</h3>
                <p className="text-xs text-slate-500">{selectedOffer.listing_title}</p>
              </div>
              <button onClick={() => setSelectedOffer(null)} className="p-1 text-slate-400 hover:text-slate-700">
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
                Immutable Proposals ({selectedOffer.proposals.length} rounds)
              </span>
              {selectedOffer.proposals.map((p) => (
                <div key={p.id} className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-900">
                      Round {p.revision_number} · {p.currency} {Number(p.offered_price).toLocaleString()}
                    </span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      p.proposed_by_role === "DEALER"
                        ? "bg-indigo-100 text-indigo-700"
                        : "bg-amber-100 text-amber-800"
                    }`}>
                      {p.proposed_by_role === "DEALER" ? "Dealership" : "Buyer (You)"}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-500">
                    Handover: {p.handover_preference === "COLLECTION" ? "Dealership Collection" : "Dealer Delivery"} · {new Date(p.created_at).toLocaleString()}
                  </div>
                  {p.notes && (
                    <p className="text-slate-700 italic bg-white p-2 rounded border border-slate-200 mt-1">
                      &quot;{p.notes}&quot;
                    </p>
                  )}
                </div>
              ))}
            </div>

            <div className="space-y-2 pt-2 border-t border-slate-100">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Action Audit Log</span>
              <div className="space-y-1 text-xs">
                {selectedOffer.actions.map((act) => (
                  <div key={act.id} className="flex items-center justify-between py-1 text-slate-600">
                    <span className="font-mono font-bold text-[11px]">{act.action_type}</span>
                    <span className="text-[10px] text-slate-400">{new Date(act.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setSelectedOffer(null)}
                className="px-4 py-2 bg-slate-900 text-white rounded-xl text-xs font-bold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: VEHICLE ORDER SUMMARY */}
      {selectedOrder && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <span className="text-[10px] font-mono font-bold text-slate-400">#{selectedOrder.order_number}</span>
                <h3 className="text-base font-black text-slate-900">Vehicle Purchase Contract Summary</h3>
              </div>
              <button onClick={() => setSelectedOrder(null)} className="p-1 text-slate-400 hover:text-slate-700">
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 bg-slate-50 rounded-2xl border border-slate-200 space-y-2 text-xs">
              <div className="flex justify-between py-1 border-b border-slate-200">
                <span className="text-slate-500">Vehicle</span>
                <span className="font-bold text-slate-900">{selectedOrder.listing_title}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-200">
                <span className="text-slate-500">Agreed Price</span>
                <span className="font-black text-slate-900">{selectedOrder.currency} {Number(selectedOrder.agreed_price).toLocaleString()}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-200">
                <span className="text-slate-500">Handover Preference</span>
                <span className="font-bold text-slate-900">{selectedOrder.handover_type === "COLLECTION" ? "Dealership Collection" : "Dealer Delivery"}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-200">
                <span className="text-slate-500">Selling Dealership</span>
                <span className="font-bold text-slate-900">{selectedOrder.organisation_name || selectedOrder.seller_name}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-200">
                <span className="text-slate-500">5-Business-Day Payment Deadline</span>
                <span className="font-bold text-slate-900">{new Date(selectedOrder.payment_deadline).toLocaleString()}</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-slate-500">Market Timezone</span>
                <span className="font-mono text-slate-700">{selectedOrder.market_timezone}</span>
              </div>
            </div>

            <div className="p-3 bg-emerald-50 rounded-xl border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-600 flex-shrink-0" />
              <span>
                Vehicle is atomically locked under reservation. Direct offline funds transfer must be reported before the statutory deadline.
              </span>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setSelectedOrder(null)}
                className="px-4 py-2 bg-slate-900 text-white rounded-xl text-xs font-bold"
              >
                Close Summary
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: REPORT OFFLINE PAYMENT (PHASE 2) */}
      {reportPaymentOrder && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
                  <CreditCard className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-base font-black text-slate-900">Report Offline Payment</h3>
                  <span className="text-[10px] font-mono text-slate-400">Order #{reportPaymentOrder.order_number}</span>
                </div>
              </div>
              <button
                onClick={() => setReportPaymentOrder(null)}
                disabled={paymentReporting}
                className="p-1 text-slate-400 hover:text-slate-700"
              >
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3 bg-slate-50 rounded-2xl border border-slate-200 text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-slate-500">Vehicle:</span>
                <span className="font-bold text-slate-900">{reportPaymentOrder.listing_title}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Beneficiary Dealership:</span>
                <span className="font-bold text-slate-900">{reportPaymentOrder.organisation_name || reportPaymentOrder.seller_name}</span>
              </div>
              <div className="flex justify-between pt-1 border-t border-slate-200">
                <span className="text-slate-600 font-bold">Agreed Total Price:</span>
                <span className="font-black text-emerald-700 text-sm">
                  {reportPaymentOrder.currency} {Number(reportPaymentOrder.agreed_price).toLocaleString()}
                </span>
              </div>
            </div>

            <form onSubmit={handleSubmitPaymentReport} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Bank Transfer / Transaction Reference *
                </label>
                <input
                  type="text"
                  required
                  minLength={3}
                  placeholder="e.g. BARC12345678 or UTR987654321"
                  value={paymentRef}
                  onChange={(e) => setPaymentRef(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-mono font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
                <span className="text-[10px] text-slate-400 mt-1 block">
                  Enter the unique reference code from your bank payment confirmation receipt.
                </span>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Date & Time Payment Was Made *
                </label>
                <input
                  type="datetime-local"
                  required
                  value={paymentPaidAt}
                  onChange={(e) => setPaymentPaidAt(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Payment Notes (Optional)
                </label>
                <textarea
                  rows={2}
                  placeholder="e.g. Remitted from HSBC account in name of J. Doe"
                  value={paymentNotes}
                  onChange={(e) => setPaymentNotes(e.target.value)}
                  className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div className="p-3 bg-amber-50 rounded-xl border border-amber-200 text-[11px] text-amber-900 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                <span>
                  DriverXtra does not hold vehicle funds. Only report payment once you have transferred funds directly to the dealership. Submitting notifies the dealership to verify arrival in their account.
                </span>
              </div>

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  disabled={paymentReporting}
                  onClick={() => setReportPaymentOrder(null)}
                  className="px-4 py-2 border border-slate-200 text-slate-600 hover:bg-slate-50 rounded-xl text-xs font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={paymentReporting}
                  className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-black shadow-xs flex items-center gap-1.5 disabled:opacity-50"
                >
                  {paymentReporting ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Submitting...</span>
                    </>
                  ) : (
                    <>
                      <Check className="w-3.5 h-3.5" />
                      <span>Submit Payment Report</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

