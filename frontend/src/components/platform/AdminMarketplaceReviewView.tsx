"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  api,
  MarketplaceVehicleListing,
  MarketplacePartListing,
} from "@/lib/api/client";
import {
  CheckCircle2,
  XCircle,
  Car,
  Wrench,
  Building2,
  Eye,
  X,
  RotateCcw,
} from "lucide-react";

export default function AdminMarketplaceReviewView() {
  const [activeQueue, setActiveQueue] = useState<"vehicles" | "parts">("vehicles");
  const [statusFilter, setStatusFilter] = useState<string>("PENDING_APPROVAL");

  // Queues
  const [vehicles, setVehicles] = useState<MarketplaceVehicleListing[]>([]);
  const [parts, setParts] = useState<MarketplacePartListing[]>([]);
  const [loading, setLoading] = useState(false);

  // Inspector & Review Modal
  const [inspectVehicle, setInspectVehicle] = useState<MarketplaceVehicleListing | null>(null);
  const [inspectPart, setInspectPart] = useState<MarketplacePartListing | null>(null);
  const [reviewAction, setReviewAction] = useState<"APPROVE" | "REJECT" | "REQUEST_CHANGES" | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");
  const [adminNotes, setAdminNotes] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const fetchVehicles = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.marketplace.listAdminVehicles(
        statusFilter === "ALL" ? undefined : statusFilter
      );
      setVehicles(data);
    } catch (err) {
      console.error("Failed to load vehicle review queue", err);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  const fetchParts = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.marketplace.listAdminParts(
        statusFilter === "ALL" ? undefined : statusFilter
      );
      setParts(data);
    } catch (err) {
      console.error("Failed to load part review queue", err);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    let ignore = false;
    const loadQueue = async () => {
      try {
        if (activeQueue === "vehicles") {
          const data = await api.marketplace.listAdminVehicles(
            statusFilter === "ALL" ? undefined : statusFilter
          );
          if (!ignore) setVehicles(data);
        } else {
          const data = await api.marketplace.listAdminParts(
            statusFilter === "ALL" ? undefined : statusFilter
          );
          if (!ignore) setParts(data);
        }
      } catch (err) {
        if (!ignore) console.error("Failed to load review queue", err);
      }
    };
    loadQueue();
    return () => {
      ignore = true;
    };
  }, [activeQueue, statusFilter]);

  const handleExecuteReview = async () => {
    if (!reviewAction) return;
    if ((reviewAction === "REJECT" || reviewAction === "REQUEST_CHANGES") && !rejectionReason.trim()) {
      setErrorMessage("Please enter a mandatory rejection / change-request reason.");
      return;
    }

    setActionLoading(true);
    setErrorMessage("");
    try {
      if (inspectVehicle) {
        await api.marketplace.reviewVehicle(inspectVehicle.id, {
          action: reviewAction,
          rejection_reason: rejectionReason,
          admin_notes: adminNotes,
        });
        setSuccessMessage(`Vehicle listing ${reviewAction.toLowerCase()}d successfully.`);
        setInspectVehicle(null);
        fetchVehicles();
      } else if (inspectPart) {
        await api.marketplace.reviewPart(inspectPart.id, {
          action: reviewAction,
          rejection_reason: rejectionReason,
          admin_notes: adminNotes,
        });
        setSuccessMessage(`Spare part listing ${reviewAction.toLowerCase()}d successfully.`);
        setInspectPart(null);
        fetchParts();
      }
      setReviewAction(null);
      setRejectionReason("");
      setAdminNotes("");
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : "Review action failed.");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Alert Banners */}
      {successMessage && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-2xl text-xs font-bold text-emerald-900 flex items-center justify-between">
          <span>{successMessage}</span>
          <button onClick={() => setSuccessMessage("")} className="text-emerald-700 hover:text-emerald-950">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
      {errorMessage && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-2xl text-xs font-bold text-red-900 flex items-center justify-between">
          <span>{errorMessage}</span>
          <button onClick={() => setErrorMessage("")} className="text-red-700 hover:text-red-950">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 text-white flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 text-xs font-bold uppercase tracking-wider border border-amber-500/20">
              Admin Compliance Console
            </span>
            <span className="text-xs text-slate-400">Marketplace Verification Queues</span>
          </div>
          <h2 className="text-2xl font-black text-white">Inventory Moderation & Approval</h2>
          <p className="text-xs text-slate-300 mt-1 max-w-xl">
            Inspect incoming seller vehicles and spare-part submissions. Audit identifiers, evidence, and trading organisations before public marketplace release.
          </p>
        </div>

        {/* Queue Selector */}
        <div className="flex p-1 bg-slate-950/80 rounded-2xl border border-slate-800 self-start md:self-auto">
          <button
            onClick={() => setActiveQueue("vehicles")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              activeQueue === "vehicles"
                ? "bg-amber-500 text-slate-950 shadow-md"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Car className="w-4 h-4" />
            <span>Vehicles Queue ({vehicles.length})</span>
          </button>
          <button
            onClick={() => setActiveQueue("parts")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              activeQueue === "parts"
                ? "bg-amber-500 text-slate-950 shadow-md"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Wrench className="w-4 h-4" />
            <span>Spare Parts Queue ({parts.length})</span>
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center justify-between gap-4 bg-white p-3.5 rounded-2xl border border-slate-200">
        <span className="text-xs font-bold text-slate-600">Filter Queue by Status:</span>
        <div className="flex items-center gap-2 text-xs">
          {["PENDING_APPROVAL", "APPROVED", "REJECTED", "CHANGES_REQUESTED", "ALL"].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-3 py-1.5 rounded-xl font-bold whitespace-nowrap transition-colors ${
                statusFilter === st
                  ? "bg-slate-900 text-white"
                  : "bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200"
              }`}
            >
              {st === "PENDING_APPROVAL"
                ? "Pending Approval"
                : st === "ALL"
                ? "All Records"
                : st.replace("_", " ")}
            </button>
          ))}
        </div>
      </div>

      {/* =========================================================================
          QUEUE: VEHICLES
      ========================================================================= */}
      {activeQueue === "vehicles" && (
        <div>
          {loading ? (
            <div className="py-20 text-center">
              <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              <p className="text-xs text-slate-500 font-medium">Scanning vehicle review queue...</p>
            </div>
          ) : vehicles.length === 0 ? (
            <div className="bg-white rounded-3xl p-12 text-center border border-slate-200 space-y-2">
              <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
              <h3 className="text-base font-bold text-slate-900">Vehicle Moderation Queue Clear</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No submissions require review under the selected filter.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {vehicles.map((v) => (
                <div
                  key={v.id}
                  className="bg-white rounded-3xl p-5 border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] font-bold text-amber-600">
                        {v.year} · {v.make_name} {v.model_name}
                      </span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700">
                        {v.status}
                      </span>
                    </div>
                    <h4 className="text-base font-black text-slate-950">{v.title}</h4>
                    <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                      <span>Seller: <strong className="text-slate-800">{v.seller_name}</strong></span>
                      {v.organisation_name && (
                        <span className="flex items-center gap-1 text-slate-700">
                          <Building2 className="w-3.5 h-3.5 text-slate-400" />
                          <span>{v.organisation_name}</span>
                        </span>
                      )}
                      <span>Mileage: {v.mileage.toLocaleString()} mi</span>
                      <span className="font-mono text-[10px] bg-slate-100 px-1 rounded">
                        VIN: {v.masked_vin}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 self-end md:self-center">
                    <div className="text-right">
                      <span className="text-xs text-slate-400">Asking Price</span>
                      <p className="text-lg font-black text-slate-950">
                        £{Number(v.price).toLocaleString()}
                      </p>
                    </div>

                    <button
                      onClick={() => {
                        setInspectVehicle(v);
                        setInspectPart(null);
                        setReviewAction(null);
                        setRejectionReason("");
                      }}
                      className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors flex items-center gap-1.5"
                    >
                      <Eye className="w-3.5 h-3.5 text-amber-400" />
                      <span>Review Submission</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          QUEUE: SPARE PARTS
      ========================================================================= */}
      {activeQueue === "parts" && (
        <div>
          {loading ? (
            <div className="py-20 text-center">
              <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              <p className="text-xs text-slate-500 font-medium">Scanning spare parts review queue...</p>
            </div>
          ) : parts.length === 0 ? (
            <div className="bg-white rounded-3xl p-12 text-center border border-slate-200 space-y-2">
              <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
              <h3 className="text-base font-bold text-slate-900">Spare Parts Review Queue Clear</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No parts submissions pending review under the current filter.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {parts.map((p) => (
                <div
                  key={p.id}
                  className="bg-white rounded-3xl p-5 border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] font-bold text-slate-700 bg-slate-100 px-2 py-0.5 rounded-full">
                        {p.brand}
                      </span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700">
                        {p.status}
                      </span>
                    </div>
                    <h4 className="text-base font-black text-slate-950">{p.name}</h4>
                    <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                      <span className="font-mono text-[10px]">MPN: {p.mpn}</span>
                      <span>Seller: <strong className="text-slate-800">{p.seller_name}</strong></span>
                      {p.organisation_name && (
                        <span className="flex items-center gap-1 text-slate-700">
                          <Building2 className="w-3.5 h-3.5 text-slate-400" />
                          <span>{p.organisation_name}</span>
                        </span>
                      )}
                      <span>Stock: {p.stock_quantity} units</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 self-end md:self-center">
                    <div className="text-right">
                      <span className="text-xs text-slate-400">Retail Price</span>
                      <p className="text-lg font-black text-slate-950">
                        £{Number(p.price).toFixed(2)}
                      </p>
                    </div>

                    <button
                      onClick={() => {
                        setInspectPart(p);
                        setInspectVehicle(null);
                        setReviewAction(null);
                        setRejectionReason("");
                      }}
                      className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors flex items-center gap-1.5"
                    >
                      <Eye className="w-3.5 h-3.5 text-amber-400" />
                      <span>Review Submission</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          MODAL: ADMIN REVIEW INSPECTOR
      ========================================================================= */}
      {(inspectVehicle || inspectPart) && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 shadow-2xl max-h-[90vh] overflow-y-auto space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <span className="text-[10px] font-bold text-amber-600 uppercase tracking-wider bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                  Compliance Audit & Verification
                </span>
                <h3 className="text-lg font-black text-slate-900 mt-1">
                  {inspectVehicle ? inspectVehicle.title : inspectPart?.name}
                </h3>
              </div>
              <button
                onClick={() => {
                  setInspectVehicle(null);
                  setInspectPart(null);
                  setReviewAction(null);
                }}
                className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Item Details */}
            {inspectVehicle && (
              <div className="space-y-4 text-xs">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Price</span>
                    <p className="font-bold text-slate-900">£{Number(inspectVehicle.price).toLocaleString()}</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Year / Transmission</span>
                    <p className="font-bold text-slate-900">{inspectVehicle.year} · {inspectVehicle.transmission}</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Mileage</span>
                    <p className="font-bold text-slate-900">{inspectVehicle.mileage.toLocaleString()} mi</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Seller</span>
                    <p className="font-bold text-slate-900 truncate">{inspectVehicle.seller_name}</p>
                  </div>
                </div>

                <div className="p-3 bg-slate-50 rounded-2xl border border-slate-200 space-y-1">
                  <span className="font-bold text-slate-800">Verified Identifiers</span>
                  <div className="flex flex-wrap gap-4 text-slate-600 text-[11px]">
                    <span>Masked VIN: <strong className="font-mono">{inspectVehicle.masked_vin}</strong></span>
                    <span>Plate: <strong className="font-mono">{inspectVehicle.masked_registration}</strong></span>
                    <span>Organisation: <strong>{inspectVehicle.organisation_name || "Personal"}</strong></span>
                  </div>
                </div>

                {inspectVehicle.description && (
                  <div>
                    <span className="font-bold text-slate-800">Seller Description</span>
                    <p className="text-slate-600 p-3 bg-slate-50 rounded-xl mt-1">{inspectVehicle.description}</p>
                  </div>
                )}
              </div>
            )}

            {inspectPart && (
              <div className="space-y-4 text-xs">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Price</span>
                    <p className="font-bold text-slate-900">£{Number(inspectPart.price).toFixed(2)}</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Brand / MPN</span>
                    <p className="font-bold text-slate-900">{inspectPart.brand} ({inspectPart.mpn})</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Stock</span>
                    <p className="font-bold text-slate-900">{inspectPart.stock_quantity} units</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Seller</span>
                    <p className="font-bold text-slate-900 truncate">{inspectPart.seller_name}</p>
                  </div>
                </div>

                {inspectPart.oem_numbers && inspectPart.oem_numbers.length > 0 && (
                  <div>
                    <span className="font-bold text-slate-800">OEM Cross-References</span>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {inspectPart.oem_numbers.map((oem, idx) => (
                        <span key={idx} className="font-mono bg-slate-100 px-2 py-0.5 rounded text-[11px]">
                          {oem}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Moderation Actions */}
            <div className="pt-4 border-t border-slate-200 space-y-3">
              <h5 className="text-xs font-bold text-slate-800">Compliance Decision</h5>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setReviewAction("APPROVE")}
                  className={`flex-1 py-2 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
                    reviewAction === "APPROVE"
                      ? "bg-emerald-600 text-white shadow"
                      : "bg-emerald-50 text-emerald-800 hover:bg-emerald-100 border border-emerald-200"
                  }`}
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Approve & Publish</span>
                </button>

                <button
                  type="button"
                  onClick={() => setReviewAction("REQUEST_CHANGES")}
                  className={`flex-1 py-2 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
                    reviewAction === "REQUEST_CHANGES"
                      ? "bg-orange-600 text-white shadow"
                      : "bg-orange-50 text-orange-800 hover:bg-orange-100 border border-orange-200"
                  }`}
                >
                  <RotateCcw className="w-4 h-4" />
                  <span>Request Changes</span>
                </button>

                <button
                  type="button"
                  onClick={() => setReviewAction("REJECT")}
                  className={`flex-1 py-2 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
                    reviewAction === "REJECT"
                      ? "bg-red-600 text-white shadow"
                      : "bg-red-50 text-red-800 hover:bg-red-100 border border-red-200"
                  }`}
                >
                  <XCircle className="w-4 h-4" />
                  <span>Reject</span>
                </button>
              </div>

              {(reviewAction === "REJECT" || reviewAction === "REQUEST_CHANGES") && (
                <div className="space-y-1 text-xs">
                  <label className="block text-red-900 font-bold">
                    Mandatory Reason for {reviewAction === "REJECT" ? "Rejection" : "Changes"} *
                  </label>
                  <textarea
                    rows={2}
                    value={rejectionReason}
                    onChange={(e) => setRejectionReason(e.target.value)}
                    placeholder="Provide specific feedback so the seller can correct the submission..."
                    className="w-full px-3 py-2 bg-red-50/50 border border-red-200 rounded-xl focus:outline-none text-xs"
                  />
                </div>
              )}

              <div className="space-y-1 text-xs">
                <label className="block text-slate-700 font-bold">Internal Audit Notes (Optional)</label>
                <input
                  type="text"
                  value={adminNotes}
                  onChange={(e) => setAdminNotes(e.target.value)}
                  placeholder="Private internal notes for compliance record..."
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none text-xs"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setInspectVehicle(null);
                    setInspectPart(null);
                    setReviewAction(null);
                  }}
                  className="px-4 py-2 text-slate-600 text-xs font-bold"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleExecuteReview}
                  disabled={!reviewAction || actionLoading}
                  className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors disabled:opacity-40"
                >
                  Confirm Decision
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
