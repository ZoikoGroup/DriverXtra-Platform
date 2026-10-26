"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  api,
  resolveMediaUrl,
  MarketplaceVehicleListing,
  MarketplacePartListing,
  VehicleCatalogueApplication,
  CataloguePhotoProposal,
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
  AlertTriangle,
  FilePlus,
  Camera,
} from "lucide-react";

interface AdminMarketplaceReviewViewProps {
  initialVehicleId?: string;
  initialPartId?: string;
}

export default function AdminMarketplaceReviewView({
  initialVehicleId,
  initialPartId,
}: AdminMarketplaceReviewViewProps = {}) {
  const [activeQueue, setActiveQueue] = useState<"vehicles" | "parts" | "applications" | "photo_proposals">("vehicles");
  const [statusFilter, setStatusFilter] = useState<string>("PENDING_APPROVAL");

  // Queues
  const [vehicles, setVehicles] = useState<MarketplaceVehicleListing[]>([]);
  const [parts, setParts] = useState<MarketplacePartListing[]>([]);
  const [applications, setApplications] = useState<VehicleCatalogueApplication[]>([]);
  const [photoProposals, setPhotoProposals] = useState<CataloguePhotoProposal[]>([]);
  const [loading, setLoading] = useState(false);

  // Inspector & Review Modal
  const [inspectVehicle, setInspectVehicle] = useState<MarketplaceVehicleListing | null>(null);
  const [inspectPart, setInspectPart] = useState<MarketplacePartListing | null>(null);
  const [inspectApplication, setInspectApplication] = useState<VehicleCatalogueApplication | null>(null);
  const [inspectPhotoProposal, setInspectPhotoProposal] = useState<CataloguePhotoProposal | null>(null);
  const [activePhotoIndex, setActivePhotoIndex] = useState(0);
  const [reviewAction, setReviewAction] = useState<"APPROVE" | "REJECT" | "REQUEST_CHANGES" | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");
  const [adminNotes, setAdminNotes] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [modalError, setModalError] = useState("");

  const resolveCatalogueStatus = (st: string) => {
    if (st === "ALL") return undefined;
    if (st === "PENDING_APPROVAL") return "PENDING";
    return st;
  };

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

  const fetchApplications = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.catalogue.listApplications(resolveCatalogueStatus(statusFilter));
      setApplications(data);
    } catch (err) {
      console.error("Failed to load vehicle catalogue applications queue", err);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  const fetchPhotoProposals = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.catalogue.listPhotoProposals(resolveCatalogueStatus(statusFilter));
      setPhotoProposals(data);
    } catch (err) {
      console.error("Failed to load catalogue photo proposals queue", err);
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
        } else if (activeQueue === "parts") {
          const data = await api.marketplace.listAdminParts(
            statusFilter === "ALL" ? undefined : statusFilter
          );
          if (!ignore) setParts(data);
        } else if (activeQueue === "applications") {
          const data = await api.catalogue.listApplications(resolveCatalogueStatus(statusFilter));
          if (!ignore) setApplications(data);
        } else if (activeQueue === "photo_proposals") {
          const data = await api.catalogue.listPhotoProposals(resolveCatalogueStatus(statusFilter));
          if (!ignore) setPhotoProposals(data);
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

  // Handle external navigation (from Global Search) to a specific admin vehicle review item
  useEffect(() => {
    if (!initialVehicleId) return;
    api.marketplace
      .listAdminVehicles()
      .then((list) => {
        setActiveQueue("vehicles");
        const match = list.find((v) => v.id === initialVehicleId);
        if (match) setInspectVehicle(match);
      })
      .catch(console.error);
  }, [initialVehicleId]);

  // Handle external navigation (from Global Search) to a specific admin part review item
  useEffect(() => {
    if (!initialPartId) return;
    api.marketplace
      .listAdminParts()
      .then((list) => {
        setActiveQueue("parts");
        const match = list.find((p) => p.id === initialPartId);
        if (match) setInspectPart(match);
      })
      .catch(console.error);
  }, [initialPartId]);

  const handleExecuteReview = async () => {
    if (!reviewAction) return;
    if (inspectPart && reviewAction === "APPROVE" && (inspectPart.fitment_summary?.conflict ?? 0) > 0) {
      setModalError("Cannot approve listing with conflicting vehicle fitments. Request changes or reject.");
      return;
    }
    if ((reviewAction === "REJECT" || reviewAction === "REQUEST_CHANGES") && !rejectionReason.trim()) {
      setModalError("Please enter a mandatory rejection / change-request reason.");
      return;
    }

    setActionLoading(true);
    setModalError("");
    setErrorMessage("");
    try {
      if (inspectVehicle) {
        await api.marketplace.reviewVehicle(inspectVehicle.id, {
          action: reviewAction,
          rejection_reason: rejectionReason.trim(),
          admin_notes: adminNotes.trim(),
        });
        setSuccessMessage(`Vehicle listing ${reviewAction.toLowerCase()}d successfully.`);
        setInspectVehicle(null);
        fetchVehicles();
      } else if (inspectPart) {
        await api.marketplace.reviewPart(inspectPart.id, {
          action: reviewAction,
          rejection_reason: rejectionReason.trim(),
          admin_notes: adminNotes.trim(),
        });
        setSuccessMessage(`Spare part listing ${reviewAction.toLowerCase()}d successfully.`);
        setInspectPart(null);
        fetchParts();
      } else if (inspectApplication) {
        await api.catalogue.reviewApplication(inspectApplication.id, {
          action: reviewAction,
          rejection_reason: rejectionReason.trim(),
          admin_notes: adminNotes.trim(),
        });
        setSuccessMessage(`Vehicle catalogue application ${reviewAction.toLowerCase()}d successfully.`);
        setInspectApplication(null);
        fetchApplications();
      } else if (inspectPhotoProposal) {
        await api.catalogue.reviewPhotoProposal(inspectPhotoProposal.id, {
          action: reviewAction === "REQUEST_CHANGES" ? "REJECT" : reviewAction,
          rejection_reason: rejectionReason.trim(),
          admin_notes: adminNotes.trim(),
        });
        setSuccessMessage(`Catalogue photo proposal ${reviewAction.toLowerCase()}d successfully.`);
        setInspectPhotoProposal(null);
        fetchPhotoProposals();
      }
      setReviewAction(null);
      setRejectionReason("");
      setAdminNotes("");
    } catch (err: unknown) {
      setModalError(err instanceof Error ? err.message : "Review action failed.");
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
        <div className="flex flex-wrap p-1 bg-slate-950/80 rounded-2xl border border-slate-800 self-start md:self-auto gap-1">
          <button
            onClick={() => setActiveQueue("vehicles")}
            className={`flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-bold transition-all ${
              activeQueue === "vehicles"
                ? "bg-amber-500 text-slate-950 shadow-md"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Car className="w-3.5 h-3.5" />
            <span>Vehicles ({vehicles.length})</span>
          </button>
          <button
            onClick={() => setActiveQueue("parts")}
            className={`flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-bold transition-all ${
              activeQueue === "parts"
                ? "bg-amber-500 text-slate-950 shadow-md"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Wrench className="w-3.5 h-3.5" />
            <span>Spare Parts ({parts.length})</span>
          </button>
          <button
            onClick={() => setActiveQueue("applications")}
            className={`flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-bold transition-all ${
              activeQueue === "applications"
                ? "bg-amber-500 text-slate-950 shadow-md"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <FilePlus className="w-3.5 h-3.5" />
            <span>Applications ({applications.length})</span>
          </button>
          <button
            onClick={() => setActiveQueue("photo_proposals")}
            className={`flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-bold transition-all ${
              activeQueue === "photo_proposals"
                ? "bg-amber-500 text-slate-950 shadow-md"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Camera className="w-3.5 h-3.5" />
            <span>Photo Proposals ({photoProposals.length})</span>
          </button>
        </div>
      </div>

      {/* Filter Tabs & Refresh */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white p-3.5 rounded-2xl border border-slate-200">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-slate-600">Filter Queue:</span>
          <button
            onClick={() => {
              if (activeQueue === "vehicles") fetchVehicles();
              else if (activeQueue === "parts") fetchParts();
              else if (activeQueue === "applications") fetchApplications();
              else if (activeQueue === "photo_proposals") fetchPhotoProposals();
            }}
            disabled={loading}
            className="px-3 py-1 rounded-xl font-bold bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs transition-colors flex items-center gap-1"
            title="Refresh review queue"
          >
            <RotateCcw className={`w-3 h-3 ${loading ? "animate-spin text-amber-500" : ""}`} />
            <span>Refresh Queue</span>
          </button>
        </div>
        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto text-xs pb-1 sm:pb-0">
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
                      {p.fitment_summary && p.fitment_summary.conflict > 0 && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-300 flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3 text-rose-600" />
                          <span>{p.fitment_summary.conflict} Fitment Conflict</span>
                        </span>
                      )}
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
          QUEUE: VEHICLE CATALOGUE APPLICATIONS
      ========================================================================= */}
      {activeQueue === "applications" && (
        <div>
          {loading ? (
            <div className="py-20 text-center">
              <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              <p className="text-xs text-slate-500 font-medium">Scanning vehicle applications queue...</p>
            </div>
          ) : applications.length === 0 ? (
            <div className="bg-white rounded-3xl p-12 text-center border border-slate-200 space-y-2">
              <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
              <h3 className="text-base font-bold text-slate-900">Vehicle Applications Queue Clear</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No new vehicle catalogue applications pending review under the current filter.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {applications.map((app) => (
                <div
                  key={app.id}
                  className="bg-white rounded-3xl p-5 border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4"
                >
                  <div className="flex items-start gap-4">
                    <div className="w-20 h-16 rounded-xl bg-slate-900 overflow-hidden flex-shrink-0 flex items-center justify-center">
                      {app.primary_image_url ? (
                        <img src={resolveMediaUrl(app.primary_image_url)} alt={app.model_name} className="w-full h-full object-cover" />
                      ) : (
                        <Car className="w-6 h-6 text-slate-700" />
                      )}
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                          {app.make_name || "Custom Make"}
                        </span>
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700">
                          {app.status}
                        </span>
                      </div>
                      <h4 className="text-base font-black text-slate-950">
                        {app.model_name}
                        {app.variant_name && <span className="text-slate-500 font-normal"> · {app.variant_name}</span>}
                      </h4>
                      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                        <span>Applicant: <strong className="text-slate-800">{app.seller_name}</strong></span>
                        <span>Years: {app.year_start} – {app.year_end || "Present"}</span>
                        {app.fuel_type && <span>Fuel: {app.fuel_type}</span>}
                        {app.transmission && <span>Trans: {app.transmission}</span>}
                        <span>Submitted: {new Date(app.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 self-end md:self-center">
                    <button
                      onClick={() => {
                        setInspectApplication(app);
                        setInspectVehicle(null);
                        setInspectPart(null);
                        setInspectPhotoProposal(null);
                        setActivePhotoIndex(0);
                        setReviewAction(null);
                        setRejectionReason("");
                      }}
                      className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors flex items-center gap-1.5"
                    >
                      <Eye className="w-3.5 h-3.5 text-amber-400" />
                      <span>Review Application</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          QUEUE: CATALOGUE PHOTO PROPOSALS
      ========================================================================= */}
      {activeQueue === "photo_proposals" && (
        <div>
          {loading ? (
            <div className="py-20 text-center">
              <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              <p className="text-xs text-slate-500 font-medium">Scanning catalogue photo proposals queue...</p>
            </div>
          ) : photoProposals.length === 0 ? (
            <div className="bg-white rounded-3xl p-12 text-center border border-slate-200 space-y-2">
              <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
              <h3 className="text-base font-bold text-slate-900">Photo Proposals Queue Clear</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No catalogue photo proposals pending moderation under the current filter.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {photoProposals.map((prop) => (
                <div
                  key={prop.id}
                  className="bg-white rounded-3xl p-5 border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4"
                >
                  <div className="flex items-start gap-4">
                    <div className="w-20 h-16 rounded-xl bg-slate-900 overflow-hidden flex-shrink-0 flex items-center justify-center border border-amber-400">
                      <img src={resolveMediaUrl(prop.proposed_image_url)} alt="Proposed" className="w-full h-full object-cover" />
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] font-bold text-slate-700 bg-slate-100 px-2 py-0.5 rounded-full">
                          {prop.make_name || "Catalogue Model"}
                        </span>
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700">
                          {prop.status}
                        </span>
                      </div>
                      <h4 className="text-base font-black text-slate-950">{prop.model_name}</h4>
                      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                        <span>Proposed by: <strong className="text-slate-800">{prop.seller_name}</strong></span>
                        <span>Submitted: {new Date(prop.created_at).toLocaleDateString()}</span>
                        {prop.notes && <span className="italic truncate max-w-xs">&quot;{prop.notes}&quot;</span>}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 self-end md:self-center">
                    <button
                      onClick={() => {
                        setInspectPhotoProposal(prop);
                        setInspectVehicle(null);
                        setInspectPart(null);
                        setInspectApplication(null);
                        setReviewAction(null);
                        setRejectionReason("");
                      }}
                      className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors flex items-center gap-1.5"
                    >
                      <Eye className="w-3.5 h-3.5 text-amber-400" />
                      <span>Review Proposal</span>
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
      {(inspectVehicle || inspectPart || inspectApplication || inspectPhotoProposal) && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 shadow-2xl max-h-[90vh] overflow-y-auto space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <span className="text-[10px] font-bold text-amber-600 uppercase tracking-wider bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                  {inspectApplication
                    ? "Catalogue Vehicle Application Review"
                    : inspectPhotoProposal
                    ? "Catalogue Official Photo Review"
                    : "Marketplace Compliance Audit"}
                </span>
                <h3 className="text-lg font-black text-slate-900 mt-1">
                  {inspectVehicle
                    ? inspectVehicle.title
                    : inspectPart
                    ? inspectPart.name
                    : inspectApplication
                    ? `${inspectApplication.make_name} ${inspectApplication.model_name}`
                    : `${inspectPhotoProposal?.make_name} ${inspectPhotoProposal?.model_name}`}
                </h3>
              </div>
              <button
                onClick={() => {
                  setInspectVehicle(null);
                  setInspectPart(null);
                  setInspectApplication(null);
                  setInspectPhotoProposal(null);
                  setReviewAction(null);
                }}
                className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Error Banner */}
            {modalError && (
              <div className="p-3.5 bg-red-50 border border-red-200 rounded-2xl text-xs font-bold text-red-900 flex items-center justify-between">
                <span>{modalError}</span>
                <button
                  type="button"
                  onClick={() => setModalError("")}
                  className="text-red-700 hover:text-red-950 p-1"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            {/* Item Details: Vehicle Listing */}
            {inspectVehicle && (
              <div className="space-y-4 text-xs">
                {/* Images Gallery */}
                {(() => {
                  const allImages = Array.from(
                    new Set(
                      [inspectVehicle.primary_image_url, ...(inspectVehicle.images || [])].filter((u): u is string =>
                        Boolean(u && u.trim())
                      )
                    )
                  );
                  const currentImage = allImages[activePhotoIndex] || allImages[0];
                  return allImages.length > 0 ? (
                    <div className="space-y-2">
                      <div className="rounded-2xl overflow-hidden h-64 bg-slate-950 relative flex items-center justify-center border border-slate-200">
                        <img
                          src={resolveMediaUrl(currentImage)}
                          alt={inspectVehicle.title}
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            (e.target as HTMLElement).style.display = "none";
                          }}
                        />
                        <div className="absolute top-2 right-2 bg-black/70 backdrop-blur-sm text-white px-2 py-0.5 rounded text-[10px] font-bold">
                          {activePhotoIndex + 1} of {allImages.length}
                          {currentImage === inspectVehicle.primary_image_url && " · Primary Image"}
                        </div>
                      </div>
                      {allImages.length > 1 && (
                        <div className="flex items-center gap-2 overflow-x-auto pb-1">
                          {allImages.map((img, idx) => (
                            <button
                              key={idx}
                              type="button"
                              onClick={() => setActivePhotoIndex(idx)}
                              className={`w-16 h-12 rounded-xl overflow-hidden flex-shrink-0 border-2 transition-all relative ${
                                activePhotoIndex === idx
                                  ? "border-amber-500 ring-2 ring-amber-500/20"
                                  : "border-slate-200 opacity-70 hover:opacity-100"
                              }`}
                            >
                              <img src={resolveMediaUrl(img)} alt={`Thumb ${idx + 1}`} className="w-full h-full object-cover" />
                              {img === inspectVehicle.primary_image_url && (
                                <span className="absolute bottom-0 inset-x-0 bg-black/70 text-[7px] text-amber-300 font-bold text-center">
                                  Primary
                                </span>
                              )}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="rounded-2xl p-6 bg-slate-100 border border-slate-200 text-center text-slate-400">
                      <Car className="w-10 h-10 mx-auto mb-1 text-slate-300" />
                      <span>No images uploaded for this vehicle</span>
                    </div>
                  );
                })()}

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Asking Price</span>
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
                    <span className="text-slate-500">Status</span>
                    <p className="font-bold text-slate-900">{inspectVehicle.status}</p>
                  </div>
                </div>

                <div className="p-3 bg-slate-50 rounded-2xl border border-slate-200 space-y-1">
                  <span className="font-bold text-slate-800">Verified Identifiers & Ownership</span>
                  <div className="flex flex-wrap gap-4 text-slate-600 text-[11px]">
                    <span>Seller: <strong className="text-slate-900">{inspectVehicle.seller_name}</strong></span>
                    <span>Organisation: <strong className="text-slate-900">{inspectVehicle.organisation_name || "Personal Trading"}</strong></span>
                    <span>Masked VIN: <strong className="font-mono">{inspectVehicle.masked_vin}</strong></span>
                    <span>Plate: <strong className="font-mono">{inspectVehicle.masked_registration}</strong></span>
                    <span>Location: <strong>{inspectVehicle.location_city || "N/A"}, {inspectVehicle.location_postcode || ""}</strong></span>
                  </div>
                </div>

                {inspectVehicle.reviewed_at && (
                  <div className="p-3 bg-slate-50 rounded-2xl border border-slate-200 text-[11px] text-slate-600">
                    <span>Review History: <strong>Reviewed by {inspectVehicle.reviewed_by_name || "Platform Admin"} on {new Date(inspectVehicle.reviewed_at).toLocaleDateString()}</strong></span>
                    {inspectVehicle.rejection_reason && (
                      <p className="text-red-700 mt-1">Previous Reason: {inspectVehicle.rejection_reason}</p>
                    )}
                  </div>
                )}

                {inspectVehicle.description && (
                  <div>
                    <span className="font-bold text-slate-800">Seller Description</span>
                    <p className="text-slate-600 p-3 bg-slate-50 rounded-xl mt-1">{inspectVehicle.description}</p>
                  </div>
                )}
              </div>
            )}

            {/* Item Details: Spare Part */}
            {inspectPart && (
              <div className="space-y-4 text-xs">
                {/* Images Gallery */}
                {(() => {
                  const allImages = Array.from(
                    new Set(
                      [inspectPart.primary_image_url, ...(inspectPart.images || [])].filter((u): u is string =>
                        Boolean(u && u.trim())
                      )
                    )
                  );
                  const currentImage = allImages[activePhotoIndex] || allImages[0];
                  return allImages.length > 0 ? (
                    <div className="space-y-2">
                      <div className="rounded-2xl overflow-hidden h-64 bg-slate-950 relative flex items-center justify-center border border-slate-200">
                        <img
                          src={resolveMediaUrl(currentImage)}
                          alt={inspectPart.name}
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            (e.target as HTMLElement).style.display = "none";
                          }}
                        />
                        <div className="absolute top-2 right-2 bg-black/70 backdrop-blur-sm text-white px-2 py-0.5 rounded text-[10px] font-bold">
                          {activePhotoIndex + 1} of {allImages.length}
                          {currentImage === inspectPart.primary_image_url && " · Primary Image"}
                        </div>
                      </div>
                      {allImages.length > 1 && (
                        <div className="flex items-center gap-2 overflow-x-auto pb-1">
                          {allImages.map((img, idx) => (
                            <button
                              key={idx}
                              type="button"
                              onClick={() => setActivePhotoIndex(idx)}
                              className={`w-16 h-12 rounded-xl overflow-hidden flex-shrink-0 border-2 transition-all relative ${
                                activePhotoIndex === idx
                                  ? "border-amber-500 ring-2 ring-amber-500/20"
                                  : "border-slate-200 opacity-70 hover:opacity-100"
                              }`}
                            >
                              <img src={resolveMediaUrl(img)} alt={`Thumb ${idx + 1}`} className="w-full h-full object-cover" />
                              {img === inspectPart.primary_image_url && (
                                <span className="absolute bottom-0 inset-x-0 bg-black/70 text-[7px] text-amber-300 font-bold text-center">
                                  Primary
                                </span>
                              )}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="rounded-2xl p-6 bg-slate-100 border border-slate-200 text-center text-slate-400">
                      <Wrench className="w-10 h-10 mx-auto mb-1 text-slate-300" />
                      <span>No images uploaded for this spare part</span>
                    </div>
                  );
                })()}

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Retail Price</span>
                    <div className="flex items-baseline gap-1.5 mt-0.5">
                      {inspectPart.compare_at_price && Number(inspectPart.compare_at_price) > Number(inspectPart.price) && (
                        <span className="text-xs text-slate-400 line-through">
                          £{Number(inspectPart.compare_at_price).toFixed(2)}
                        </span>
                      )}
                      <p className="font-bold text-slate-900">£{Number(inspectPart.price).toFixed(2)}</p>
                    </div>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Brand / MPN</span>
                    <p className="font-bold text-slate-900">{inspectPart.brand} ({inspectPart.mpn})</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Stock Quantity</span>
                    <p className="font-bold text-slate-900">{inspectPart.stock_quantity} units</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Status</span>
                    <p className="font-bold text-slate-900">{inspectPart.status}</p>
                  </div>
                </div>

                {inspectPart.price_flags && (
                  <div className="p-3.5 rounded-2xl border text-xs space-y-1.5 transition-colors">
                    {inspectPart.price_flags.flag === "OUTLIER_VS_MEDIAN" ? (
                      <div className="flex items-start gap-2.5 text-amber-900 bg-amber-50 p-3 rounded-xl border border-amber-300">
                        <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                        <div>
                          <span className="font-bold block">Advisory Flag: Potential Price Outlier (vs Catalogue Median)</span>
                          <p className="text-[11px] text-amber-800 leading-relaxed mt-0.5">
                            This listing price (£{Number(inspectPart.price).toFixed(2)}) deviates by{" "}
                            <strong>{Math.round(Number(inspectPart.price_flags.deviation ?? 0) * 100)}%</strong> from the
                            median of comparable listings (£{Number(inspectPart.price_flags.median).toFixed(2)}) across{" "}
                            {inspectPart.price_flags.comparable_count} active comparable offers.
                          </p>
                        </div>
                      </div>
                    ) : inspectPart.price_flags.flag === "INSUFFICIENT_COMPARABLES" ? (
                      <div className="flex items-center gap-2 text-slate-700 bg-slate-50 p-2.5 rounded-xl border border-slate-200">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500 bg-slate-200 px-2 py-0.5 rounded">
                          Benchmark
                        </span>
                        <span className="text-[11px]">
                          Insufficient comparables ({inspectPart.price_flags.comparable_count} found).
                        </span>
                      </div>
                    ) : null}
                  </div>
                )}

                <div className="p-3 bg-slate-50 rounded-2xl border border-slate-200 space-y-1">
                  <span className="font-bold text-slate-800">Ownership & Category</span>
                  <div className="flex flex-wrap gap-4 text-slate-600 text-[11px]">
                    <span>Seller: <strong className="text-slate-900">{inspectPart.seller_name}</strong></span>
                    <span>Organisation: <strong className="text-slate-900">{inspectPart.organisation_name || "Personal Trading"}</strong></span>
                    {inspectPart.catalogue_part_name && (
                      <span>Catalogue Part: <strong className="text-amber-800">{inspectPart.catalogue_part_name}</strong></span>
                    )}
                    <span>Condition: <strong>{inspectPart.condition}</strong></span>
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

                {/* Fitment Verification */}
                <div className="p-3.5 bg-slate-50 rounded-2xl border border-slate-200 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-800 text-xs flex items-center gap-1.5">
                      <Wrench className="w-3.5 h-3.5 text-slate-600" />
                      <span>Catalogue Fitment Verification</span>
                    </span>
                    {inspectPart.fitment_summary && (
                      <div className="flex items-center gap-1.5">
                        {inspectPart.fitment_summary.conflict > 0 && (
                          <span className="px-2 py-0.5 rounded-full bg-rose-100 text-rose-800 text-[10px] font-bold border border-rose-300 flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3 text-rose-600" />
                            <span>{inspectPart.fitment_summary.conflict} Conflict</span>
                          </span>
                        )}
                        {inspectPart.fitment_summary.verified > 0 && (
                          <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 text-[10px] font-bold border border-emerald-200">
                            {inspectPart.fitment_summary.verified} Verified
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Item Details: Vehicle Catalogue Application */}
            {inspectApplication && (
              <div className="space-y-4 text-xs">
                {/* Images Gallery */}
                {(() => {
                  const allImages = Array.from(
                    new Set(
                      [inspectApplication.primary_image_url, ...(inspectApplication.images || [])].filter((u): u is string =>
                        Boolean(u && u.trim())
                      )
                    )
                  );
                  const currentImage = allImages[activePhotoIndex] || allImages[0];
                  return allImages.length > 0 ? (
                    <div className="space-y-2">
                      <div className="rounded-2xl overflow-hidden h-64 bg-slate-950 relative flex items-center justify-center border border-slate-200">
                        <img
                          src={resolveMediaUrl(currentImage)}
                          alt={inspectApplication.model_name}
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            (e.target as HTMLElement).style.display = "none";
                          }}
                        />
                        <div className="absolute top-2 right-2 bg-black/70 backdrop-blur-sm text-white px-2 py-0.5 rounded text-[10px] font-bold">
                          {activePhotoIndex + 1} of {allImages.length}
                          {currentImage === inspectApplication.primary_image_url && " · Primary Image"}
                        </div>
                      </div>
                      {allImages.length > 1 && (
                        <div className="flex items-center gap-2 overflow-x-auto pb-1">
                          {allImages.map((img, idx) => (
                            <button
                              key={idx}
                              type="button"
                              onClick={() => setActivePhotoIndex(idx)}
                              className={`w-16 h-12 rounded-xl overflow-hidden flex-shrink-0 border-2 transition-all relative ${
                                activePhotoIndex === idx
                                  ? "border-amber-500 ring-2 ring-amber-500/20"
                                  : "border-slate-200 opacity-70 hover:opacity-100"
                              }`}
                            >
                              <img src={resolveMediaUrl(img)} alt={`Thumb ${idx + 1}`} className="w-full h-full object-cover" />
                              {img === inspectApplication.primary_image_url && (
                                <span className="absolute bottom-0 inset-x-0 bg-black/70 text-[7px] text-amber-300 font-bold text-center">
                                  Primary
                                </span>
                              )}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="rounded-2xl p-6 bg-slate-100 border border-slate-200 text-center text-slate-400">
                      <Car className="w-10 h-10 mx-auto mb-1 text-slate-300" />
                      <span>No images provided for this vehicle application</span>
                    </div>
                  );
                })()}

                <div className="p-3 bg-amber-50/70 rounded-2xl border border-amber-200 text-amber-900 flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold block">Catalogue Inclusion Impact</span>
                    <span>
                      Approving this application will automatically generate or update official catalogue records
                      (VehicleModel and VehicleVariant) with the primary image and technical specifications.
                      It will become available for all sellers to select. It does NOT create an active sales listing.
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Make</span>
                    <p className="font-bold text-slate-900">{inspectApplication.make_name}</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Model</span>
                    <p className="font-bold text-slate-900">{inspectApplication.model_name}</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Production Years</span>
                    <p className="font-bold text-slate-900">{inspectApplication.year_start} – {inspectApplication.year_end || "Present"}</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Status</span>
                    <p className="font-bold text-slate-900">{inspectApplication.status}</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Trim / Variant</span>
                    <p className="font-bold text-slate-900">{inspectApplication.variant_name || "Base"}</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Fuel</span>
                    <p className="font-bold text-slate-900">{inspectApplication.fuel_type || "N/A"}</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Transmission</span>
                    <p className="font-bold text-slate-900">{inspectApplication.transmission || "N/A"}</p>
                  </div>
                  <div className="p-3 bg-slate-50 rounded-xl">
                    <span className="text-slate-500">Body Type</span>
                    <p className="font-bold text-slate-900">{inspectApplication.body_type || "N/A"}</p>
                  </div>
                </div>

                <div className="p-3 bg-slate-50 rounded-2xl border border-slate-200 text-slate-600 space-y-1">
                  <div className="flex flex-wrap gap-4 text-[11px]">
                    <span>Applicant: <strong className="text-slate-900">{inspectApplication.seller_name}</strong></span>
                    <span>Submitted: <strong>{new Date(inspectApplication.created_at).toLocaleDateString()}</strong></span>
                    {inspectApplication.power_bhp && <span>Power: <strong>{inspectApplication.power_bhp} BHP</strong></span>}
                    {inspectApplication.engine_code && <span>Engine Code: <strong>{inspectApplication.engine_code}</strong></span>}
                  </div>
                  {inspectApplication.notes && (
                    <div className="pt-2 border-t border-slate-200 mt-2">
                      <span className="font-bold block text-slate-700">Applicant Notes:</span>
                      <p className="italic text-slate-800">&quot;{inspectApplication.notes}&quot;</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Item Details: Catalogue Photo Proposal */}
            {inspectPhotoProposal && (
              <div className="space-y-4 text-xs">
                <div className="p-3 bg-amber-50/70 rounded-2xl border border-amber-200 text-amber-900">
                  <span className="font-bold block">Official Catalogue Photo Moderation</span>
                  <span>
                    Approving this proposal will overwrite the canonical catalogue image for{" "}
                    <strong>{inspectPhotoProposal.model_name}</strong>. If rejected, the current official image will remain intact.
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <span className="font-bold text-slate-500 uppercase tracking-wider text-[10px] block">Current Official Image</span>
                    <div className="h-44 rounded-2xl bg-slate-900 overflow-hidden flex items-center justify-center border border-slate-200">
                      {inspectPhotoProposal.current_image_url ? (
                        <img src={resolveMediaUrl(inspectPhotoProposal.current_image_url)} alt="Current" className="w-full h-full object-cover" />
                      ) : (
                        <span className="text-slate-400 italic">No image currently set</span>
                      )}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <span className="font-bold text-amber-600 uppercase tracking-wider text-[10px] block">Proposed Image</span>
                    <div className="h-44 rounded-2xl bg-slate-900 overflow-hidden flex items-center justify-center border-2 border-amber-500">
                      <img src={resolveMediaUrl(inspectPhotoProposal.proposed_image_url)} alt="Proposed" className="w-full h-full object-cover" />
                    </div>
                  </div>
                </div>

                <div className="p-3 bg-slate-50 rounded-2xl border border-slate-200 space-y-1 text-slate-700">
                  <div className="flex flex-wrap gap-4 text-[11px]">
                    <span>Model: <strong className="text-slate-900">{inspectPhotoProposal.make_name} {inspectPhotoProposal.model_name}</strong></span>
                    <span>Proposed by: <strong className="text-slate-900">{inspectPhotoProposal.seller_name}</strong></span>
                    <span>Submitted: <strong>{new Date(inspectPhotoProposal.created_at).toLocaleDateString()}</strong></span>
                  </div>
                  {inspectPhotoProposal.notes && (
                    <div className="pt-2 border-t border-slate-200 mt-2">
                      <span className="font-bold block text-slate-700">Proposal Notes:</span>
                      <p className="italic text-slate-800">&quot;{inspectPhotoProposal.notes}&quot;</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Moderation Actions */}
            <div className="pt-4 border-t border-slate-200 space-y-3">
              <h5 className="text-xs font-bold text-slate-800">Compliance Decision</h5>

              {/* Conflict Explanation Banner if conflicts exist */}
              {inspectPart && (inspectPart.fitment_summary?.conflict ?? 0) > 0 && (
                <div className="p-3 bg-rose-50 border border-rose-300 rounded-xl text-xs text-rose-900 flex items-start gap-2 font-medium">
                  <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold block">Approve Disabled: Fitment Conflict Detected</span>
                    <span>
                      This listing declares {inspectPart.fitment_summary?.conflict} vehicle variant(s) confirmed as incompatible by canonical catalogue records. Under platform policy, listings with fitment conflicts cannot be approved. Request Changes or Reject this submission.
                    </span>
                  </div>
                </div>
              )}

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (inspectPart && (inspectPart.fitment_summary?.conflict ?? 0) > 0) return;
                    setReviewAction("APPROVE");
                  }}
                  disabled={Boolean(inspectPart && (inspectPart.fitment_summary?.conflict ?? 0) > 0)}
                  className={`flex-1 py-2 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
                    inspectPart && (inspectPart.fitment_summary?.conflict ?? 0) > 0
                      ? "bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed opacity-60"
                      : reviewAction === "APPROVE"
                      ? "bg-emerald-600 text-white shadow"
                      : "bg-emerald-50 text-emerald-800 hover:bg-emerald-100 border border-emerald-200"
                  }`}
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>
                    {inspectApplication
                      ? "Approve & Add to Catalogue"
                      : inspectPhotoProposal
                      ? "Approve & Update Photo"
                      : "Approve & Publish"}
                  </span>
                </button>

                {/* Only listings support REQUEST_CHANGES */}
                {!inspectApplication && !inspectPhotoProposal && (
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
                )}

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
                    placeholder="Provide specific feedback..."
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
                    setInspectApplication(null);
                    setInspectPhotoProposal(null);
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
                  className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl transition-colors disabled:opacity-40 flex items-center gap-1.5"
                >
                  {actionLoading && <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />}
                  <span>Confirm Decision</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
