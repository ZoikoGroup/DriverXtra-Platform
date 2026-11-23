"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  api,
  AdvertisingCampaign,
  CampaignAnalytics,
  CampaignStatus,
} from "@/lib/api/client";
import CreateCampaignModal from "./CreateCampaignModal";
import {
  Megaphone,
  Plus,
  TrendingUp,
  Eye,
  MousePointerClick,
  Percent,
  Wallet,
  Play,
  Pause,
  XCircle,
  Clock,
  CheckCircle2,
  AlertTriangle,
  BarChart3,
  Calendar,
  ArrowUpRight,
  Loader2,
  CreditCard,
  X,
  Send,
  HelpCircle,
  FileText,
  Building2,
  Info,
  ShieldCheck,
} from "lucide-react";

interface ActiveAdvertisingPaymentSession {
  campaign: AdvertisingCampaign;
  provider: string;
  currency: string;
  amount_minor: number;
  session_data: Record<string, unknown> & {
    checkout_url?: string;
    order_id?: string;
    provider_order_id?: string;
    client_secret?: string;
    publishable_key?: string;
    is_test_mode?: boolean;
    key_id?: string;
  };
  is_resumed: boolean;
}

function loadRazorpayScript(): Promise<boolean> {
  return new Promise((resolve) => {
    if (typeof window === "undefined") {
      resolve(false);
      return;
    }
    if ((window as unknown as { Razorpay?: unknown }).Razorpay) {
      resolve(true);
      return;
    }
    const existing = document.getElementById("razorpay-checkout-js");
    if (existing) {
      if ((window as unknown as { Razorpay?: unknown }).Razorpay) {
        resolve(true);
      } else {
        existing.addEventListener("load", () => resolve(true));
        existing.addEventListener("error", () => resolve(false));
      }
      return;
    }
    const script = document.createElement("script");
    script.id = "razorpay-checkout-js";
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

export default function SellerAdvertisingView() {
  const [campaigns, setCampaigns] = useState<AdvertisingCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [typeFilter, setTypeFilter] = useState<string>("ALL");

  // Create Modal
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  // Analytics Modal
  const [selectedAnalytics, setSelectedAnalytics] = useState<CampaignAnalytics | null>(null);
  const [loadingAnalytics, setLoadingAnalytics] = useState(false);

  // Cancel Confirmation Modal
  const [campaignToCancel, setCampaignToCancel] = useState<AdvertisingCampaign | null>(null);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelling, setCancelling] = useState(false);

  // Payment State
  const [payingCampaignId, setPayingCampaignId] = useState<string | null>(null);
  const [activePaymentSession, setActivePaymentSession] = useState<ActiveAdvertisingPaymentSession | null>(null);
  const [confirmingPayment, setConfirmingPayment] = useState(false);
  const [paymentError, setPaymentError] = useState<string | null>(null);
  const [paymentSuccessMsg, setPaymentSuccessMsg] = useState<string | null>(null);

  const fetchCampaigns = useCallback(async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const data = await api.marketplace.listAdvertisingCampaigns({
        status: statusFilter === "ALL" ? undefined : statusFilter,
        campaign_type: typeFilter === "ALL" ? undefined : typeFilter,
      });
      setCampaigns(data || []);
    } catch (err: unknown) {
      console.error("Failed to load advertising campaigns", err);
      setErrorMsg("Failed to load your advertising campaigns. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, typeFilter]);

  useEffect(() => {
    fetchCampaigns();
  }, [fetchCampaigns]);

  // Aggregate Metrics
  const totalSpendMinor = campaigns.reduce((acc, c) => acc + (c.spent_amount_minor || 0), 0);
  const totalBudgetMinor = campaigns.reduce((acc, c) => acc + (c.total_budget_minor || 0), 0);
  const activeCount = campaigns.filter((c) => c.status === "ACTIVE").length;
  const totalImpressions = campaigns.reduce((acc, c) => acc + (c.total_impressions || 0), 0);
  const totalClicks = campaigns.reduce((acc, c) => acc + (c.total_clicks || 0), 0);
  const overallCtr = totalImpressions > 0 ? ((totalClicks / totalImpressions) * 100).toFixed(2) : "0.00";
  const remainingBudgetMinor = Math.max(0, totalBudgetMinor - totalSpendMinor);

  // Action Handlers
  const handleOpenAnalytics = async (campaignId: string) => {
    setLoadingAnalytics(true);
    try {
      const data = await api.marketplace.getAdvertisingCampaignAnalytics(campaignId);
      setSelectedAnalytics(data);
    } catch (err: unknown) {
      console.error("Failed to fetch analytics", err);
      alert("Unable to fetch performance analytics for this campaign.");
    } finally {
      setLoadingAnalytics(false);
    }
  };

  const handleSubmitForReview = async (campaignId: string) => {
    try {
      await api.marketplace.submitAdvertisingCampaign(campaignId);
      await fetchCampaigns();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : (typeof err === "object" && err !== null && "detail" in err ? String((err as { detail: unknown }).detail) : "Failed to submit campaign for review.");
      alert(msg);
    }
  };

  const handlePause = async (campaignId: string) => {
    try {
      await api.marketplace.pauseAdvertisingCampaign(campaignId);
      await fetchCampaigns();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : (typeof err === "object" && err !== null && "detail" in err ? String((err as { detail: unknown }).detail) : "Failed to pause campaign.");
      alert(msg);
    }
  };

  const handleResume = async (campaignId: string) => {
    try {
      await api.marketplace.resumeAdvertisingCampaign(campaignId);
      await fetchCampaigns();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : (typeof err === "object" && err !== null && "detail" in err ? String((err as { detail: unknown }).detail) : "Failed to resume campaign.");
      alert(msg);
    }
  };

  const handleConfirmCancel = async () => {
    if (!campaignToCancel) return;
    setCancelling(true);
    try {
      const res = await api.marketplace.cancelAdvertisingCampaign(
        campaignToCancel.id,
        cancelReason || "Cancelled by seller"
      );
      setCampaignToCancel(null);
      setCancelReason("");
      alert(
        `Campaign cancelled. ${
          res.refund_amount_minor > 0
            ? `A pro-rata refund of ${(res.refund_amount_minor / 100).toFixed(2)} ${campaignToCancel.currency} has been processed.`
            : "No remaining unserved days for refund."
        }`
      );
      await fetchCampaigns();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : (typeof err === "object" && err !== null && "detail" in err ? String((err as { detail: unknown }).detail) : "Failed to cancel campaign.");
      alert(msg);
    } finally {
      setCancelling(false);
    }
  };

  const handleInitiatePayment = async (campaign: AdvertisingCampaign) => {
    setPayingCampaignId(campaign.id);
    setPaymentError(null);
    try {
      const returnUrl = typeof window !== "undefined" ? window.location.href : "";
      const session = await api.marketplace.getAdvertisingPaymentSession(campaign.id, returnUrl, returnUrl);

      if (session.session_data?.checkout_url) {
        window.location.assign(session.session_data.checkout_url);
      } else {
        setActivePaymentSession({
          campaign,
          provider: session.provider || (campaign.currency === "INR" ? "RAZORPAY" : "STRIPE"),
          currency: campaign.currency || "GBP",
          amount_minor: session.amount_minor || campaign.total_budget_minor,
          session_data: session.session_data || {},
          is_resumed: campaign.status === "PAYMENT_PENDING",
        });
      }
    } catch (err: unknown) {
      console.error("Payment error", err);
      const msg = err instanceof Error ? err.message : (typeof err === "object" && err !== null && "detail" in err ? String((err as { detail: unknown }).detail) : "Unable to initiate payment session.");
      alert(msg);
    } finally {
      setPayingCampaignId(null);
    }
  };

  const handleConfirmPayment = async () => {
    if (!activePaymentSession) return;
    setConfirmingPayment(true);
    setPaymentError(null);
    try {
      const { campaign, session_data, currency } = activePaymentSession;

      if (currency.toUpperCase() === "INR") {
        const loaded = await loadRazorpayScript();
        const RazorpayClass = (window as unknown as {
          Razorpay?: new (opts: unknown) => {
            open: () => void;
            on: (evt: string, cb: (resp: unknown) => void) => void;
          };
        }).Razorpay;

        if (!loaded || !RazorpayClass) {
          setPaymentError("Unable to load Razorpay Checkout SDK. Please check your network connection and retry.");
          setConfirmingPayment(false);
          return;
        }

        const razorpayKey =
          session_data.key_id ||
          process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID ||
          "rzp_test_placeholder_key";
        const razorpayOrderId =
          session_data.order_id || session_data.provider_order_id || "";

        const options = {
          key: razorpayKey,
          amount: activePaymentSession.amount_minor,
          currency: "INR",
          name: "DriverXtra Platform",
          description: `Sponsored Campaign: ${campaign.title}`,
          order_id: razorpayOrderId,
          prefill: {
            name: campaign.seller_name || "",
            email: campaign.seller_email || "",
          },
          theme: {
            color: "#f59e0b",
          },
          modal: {
            confirm_close: true,
            ondismiss: function () {
              setConfirmingPayment(false);
            },
          },
          handler: async function (response: {
            razorpay_payment_id: string;
            razorpay_order_id: string;
            razorpay_signature: string;
          }) {
            setConfirmingPayment(true);
            setPaymentError(null);
            try {
              const res = await api.marketplace.confirmAdvertisingPayment(campaign.id, {
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_order_id: response.razorpay_order_id,
                razorpay_signature: response.razorpay_signature,
              });
              setPaymentSuccessMsg(`Payment confirmed for "${campaign.title}". Campaign status is now ${res.campaign.status_display || res.campaign.status}!`);
              await fetchCampaigns();
              setTimeout(() => {
                setActivePaymentSession(null);
                setConfirmingPayment(false);
              }, 1200);
            } catch (err: unknown) {
              console.error("Confirmation error", err);
              const msg = err instanceof Error ? err.message : (typeof err === "object" && err !== null && "detail" in err ? String((err as { detail: unknown }).detail) : "Payment verification failed.");
              setPaymentError(msg);
              setConfirmingPayment(false);
            }
          },
        };

        const rzp = new RazorpayClass(options);
        rzp.on("payment.failed", function (resp: unknown) {
          setConfirmingPayment(false);
          const desc =
            (resp as { error?: { description?: string } })?.error?.description ||
            "Payment was declined or failed.";
          setPaymentError(desc);
        });
        rzp.open();
        setConfirmingPayment(false);
        return;
      }

      let payload: Record<string, unknown> = {};
      if (currency.toUpperCase() === "GBP") {
        payload = {
          payment_intent_id: session_data.provider_order_id,
          client_secret: session_data.client_secret,
        };
      }

      const res = await api.marketplace.confirmAdvertisingPayment(campaign.id, payload);
      setPaymentSuccessMsg(`Payment confirmed for "${campaign.title}". Campaign status is now ${res.campaign.status_display || res.campaign.status}!`);
      await fetchCampaigns();
      setTimeout(() => {
        setActivePaymentSession(null);
        setConfirmingPayment(false);
      }, 1200);
    } catch (err: unknown) {
      console.error("Confirmation error", err);
      const msg = err instanceof Error ? err.message : (typeof err === "object" && err !== null && "detail" in err ? String((err as { detail: unknown }).detail) : "Payment verification failed.");
      setPaymentError(msg);
      setConfirmingPayment(false);
    }
  };

  const getStatusBadge = (status: CampaignStatus) => {
    switch (status) {
      case "ACTIVE":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Active
          </span>
        );
      case "PENDING_APPROVAL":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/30">
            <Clock className="w-3 h-3" />
            Pending Staff Review
          </span>
        );
      case "APPROVED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-300 border border-blue-500/30">
            <CheckCircle2 className="w-3 h-3" />
            Approved • Pay to Activate
          </span>
        );
      case "PAYMENT_PENDING":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-300 border border-indigo-500/30">
            <CreditCard className="w-3 h-3" />
            Payment Pending
          </span>
        );
      case "SCHEDULED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-300 border border-purple-500/30">
            <Calendar className="w-3 h-3" />
            Scheduled
          </span>
        );
      case "PAUSED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30">
            <Pause className="w-3 h-3" />
            Paused
          </span>
        );
      case "COMPLETED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-500/10 text-slate-400 border border-slate-500/30">
            Completed
          </span>
        );
      case "REJECTED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/30">
            <XCircle className="w-3 h-3" />
            Rejected
          </span>
        );
      case "CANCELLED":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-800 text-slate-400 border border-slate-700">
            Cancelled
          </span>
        );
      case "DRAFT":
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-800 text-slate-300 border border-slate-700">
            Draft
          </span>
        );
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* View Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-black text-white">Sponsored Listings & Ads</h1>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-400/10 text-amber-400 border border-amber-400/20">
              Phase 7.2
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Drive high-intent buyer traffic to your vehicle and spare-part listings with prominent sponsored placements.
          </p>
        </div>

        <button
          onClick={() => setIsCreateOpen(true)}
          className="px-4 py-2.5 rounded-xl bg-amber-400 hover:bg-amber-300 text-slate-950 font-bold text-xs flex items-center gap-2 transition shadow-lg shadow-amber-400/10"
        >
          <Plus className="w-4 h-4" />
          <span>Create New Campaign</span>
        </button>
      </div>

      {/* Global Success Notification */}
      {paymentSuccessMsg && (
        <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between gap-3 animate-in fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span className="font-medium">{paymentSuccessMsg}</span>
          </div>
          <button
            onClick={() => setPaymentSuccessMsg(null)}
            className="text-slate-400 hover:text-white p-1 rounded-lg transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Total Ad Spend</span>
            <Wallet className="w-4 h-4 text-amber-400" />
          </div>
          <div className="mt-2">
            <span className="text-xl font-bold text-white">
              £ {(totalSpendMinor / 100).toFixed(2)}
            </span>
            <span className="text-[10px] text-slate-500 block">Across all campaigns</span>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Active Campaigns</span>
            <Play className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-2">
            <span className="text-xl font-bold text-emerald-400">{activeCount}</span>
            <span className="text-[10px] text-slate-500 block">Currently serving</span>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Impressions</span>
            <Eye className="w-4 h-4 text-blue-400" />
          </div>
          <div className="mt-2">
            <span className="text-xl font-bold text-white">{totalImpressions.toLocaleString()}</span>
            <span className="text-[10px] text-slate-500 block">De-duplicated views</span>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Total Clicks</span>
            <MousePointerClick className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="mt-2">
            <span className="text-xl font-bold text-white">{totalClicks.toLocaleString()}</span>
            <span className="text-[10px] text-slate-500 block">Qualified interactions</span>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Average CTR</span>
            <Percent className="w-4 h-4 text-amber-400" />
          </div>
          <div className="mt-2">
            <span className="text-xl font-bold text-amber-400">{overallCtr}%</span>
            <span className="text-[10px] text-slate-500 block">Click-through rate</span>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Remaining Budget</span>
            <TrendingUp className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-2">
            <span className="text-xl font-bold text-white">
              £ {(remainingBudgetMinor / 100).toFixed(2)}
            </span>
            <span className="text-[10px] text-slate-500 block">Committed unspent</span>
          </div>
        </div>
      </div>

      {/* Filters Row */}
      <div className="p-3 bg-slate-900 border border-slate-800 rounded-xl flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-slate-500 mr-1 font-medium">Status:</span>
          {[
            { id: "ALL", label: "All" },
            { id: "ACTIVE", label: "Active" },
            { id: "PENDING_APPROVAL", label: "Pending Review" },
            { id: "APPROVED", label: "Approved" },
            { id: "PAYMENT_PENDING", label: "Payment Pending" },
            { id: "SCHEDULED", label: "Scheduled" },
            { id: "PAUSED", label: "Paused" },
            { id: "COMPLETED", label: "Completed" },
          ].map((st) => (
            <button
              key={st.id}
              onClick={() => setStatusFilter(st.id)}
              className={`px-3 py-1.5 rounded-lg font-semibold transition ${
                statusFilter === st.id
                  ? "bg-amber-400 text-slate-950 shadow"
                  : "bg-slate-950 text-slate-400 hover:text-white border border-slate-800"
              }`}
            >
              {st.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <span className="text-slate-500 font-medium">Type:</span>
          {["ALL", "VEHICLES", "SPARE_PARTS"].map((tp) => (
            <button
              key={tp}
              onClick={() => setTypeFilter(tp)}
              className={`px-3 py-1.5 rounded-lg font-semibold transition ${
                typeFilter === tp
                  ? "bg-slate-800 text-amber-400 border border-amber-400/30"
                  : "bg-slate-950 text-slate-400 hover:text-white border border-slate-800"
              }`}
            >
              {tp === "ALL" ? "All Types" : tp === "VEHICLES" ? "Vehicles" : "Spare Parts"}
            </button>
          ))}
        </div>
      </div>

      {/* Campaigns Table */}
      {loading ? (
        <div className="py-20 flex flex-col items-center justify-center text-slate-400 gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
          <span className="text-xs">Loading advertising campaigns...</span>
        </div>
      ) : campaigns.length === 0 ? (
        <div className="py-16 text-center rounded-2xl border border-dashed border-slate-800 bg-slate-950/40 p-8 space-y-3">
          <div className="w-12 h-12 rounded-2xl bg-amber-400/10 border border-amber-400/20 text-amber-400 flex items-center justify-center mx-auto">
            <Megaphone className="w-6 h-6" />
          </div>
          <h3 className="text-base font-bold text-white">No advertising campaigns found</h3>
          <p className="text-xs text-slate-400 max-w-md mx-auto">
            Boost your marketplace presence! Create a sponsored ad campaign to pin your approved inventory to top buyer search slots.
          </p>
          <button
            onClick={() => setIsCreateOpen(true)}
            className="px-4 py-2 rounded-xl bg-amber-400 hover:bg-amber-300 text-slate-950 font-bold text-xs inline-flex items-center gap-2 transition mt-2"
          >
            <Plus className="w-4 h-4" />
            <span>Create Campaign</span>
          </button>
        </div>
      ) : (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/80 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                <tr>
                  <th className="py-3 px-4">Campaign Title & Type</th>
                  <th className="py-3 px-4">Schedule & Duration</th>
                  <th className="py-3 px-4">Budget & Spend</th>
                  <th className="py-3 px-4">Performance</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {campaigns.map((c) => {
                  const isPaying = payingCampaignId === c.id;

                  return (
                    <tr key={c.id} className="hover:bg-slate-800/40 transition">
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-2.5">
                          <div className="w-8 h-8 rounded-lg bg-amber-400/10 border border-amber-400/20 flex items-center justify-center text-amber-400 shrink-0">
                            <Megaphone className="w-4 h-4" />
                          </div>
                          <div>
                            <p className="font-bold text-white text-sm line-clamp-1">{c.title}</p>
                            <p className="text-[11px] text-slate-400">
                              {c.campaign_type_display} • {c.listings_count} listing(s)
                              {c.target_country ? ` • ${c.target_country}` : ""}
                            </p>
                          </div>
                        </div>
                      </td>

                      <td className="py-3.5 px-4 text-slate-300">
                        <span className="font-semibold block text-white">{c.duration_days} Days</span>
                        <span className="text-[11px] text-slate-400">
                          {c.start_date} → {c.end_date}
                        </span>
                      </td>

                      <td className="py-3.5 px-4">
                        <span className="font-bold text-white block">
                          {c.currency} {(c.total_budget_minor / 100).toFixed(2)}
                        </span>
                        <span className="text-[11px] text-slate-400">
                          Spent: {c.currency} {(c.spent_amount_minor / 100).toFixed(2)}
                        </span>
                      </td>

                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-3">
                          <div>
                            <span className="text-white font-semibold">{c.total_impressions.toLocaleString()}</span>
                            <span className="text-[10px] text-slate-500 block">Impr</span>
                          </div>
                          <div>
                            <span className="text-white font-semibold">{c.total_clicks.toLocaleString()}</span>
                            <span className="text-[10px] text-slate-500 block">Clicks</span>
                          </div>
                          <div>
                            <span className="text-amber-400 font-bold">{c.ctr_percentage}%</span>
                            <span className="text-[10px] text-slate-500 block">CTR</span>
                          </div>
                        </div>
                      </td>

                      <td className="py-3.5 px-4">{getStatusBadge(c.status)}</td>

                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {/* Payment action for PAYMENT_PENDING and APPROVED campaigns requiring payment */}
                          {c.payment_status !== "PAID" && (c.status === "PAYMENT_PENDING" || c.status === "APPROVED") && (
                            <button
                              onClick={() => handleInitiatePayment(c)}
                              disabled={isPaying}
                              className="px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-xs font-bold flex items-center gap-1.5 transition disabled:opacity-50 shadow-sm"
                              title={c.status === "PAYMENT_PENDING" ? "Complete payment for this campaign" : "Pay to activate campaign"}
                            >
                              {isPaying ? (
                                <>
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  <span>Connecting...</span>
                                </>
                              ) : (
                                <>
                                  <CreditCard className="w-3.5 h-3.5" />
                                  <span>{c.status === "PAYMENT_PENDING" ? "Pay Now" : "Pay & Activate"}</span>
                                </>
                              )}
                            </button>
                          )}

                          {/* Submit if Draft */}
                          {c.status === "DRAFT" && (
                            <button
                              onClick={() => handleSubmitForReview(c.id)}
                              className="px-3 py-1.5 rounded-lg bg-amber-400 hover:bg-amber-300 text-slate-950 text-xs font-bold flex items-center gap-1.5 transition"
                            >
                              <Send className="w-3.5 h-3.5" />
                              <span>Submit</span>
                            </button>
                          )}

                          {/* Pause if Active */}
                          {c.status === "ACTIVE" && (
                            <button
                              onClick={() => handlePause(c.id)}
                              className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-amber-400 hover:bg-slate-700 transition"
                              title="Pause Campaign"
                            >
                              <Pause className="w-4 h-4" />
                            </button>
                          )}

                          {/* Resume if Paused */}
                          {c.status === "PAUSED" && (
                            <button
                              onClick={() => handleResume(c.id)}
                              className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-emerald-400 hover:bg-slate-700 transition"
                              title="Resume Campaign"
                            >
                              <Play className="w-4 h-4" />
                            </button>
                          )}

                          {/* Cancel if Active, Paused, Scheduled */}
                          {["ACTIVE", "PAUSED", "SCHEDULED"].includes(c.status) && (
                            <button
                              onClick={() => setCampaignToCancel(c)}
                              className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-rose-400 hover:bg-slate-700 transition"
                              title="Cancel & Refund"
                            >
                              <XCircle className="w-4 h-4" />
                            </button>
                          )}

                          {/* View Analytics */}
                          <button
                            onClick={() => handleOpenAnalytics(c.id)}
                            className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 transition"
                            title="Detailed Analytics"
                          >
                            <BarChart3 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* CREATE CAMPAIGN MODAL */}
      <CreateCampaignModal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSuccess={() => fetchCampaigns()}
      />

      {/* ANALYTICS DRAWER / MODAL */}
      {selectedAnalytics && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-3xl overflow-hidden shadow-2xl flex flex-col max-h-[85vh]">
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/50">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-amber-400/10 border border-amber-400/30 flex items-center justify-center text-amber-400">
                  <BarChart3 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">{selectedAnalytics.title}</h3>
                  <p className="text-xs text-slate-400">Performance Metrics & Engagement Analytics</p>
                </div>
              </div>
              <button
                onClick={() => setSelectedAnalytics(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-6">
              {/* Top stats */}
              <div className="grid grid-cols-4 gap-3">
                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-[10px] text-slate-500 uppercase font-semibold">Impressions</span>
                  <p className="text-lg font-bold text-white mt-1">
                    {selectedAnalytics.total_impressions.toLocaleString()}
                  </p>
                </div>
                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-[10px] text-slate-500 uppercase font-semibold">Clicks</span>
                  <p className="text-lg font-bold text-white mt-1">
                    {selectedAnalytics.total_clicks.toLocaleString()}
                  </p>
                </div>
                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-[10px] text-slate-500 uppercase font-semibold">CTR %</span>
                  <p className="text-lg font-bold text-amber-400 mt-1">
                    {selectedAnalytics.click_through_rate_pct}%
                  </p>
                </div>
                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <span className="text-[10px] text-slate-500 uppercase font-semibold">Spend</span>
                  <p className="text-lg font-bold text-white mt-1">
                    {selectedAnalytics.currency} {(selectedAnalytics.spent_amount_minor / 100).toFixed(2)}
                  </p>
                </div>
              </div>

              {/* Per-Listing Performance */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
                  Per-Listing Breakdown
                </h4>
                <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-slate-900/60 text-slate-400 border-b border-slate-800">
                      <tr>
                        <th className="py-2.5 px-3">Listing Title</th>
                        <th className="py-2.5 px-3">Target</th>
                        <th className="py-2.5 px-3">Impressions</th>
                        <th className="py-2.5 px-3">Clicks</th>
                        <th className="py-2.5 px-3">CTR %</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/40">
                      {selectedAnalytics.listings_metrics.map((lm) => (
                        <tr key={lm.sponsored_listing_id}>
                          <td className="py-2 px-3 font-medium text-white">{lm.title || "Inventory Item"}</td>
                          <td className="py-2 px-3 text-slate-400">{lm.target_type}</td>
                          <td className="py-2 px-3 text-slate-300">{lm.impressions}</td>
                          <td className="py-2 px-3 text-slate-300">{lm.clicks}</td>
                          <td className="py-2 px-3 font-semibold text-amber-400">{lm.ctr_pct}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Daily Performance */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">Daily Trend</h4>
                {selectedAnalytics.daily_metrics.length === 0 ? (
                  <p className="text-xs text-slate-500 italic p-4 rounded-xl bg-slate-950 border border-slate-800 text-center">
                    No daily aggregate data recorded yet. Metrics are aggregated by Celery tasks daily.
                  </p>
                ) : (
                  <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-slate-900/60 text-slate-400 border-b border-slate-800">
                        <tr>
                          <th className="py-2 px-3">Date</th>
                          <th className="py-2 px-3">Impressions</th>
                          <th className="py-2 px-3">Clicks</th>
                          <th className="py-2 px-3">CTR %</th>
                          <th className="py-2 px-3">Spend</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/40">
                        {selectedAnalytics.daily_metrics.map((dm) => (
                          <tr key={dm.date}>
                            <td className="py-2 px-3 font-mono text-slate-300">{dm.date}</td>
                            <td className="py-2 px-3 text-white">{dm.impressions}</td>
                            <td className="py-2 px-3 text-white">{dm.clicks}</td>
                            <td className="py-2 px-3 text-amber-400 font-semibold">{dm.ctr_pct}%</td>
                            <td className="py-2 px-3 text-slate-300">
                              {selectedAnalytics.currency} {(dm.spend_minor / 100).toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>

            <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/50 flex justify-end">
              <button
                onClick={() => setSelectedAnalytics(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 hover:text-white text-xs font-semibold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* CANCEL & REFUND CONFIRMATION MODAL */}
      {campaignToCancel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl p-6 space-y-4">
            <div className="flex items-center gap-3 text-rose-400">
              <div className="w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Cancel Campaign</h3>
                <p className="text-xs text-slate-400">Pro-Rata Refund Calculation</p>
              </div>
            </div>

            <p className="text-xs text-slate-300">
              Are you sure you want to cancel <strong className="text-white">{campaignToCancel.title}</strong>?
              A whole-day pro-rata refund will be issued for unserved campaign days. Served days are non-refundable.
            </p>

            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-1">
                Reason for Cancellation (Optional)
              </label>
              <textarea
                rows={2}
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="e.g. Inventory sold offline, budget adjustment..."
                className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white placeholder-slate-600 focus:outline-none focus:border-rose-400 text-xs"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setCampaignToCancel(null)}
                disabled={cancelling}
                className="px-4 py-2 rounded-xl text-slate-400 hover:text-white text-xs font-semibold"
              >
                Keep Active
              </button>
              <button
                onClick={handleConfirmCancel}
                disabled={cancelling}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold flex items-center gap-1.5 transition disabled:opacity-50"
              >
                {cancelling ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Processing...</span>
                  </>
                ) : (
                  <span>Confirm Cancellation & Refund</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* COMPLETE / RESUME PAYMENT MODAL */}
      {activePaymentSession && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl space-y-0">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                  <CreditCard className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">
                    {activePaymentSession.is_resumed ? "Resume Campaign Payment" : "Complete Campaign Payment"}
                  </h3>
                  <p className="text-xs text-slate-400">{activePaymentSession.campaign.title}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (!confirmingPayment) {
                    setActivePaymentSession(null);
                    setPaymentError(null);
                  }
                }}
                disabled={confirmingPayment}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition disabled:opacity-40"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
              {/* Resumed Session Alert */}
              {activePaymentSession.is_resumed && (
                <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-300 text-xs flex items-start gap-2.5">
                  <Info className="w-4 h-4 text-blue-400 mt-0.5 shrink-0" />
                  <div>
                    <p className="font-semibold text-white">Active Payment Session Retrieved</p>
                    <p className="text-blue-300/90 text-[11px] mt-0.5">
                      Resuming your previous checkout session safely. No duplicate payment intents will be created.
                    </p>
                  </div>
                </div>
              )}

              {/* Error Message */}
              {paymentError && (
                <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                    <span>{paymentError}</span>
                  </div>
                  <button onClick={() => setPaymentError(null)} className="text-slate-400 hover:text-white">
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}

              {/* Campaign & Pricing Summary Card */}
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between text-xs border-b border-slate-800/80 pb-2.5">
                  <span className="text-slate-400">Campaign Schedule</span>
                  <span className="font-semibold text-white">
                    {activePaymentSession.campaign.start_date} → {activePaymentSession.campaign.end_date} ({activePaymentSession.campaign.duration_days} Days)
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs border-b border-slate-800/80 pb-2.5">
                  <span className="text-slate-400">Payment Gateway</span>
                  <span className="font-semibold text-slate-200">
                    {activePaymentSession.currency === "GBP" ? "Stripe UK (Online Card)" : "Razorpay India (UPI / Cards)"}
                  </span>
                </div>
                {activePaymentSession.session_data?.provider_order_id && (
                  <div className="flex items-center justify-between text-xs border-b border-slate-800/80 pb-2.5">
                    <span className="text-slate-400">Session Reference</span>
                    <span className="font-mono text-[11px] text-amber-400 truncate max-w-[220px]">
                      {activePaymentSession.session_data.provider_order_id}
                    </span>
                  </div>
                )}
                <div className="flex items-center justify-between pt-1">
                  <span className="text-sm font-bold text-white">Total Amount Due</span>
                  <span className="text-lg font-black text-emerald-400">
                    {activePaymentSession.currency} {(activePaymentSession.amount_minor / 100).toFixed(2)}
                  </span>
                </div>
              </div>

              {/* Non-Live / Sandbox Configuration Indicator */}
              <div className="p-3 rounded-xl bg-amber-400/10 border border-amber-400/20 text-amber-300 text-xs flex items-start gap-2.5">
                <ShieldCheck className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                <div>
                  <p className="font-semibold text-white">Non-Live Payment Sandbox</p>
                  <p className="text-slate-400 text-[11px] mt-0.5">
                    Live commercial payment charges are currently disabled. This session operates in secure sandbox mode.
                  </p>
                </div>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="px-6 py-4 border-t border-slate-800 bg-slate-950/50 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  setActivePaymentSession(null);
                  setPaymentError(null);
                }}
                disabled={confirmingPayment}
                className="px-4 py-2 rounded-xl text-slate-400 hover:text-white text-xs font-semibold disabled:opacity-50"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={handleConfirmPayment}
                disabled={confirmingPayment}
                className="px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs flex items-center gap-2 transition disabled:opacity-50 shadow-lg shadow-emerald-500/20"
              >
                {confirmingPayment ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Verifying with Gateway...</span>
                  </>
                ) : (
                  <>
                    <CreditCard className="w-4 h-4" />
                    <span>
                      {activePaymentSession.currency === 'INR'
                        ? `Open Razorpay Checkout (${activePaymentSession.currency} ${(activePaymentSession.amount_minor / 100).toFixed(2)})`
                        : `Confirm & Pay ${activePaymentSession.currency} ${(activePaymentSession.amount_minor / 100).toFixed(2)}`}
                    </span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
