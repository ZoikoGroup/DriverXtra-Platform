"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  api,
  VehicleOrder,
  VehiclePurchaseDocument,
  VehicleOrderDocumentsResponse,
  VehicleDocumentCategory,
  DocumentRequirementDetail,
} from "@/lib/api/client";
import {
  FileText,
  UploadCloud,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Download,
  History,
  RefreshCw,
  Building2,
  UserCheck,
  Check,
} from "lucide-react";

interface VehicleOrderDocumentsModalProps {
  order: VehicleOrder;
  userRole: "BUYER" | "SELLER";
  isOpen: boolean;
  onClose: () => void;
  onOrderUpdated?: (updatedOrder?: VehicleOrder) => void;
}

export default function VehicleOrderDocumentsModal({
  order,
  userRole,
  isOpen,
  onClose,
  onOrderUpdated,
}: VehicleOrderDocumentsModalProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [docsData, setDocsData] = useState<VehicleOrderDocumentsResponse | null>(null);

  // Upload Modal State
  const [uploadCategory, setUploadCategory] = useState<VehicleDocumentCategory | null>(null);
  const [uploadCategoryLabel, setUploadCategoryLabel] = useState<string>("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadNotes, setUploadNotes] = useState<string>("");
  const [uploadExpiryDate, setUploadExpiryDate] = useState<string>("");
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Review / Verify Modal State (Seller reviewing buyer docs)
  const [reviewDoc, setReviewDoc] = useState<VehiclePurchaseDocument | null>(null);
  const [reviewAction, setReviewAction] = useState<"APPROVE" | "REJECT">("APPROVE");
  const [rejectionReason, setRejectionReason] = useState<string>("");
  const [reviewNotes, setReviewNotes] = useState<string>("");
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  // History expansion state: Record of category -> boolean
  const [expandedHistory, setExpandedHistory] = useState<Record<string, boolean>>({});

  // Downloading document state
  const [downloadingDocId, setDownloadingDocId] = useState<string | null>(null);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.marketplace.getVehicleOrderDocuments(order.id);
      setDocsData(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load vehicle documents.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [order.id]);

  useEffect(() => {
    if (isOpen) {
      queueMicrotask(() => {
        void fetchDocuments();
      });
    }
  }, [isOpen, fetchDocuments]);

  if (!isOpen) return null;

  // Group requirements by owner role
  const readiness = docsData?.readiness;
  const verifiedCount = readiness?.verified_count ?? readiness?.verified_required_count ?? 0;
  const requiredCount = readiness?.required_count ?? readiness?.total_required ?? 0;
  const allVerified = Boolean(readiness?.all_verified ?? readiness?.all_required_verified);
  const byCategory: Record<string, DocumentRequirementDetail> = readiness?.by_category || {};
  const allDocs = docsData?.documents || [];

  const isPaymentConfirmed = Boolean(
    order.status === "PAYMENT_CONFIRMED" ||
    order.status === "READY_FOR_HANDOVER" ||
    order.payment_confirmed_at != null ||
    readiness?.has_payment_confirmed
  );
  const isReadyForHandover = Boolean(
    order.status === "READY_FOR_HANDOVER" ||
    (allVerified && isPaymentConfirmed)
  );

  // Extract requirements list from requirements array or by_category object
  const requirementsList: DocumentRequirementDetail[] =
    readiness?.requirements && readiness.requirements.length > 0
      ? readiness.requirements
      : (Object.values(byCategory) as DocumentRequirementDetail[]);

  const dealerCategories = requirementsList.filter(
    (req) => req.owner_role === "DEALER"
  );
  const buyerCategories = requirementsList.filter(
    (req) => req.owner_role === "BUYER"
  );

  const getDocumentsForCategory = (cat: string) => {
    return allDocs.filter((d) => d.category === cat);
  };

  const handleOpenUpload = (cat: VehicleDocumentCategory, label: string) => {
    setUploadCategory(cat);
    setUploadCategoryLabel(label);
    setUploadFile(null);
    setUploadNotes("");
    setUploadExpiryDate("");
    setUploadError(null);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 10 * 1024 * 1024) {
      setUploadError("File exceeds the 10MB maximum limit. Please choose a smaller file.");
      setUploadFile(null);
      return;
    }

    const ext = file.name.split(".").pop()?.toLowerCase();
    const allowed = ["pdf", "jpg", "jpeg", "png", "webp"];
    if (!ext || !allowed.includes(ext)) {
      setUploadError("Invalid file type. Allowed formats: PDF, JPEG, PNG, WEBP.");
      setUploadFile(null);
      return;
    }

    setUploadError(null);
    setUploadFile(file);
  };

  const handleSubmitUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadCategory || !uploadFile) {
      setUploadError("Please select a valid document file.");
      return;
    }

    setUploadLoading(true);
    setUploadError(null);

    try {
      const formData = new FormData();
      formData.append("category", uploadCategory);
      formData.append("file", uploadFile);
      if (uploadNotes.trim()) {
        formData.append("notes", uploadNotes.trim());
      }
      if (uploadExpiryDate) {
        formData.append("expiry_date", uploadExpiryDate);
      }

      await api.marketplace.uploadVehicleOrderDocument(order.id, formData);
      setSuccessMessage(`Document "${uploadCategoryLabel}" uploaded successfully.`);
      setUploadCategory(null);
      setUploadFile(null);
      await fetchDocuments();
      if (onOrderUpdated) onOrderUpdated();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to upload document.";
      setUploadError(msg);
    } finally {
      setUploadLoading(false);
    }
  };

  const handleOpenReview = (doc: VehiclePurchaseDocument) => {
    setReviewDoc(doc);
    setReviewAction("APPROVE");
    setRejectionReason("");
    setReviewNotes("");
    setReviewError(null);
  };

  const handleSubmitReview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reviewDoc) return;

    if (reviewAction === "REJECT" && (!rejectionReason || rejectionReason.trim().length < 5)) {
      setReviewError("A rejection reason of at least 5 characters is required.");
      return;
    }

    setReviewLoading(true);
    setReviewError(null);

    try {
      await api.marketplace.verifyVehicleOrderDocument(order.id, reviewDoc.id, {
        action: reviewAction,
        rejection_reason: reviewAction === "REJECT" ? rejectionReason.trim() : undefined,
        notes: reviewNotes.trim() || undefined,
      });

      setSuccessMessage(
        reviewAction === "APPROVE"
          ? `Document "${reviewDoc.category_display}" has been approved.`
          : `Document "${reviewDoc.category_display}" has been rejected with feedback provided to buyer.`
      );
      setReviewDoc(null);
      await fetchDocuments();
      if (onOrderUpdated) onOrderUpdated();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to review document.";
      setReviewError(msg);
    } finally {
      setReviewLoading(false);
    }
  };

  const handleDownload = async (doc: VehiclePurchaseDocument) => {
    setDownloadingDocId(doc.id);
    try {
      const blob = await api.marketplace.downloadVehicleOrderDocument(order.id, doc.id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = doc.original_filename || `document_${doc.id.slice(0, 8)}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to download document.";
      setError(msg);
    } finally {
      setDownloadingDocId(null);
    }
  };

  const toggleHistory = (cat: string) => {
    setExpandedHistory((prev) => ({
      ...prev,
      [cat]: !prev[cat],
    }));
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const renderRequirementCard = (req: DocumentRequirementDetail) => {
    const catKey = req.category;
    const label = req.label || req.name || catKey;
    const notes = req.notes || req.description || "";
    const isRequired = req.required ?? req.is_required ?? false;

    const categoryDocs = getDocumentsForCategory(catKey);
    const currentDoc = categoryDocs.find((d) => d.is_current) || categoryDocs[0];
    const previousDocs = categoryDocs.filter((d) => d.id !== currentDoc?.id);

    const isVerified = currentDoc?.status === "VERIFIED";
    const isPending = currentDoc?.status === "PENDING_REVIEW";
    const isRejected = currentDoc?.status === "REJECTED";
    const isExpired = currentDoc?.status === "EXPIRED";
    const isMissing = !currentDoc || (!isVerified && !isPending && !isRejected && !isExpired);

    const canUpload =
      (userRole === "SELLER" && req.owner_role === "DEALER") ||
      (userRole === "BUYER" && req.owner_role === "BUYER");

    // Review allowed for seller on buyer documents when PENDING_REVIEW
    const canReview =
      userRole === "SELLER" &&
      req.owner_role === "BUYER" &&
      currentDoc &&
      currentDoc.status === "PENDING_REVIEW";

    return (
      <div
        key={catKey}
        className={`p-4 rounded-2xl border transition-all ${
          isVerified
            ? "bg-emerald-50/40 border-emerald-200"
            : isRejected
            ? "bg-rose-50/50 border-rose-200"
            : isExpired
            ? "bg-amber-50/50 border-amber-300"
            : isPending
            ? "bg-blue-50/40 border-blue-200"
            : "bg-slate-50 border-slate-200"
        }`}
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-black text-slate-900">{label}</span>
              {isRequired ? (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-slate-900 text-white">
                  Required
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-200 text-slate-700">
                  Optional
                </span>
              )}
            </div>
            {notes && <p className="text-[11px] text-slate-500 mt-0.5">{notes}</p>}
            <div className="flex flex-wrap items-center gap-2 mt-1 text-[11px] text-slate-400">
              <span>Submitter: <strong className="text-slate-600">{req.owner_role === "DEALER" ? "Dealership" : "Buyer"}</strong></span>
              <span>•</span>
              <span>Reviewer: <strong className="text-slate-600">{req.owner_role === "DEALER" ? "Platform Compliance Officer" : "Dealership Staff"}</strong></span>
            </div>
          </div>

          <div>
            {isVerified && (
              <span className="px-2.5 py-1 rounded-full text-xs font-black bg-emerald-100 text-emerald-800 border border-emerald-300 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                Verified
              </span>
            )}
            {isPending && (
              <span className="px-2.5 py-1 rounded-full text-xs font-black bg-blue-100 text-blue-800 border border-blue-300 flex items-center gap-1">
                <Clock className="w-3.5 h-3.5 text-blue-600" />
                Pending Verification
              </span>
            )}
            {isRejected && (
              <span className="px-2.5 py-1 rounded-full text-xs font-black bg-rose-100 text-rose-800 border border-rose-300 flex items-center gap-1">
                <XCircle className="w-3.5 h-3.5 text-rose-600" />
                Rejected
              </span>
            )}
            {isExpired && (
              <span className="px-2.5 py-1 rounded-full text-xs font-black bg-amber-100 text-amber-900 border border-amber-300 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                Expired
              </span>
            )}
            {isMissing && (
              <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-slate-200 text-slate-600">
                {isRequired ? "Action Required" : "Not Uploaded"}
              </span>
            )}
          </div>
        </div>

        {/* Current Document File Info */}
        {currentDoc && (
          <div className="mt-3 p-3 bg-white rounded-xl border border-slate-200 text-xs space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-slate-500" />
                <span className="font-bold text-slate-800">{currentDoc.original_filename}</span>
                <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-100 text-slate-600">
                  v{currentDoc.version_number}
                </span>
                <span className="text-[11px] text-slate-400">
                  ({formatFileSize(currentDoc.file_size_bytes)})
                </span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleDownload(currentDoc)}
                  disabled={downloadingDocId === currentDoc.id}
                  className="px-2.5 py-1 rounded-lg border border-slate-200 hover:bg-slate-50 text-[11px] font-bold text-slate-700 flex items-center gap-1 transition-colors"
                >
                  {downloadingDocId === currentDoc.id ? (
                    <RefreshCw className="w-3 h-3 animate-spin text-slate-500" />
                  ) : (
                    <Download className="w-3 h-3 text-slate-500" />
                  )}
                  <span>Download</span>
                </button>

                {canReview && (
                  <button
                    type="button"
                    onClick={() => handleOpenReview(currentDoc)}
                    className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-[11px] font-black text-white flex items-center gap-1 transition-colors shadow-xs"
                  >
                    <CheckCircle2 className="w-3 h-3" />
                    <span>Review & Verify</span>
                  </button>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1 text-[11px] text-slate-500 pt-1 border-t border-slate-100">
              <div>
                Submitted by: <strong className="text-slate-700">{currentDoc.submitted_by_name}</strong> on{" "}
                {new Date(currentDoc.created_at).toLocaleDateString()}
              </div>
              {currentDoc.expiry_date && (
                <div>
                  Expiry Date: <strong className="text-slate-700">{currentDoc.expiry_date}</strong>
                </div>
              )}
              {currentDoc.verified_at && (
                <div>
                  Verified by: <strong className="text-slate-700">{currentDoc.verified_by_name}</strong> on{" "}
                  {new Date(currentDoc.verified_at).toLocaleDateString()}
                </div>
              )}
            </div>

            {/* Rejection Details Banner */}
            {isRejected && currentDoc.rejection_reason && (
              <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-900">
                <div className="font-bold flex items-center gap-1 text-rose-800">
                  <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />
                  <span>Rejection Feedback:</span>
                </div>
                <p className="mt-0.5 text-[11px]">{currentDoc.rejection_reason}</p>
              </div>
            )}
          </div>
        )}

        {/* Upload / Replace Action Bar */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-200/60">
          <div>
            {previousDocs.length > 0 && (
              <button
                type="button"
                onClick={() => toggleHistory(catKey)}
                className="text-[11px] font-bold text-slate-500 hover:text-slate-800 flex items-center gap-1"
              >
                <History className="w-3 h-3 text-slate-400" />
                <span>
                  {expandedHistory[catKey] ? "Hide version history" : `History (${previousDocs.length} previous versions)`}
                </span>
              </button>
            )}
          </div>

          <div>
            {canUpload && (
              <button
                type="button"
                onClick={() => handleOpenUpload(catKey as VehicleDocumentCategory, label)}
                className={`px-3 py-1.5 rounded-xl text-xs font-black flex items-center gap-1.5 shadow-xs transition-colors ${
                  isRejected || isExpired || isMissing
                    ? "bg-slate-900 hover:bg-slate-800 text-white"
                    : "bg-white hover:bg-slate-100 text-slate-800 border border-slate-300"
                }`}
              >
                <UploadCloud className="w-3.5 h-3.5" />
                <span>{currentDoc ? "Upload Replacement Version" : "Upload Document"}</span>
              </button>
            )}
          </div>
        </div>

        {/* Expandable Version History */}
        {expandedHistory[catKey] && previousDocs.length > 0 && (
          <div className="mt-3 p-3 bg-white/80 rounded-xl border border-slate-200 space-y-2 text-xs">
            <h5 className="font-bold text-slate-700 text-[11px] uppercase tracking-wider">
              Prior Versions & Review Audit
            </h5>
            <div className="space-y-2">
              {previousDocs.map((prevDoc) => (
                <div
                  key={prevDoc.id}
                  className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 text-[11px] space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-800">
                      v{prevDoc.version_number} — {prevDoc.original_filename}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleDownload(prevDoc)}
                      className="text-slate-600 hover:text-slate-900 font-bold flex items-center gap-1"
                    >
                      <Download className="w-3 h-3" />
                      <span>Download</span>
                    </button>
                  </div>
                  <div className="text-slate-500">
                    Status: <span className="font-semibold">{prevDoc.status_display}</span> · Uploaded on{" "}
                    {new Date(prevDoc.created_at).toLocaleDateString()}
                  </div>
                  {prevDoc.rejection_reason && (
                    <div className="text-rose-700 italic">
                      Rejection note: {prevDoc.rejection_reason}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-3xl max-w-3xl w-full max-h-[90vh] shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between flex-shrink-0">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono font-bold text-slate-400">
                #{order.order_number}
              </span>
              <span className="text-xs px-2 py-0.5 rounded-full font-bold bg-slate-100 text-slate-700">
                Market: {order.currency === "GBP" ? "United Kingdom (DVLA / MOT)" : order.currency === "INR" ? "India (RTO / PUC)" : "Global Standards"}
              </span>
            </div>
            <h3 className="text-base font-black text-slate-900 mt-0.5">
              Vehicle Purchase Compliance & Documents
            </h3>
            <p className="text-xs text-slate-500">{order.listing_title}</p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => void fetchDocuments()}
              disabled={loading}
              className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
              title="Refresh documents"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </button>
            <button
              onClick={onClose}
              className="p-1 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100"
            >
              <XCircle className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {/* Messages */}
          {error && (
            <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-rose-600 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {successMessage && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl text-xs flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                <span>{successMessage}</span>
              </div>
              <button
                onClick={() => setSuccessMessage(null)}
                className="text-emerald-700 hover:text-emerald-900 font-bold"
              >
                ✕
              </button>
            </div>
          )}

          {/* Dual Workflow Status: Payment & Document Gates (Separately Reported) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Gate 1: Payment Status Card */}
            <div className={`p-4 rounded-2xl border transition-all ${
              isPaymentConfirmed
                ? "bg-emerald-50/70 border-emerald-200"
                : order.status === "PAYMENT_SUBMITTED"
                ? "bg-blue-50/70 border-blue-200"
                : "bg-amber-50/70 border-amber-200"
            }`}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] uppercase font-bold tracking-wider text-slate-500">
                  Gate 1: Payment Verification
                </span>
                {isPaymentConfirmed ? (
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-black bg-emerald-100 text-emerald-800 border border-emerald-300 flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                    Confirmed & Credited
                  </span>
                ) : order.status === "PAYMENT_SUBMITTED" ? (
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-black bg-blue-100 text-blue-800 border border-blue-300 flex items-center gap-1">
                    <Clock className="w-3 h-3 text-blue-600" />
                    Pending Dealer Confirmation
                  </span>
                ) : (
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-black bg-amber-100 text-amber-900 border border-amber-300 flex items-center gap-1">
                    <Clock className="w-3 h-3 text-amber-600" />
                    Awaiting Offline Transfer
                  </span>
                )}
              </div>
              <h5 className="text-sm font-black text-slate-900 mt-1.5">
                {isPaymentConfirmed
                  ? "Direct Payment Verified"
                  : order.status === "PAYMENT_SUBMITTED"
                  ? "Payment Reported by Buyer"
                  : "Offline Payment Pending"}
              </h5>
              <p className="text-[11px] text-slate-600 mt-0.5">
                {isPaymentConfirmed
                  ? `Dealership confirmed receipt of ${order.currency} ${Number(order.agreed_price).toLocaleString()} in bank account.`
                  : order.status === "PAYMENT_SUBMITTED"
                  ? "Buyer submitted payment confirmation. Dealership verification in progress."
                  : `Agreed price ${order.currency} ${Number(order.agreed_price).toLocaleString()}. Direct transfer between buyer and dealership.`}
              </p>
            </div>

            {/* Gate 2: Compliance & Document Readiness Card */}
            <div className={`p-4 rounded-2xl border transition-all ${
              allVerified
                ? "bg-emerald-50/70 border-emerald-200"
                : verifiedCount > 0
                ? "bg-purple-50/70 border-purple-200"
                : "bg-slate-50 border-slate-200"
            }`}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] uppercase font-bold tracking-wider text-slate-500">
                  Gate 2: Document Compliance
                </span>
                {allVerified ? (
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-black bg-emerald-100 text-emerald-800 border border-emerald-300 flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                    All Verified
                  </span>
                ) : (
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-black bg-purple-100 text-purple-800 border border-purple-300 flex items-center gap-1">
                    <Clock className="w-3 h-3 text-purple-600" />
                    {verifiedCount} of {requiredCount} Verified
                  </span>
                )}
              </div>
              <h5 className="text-sm font-black text-slate-900 mt-1.5">
                {allVerified
                  ? "All Required Documents Verified"
                  : `${verifiedCount} of ${requiredCount} Required Documents Verified`}
              </h5>
              <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden mt-2">
                <div
                  className="bg-purple-600 h-1.5 rounded-full transition-all duration-500"
                  style={{
                    width: `${requiredCount > 0 ? Math.min(100, Math.round((verifiedCount / requiredCount) * 100)) : 100}%`,
                  }}
                />
              </div>
            </div>
          </div>

          {/* Dual Gate Handover Authorization Notice */}
          {isReadyForHandover ? (
            <div className="p-3.5 bg-emerald-50 border border-emerald-300 rounded-2xl flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
              <div>
                <strong className="block text-emerald-950 font-black text-xs">Vehicle Ready for Handover!</strong>
                <span className="text-[11px] text-emerald-800">
                  Both required gates are satisfied: Direct offline payment is confirmed by the dealership, and all {requiredCount} required compliance and registration documents are verified. The vehicle may be released.
                </span>
              </div>
            </div>
          ) : (
            <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-2xl text-xs space-y-1.5">
              <div className="flex items-center gap-2 text-slate-800 font-bold">
                <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0" />
                <span>Strict Dual Handover Requirement:</span>
              </div>
              <p className="text-[11px] text-slate-500">
                Vehicle release (<strong>READY_FOR_HANDOVER</strong>) requires BOTH conditions below to be satisfied. Neither payment confirmation alone nor document verification alone authorizes vehicle release.
              </p>
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <span className={`px-2.5 py-1 rounded-full text-[11px] font-bold flex items-center gap-1 border ${
                  isPaymentConfirmed
                    ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                    : "bg-amber-100 text-amber-900 border-amber-300"
                }`}>
                  {isPaymentConfirmed ? <Check className="w-3 h-3 text-emerald-600" /> : <Clock className="w-3 h-3 text-amber-600" />}
                  Gate 1: Payment {isPaymentConfirmed ? "Confirmed" : "Pending"}
                </span>
                <span className={`px-2.5 py-1 rounded-full text-[11px] font-bold flex items-center gap-1 border ${
                  allVerified
                    ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                    : "bg-purple-100 text-purple-900 border-purple-300"
                }`}>
                  {allVerified ? <Check className="w-3 h-3 text-emerald-600" /> : <Clock className="w-3 h-3 text-purple-600" />}
                  Gate 2: Documents ({verifiedCount}/{requiredCount} Verified)
                </span>
              </div>
            </div>
          )}

          {/* Section 1: Dealer Compliance Documents */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-black text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                <Building2 className="w-4 h-4 text-slate-500" />
                <span>Dealership Registration & Compliance Records</span>
              </h4>
              <span className="text-[11px] text-slate-400">
                Uploaded by dealership · Verified for buyer inspection
              </span>
            </div>

            <div className="space-y-3">
              {dealerCategories.length > 0 ? (
                dealerCategories.map((req) => renderRequirementCard(req))
              ) : (
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-500">
                  No dealership compliance documents configured for this market.
                </div>
              )}
            </div>
          </div>

          {/* Section 2: Buyer Verification Documents */}
          <div className="space-y-3 pt-3 border-t border-slate-100">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-black text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                <UserCheck className="w-4 h-4 text-slate-500" />
                <span>Buyer Identification & Verification</span>
              </h4>
              <span className="text-[11px] text-slate-400">
                Uploaded by buyer · Reviewed by dealership staff
              </span>
            </div>

            <div className="space-y-3">
              {buyerCategories.length > 0 ? (
                buyerCategories.map((req) => renderRequirementCard(req))
              ) : (
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-500">
                  No buyer verification documents required for this market.
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-100 flex items-center justify-between flex-shrink-0 bg-slate-50">
          <p className="text-[11px] text-slate-500">
            Documents are encrypted and stored securely in isolated platform storage.
          </p>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold"
          >
            Close
          </button>
        </div>
      </div>

      {/* SUB-MODAL: UPLOAD DOCUMENT */}
      {uploadCategory && (
        <div className="fixed inset-0 z-60 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h4 className="text-base font-black text-slate-900">Upload Document</h4>
                <p className="text-xs text-slate-500">{uploadCategoryLabel}</p>
              </div>
              <button
                onClick={() => setUploadCategory(null)}
                className="p-1 text-slate-400 hover:text-slate-700"
              >
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            {uploadError && (
              <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                <span>{uploadError}</span>
              </div>
            )}

            <form onSubmit={handleSubmitUpload} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Document File * (PDF, JPEG, PNG, WEBP — Max 10MB)
                </label>
                <input
                  type="file"
                  accept=".pdf, .jpg, .jpeg, .png, .webp"
                  onChange={handleFileChange}
                  className="w-full text-xs text-slate-600 file:mr-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-bold file:bg-slate-900 file:text-white hover:file:bg-slate-800 cursor-pointer"
                  required
                />
                {uploadFile && (
                  <p className="text-[11px] text-slate-500 mt-1 font-mono">
                    Selected: {uploadFile.name} ({formatFileSize(uploadFile.size)})
                  </p>
                )}
              </div>

              {/* Expiry Date (if dealer doc that expires) */}
              {(uploadCategory === "ROADWORTHINESS_MOT" || uploadCategory === "INSURANCE_CERTIFICATE") && (
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Document Expiry Date (Optional)
                  </label>
                  <input
                    type="date"
                    value={uploadExpiryDate}
                    onChange={(e) => setUploadExpiryDate(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 rounded-xl text-xs text-slate-800"
                  />
                  <p className="text-[10px] text-slate-400 mt-0.5">
                    Orders will automatically track validity before final handover.
                  </p>
                </div>
              )}

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Submission Notes (Optional)
                </label>
                <textarea
                  rows={2}
                  value={uploadNotes}
                  onChange={(e) => setUploadNotes(e.target.value)}
                  placeholder="e.g. Valid until next annual inspection; stamped by official MOT test centre."
                  className="w-full px-3 py-2 border border-slate-200 rounded-xl text-xs text-slate-800"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setUploadCategory(null)}
                  disabled={uploadLoading}
                  className="px-4 py-2 border border-slate-200 text-slate-600 rounded-xl text-xs font-bold hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={uploadLoading || !uploadFile}
                  className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-black shadow-xs flex items-center gap-1.5 disabled:opacity-50"
                >
                  {uploadLoading ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Uploading...</span>
                    </>
                  ) : (
                    <>
                      <UploadCloud className="w-3.5 h-3.5" />
                      <span>Upload Document</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* SUB-MODAL: REVIEW / VERIFY BUYER DOCUMENT */}
      {reviewDoc && (
        <div className="fixed inset-0 z-60 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h4 className="text-base font-black text-slate-900">Review Buyer Document</h4>
                <p className="text-xs text-slate-500">{reviewDoc.category_display}</p>
              </div>
              <button
                onClick={() => setReviewDoc(null)}
                className="p-1 text-slate-400 hover:text-slate-700"
              >
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            {reviewError && (
              <div className="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-xl text-xs flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                <span>{reviewError}</span>
              </div>
            )}

            <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1">
              <div>
                Submitted by: <strong>{reviewDoc.submitted_by_name}</strong>
              </div>
              <div>
                Filename: <strong>{reviewDoc.original_filename}</strong> ({formatFileSize(reviewDoc.file_size_bytes)})
              </div>
              <div className="pt-1">
                <button
                  type="button"
                  onClick={() => handleDownload(reviewDoc)}
                  className="px-2.5 py-1 rounded-lg bg-white border border-slate-300 hover:bg-slate-100 text-xs font-bold text-slate-800 flex items-center gap-1 shadow-2xs"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download & Inspect Document</span>
                </button>
              </div>
            </div>

            <form onSubmit={handleSubmitReview} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-2">
                  Review Determination *
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setReviewAction("APPROVE")}
                    className={`p-3 rounded-xl border text-xs font-bold flex items-center justify-center gap-1.5 transition-all ${
                      reviewAction === "APPROVE"
                        ? "bg-emerald-600 text-white border-emerald-600 shadow-xs"
                        : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Approve Document</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setReviewAction("REJECT")}
                    className={`p-3 rounded-xl border text-xs font-bold flex items-center justify-center gap-1.5 transition-all ${
                      reviewAction === "REJECT"
                        ? "bg-rose-600 text-white border-rose-600 shadow-xs"
                        : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    <XCircle className="w-4 h-4" />
                    <span>Reject Document</span>
                  </button>
                </div>
              </div>

              {reviewAction === "REJECT" ? (
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Rejection Feedback * (minimum 5 characters)
                  </label>
                  <textarea
                    rows={3}
                    required
                    minLength={5}
                    value={rejectionReason}
                    onChange={(e) => setRejectionReason(e.target.value)}
                    placeholder="e.g. Utility bill exceeds 3 months; please provide a recent bank statement or council tax bill."
                    className="w-full px-3 py-2 border border-slate-300 rounded-xl text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-rose-500"
                  />
                  <p className="text-[10px] text-slate-500 mt-1">
                    The buyer will see this feedback and can upload a corrected version.
                  </p>
                </div>
              ) : (
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Approval Notes (Optional)
                  </label>
                  <textarea
                    rows={2}
                    value={reviewNotes}
                    onChange={(e) => setReviewNotes(e.target.value)}
                    placeholder="e.g. Address matches contract handover address perfectly."
                    className="w-full px-3 py-2 border border-slate-200 rounded-xl text-xs text-slate-800"
                  />
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setReviewDoc(null)}
                  disabled={reviewLoading}
                  className="px-4 py-2 border border-slate-200 text-slate-600 rounded-xl text-xs font-bold hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={reviewLoading}
                  className={`px-5 py-2 rounded-xl text-xs font-black shadow-xs flex items-center gap-1.5 text-white ${
                    reviewAction === "APPROVE"
                      ? "bg-emerald-600 hover:bg-emerald-700"
                      : "bg-rose-600 hover:bg-rose-700"
                  }`}
                >
                  {reviewLoading ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Saving...</span>
                    </>
                  ) : reviewAction === "APPROVE" ? (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Confirm Approval</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="w-3.5 h-3.5" />
                      <span>Confirm Rejection</span>
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
