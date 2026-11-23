"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  api,
  AdvertisingCampaign,
  AdminAdvertisingOverview,
  CampaignStatus,
} from "@/lib/api/client";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  ShieldCheck,
  Megaphone,
  CheckCircle2,
  XCircle,
  Clock,
  Search,
  DollarSign,
  TrendingUp,
  Pause,
  Loader2,
  Layers,
  Building2,
  Mail,
  User,
  X,
  Check,
  FileText,
  HelpCircle,
  ChevronRight,
} from "lucide-react";

export default function AdminAdvertisingView() {
  const { user } = useAuth();
  const [overview, setOverview] = useState<AdminAdvertisingOverview | null>(null);
  const [campaigns, setCampaigns] = useState<AdvertisingCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("PENDING_APPROVAL");
  const [countryFilter, setCountryFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  // Review Modal State
  const [reviewCampaign, setReviewCampaign] = useState<AdvertisingCampaign | null>(null);
  const [reviewAction, setReviewAction] = useState<"APPROVE" | "REJECT">("APPROVE");
  const [rejectionReason, setRejectionReason] = useState("");
  const [approvalNotes, setApprovalNotes] = useState("");
  const [reviewing, setReviewing] = useState(false);

  // Terminate Modal State
  const [terminateCampaign, setTerminateCampaign] = useState<AdvertisingCampaign | null>(null);
  const [terminationReason, setTerminationReason] = useState("");
  const [terminating, setTerminating] = useState(false);

  // Detail Inspection Modal
  const [inspectCampaign, setInspectCampaign] = useState<AdvertisingCampaign | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const [overviewData, campaignsData] = await Promise.all([
        api.marketplace.adminGetAdvertisingOverview(),
        api.marketplace.adminListAdvertisingCampaigns({
          status: statusFilter === "ALL" ? undefined : statusFilter,
          country: countryFilter === "ALL" ? undefined : countryFilter,
          search: searchQuery || undefined,
        }),
      ]);
      setOverview(overviewData);
      setCampaigns(campaignsData || []);
    } catch (err: unknown) {
      console.error("Failed to load admin advertising data", err);
      setErrorMsg("Failed to load advertising administrative overview.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, countryFilter, searchQuery]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleReviewSubmit = async () => {
    if (!reviewCampaign) return;
    if (reviewAction === "REJECT" && !rejectionReason.trim()) {
      alert("A detailed rejection reason is mandatory when rejecting a campaign.");
      return;
    }

    setReviewing(true);
    try {
      await api.marketplace.adminReviewAdvertisingCampaign(
        reviewCampaign.id,
        reviewAction,
        rejectionReason.trim(),
        approvalNotes.trim()
      );
      setReviewCampaign(null);
      setRejectionReason("");
      setApprovalNotes("");
      await fetchData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : (typeof err === "object" && err !== null && "detail" in err ? String((err as { detail: unknown }).detail) : "Failed to submit campaign review.");
      alert(msg);
    } finally {
      setReviewing(false);
    }
  };

  const handlePauseCampaign = async (campaignId: string) => {
    try {
      await api.marketplace.adminPauseAdvertisingCampaign(campaignId);
      await fetchData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : (typeof err === "object" && err !== null && "detail" in err ? String((err as { detail: unknown }).detail) : "Failed to pause campaign.");
      alert(msg);
    }
  };

  const handleTerminateSubmit = async () => {
    if (!terminateCampaign) return;
    setTerminating(true);
    try {
      const res = await api.marketplace.adminTerminateAdvertisingCampaign(
        terminateCampaign.id,
        terminationReason || "Administrative policy termination"
      );
      setTerminateCampaign(null);
      setTerminationReason("");
      alert(
        `Campaign terminated. Refund of ${(res.refund_amount_minor / 100).toFixed(2)} ${
          terminateCampaign.currency
        } calculated.`
      );
      await fetchData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : (typeof err === "object" && err !== null && "detail" in err ? String((err as { detail: unknown }).detail) : "Failed to terminate campaign.");
      alert(msg);
    } finally {
      setTerminating(false);
    }
  };

  const getStatusBadge = (status: CampaignStatus) => {
    switch (status) {
      case "ACTIVE":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            Active
          </span>
        );
      case "PENDING_APPROVAL":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/30">
            <Clock className="w-3 h-3" />
            Pending Review
          </span>
        );
      case "APPROVED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-300 border border-blue-500/30">
            Approved
          </span>
        );
      case "SCHEDULED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-300 border border-purple-500/30">
            Scheduled
          </span>
        );
      case "PAUSED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30">
            Paused
          </span>
        );
      case "COMPLETED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-700 text-slate-300">
            Completed
          </span>
        );
      case "REJECTED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/30">
            Rejected
          </span>
        );
      case "CANCELLED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-800 text-slate-400 border border-slate-700">
            Cancelled
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-800 text-slate-400">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-black text-white">Advertising Moderation & Oversight</h1>
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-400/10 text-amber-400 border border-amber-400/20">
              Staff Only
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Authoritative staff review for sponsored listings, digital service tax compliance, and revenue reporting.
          </p>
        </div>
      </div>

      {/* Overview Cards */}
      {overview && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
            <div className="flex items-center justify-between text-slate-400">
              <span className="text-[11px] font-semibold uppercase tracking-wider">Total Ad Revenue</span>
              <DollarSign className="w-4 h-4 text-emerald-400" />
            </div>
            <p className="text-2xl font-black text-emerald-400 mt-2">
              £ {(overview.total_revenue_minor / 100).toFixed(2)}
            </p>
            <span className="text-[10px] text-slate-500">Gross advertising billed</span>
          </div>

          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
            <div className="flex items-center justify-between text-slate-400">
              <span className="text-[11px] font-semibold uppercase tracking-wider">Pending Review</span>
              <Clock className="w-4 h-4 text-amber-400" />
            </div>
            <p className="text-2xl font-black text-amber-400 mt-2">{overview.pending_approval}</p>
            <span className="text-[10px] text-slate-500">Requires staff decision</span>
          </div>

          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
            <div className="flex items-center justify-between text-slate-400">
              <span className="text-[11px] font-semibold uppercase tracking-wider">Active Campaigns</span>
              <Megaphone className="w-4 h-4 text-blue-400" />
            </div>
            <p className="text-2xl font-black text-white mt-2">{overview.active_campaigns}</p>
            <span className="text-[10px] text-slate-500">Currently serving in feed</span>
          </div>

          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
            <div className="flex items-center justify-between text-slate-400">
              <span className="text-[11px] font-semibold uppercase tracking-wider">CTR & Interactions</span>
              <TrendingUp className="w-4 h-4 text-purple-400" />
            </div>
            <p className="text-2xl font-black text-purple-300 mt-2">{overview.overall_ctr_percent}%</p>
            <span className="text-[10px] text-slate-500">
              {overview.total_clicks.toLocaleString()} clicks / {overview.total_impressions.toLocaleString()} views
            </span>
          </div>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="p-3 bg-slate-900 border border-slate-800 rounded-xl flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-slate-500 mr-1 font-medium">Review Status:</span>
          {[
            { id: "PENDING_APPROVAL", label: "Pending Review" },
            { id: "ACTIVE", label: "Active" },
            { id: "ALL", label: "All Campaigns" },
            { id: "APPROVED", label: "Approved" },
            { id: "SCHEDULED", label: "Scheduled" },
            { id: "REJECTED", label: "Rejected" },
            { id: "CANCELLED", label: "Cancelled" },
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
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-500" />
            <input
              type="text"
              placeholder="Search seller or title..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 pr-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-white placeholder-slate-600 focus:outline-none focus:border-amber-400 text-xs w-48"
            />
          </div>
        </div>
      </div>

      {/* Campaigns Table */}
      {loading ? (
        <div className="py-20 flex flex-col items-center justify-center text-slate-400 gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
          <span className="text-xs">Loading campaign moderation queue...</span>
        </div>
      ) : campaigns.length === 0 ? (
        <div className="py-16 text-center rounded-2xl border border-dashed border-slate-800 bg-slate-950/40 p-8 space-y-2">
          <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto" />
          <h3 className="text-sm font-bold text-white">Moderation Queue Clear</h3>
          <p className="text-xs text-slate-500">No campaigns found matching current filters.</p>
        </div>
      ) : (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/80 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                <tr>
                  <th className="py-3 px-4">Campaign & Seller</th>
                  <th className="py-3 px-4">Target & Tax Regime</th>
                  <th className="py-3 px-4">Budget & Days</th>
                  <th className="py-3 px-4">Listings</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Moderation Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {campaigns.map((c) => {
                  const isOwnCampaign = user?.id === c.seller;

                  return (
                    <tr key={c.id} className="hover:bg-slate-800/40 transition">
                      <td className="py-3.5 px-4">
                        <p className="font-bold text-white text-sm line-clamp-1">{c.title}</p>
                        <p className="text-[11px] text-slate-400 flex items-center gap-1.5 mt-0.5">
                          <User className="w-3 h-3 text-slate-500" />
                          <span>{c.seller_name || c.seller_email}</span>
                          {c.organisation_name && (
                            <span className="text-amber-400/80">• {c.organisation_name}</span>
                          )}
                        </p>
                      </td>

                      <td className="py-3.5 px-4 text-slate-300">
                        <span className="font-semibold block text-white">
                          {c.target_country === "GB" ? "United Kingdom" : "India"}
                        </span>
                        <span className="text-[11px] text-slate-400">
                          {c.tax_regime} ({c.tax_rate_percent}%)
                          {c.sac_code ? ` [${c.sac_code}]` : ""}
                        </span>
                      </td>

                      <td className="py-3.5 px-4">
                        <span className="font-bold text-white block">
                          {c.currency} {(c.total_budget_minor / 100).toFixed(2)}
                        </span>
                        <span className="text-[11px] text-slate-400">
                          {c.duration_days} Days ({c.package_code})
                        </span>
                      </td>

                      <td className="py-3.5 px-4">
                        <span className="font-semibold text-white">{c.listings_count} item(s)</span>
                        <span className="text-[11px] text-slate-400 block">{c.campaign_type_display}</span>
                      </td>

                      <td className="py-3.5 px-4">{getStatusBadge(c.status)}</td>

                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {/* Inspect Detail */}
                          <button
                            onClick={() => setInspectCampaign(c)}
                            className="px-2.5 py-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 text-xs font-semibold transition"
                          >
                            Inspect
                          </button>

                          {/* Review if Pending */}
                          {c.status === "PENDING_APPROVAL" && (
                            <button
                              onClick={() => {
                                if (isOwnCampaign) {
                                  alert("Self-approval guard: You cannot review or approve your own advertising campaigns.");
                                  return;
                                }
                                setReviewCampaign(c);
                                setReviewAction("APPROVE");
                                setRejectionReason("");
                                setApprovalNotes("");
                              }}
                              disabled={isOwnCampaign}
                              className="px-3 py-1.5 rounded-lg bg-amber-400 hover:bg-amber-300 text-slate-950 font-bold text-xs flex items-center gap-1 transition disabled:opacity-40"
                              title={isOwnCampaign ? "Self-approval forbidden" : "Review Campaign"}
                            >
                              <ShieldCheck className="w-3.5 h-3.5" />
                              <span>Review</span>
                            </button>
                          )}

                          {/* Force Pause if Active */}
                          {c.status === "ACTIVE" && (
                            <button
                              onClick={() => handlePauseCampaign(c.id)}
                              className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-amber-400 transition"
                              title="Force Pause Campaign"
                            >
                              <Pause className="w-4 h-4" />
                            </button>
                          )}

                          {/* Force Terminate */}
                          {["ACTIVE", "PAUSED", "SCHEDULED"].includes(c.status) && (
                            <button
                              onClick={() => setTerminateCampaign(c)}
                              className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-rose-400 transition"
                              title="Force Terminate"
                            >
                              <XCircle className="w-4 h-4" />
                            </button>
                          )}
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

      {/* REVIEW DECISION MODAL */}
      {reviewCampaign && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-amber-400/10 border border-amber-400/20 text-amber-400 flex items-center justify-center">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Review Campaign</h3>
                <p className="text-xs text-slate-400">{reviewCampaign.title}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <button
                type="button"
                onClick={() => setReviewAction("APPROVE")}
                className={`p-3 rounded-xl border font-bold flex items-center justify-center gap-2 transition ${
                  reviewAction === "APPROVE"
                    ? "bg-emerald-500/15 border-emerald-500 text-emerald-400"
                    : "bg-slate-950 border-slate-800 text-slate-400 hover:text-white"
                }`}
              >
                <Check className="w-4 h-4" />
                <span>Approve Campaign</span>
              </button>

              <button
                type="button"
                onClick={() => setReviewAction("REJECT")}
                className={`p-3 rounded-xl border font-bold flex items-center justify-center gap-2 transition ${
                  reviewAction === "REJECT"
                    ? "bg-rose-500/15 border-rose-500 text-rose-400"
                    : "bg-slate-950 border-slate-800 text-slate-400 hover:text-white"
                }`}
              >
                <X className="w-4 h-4" />
                <span>Reject Campaign</span>
              </button>
            </div>

            {reviewAction === "APPROVE" ? (
              <div>
                <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-1">
                  Approval Notes (Optional)
                </label>
                <textarea
                  rows={2}
                  placeholder="Verification notes or special terms..."
                  value={approvalNotes}
                  onChange={(e) => setApprovalNotes(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white placeholder-slate-600 focus:outline-none focus:border-emerald-400 text-xs"
                />
              </div>
            ) : (
              <div>
                <label className="block text-[11px] font-semibold uppercase tracking-wider text-rose-400 mb-1">
                  Mandatory Rejection Reason *
                </label>
                <textarea
                  rows={3}
                  placeholder="Detailed policy reason why this campaign cannot be approved..."
                  value={rejectionReason}
                  onChange={(e) => setRejectionReason(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-800 text-white placeholder-slate-600 focus:outline-none focus:border-rose-400 text-xs"
                />
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setReviewCampaign(null)}
                disabled={reviewing}
                className="px-4 py-2 rounded-xl text-slate-400 hover:text-white text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={handleReviewSubmit}
                disabled={reviewing}
                className={`px-5 py-2 rounded-xl font-bold text-xs flex items-center gap-1.5 transition disabled:opacity-50 ${
                  reviewAction === "APPROVE"
                    ? "bg-emerald-500 hover:bg-emerald-400 text-slate-950"
                    : "bg-rose-600 hover:bg-rose-500 text-white"
                }`}
              >
                {reviewing ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <span>{reviewAction === "APPROVE" ? "Confirm Approval" : "Confirm Rejection"}</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* INSPECT DETAIL MODAL */}
      {inspectCampaign && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl flex flex-col max-h-[85vh]">
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/50">
              <div>
                <h3 className="text-base font-bold text-white">{inspectCampaign.title}</h3>
                <p className="text-xs text-slate-400">ID: {inspectCampaign.id}</p>
              </div>
              <button
                onClick={() => setInspectCampaign(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-5 text-xs">
              <div className="grid grid-cols-2 gap-3 p-4 rounded-xl bg-slate-950 border border-slate-800">
                <div>
                  <span className="text-slate-500 block text-[10px] uppercase">Seller Email</span>
                  <span className="font-semibold text-white">{inspectCampaign.seller_email}</span>
                </div>
                <div>
                  <span className="text-slate-500 block text-[10px] uppercase">Dealership / Org</span>
                  <span className="font-semibold text-white">
                    {inspectCampaign.organisation_name || "Independent Seller"}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 block text-[10px] uppercase">Status</span>
                  <div>{getStatusBadge(inspectCampaign.status)}</div>
                </div>
                <div>
                  <span className="text-slate-500 block text-[10px] uppercase">Payment Status</span>
                  <span className="font-semibold text-amber-400">
                    {inspectCampaign.payment_status_display}
                  </span>
                </div>
              </div>

              {/* Statutory Tax Breakdown */}
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                <h4 className="font-bold text-white text-xs uppercase tracking-wider">
                  Commercial Pricing & Tax Computation
                </h4>
                <div className="flex justify-between text-slate-400">
                  <span>Net Advertising Base:</span>
                  <span className="text-white">
                    {inspectCampaign.currency} {(inspectCampaign.net_amount_minor / 100).toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>
                    {inspectCampaign.tax_regime} ({inspectCampaign.tax_rate_percent}%)
                    {inspectCampaign.sac_code ? ` [SAC ${inspectCampaign.sac_code}]` : ""}
                  </span>
                  <span className="text-white">
                    {inspectCampaign.currency} {(inspectCampaign.tax_amount_minor / 100).toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between pt-2 border-t border-slate-800 font-bold text-sm">
                  <span className="text-white">Gross Total:</span>
                  <span className="text-amber-400">
                    {inspectCampaign.currency} {(inspectCampaign.total_budget_minor / 100).toFixed(2)}
                  </span>
                </div>
              </div>

              {/* Sponsored Listings list */}
              <div>
                <h4 className="font-bold text-white text-xs uppercase tracking-wider mb-2">
                  Included Listings ({inspectCampaign.sponsored_listings.length})
                </h4>
                <div className="space-y-1.5 max-h-48 overflow-y-auto">
                  {inspectCampaign.sponsored_listings.map((sl) => (
                    <div
                      key={sl.id}
                      className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between"
                    >
                      <div>
                        <p className="font-semibold text-white">{sl.listing_title}</p>
                        <p className="text-[10px] text-slate-500">
                          {sl.target_type} • Impr: {sl.impression_count} • Clicks: {sl.click_count}
                        </p>
                      </div>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400">
                        {sl.listing_status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {inspectCampaign.rejection_reason && (
                <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs">
                  <strong className="block text-rose-400 mb-0.5">Staff Rejection Reason:</strong>
                  {inspectCampaign.rejection_reason}
                </div>
              )}
            </div>

            <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/50 flex justify-end">
              <button
                onClick={() => setInspectCampaign(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 hover:text-white text-xs font-semibold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
