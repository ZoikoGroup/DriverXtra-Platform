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
  Send,
  Check,
  RotateCcw,
  RefreshCw,
  FileText,
  ShieldCheck,
  ChevronRight,
  Receipt,
  Eye,
  Calendar,
  User,
} from "lucide-react";

interface SellerVehicleOrdersOffersSectionProps {
  onNavigateToListings?: () => void;
}

export default function SellerVehicleOrdersOffersSection({
  onNavigateToListings,
}: SellerVehicleOrdersOffersSectionProps) {
  const [subTab, setSubTab] = useState<"offers" | "orders">("offers");
  const [offers, setOffers] = useState<VehiclePurchaseOffer[]>([]);
  const [orders, setOrders] = useState<VehicleOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Filters
  const [offerStatusFilter, setOfferStatusFilter] = useState<string>("ALL");
  const [orderStatusFilter, setOrderStatusFilter] = useState<string>("ALL");

  // Counter Modal State (Dealer countering buyer)
  const [counterModalOffer, setCounterModalOffer] = useState<VehiclePurchaseOffer | null>(null);
  const [counterPrice, setCounterPrice] = useState<string>("");
  const [counterHandover, setCounterHandover] = useState<"COLLECTION" | "DELIVERY">("COLLECTION");
  const [counterNotes, setCounterNotes] = useState<string>("");
  const [actionLoading, setActionLoading] = useState(false);

  // Detail Modals
  const [selectedOffer, setSelectedOffer] = useState<VehiclePurchaseOffer | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<VehicleOrder | null>(null);

  // Payment Verification Modals (Phase 2)
  const [confirmModalOrder, setConfirmModalOrder] = useState<VehicleOrder | null>(null);
  const [confirmNotes, setConfirmNotes] = useState<string>("");
  const [rejectModalOrder, setRejectModalOrder] = useState<VehicleOrder | null>(null);
  const [rejectReason, setRejectReason] = useState<string>("");
  const [flagModalOrder, setFlagModalOrder] = useState<VehicleOrder | null>(null);
  const [flagReason, setFlagReason] = useState<string>("");
  const [verificationActionLoading, setVerificationActionLoading] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [offersData, ordersData] = await Promise.all([
        api.marketplace.listSellerVehicleOffers(),
        api.marketplace.listSellerVehicleOrders(),
      ]);
      setOffers(offersData);
      setOrders(ordersData);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load seller vehicle offers and orders.";
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

  // Dealer accepts buyer offer
  const handleAcceptOffer = async (offer: VehiclePurchaseOffer) => {
    const latestProposal = offer.proposals && offer.proposals.length > 0
      ? offer.proposals[offer.proposals.length - 1]
      : null;
    const acceptedPrice = latestProposal ? Number(latestProposal.offered_price) : Number(offer.agreed_price);

    const confirmed = confirm(
      `Accept Offer on ${offer.listing_title || "Vehicle"} for £${acceptedPrice.toLocaleString()}?\n\n` +
      `This action will:\n` +
      `1. Atomically lock and reserve the vehicle listing.\n` +
      `2. Supersede any other competing active offers.\n` +
      `3. Create a formal Vehicle Purchase Order with a statutory 5-business-day payment deadline for the buyer.\n\n` +
      `Proceed?`
    );

    if (!confirmed) return;

    setActionLoading(true);
    setError(null);
    try {
      const createdOrder = await api.marketplace.acceptSellerVehicleOffer(offer.id);
      setActionSuccess(`Offer accepted! Vehicle reserved under Order #${createdOrder.order_number}.`);
      setSubTab("orders");
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to accept offer.";
      setError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  // Dealer submits counteroffer
  const handleSubmitCounteroffer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!counterModalOffer) return;

    const priceNum = parseFloat(counterPrice);
    if (isNaN(priceNum) || priceNum <= 0) {
      setError("Please enter a valid counteroffer amount.");
      return;
    }

    setActionLoading(true);
    setError(null);
    try {
      await api.marketplace.counterSellerVehicleOffer(counterModalOffer.id, {
        counter_price: priceNum,
        handover_preference: counterHandover,
        notes: counterNotes || undefined,
      });
      setActionSuccess("Counteroffer successfully submitted to the buyer.");
      setCounterModalOffer(null);
      setCounterPrice("");
      setCounterNotes("");
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to submit counteroffer.";
      setError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  // Dealer rejects buyer offer
  const handleRejectOffer = async (offer: VehiclePurchaseOffer) => {
    const reason = prompt("Enter a reason for declining this offer (optional):") || "";
    setActionLoading(true);
    setError(null);
    try {
      await api.marketplace.rejectSellerVehicleOffer(offer.id, reason);
      setActionSuccess("Offer rejected.");
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to reject offer.";
      setError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  // Dealer confirms buyer payment has arrived
  const handleConfirmPayment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!confirmModalOrder) return;
    setVerificationActionLoading(true);
    setError(null);
    try {
      await api.marketplace.confirmSellerVehicleOrderPayment(confirmModalOrder.id, {
        notes: confirmNotes.trim(),
      });
      setActionSuccess(`Payment confirmed for Order #${confirmModalOrder.order_number}! Order transitioned to Confirmed.`);
      setConfirmModalOrder(null);
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to confirm payment.";
      setError(msg);
    } finally {
      setVerificationActionLoading(false);
    }
  };

  // Dealer rejects buyer payment report
  const handleRejectPayment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rejectModalOrder) return;
    if (!rejectReason.trim() || rejectReason.trim().length < 5) {
      setError("Please provide a clear reason for rejecting payment (minimum 5 characters).");
      return;
    }
    setVerificationActionLoading(true);
    setError(null);
    try {
      await api.marketplace.rejectSellerVehicleOrderPayment(rejectModalOrder.id, {
        reason: rejectReason.trim(),
      });
      setActionSuccess(`Payment report rejected for Order #${rejectModalOrder.order_number}. Order returned to Payment Pending and vehicle reservation preserved.`);
      setRejectModalOrder(null);
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to reject payment.";
      setError(msg);
    } finally {
      setVerificationActionLoading(false);
    }
  };

  // Dealer flags discrepancy on payment report
  const handleFlagPayment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!flagModalOrder) return;
    if (!flagReason.trim() || flagReason.trim().length < 5) {
      setError("Please provide an explanation for the discrepancy (minimum 5 characters).");
      return;
    }
    setVerificationActionLoading(true);
    setError(null);
    try {
      await api.marketplace.flagSellerVehicleOrderPayment(flagModalOrder.id, {
        reason: flagReason.trim(),
      });
      setActionSuccess(`Discrepancy flagged for Order #${flagModalOrder.order_number}.`);
      setFlagModalOrder(null);
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to flag payment discrepancy.";
      setError(msg);
    } finally {
      setVerificationActionLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "PENDING_DEALER":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200 animate-pulse">
            <Clock className="w-3.5 h-3.5" /> Action Required
          </span>
        );
      case "PENDING_BUYER":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-blue-100 text-blue-800 border border-blue-200">
            <RotateCcw className="w-3.5 h-3.5" /> Countered (Awaiting Buyer)
          </span>
        );
      case "ACCEPTED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5" /> Accepted & Reserved
          </span>
        );
      case "REJECTED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-200">
            <XCircle className="w-3.5 h-3.5" /> Declined
          </span>
        );
      case "SUPERSEDED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-600 border border-slate-200">
            <AlertTriangle className="w-3.5 h-3.5" /> Superseded
          </span>
        );
      case "WITHDRAWN":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-gray-100 text-gray-600 border border-gray-200">
            <XCircle className="w-3.5 h-3.5" /> Buyer Withdrew
          </span>
        );
      case "EXPIRED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-gray-100 text-gray-500 border border-gray-200">
            <Clock className="w-3.5 h-3.5" /> Expired
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-700 border border-slate-200">
            {status}
          </span>
        );
    }
  };

  const getOrderStatusBadge = (status: string) => {
    switch (status) {
      case "PAYMENT_PENDING":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200 animate-pulse">
            <Clock className="w-3.5 h-3.5" /> Awaiting Payment
          </span>
        );
      case "PAYMENT_SUBMITTED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-blue-100 text-blue-800 border border-blue-200">
            <Receipt className="w-3.5 h-3.5" /> Payment Submitted
          </span>
        );
      case "PAYMENT_CONFIRMED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5" /> Payment Confirmed
          </span>
        );
      case "COMPLETED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-teal-100 text-teal-800 border border-teal-200">
            <ShieldCheck className="w-3.5 h-3.5" /> Handover Complete
          </span>
        );
      case "CANCELLED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-200">
            <XCircle className="w-3.5 h-3.5" /> Order Cancelled
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-700 border border-slate-200">
            {status}
          </span>
        );
    }
  };

  const calculateRemainingTime = (deadlineStr: string) => {
    const deadline = new Date(deadlineStr).getTime();
    const now = new Date().getTime();
    const diff = deadline - now;
    if (diff <= 0) return "Payment Overdue";
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    return `${days}d ${hours}h remaining`;
  };

  const filteredOffers = offers.filter((o) => {
    if (offerStatusFilter === "ALL") return true;
    return o.status === offerStatusFilter;
  });

  const filteredOrders = orders.filter((ord) => {
    if (orderStatusFilter === "ALL") return true;
    return ord.status === orderStatusFilter;
  });

  const pendingOffersCount = offers.filter((o) => o.status === "PENDING_DEALER").length;
  const activeOrdersCount = orders.filter((ord) => ord.status === "PAYMENT_PENDING" || ord.status === "PAYMENT_SUBMITTED").length;

  return (
    <div className="space-y-6">
      {/* Top Banner / Notification */}
      {actionSuccess && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
            <span className="text-sm font-medium">{actionSuccess}</span>
          </div>
          <button
            onClick={() => setActionSuccess(null)}
            className="text-xs font-bold text-emerald-700 hover:text-emerald-900"
          >
            Dismiss
          </button>
        </div>
      )}

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0" />
            <span className="text-sm font-medium">{error}</span>
          </div>
          <button
            onClick={() => setError(null)}
            className="text-xs font-bold text-rose-700 hover:text-rose-900"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Header and Sub Tabs */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="text-lg font-black text-slate-900 flex items-center gap-2">
            <Car className="w-5 h-5 text-amber-500" />
            Vehicle Sales, Negotiation & Orders
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Review buyer purchase offers, negotiate counter proposals, and track reserved vehicle orders with statutory payment deadlines.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex p-1 bg-slate-100 rounded-xl border border-slate-200">
            <button
              onClick={() => setSubTab("offers")}
              className={`px-4 py-2 rounded-lg text-xs font-bold flex items-center gap-2 transition-all ${
                subTab === "offers"
                  ? "bg-white text-slate-900 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <Tag className="w-4 h-4" />
              Incoming Offers
              {pendingOffersCount > 0 && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-amber-500 text-white">
                  {pendingOffersCount}
                </span>
              )}
            </button>
            <button
              onClick={() => setSubTab("orders")}
              className={`px-4 py-2 rounded-lg text-xs font-bold flex items-center gap-2 transition-all ${
                subTab === "orders"
                  ? "bg-white text-slate-900 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <Receipt className="w-4 h-4" />
              Vehicle Orders
              {activeOrdersCount > 0 && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-blue-600 text-white">
                  {activeOrdersCount}
                </span>
              )}
            </button>
          </div>

          <button
            onClick={loadData}
            disabled={loading}
            className="p-2 text-slate-500 hover:text-slate-900 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors"
            title="Refresh Data"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* OFFERS TAB */}
      {subTab === "offers" && (
        <div className="space-y-4">
          {/* Status Filter Bar */}
          <div className="flex flex-wrap items-center gap-2">
            {[
              { id: "ALL", label: "All Offers" },
              { id: "PENDING_DEALER", label: "Needs Review", count: pendingOffersCount },
              { id: "PENDING_BUYER", label: "Awaiting Buyer" },
              { id: "ACCEPTED", label: "Accepted" },
              { id: "REJECTED", label: "Declined" },
              { id: "SUPERSEDED", label: "Superseded" },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setOfferStatusFilter(tab.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                  offerStatusFilter === tab.id
                    ? "bg-slate-900 text-white"
                    : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
                }`}
              >
                {tab.label}
                {tab.count !== undefined && tab.count > 0 && (
                  <span className={`ml-1.5 px-1.5 py-0.5 rounded-full text-[10px] ${
                    offerStatusFilter === tab.id ? "bg-amber-500 text-white" : "bg-slate-200 text-slate-700"
                  }`}>
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {loading ? (
            <div className="p-12 text-center bg-white rounded-2xl border border-slate-200">
              <RefreshCw className="w-8 h-8 animate-spin text-amber-500 mx-auto mb-3" />
              <p className="text-sm font-medium text-slate-600">Loading incoming vehicle offers...</p>
            </div>
          ) : filteredOffers.length === 0 ? (
            <div className="p-12 text-center bg-white rounded-2xl border border-slate-200">
              <Tag className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <h3 className="text-base font-bold text-slate-900">No Vehicle Offers Found</h3>
              <p className="text-xs text-slate-500 max-w-md mx-auto mt-1 mb-4">
                {offerStatusFilter === "ALL"
                  ? "When buyers make purchase offers on your vehicle listings, they will appear here for negotiation."
                  : `There are currently no vehicle offers matching the filter "${offerStatusFilter}".`}
              </p>
              {onNavigateToListings && (
                <button
                  onClick={onNavigateToListings}
                  className="px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-bold hover:bg-slate-800 transition-colors"
                >
                  View Vehicle Inventory
                </button>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {filteredOffers.map((offer) => {
                const latestProposal = offer.proposals && offer.proposals.length > 0
                  ? offer.proposals[offer.proposals.length - 1]
                  : null;
                const offeredPrice = latestProposal ? Number(latestProposal.offered_price) : 0;
                const isBuyerActionPending = offer.status === "PENDING_BUYER";
                const isDealerActionRequired = offer.status === "PENDING_DEALER";

                return (
                  <div
                    key={offer.id}
                    className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs hover:border-slate-300 transition-all"
                  >
                    <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                      {/* Left: Vehicle & Buyer Overview */}
                      <div className="flex items-start gap-4">
                        <div className="w-20 h-16 rounded-xl bg-slate-100 overflow-hidden relative flex-shrink-0 border border-slate-200 flex items-center justify-center">
                          <Car className="w-8 h-8 text-slate-400" />
                          {Boolean(offer.listing_image_url) && (
                            <Image
                              src={resolveMediaUrl(offer.listing_image_url)}
                              alt={offer.listing_title || "Vehicle"}
                              fill
                              sizes="80px"
                              className="object-cover"
                              onError={(e) => {
                                (e.target as HTMLElement).style.display = "none";
                              }}
                            />
                          )}
                        </div>

                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-xs font-mono text-slate-400">
                              Offer #{offer.id.slice(0, 8)}
                            </span>
                            {getStatusBadge(offer.status)}
                            <span className="text-xs text-slate-400">
                              Round {offer.current_round}
                            </span>
                          </div>

                          <h3 className="text-base font-black text-slate-900 mt-1">
                            {offer.listing_title || "Vehicle Listing"}
                          </h3>

                          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500 mt-1">
                            <span className="flex items-center gap-1 font-medium text-slate-700">
                              <User className="w-3.5 h-3.5 text-slate-400" />
                              Buyer: {offer.buyer_name || offer.buyer_email || "Verified Buyer"}
                            </span>
                            <span>•</span>
                            <span className="flex items-center gap-1">
                              <Calendar className="w-3.5 h-3.5 text-slate-400" />
                              {new Date(offer.created_at).toLocaleDateString("en-GB", {
                                day: "numeric",
                                month: "short",
                                year: "numeric",
                              })}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Right: Price & Key Terms */}
                      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 lg:self-center">
                        <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 min-w-[160px]">
                          <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">
                            {latestProposal?.proposed_by_role === "BUYER" ? "Buyer's Offer" : "Dealer's Counter"}
                          </span>
                          <span className="text-xl font-black text-slate-900">
                            £{offeredPrice.toLocaleString()}
                          </span>
                        </div>

                        {/* Action Buttons */}
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            onClick={() => setSelectedOffer(offer)}
                            className="px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-bold flex items-center gap-1.5 transition-colors"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            History ({offer.proposals?.length || 1})
                          </button>

                          {isDealerActionRequired && (
                            <>
                              <button
                                onClick={() => handleAcceptOffer(offer)}
                                disabled={actionLoading}
                                className="px-3 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold flex items-center gap-1.5 transition-colors shadow-xs disabled:opacity-50"
                              >
                                <Check className="w-3.5 h-3.5" />
                                Accept & Reserve
                              </button>

                              <button
                                onClick={() => {
                                  setCounterModalOffer(offer);
                                  setCounterPrice(offeredPrice ? String(offeredPrice) : "");
                                  setCounterNotes("");
                                }}
                                disabled={actionLoading}
                                className="px-3 py-2 rounded-xl bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold flex items-center gap-1.5 transition-colors shadow-xs disabled:opacity-50"
                              >
                                <RotateCcw className="w-3.5 h-3.5" />
                                Counteroffer
                              </button>

                              <button
                                onClick={() => handleRejectOffer(offer)}
                                disabled={actionLoading}
                                className="px-3 py-2 rounded-xl border border-rose-200 text-rose-700 hover:bg-rose-50 text-xs font-bold flex items-center gap-1.5 transition-colors disabled:opacity-50"
                              >
                                <XCircle className="w-3.5 h-3.5" />
                                Decline
                              </button>
                            </>
                          )}

                          {isBuyerActionPending && (
                            <span className="text-xs text-blue-700 font-semibold bg-blue-50 px-3 py-2 rounded-xl border border-blue-200 flex items-center gap-1">
                              <Clock className="w-3.5 h-3.5" /> Awaiting Buyer Response
                            </span>
                          )}

                          {offer.status === "ACCEPTED" && (
                            <button
                              onClick={() => setSubTab("orders")}
                              className="px-3 py-2 rounded-xl bg-slate-900 text-white text-xs font-bold flex items-center gap-1.5 transition-colors"
                            >
                              View Order <ChevronRight className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Proposal Details Snippet */}
                    {latestProposal && (
                      <div className="mt-4 pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between text-xs text-slate-600 gap-2">
                        <div className="flex flex-wrap items-center gap-4">
                          <span>
                            <strong>Handover:</strong>{" "}
                            {latestProposal.handover_preference === "COLLECTION"
                              ? "Dealership Collection"
                              : "Home Delivery"}
                          </span>
                          {latestProposal.notes && (
                            <span className="italic text-slate-500">
                              &ldquo;{latestProposal.notes}&rdquo;
                            </span>
                          )}
                        </div>
                        {offer.expires_at && (
                          <span className="text-slate-400 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            Expires: {new Date(offer.expires_at).toLocaleDateString("en-GB")}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ORDERS TAB */}
      {subTab === "orders" && (
        <div className="space-y-4">
          {/* Status Filter Bar */}
          <div className="flex flex-wrap items-center gap-2">
            {[
              { id: "ALL", label: "All Orders" },
              { id: "PAYMENT_PENDING", label: "Awaiting Payment", count: orders.filter((o) => o.status === "PAYMENT_PENDING").length },
              { id: "PAYMENT_SUBMITTED", label: "Payment Submitted", count: orders.filter((o) => o.status === "PAYMENT_SUBMITTED").length },
              { id: "PAYMENT_CONFIRMED", label: "Confirmed" },
              { id: "COMPLETED", label: "Completed" },
              { id: "CANCELLED", label: "Cancelled" },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setOrderStatusFilter(tab.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                  orderStatusFilter === tab.id
                    ? "bg-slate-900 text-white"
                    : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
                }`}
              >
                {tab.label}
                {tab.count !== undefined && tab.count > 0 && (
                  <span className={`ml-1.5 px-1.5 py-0.5 rounded-full text-[10px] ${
                    orderStatusFilter === tab.id ? "bg-blue-500 text-white" : "bg-slate-200 text-slate-700"
                  }`}>
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {loading ? (
            <div className="p-12 text-center bg-white rounded-2xl border border-slate-200">
              <RefreshCw className="w-8 h-8 animate-spin text-amber-500 mx-auto mb-3" />
              <p className="text-sm font-medium text-slate-600">Loading vehicle orders...</p>
            </div>
          ) : filteredOrders.length === 0 ? (
            <div className="p-12 text-center bg-white rounded-2xl border border-slate-200">
              <Receipt className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <h3 className="text-base font-bold text-slate-900">No Vehicle Orders Found</h3>
              <p className="text-xs text-slate-500 max-w-md mx-auto mt-1 mb-4">
                When an offer is accepted by either party, a Vehicle Purchase Order is created and the vehicle is reserved.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {filteredOrders.map((order) => {
                const isAwaitingPayment = order.status === "PAYMENT_PENDING";
                const remainingTime = order.payment_deadline
                  ? calculateRemainingTime(order.payment_deadline)
                  : null;

                return (
                  <div
                    key={order.id}
                    className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs hover:border-slate-300 transition-all"
                  >
                    <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
                      {/* Left: Vehicle and Order Meta */}
                      <div className="flex items-start gap-4">
                        <div className="w-20 h-16 rounded-xl bg-slate-100 overflow-hidden relative flex-shrink-0 border border-slate-200 flex items-center justify-center">
                          <Car className="w-8 h-8 text-slate-400" />
                          {Boolean(order.listing_image_url) && (
                            <Image
                              src={resolveMediaUrl(order.listing_image_url)}
                              alt={order.listing_title || "Vehicle"}
                              fill
                              sizes="80px"
                              className="object-cover"
                              onError={(e) => {
                                (e.target as HTMLElement).style.display = "none";
                              }}
                            />
                          )}
                        </div>

                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-xs font-mono font-bold text-slate-900">
                              {order.order_number}
                            </span>
                            {getOrderStatusBadge(order.status)}
                          </div>

                          <h3 className="text-base font-black text-slate-900 mt-1">
                            {order.listing_title || "Vehicle Order"}
                          </h3>

                          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500 mt-1">
                            <span className="flex items-center gap-1 font-medium text-slate-700">
                              <User className="w-3.5 h-3.5 text-slate-400" />
                              Buyer: {order.buyer_name || order.buyer_email || "Customer"}
                            </span>
                            <span>•</span>
                            <span className="flex items-center gap-1">
                              <Calendar className="w-3.5 h-3.5 text-slate-400" />
                              Created: {new Date(order.created_at).toLocaleDateString("en-GB")}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Right: Agreed Price and Payment Deadline Alert */}
                      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
                        <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 min-w-[170px]">
                          <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">
                            Agreed Sale Price
                          </span>
                          <span className="text-xl font-black text-slate-900">
                            £{Number(order.agreed_price).toLocaleString()}
                          </span>
                        </div>

                        <div className="flex flex-col gap-2">
                          <button
                            onClick={() => setSelectedOrder(order)}
                            className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold flex items-center gap-1.5 transition-colors"
                          >
                            <FileText className="w-3.5 h-3.5" />
                            Order Details
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Statutory 5-Business-Day Payment Deadline Banner */}
                    {order.payment_deadline && (
                      <div className={`mt-4 p-3 rounded-xl border flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs ${
                        isAwaitingPayment
                          ? "bg-amber-50 border-amber-200 text-amber-900"
                          : "bg-slate-50 border-slate-200 text-slate-700"
                      }`}>
                        <div className="flex items-center gap-2">
                          <Clock className={`w-4 h-4 flex-shrink-0 ${isAwaitingPayment ? "text-amber-600" : "text-slate-500"}`} />
                          <span>
                            <strong>5-Business-Day Payment Deadline:</strong>{" "}
                            {new Date(order.payment_deadline).toLocaleString("en-GB", {
                              weekday: "short",
                              day: "numeric",
                              month: "short",
                              year: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        </div>

                        {isAwaitingPayment && remainingTime && (
                          <span className="font-bold text-amber-700 bg-amber-100 px-2.5 py-1 rounded-lg border border-amber-300 self-start sm:self-auto">
                            {remainingTime}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Dealer Payment Verification Box (Phase 2) */}
                    {order.status === "PAYMENT_SUBMITTED" && (
                      <div className="mt-4 p-4 rounded-xl border border-blue-200 bg-blue-50/70 space-y-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <Clock className="w-4 h-4 text-blue-600 flex-shrink-0" />
                            <h4 className="text-xs font-black text-blue-950 uppercase tracking-wider">
                              Buyer Reported Direct Payment — Verification Required
                            </h4>
                          </div>

                          {order.latest_payment_report?.status === "FLAGGED" ? (
                            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-black bg-amber-100 text-amber-900 border border-amber-300 flex items-center gap-1">
                              <AlertTriangle className="w-3 h-3 text-amber-600" /> Discrepancy Flagged — Awaiting Dealership Resolution
                            </span>
                          ) : order.latest_payment_report?.escalation_level === "ESCALATED_120H" ? (
                            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-black bg-rose-100 text-rose-800 border border-rose-300 flex items-center gap-1">
                              <AlertTriangle className="w-3 h-3 text-rose-600" /> Escalated to Operations (&gt;120h)
                            </span>
                          ) : order.latest_payment_report?.escalation_level === "OVERDUE_72H" ? (
                            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-black bg-amber-100 text-amber-900 border border-amber-300 flex items-center gap-1">
                              <AlertTriangle className="w-3 h-3 text-amber-600" /> Overdue (&gt;72h Deadline Passed)
                            </span>
                          ) : order.latest_payment_report?.escalation_level === "WARNING_48H" ? (
                            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200 flex items-center gap-1">
                              <Clock className="w-3 h-3 text-amber-600" /> Warning Sent (&gt;48h Pending)
                            </span>
                          ) : (
                            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 border border-blue-200">
                              72-Hour Verification Window Active
                            </span>
                          )}
                        </div>

                        {/* Report Details Grid */}
                        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 bg-white p-3 rounded-lg border border-blue-100 text-xs">
                          <div>
                            <span className="text-slate-400 font-medium text-[11px] block">Amount to Verify</span>
                            <span className="font-black text-slate-900">
                              {order.currency} {Number(order.agreed_price).toLocaleString()}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-400 font-medium text-[11px] block">Transfer Reference</span>
                            <span className="font-mono font-bold text-slate-900">
                              {order.latest_payment_report?.payment_reference || "Direct Bank Remittance"}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-400 font-medium text-[11px] block">Transfer Date</span>
                            <span className="text-slate-700">
                              {order.latest_payment_report?.paid_at ? new Date(order.latest_payment_report.paid_at).toLocaleString("en-GB") : (order.payment_submitted_at ? new Date(order.payment_submitted_at).toLocaleString("en-GB") : "Recently")}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-400 font-medium text-[11px] block">Buyer Notes</span>
                            <span className="text-slate-700 italic">
                              {order.latest_payment_report?.payment_notes || "None provided"}
                            </span>
                          </div>
                        </div>

                        {/* Discrepancy Flagged Callout */}
                        {order.latest_payment_report?.status === "FLAGGED" && (
                          <div className="p-3 rounded-lg bg-amber-100/80 border border-amber-300 text-amber-950 text-xs flex items-start gap-2">
                            <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                            <div>
                              <strong className="block">Dealership Flagged Discrepancy:</strong>
                              <span>{order.latest_payment_report?.verification_notes || "A discrepancy was flagged for this payment report. Cross-check with your bank records. You may confirm payment once funds settle or reject the report to require buyer re-submission."}</span>
                            </div>
                          </div>
                        )}

                        {/* Verification Action Buttons */}
                        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                          <p className="text-[11px] text-blue-800">
                            {order.latest_payment_report?.status === "FLAGGED"
                              ? "Verify whether funds have subsequently credited, then resolve by confirming or rejecting."
                              : "Check your dealership bank account to confirm funds have credited before confirming."}
                          </p>
                          <div className="flex flex-wrap items-center gap-2">
                            {order.latest_payment_report?.status !== "FLAGGED" && (
                              <button
                                onClick={() => {
                                  setFlagModalOrder(order);
                                  setFlagReason("");
                                }}
                                disabled={verificationActionLoading}
                                className="px-3 py-1.5 rounded-xl border border-amber-300 bg-amber-50 hover:bg-amber-100 text-amber-900 text-xs font-bold transition-colors disabled:opacity-50"
                              >
                                Flag Discrepancy
                              </button>
                            )}
                            <button
                              onClick={() => {
                                setRejectModalOrder(order);
                                setRejectReason("");
                              }}
                              disabled={verificationActionLoading}
                              className="px-3 py-1.5 rounded-xl border border-rose-300 bg-white hover:bg-rose-50 text-rose-700 text-xs font-bold transition-colors disabled:opacity-50"
                            >
                              Reject Payment
                            </button>
                            <button
                              onClick={() => {
                                setConfirmModalOrder(order);
                                setConfirmNotes("");
                              }}
                              disabled={verificationActionLoading}
                              className="px-4 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-black flex items-center gap-1.5 transition-colors shadow-xs disabled:opacity-50"
                            >
                              <Check className="w-3.5 h-3.5" />
                              Confirm Payment Received
                            </button>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Confirmed Banner */}
                    {order.status === "PAYMENT_CONFIRMED" && (
                      <div className="mt-4 p-3 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-950 flex flex-wrap items-center justify-between gap-2 text-xs">
                        <div className="flex items-center gap-2">
                          <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                          <span>
                            <strong>Payment Confirmed</strong> {order.payment_confirmed_at ? `on ${new Date(order.payment_confirmed_at).toLocaleDateString("en-GB")}` : ""}. Funds credited. Handover & registration documents active.
                          </span>
                        </div>
                        {order.confirmed_by_name && (
                          <span className="text-[11px] text-emerald-800 font-medium">
                            Verified by: {order.confirmed_by_name}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* DEALER COUNTEROFFER MODAL */}
      {counterModalOffer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <RotateCcw className="w-5 h-5 text-amber-500" />
                <h3 className="text-base font-black text-slate-900">Make Counteroffer</h3>
              </div>
              <button
                onClick={() => setCounterModalOffer(null)}
                className="text-slate-400 hover:text-slate-600 text-lg font-bold"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSubmitCounteroffer} className="space-y-4 mt-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Counteroffer Amount (£) *
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-2.5 text-slate-400 font-bold">£</span>
                  <input
                    type="number"
                    step="0.01"
                    min="1"
                    value={counterPrice}
                    onChange={(e) => setCounterPrice(e.target.value)}
                    required
                    placeholder="Enter counter price..."
                    className="w-full pl-8 pr-4 py-2 border border-slate-300 rounded-xl text-sm font-bold text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-amber-500"
                  />
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  Buyer&apos;s proposed price was £{Number(
                    counterModalOffer.proposals?.[counterModalOffer.proposals.length - 1]?.offered_price || 0
                  ).toLocaleString()}
                </p>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Handover Preference
                </label>
                <select
                  value={counterHandover}
                  onChange={(e) => setCounterHandover(e.target.value as "COLLECTION" | "DELIVERY")}
                  className="w-full px-3 py-2 border border-slate-300 rounded-xl text-xs font-medium text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-amber-500"
                >
                  <option value="COLLECTION">Dealership Collection (Collection by Buyer)</option>
                  <option value="DELIVERY">Home Delivery</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Notes / Terms for Buyer (Optional)
                </label>
                <textarea
                  rows={3}
                  value={counterNotes}
                  onChange={(e) => setCounterNotes(e.target.value)}
                  placeholder="e.g. Includes 12-month nationwide warranty, free service before delivery..."
                  className="w-full px-3 py-2 border border-slate-300 rounded-xl text-xs text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-amber-500"
                />
              </div>

              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-[11px] text-slate-600 leading-relaxed">
                <p>
                  <strong>Note:</strong> Submitting a counteroffer will advance the negotiation to Round {counterModalOffer.current_round + 1}. The buyer will have 3 days to accept, reject, or counter your terms.
                </p>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setCounterModalOffer(null)}
                  className="px-4 py-2 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 text-xs font-bold transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-5 py-2 rounded-xl bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold flex items-center gap-1.5 transition-colors shadow-xs disabled:opacity-50"
                >
                  {actionLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                  Send Counteroffer
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* OFFER IMMUTABLE TIMELINE MODAL */}
      {selectedOffer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl border border-slate-200 max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <div>
                <h3 className="text-base font-black text-slate-900">
                  Negotiation History: Offer #{selectedOffer.id.slice(0, 8)}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Vehicle: {selectedOffer.listing_title}
                </p>
              </div>
              <button
                onClick={() => setSelectedOffer(null)}
                className="text-slate-400 hover:text-slate-600 text-lg font-bold"
              >
                ✕
              </button>
            </div>

            <div className="mt-5 space-y-4">
              <h4 className="text-xs font-black text-slate-400 uppercase tracking-wider">
                Immutable Proposal Rounds
              </h4>

              <div className="space-y-3">
                {selectedOffer.proposals?.map((prop) => (
                  <div
                    key={prop.id}
                    className={`p-4 rounded-xl border ${
                      prop.proposed_by_role === "DEALER"
                        ? "bg-amber-50/50 border-amber-200"
                        : "bg-blue-50/50 border-blue-200"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-900 flex items-center gap-2">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-black ${
                          prop.proposed_by_role === "DEALER" ? "bg-amber-500 text-white" : "bg-blue-600 text-white"
                        }`}>
                          Revision {prop.revision_number} ({prop.proposed_by_role})
                        </span>
                        Proposed: £{Number(prop.offered_price).toLocaleString()}
                      </span>
                      <span className="text-[11px] text-slate-400">
                        {new Date(prop.created_at).toLocaleString("en-GB")}
                      </span>
                    </div>

                    <div className="mt-2 text-xs text-slate-600">
                      <strong>Handover:</strong>{" "}
                      {prop.handover_preference === "COLLECTION"
                        ? "Dealership Collection"
                        : "Home Delivery"}
                    </div>

                    {prop.notes && (
                      <p className="mt-2 text-xs text-slate-700 italic bg-white/70 p-2 rounded-lg border border-slate-100">
                        &ldquo;{prop.notes}&rdquo;
                      </p>
                    )}
                  </div>
                ))}
              </div>

              {selectedOffer.actions && selectedOffer.actions.length > 0 && (
                <>
                  <h4 className="text-xs font-black text-slate-400 uppercase tracking-wider pt-3">
                    Action Audit Log
                  </h4>
                  <div className="space-y-2">
                    {selectedOffer.actions.map((act) => (
                      <div
                        key={act.id}
                        className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs flex items-center justify-between"
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-slate-800">{act.action_type}</span>
                          <span className="text-slate-500">by {act.actor_name || act.actor_email}</span>
                          {act.notes && (
                            <span className="text-slate-600 italic">- {act.notes}</span>
                          )}
                        </div>
                        <span className="text-[10px] text-slate-400">
                          {new Date(act.created_at).toLocaleString("en-GB")}
                        </span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>

            <div className="mt-6 pt-4 border-t border-slate-100 flex justify-end">
              <button
                onClick={() => setSelectedOffer(null)}
                className="px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-bold hover:bg-slate-800 transition-colors"
              >
                Close History
              </button>
            </div>
          </div>
        </div>
      )}

      {/* FULL ORDER DETAILS MODAL */}
      {selectedOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl border border-slate-200 max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-base font-black text-slate-900">
                    Order {selectedOrder.order_number}
                  </h3>
                  {getOrderStatusBadge(selectedOrder.status)}
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Created {new Date(selectedOrder.created_at).toLocaleString("en-GB")}
                </p>
              </div>
              <button
                onClick={() => setSelectedOrder(null)}
                className="text-slate-400 hover:text-slate-600 text-lg font-bold"
              >
                ✕
              </button>
            </div>

            <div className="mt-5 space-y-4">
              {/* Vehicle Summary */}
              <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 flex items-center gap-4">
                <div className="w-20 h-16 rounded-xl bg-slate-200 overflow-hidden relative flex-shrink-0 flex items-center justify-center">
                  <Car className="w-8 h-8 text-slate-400" />
                  {Boolean(selectedOrder.listing_image_url) && (
                    <Image
                      src={resolveMediaUrl(selectedOrder.listing_image_url)}
                      alt={selectedOrder.listing_title || "Vehicle"}
                      fill
                      sizes="80px"
                      className="object-cover"
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = "none";
                      }}
                    />
                  )}
                </div>
                <div>
                  <h4 className="text-sm font-bold text-slate-900">{selectedOrder.listing_title}</h4>
                  <div className="text-xs text-slate-500 mt-1 flex flex-wrap gap-2">
                    {Boolean(selectedOrder.listing_snapshot?.vin) && (
                      <span>VIN: {String(selectedOrder.listing_snapshot?.vin)}</span>
                    )}
                    {Boolean(selectedOrder.listing_snapshot?.registration_plate) && (
                      <span>Reg: {String(selectedOrder.listing_snapshot?.registration_plate)}</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Financial Breakdown */}
              <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-2 text-xs">
                <h4 className="font-bold text-slate-900 uppercase tracking-wider text-[11px]">
                  Transaction Summary
                </h4>
                <div className="flex justify-between py-1 border-b border-slate-200">
                  <span className="text-slate-600">Agreed Purchase Price</span>
                  <span className="font-bold text-slate-900">
                    £{Number(selectedOrder.agreed_price).toLocaleString()}
                  </span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-600">Handover Preference</span>
                  <span className="font-bold text-slate-900">
                    {selectedOrder.handover_type === "COLLECTION"
                      ? "Dealership Collection"
                      : "Home Delivery"}
                  </span>
                </div>
              </div>

              {/* Statutory Deadline Notice */}
              {selectedOrder.payment_deadline && (
                <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs space-y-1">
                  <div className="flex items-center gap-1.5 font-bold">
                    <Clock className="w-4 h-4 text-amber-700" />
                    Statutory 5-Business-Day Payment Deadline
                  </div>
                  <p>
                    {new Date(selectedOrder.payment_deadline).toLocaleString("en-GB", {
                      weekday: "long",
                      day: "numeric",
                      month: "long",
                      year: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </p>
                  <p className="text-[11px] text-amber-700 pt-1">
                    The listing is reserved exclusively for this buyer until this deadline. If payment is not submitted by this time, the order expires and the vehicle is automatically returned to AVAILABLE status.
                  </p>
                </div>
              )}

              {/* Buyer Contact Info */}
              <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1">
                <h4 className="font-bold text-slate-900 uppercase tracking-wider text-[11px] mb-2">
                  Buyer Information
                </h4>
                <div className="grid grid-cols-2 gap-2 text-slate-600">
                  <div>
                    <strong>Name:</strong> {selectedOrder.buyer_name || "N/A"}
                  </div>
                  <div>
                    <strong>Email:</strong> {selectedOrder.buyer_email || "N/A"}
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-slate-100 flex justify-end">
              <button
                onClick={() => setSelectedOrder(null)}
                className="px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-bold hover:bg-slate-800 transition-colors"
              >
                Close Order Details
              </button>
            </div>
          </div>
        </div>
      )}

      {/* CONFIRM PAYMENT MODAL (PHASE 2) */}
      {confirmModalOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                <h3 className="text-base font-black text-slate-900">Confirm Payment Received</h3>
              </div>
              <button
                onClick={() => setConfirmModalOrder(null)}
                disabled={verificationActionLoading}
                className="text-slate-400 hover:text-slate-600 font-bold"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleConfirmPayment} className="space-y-4 mt-4">
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1">
                <div><strong>Order:</strong> #{confirmModalOrder.order_number}</div>
                <div><strong>Vehicle:</strong> {confirmModalOrder.listing_title}</div>
                <div><strong>Agreed Price:</strong> {confirmModalOrder.currency} {Number(confirmModalOrder.agreed_price).toLocaleString()}</div>
                <div><strong>Reported Reference:</strong> <span className="font-mono">{confirmModalOrder.latest_payment_report?.payment_reference || "Direct Transfer"}</span></div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Verification Notes (Optional)
                </label>
                <textarea
                  rows={2}
                  value={confirmNotes}
                  onChange={(e) => setConfirmNotes(e.target.value)}
                  placeholder="e.g. Funds credited in Barclays account on 12/11/2026."
                  className="w-full px-3 py-2 border border-slate-300 rounded-xl text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div className="p-3 bg-emerald-50 rounded-xl border border-emerald-200 text-[11px] text-emerald-900 flex items-start gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                <span>
                  Confirming indicates that your dealership has verified direct receipt of offline funds. The order will immediately transition to Payment Confirmed.
                </span>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  disabled={verificationActionLoading}
                  onClick={() => setConfirmModalOrder(null)}
                  className="px-4 py-2 border border-slate-200 text-slate-600 rounded-xl text-xs font-bold hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={verificationActionLoading}
                  className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-black shadow-xs flex items-center gap-1.5"
                >
                  {verificationActionLoading ? "Confirming..." : "Confirm Funds Received"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* REJECT PAYMENT MODAL (PHASE 2) */}
      {rejectModalOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <XCircle className="w-5 h-5 text-rose-600" />
                <h3 className="text-base font-black text-slate-900">Reject Payment Report</h3>
              </div>
              <button
                onClick={() => setRejectModalOrder(null)}
                disabled={verificationActionLoading}
                className="text-slate-400 hover:text-slate-600 font-bold"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleRejectPayment} className="space-y-4 mt-4">
              <div className="p-3 bg-amber-50 rounded-xl border border-amber-200 text-xs text-amber-900 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                <span>
                  Rejecting this payment report reverts the order to <strong>Payment Pending</strong> so the buyer can re-submit valid payment details. The vehicle <strong>remains reserved</strong> for this buyer.
                </span>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Reason for Rejection * (minimum 5 characters)
                </label>
                <textarea
                  rows={3}
                  required
                  minLength={5}
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="e.g. Funds not received in account or reference number BARC123 could not be located in bank records."
                  className="w-full px-3 py-2 border border-slate-300 rounded-xl text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-rose-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  disabled={verificationActionLoading}
                  onClick={() => setRejectModalOrder(null)}
                  className="px-4 py-2 border border-slate-200 text-slate-600 rounded-xl text-xs font-bold hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={verificationActionLoading}
                  className="px-5 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-black shadow-xs flex items-center gap-1.5"
                >
                  {verificationActionLoading ? "Rejecting..." : "Reject Payment Report"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* FLAG DISCREPANCY MODAL (PHASE 2) */}
      {flagModalOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-amber-500" />
                <h3 className="text-base font-black text-slate-900">Flag Payment Discrepancy</h3>
              </div>
              <button
                onClick={() => setFlagModalOrder(null)}
                disabled={verificationActionLoading}
                className="text-slate-400 hover:text-slate-600 font-bold"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleFlagPayment} className="space-y-4 mt-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Discrepancy Details * (minimum 5 characters)
                </label>
                <textarea
                  rows={3}
                  required
                  minLength={5}
                  value={flagReason}
                  onChange={(e) => setFlagReason(e.target.value)}
                  placeholder="e.g. Received partial amount or sender account name does not match order contract."
                  className="w-full px-3 py-2 border border-slate-300 rounded-xl text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-amber-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  disabled={verificationActionLoading}
                  onClick={() => setFlagModalOrder(null)}
                  className="px-4 py-2 border border-slate-200 text-slate-600 rounded-xl text-xs font-bold hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={verificationActionLoading}
                  className="px-5 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-xl text-xs font-black shadow-xs flex items-center gap-1.5"
                >
                  {verificationActionLoading ? "Flagging..." : "Flag Discrepancy"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
