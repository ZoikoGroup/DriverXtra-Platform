"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  api,
  resolveMediaUrl,
  VehicleEnquiry,
  VehicleEnquiryStatus,
} from "@/lib/api/client";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  MessageSquare,
  Car,
  Clock,
  CheckCircle2,
  RotateCcw,
  ShoppingBag,
  Building2,
  User,
  AlertTriangle,
  Mail,
  Phone,
  Send,
  Check,
  Calendar,
  Sparkles,
} from "lucide-react";

interface BuyerEnquiriesViewProps {
  onNavigateToBrowse?: () => void;
}

type FilterTab = "ALL" | "AWAITING" | "RESPONDED" | "CLOSED";

export default function BuyerEnquiriesView({ onNavigateToBrowse }: BuyerEnquiriesViewProps) {
  const { user } = useAuth();
  const [enquiries, setEnquiries] = useState<VehicleEnquiry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterTab, setFilterTab] = useState<FilterTab>("ALL");

  const loadEnquiries = useCallback(async () => {
    if (!user) {
      setEnquiries([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await api.marketplace.listBuyerEnquiries();
      setEnquiries(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      console.error("Failed to load buyer enquiries", err);
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to load enquiries. Please check your network connection.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    let ignore = false;
    Promise.resolve().then(() => {
      if (!ignore) {
        loadEnquiries();
      }
    });
    return () => {
      ignore = true;
    };
  }, [loadEnquiries]);

  // Derived metrics
  const totalCount = enquiries.length;
  const awaitingCount = useMemo(
    () => enquiries.filter((e) => e.status === "NEW" && !e.seller_reply).length,
    [enquiries]
  );
  const respondedCount = useMemo(
    () => enquiries.filter((e) => e.status === "RESPONDED" || Boolean(e.seller_reply)).length,
    [enquiries]
  );
  const closedCount = useMemo(
    () => enquiries.filter((e) => e.status === "CLOSED").length,
    [enquiries]
  );

  // Filtered list
  const filteredEnquiries = useMemo(() => {
    switch (filterTab) {
      case "AWAITING":
        return enquiries.filter((e) => e.status === "NEW" && !e.seller_reply);
      case "RESPONDED":
        return enquiries.filter((e) => e.status === "RESPONDED" || Boolean(e.seller_reply));
      case "CLOSED":
        return enquiries.filter((e) => e.status === "CLOSED");
      default:
        return enquiries;
    }
  }, [enquiries, filterTab]);

  return (
    <div className="p-6 max-w-[1440px] mx-auto space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-200 gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-black uppercase tracking-wider text-amber-900 bg-amber-100 px-2 py-0.5 rounded">
              Buyer Dashboard
            </span>
            <span className="text-xs text-slate-500">• In-Platform Direct Enquiries</span>
          </div>
          <h2 className="text-2xl font-black text-slate-950 mt-1 flex items-center gap-2">
            <span>My Vehicle Enquiries</span>
            <span className="text-sm font-bold text-slate-400">({totalCount})</span>
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Track inquiries you have sent to vehicle sellers and view official seller responses directly within DriverXtra.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadEnquiries}
            disabled={loading}
            className="px-3.5 py-2 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-bold flex items-center gap-1.5 transition-colors shadow-xs disabled:opacity-50"
            title="Refresh enquiries"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
          {onNavigateToBrowse && (
            <button
              onClick={onNavigateToBrowse}
              className="px-4 py-2 rounded-xl bg-slate-950 hover:bg-slate-800 text-amber-400 text-xs font-bold flex items-center gap-1.5 shadow-xs transition-colors"
            >
              <ShoppingBag className="w-3.5 h-3.5" />
              <span>Browse Vehicles</span>
            </button>
          )}
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-2xl flex items-start justify-between gap-3 text-rose-800 text-xs">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-500 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={loadEnquiries}
            className="font-bold underline hover:text-rose-950 text-xs shrink-0"
          >
            Try Again
          </button>
        </div>
      )}

      {/* Metric Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-4 bg-white rounded-2xl border border-slate-200 shadow-xs">
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
            Total Enquiries
          </div>
          <div className="text-2xl font-black text-slate-900 mt-1">
            {totalCount}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">
            Submitted inquiries
          </div>
        </div>

        <div className="p-4 bg-amber-50/70 rounded-2xl border border-amber-200 shadow-xs">
          <div className="text-[10px] font-bold text-amber-800 uppercase tracking-wider flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
            <span>Awaiting Response</span>
          </div>
          <div className="text-2xl font-black text-amber-950 mt-1">
            {awaitingCount}
          </div>
          <div className="text-[11px] text-amber-700 mt-0.5">
            Pending seller review
          </div>
        </div>

        <div className="p-4 bg-emerald-50/70 rounded-2xl border border-emerald-200 shadow-xs">
          <div className="text-[10px] font-bold text-emerald-800 uppercase tracking-wider flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            <span>Seller Responded</span>
          </div>
          <div className="text-2xl font-black text-emerald-950 mt-1">
            {respondedCount}
          </div>
          <div className="text-[11px] text-emerald-700 mt-0.5">
            Official replies ready
          </div>
        </div>

        <div className="p-4 bg-slate-100/70 rounded-2xl border border-slate-200 shadow-xs">
          <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
            Closed Enquiries
          </div>
          <div className="text-2xl font-black text-slate-700 mt-1">
            {closedCount}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">
            Completed discussions
          </div>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex flex-wrap items-center gap-2 p-1 bg-slate-200/80 rounded-2xl w-fit">
        <button
          type="button"
          onClick={() => setFilterTab("ALL")}
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all ${
            filterTab === "ALL"
              ? "bg-white text-slate-950 shadow-xs"
              : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/50"
          }`}
        >
          <MessageSquare className="w-3.5 h-3.5 text-amber-500" />
          <span>All Enquiries</span>
          <span
            className={`px-1.5 py-0.2 rounded-full text-[10px] ${
              filterTab === "ALL"
                ? "bg-slate-900 text-white"
                : "bg-slate-300 text-slate-700"
            }`}
          >
            {totalCount}
          </span>
        </button>

        <button
          type="button"
          onClick={() => setFilterTab("AWAITING")}
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all ${
            filterTab === "AWAITING"
              ? "bg-white text-slate-950 shadow-xs"
              : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/50"
          }`}
        >
          <Clock className="w-3.5 h-3.5 text-amber-600" />
          <span>Awaiting Response</span>
          <span
            className={`px-1.5 py-0.2 rounded-full text-[10px] ${
              filterTab === "AWAITING"
                ? "bg-amber-500 text-slate-950"
                : "bg-slate-300 text-slate-700"
            }`}
          >
            {awaitingCount}
          </span>
        </button>

        <button
          type="button"
          onClick={() => setFilterTab("RESPONDED")}
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all ${
            filterTab === "RESPONDED"
              ? "bg-white text-slate-950 shadow-xs"
              : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/50"
          }`}
        >
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
          <span>Responded</span>
          <span
            className={`px-1.5 py-0.2 rounded-full text-[10px] ${
              filterTab === "RESPONDED"
                ? "bg-emerald-600 text-white"
                : "bg-slate-300 text-slate-700"
            }`}
          >
            {respondedCount}
          </span>
        </button>

        <button
          type="button"
          onClick={() => setFilterTab("CLOSED")}
          className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all ${
            filterTab === "CLOSED"
              ? "bg-white text-slate-950 shadow-xs"
              : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/50"
          }`}
        >
          <span>Closed</span>
          <span
            className={`px-1.5 py-0.2 rounded-full text-[10px] ${
              filterTab === "CLOSED"
                ? "bg-slate-900 text-white"
                : "bg-slate-300 text-slate-700"
            }`}
          >
            {closedCount}
          </span>
        </button>
      </div>

      {/* Loading Skeleton */}
      {loading && enquiries.length === 0 && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-white rounded-3xl border border-slate-200 p-6 space-y-4 animate-pulse"
            >
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <div className="flex items-center gap-3">
                  <div className="w-14 h-14 bg-slate-200 rounded-2xl" />
                  <div className="space-y-2">
                    <div className="w-48 h-4 bg-slate-200 rounded" />
                    <div className="w-24 h-3 bg-slate-100 rounded" />
                  </div>
                </div>
                <div className="w-28 h-7 bg-slate-200 rounded-full" />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="h-24 bg-slate-100 rounded-2xl" />
                <div className="h-24 bg-slate-100 rounded-2xl" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty State: No enquiries at all */}
      {!loading && enquiries.length === 0 && (
        <div className="bg-white rounded-3xl border border-slate-200 p-12 text-center max-w-lg mx-auto space-y-4 shadow-xs">
          <div className="w-16 h-16 rounded-3xl bg-amber-100 text-amber-700 flex items-center justify-center mx-auto shadow-inner">
            <MessageSquare className="w-8 h-8" />
          </div>
          <div className="space-y-1.5">
            <h3 className="text-lg font-black text-slate-900">
              No Vehicle Enquiries Yet
            </h3>
            <p className="text-xs text-slate-500 leading-relaxed max-w-sm mx-auto">
              When you browse approved vehicles on the DriverXtra marketplace and use the &quot;Contact Seller&quot; button to ask questions, your submitted inquiries and seller replies will appear here.
            </p>
          </div>
          {onNavigateToBrowse && (
            <div className="pt-2">
              <button
                onClick={onNavigateToBrowse}
                className="px-5 py-2.5 rounded-xl bg-slate-950 hover:bg-slate-800 text-amber-400 text-xs font-bold inline-flex items-center gap-2 shadow-sm transition-all"
              >
                <ShoppingBag className="w-4 h-4" />
                <span>Explore Approved Vehicles</span>
              </button>
            </div>
          )}
        </div>
      )}

      {/* Empty Filter State */}
      {!loading && enquiries.length > 0 && filteredEnquiries.length === 0 && (
        <div className="bg-white rounded-3xl border border-slate-200 p-8 text-center space-y-3">
          <p className="text-xs text-slate-500 font-medium">
            No enquiries match the selected filter &quot;{filterTab}&quot;.
          </p>
          <button
            onClick={() => setFilterTab("ALL")}
            className="text-xs font-bold text-amber-700 hover:underline"
          >
            Show All Enquiries
          </button>
        </div>
      )}

      {/* Enquiries List */}
      <div className="space-y-4">
        {filteredEnquiries.map((enq) => {
          const isNew = enq.status === "NEW";
          const isResponded = enq.status === "RESPONDED" || Boolean(enq.seller_reply);
          const isClosed = enq.status === "CLOSED";
          const hasReply = Boolean(enq.seller_reply);

          const sellerDisplayName =
            enq.organisation_name || enq.seller_name || "Verified Dealer";

          return (
            <div
              key={enq.id}
              className={`bg-white rounded-3xl border transition-all p-5 sm:p-6 space-y-4 ${
                hasReply
                  ? "border-emerald-300 shadow-sm ring-1 ring-emerald-300/40 hover:border-emerald-400"
                  : isNew
                  ? "border-amber-300 shadow-sm ring-1 ring-amber-300/30 hover:border-amber-400"
                  : "border-slate-200 shadow-xs hover:border-slate-300"
              }`}
            >
              {/* Header: Vehicle Summary & Status */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3.5 border-b border-slate-100">
                <div className="flex items-center gap-3.5">
                  {enq.listing_details?.primary_image_url ? (
                    <img
                      src={resolveMediaUrl(enq.listing_details.primary_image_url)}
                      alt={enq.listing_details.title || "Vehicle"}
                      className="w-14 h-14 rounded-2xl object-cover border border-slate-200 shrink-0 shadow-xs"
                    />
                  ) : (
                    <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center text-slate-400 shrink-0">
                      <Car className="w-7 h-7" />
                    </div>
                  )}

                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="text-base font-black text-slate-900">
                        {enq.listing_details?.title || "Vehicle Listing"}
                      </h4>
                      <span className="text-xs font-mono font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-lg border border-amber-200">
                        £{Number(enq.listing_details?.price || 0).toLocaleString()}
                      </span>
                    </div>

                    <div className="text-[11px] text-slate-500 flex flex-wrap items-center gap-2 mt-1">
                      <span className="flex items-center gap-1 font-semibold text-slate-700">
                        <Building2 className="w-3.5 h-3.5 text-slate-400" />
                        <span>Seller: {sellerDisplayName}</span>
                      </span>
                      <span>·</span>
                      <span>Year: {enq.listing_details?.year || "N/A"}</span>
                      <span>·</span>
                      <span>Location: {enq.listing_details?.location_city || "UK"}</span>
                      <span>·</span>
                      <span className="font-mono text-[10px] text-slate-400">
                        Ref: #{enq.id.slice(0, 8)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Status Badges */}
                <div className="flex items-center gap-2 self-start sm:self-auto shrink-0">
                  {hasReply ? (
                    <span className="px-3.5 py-1.5 rounded-full text-xs font-black bg-emerald-100 text-emerald-900 border border-emerald-300 flex items-center gap-1.5 shadow-xs">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                      <span>Seller Responded</span>
                    </span>
                  ) : isNew ? (
                    <span className="px-3.5 py-1.5 rounded-full text-xs font-bold bg-amber-100 text-amber-900 border border-amber-300 flex items-center gap-1.5 shadow-xs">
                      <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
                      <span>Waiting for seller response</span>
                    </span>
                  ) : isClosed ? (
                    <span className="px-3.5 py-1.5 rounded-full text-xs font-bold bg-slate-100 text-slate-600 border border-slate-300">
                      Closed
                    </span>
                  ) : (
                    <span className="px-3.5 py-1.5 rounded-full text-xs font-bold bg-slate-100 text-slate-700 border border-slate-300">
                      {enq.status}
                    </span>
                  )}
                </div>
              </div>

              {/* Conversation Grid: Buyer's Sent Message + Seller's Reply */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* 1. Buyer's Original Sent Message */}
                <div className="p-4 bg-amber-50/50 rounded-2xl border border-amber-200/70 space-y-2 flex flex-col justify-between">
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-[11px] font-bold text-amber-900">
                      <span className="flex items-center gap-1.5">
                        <MessageSquare className="w-3.5 h-3.5 text-amber-600" />
                        <span>Your Message</span>
                      </span>
                      <span className="font-normal text-[10px] text-amber-700 flex items-center gap-1">
                        <Calendar className="w-3 h-3 text-amber-500" />
                        <span>{new Date(enq.created_at).toLocaleString()}</span>
                      </span>
                    </div>

                    <p className="text-xs text-slate-800 whitespace-pre-line leading-relaxed bg-white/70 p-3 rounded-xl border border-amber-100">
                      {enq.message}
                    </p>
                  </div>

                  {enq.buyer_phone && (
                    <div className="pt-2 border-t border-amber-200/50 text-[10px] text-amber-800 flex items-center gap-1.5">
                      <Phone className="w-3 h-3 text-amber-600" />
                      <span>You provided phone number for callback: <strong>{enq.buyer_phone}</strong></span>
                    </div>
                  )}
                </div>

                {/* 2. Seller's Official Reply Message */}
                {hasReply ? (
                  <div className="p-4 bg-emerald-50/70 rounded-2xl border border-emerald-200/90 space-y-2 flex flex-col justify-between">
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-[11px] font-bold text-emerald-950">
                        <span className="flex items-center gap-1.5">
                          <Send className="w-3.5 h-3.5 text-emerald-600" />
                          <span>Seller Response ({sellerDisplayName})</span>
                        </span>
                        {(enq.replied_at || enq.responded_at) && (
                          <span className="font-normal text-[10px] text-emerald-800 flex items-center gap-1">
                            <Clock className="w-3 h-3 text-emerald-600" />
                            <span>
                              {new Date(enq.replied_at || enq.responded_at || "").toLocaleString()}
                            </span>
                          </span>
                        )}
                      </div>

                      <div className="bg-white/90 p-3.5 rounded-xl border border-emerald-200 shadow-xs">
                        <p className="text-xs text-slate-900 whitespace-pre-line leading-relaxed font-medium">
                          {enq.seller_reply}
                        </p>
                      </div>
                    </div>

                    <div className="pt-2 border-t border-emerald-200/60 text-[10px] text-emerald-800 flex items-center gap-1.5 font-medium">
                      <Sparkles className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                      <span>Official in-platform response from {sellerDisplayName}.</span>
                    </div>
                  </div>
                ) : (
                  <div className="p-5 bg-slate-50 rounded-2xl border border-dashed border-slate-200 flex flex-col items-center justify-center text-center space-y-2">
                    <div className="w-10 h-10 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center">
                      <Clock className="w-5 h-5" />
                    </div>
                    <div className="space-y-0.5">
                      <h5 className="text-xs font-bold text-slate-900">
                        Waiting for seller response
                      </h5>
                      <p className="text-[11px] text-slate-500 max-w-xs leading-relaxed">
                        The seller has received your enquiry. When they respond, their reply and timestamp will appear right here.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
