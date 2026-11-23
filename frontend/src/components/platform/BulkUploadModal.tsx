"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  api,
  BulkUploadJob,
  BulkUploadRowError,
  BackendOrganisation,
  ApiError,
} from "@/lib/api/client";
import {
  Upload,
  FileText,
  Car,
  Wrench,
  Download,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  RefreshCw,
  X,
  Building2,
  Copy,
  Check,
  ChevronLeft,
  ChevronRight,
  RotateCcw,
  History,
  FileSpreadsheet,
  Layers,
} from "lucide-react";

interface BulkUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialUploadType?: "VEHICLES" | "SPARE_PARTS";
  userOrgs?: BackendOrganisation[];
  onUploadComplete?: () => void;
}

function formatFileSize(bytes: number): string {
  if (!bytes || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}

export default function BulkUploadModal({
  isOpen,
  onClose,
  initialUploadType = "VEHICLES",
  userOrgs = [],
  onUploadComplete,
}: BulkUploadModalProps) {
  // Modal active tab
  const [activeTab, setActiveTab] = useState<"upload" | "progress" | "history">("upload");

  // Upload Form State
  const [uploadType, setUploadType] = useState<"VEHICLES" | "SPARE_PARTS">(initialUploadType);
  const [duplicatePolicy, setDuplicatePolicy] = useState<"SKIP" | "FAIL_ROW">("SKIP");
  const [selectedOrgId, setSelectedOrgId] = useState<string>(() => userOrgs[0]?.id || "");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [templateDownloading, setTemplateDownloading] = useState<string | null>(null);

  // Sync initial upload type when prop changes
  const [prevInitialType, setPrevInitialType] = useState(initialUploadType);
  if (prevInitialType !== initialUploadType) {
    setPrevInitialType(initialUploadType);
    setUploadType(initialUploadType);
  }

  // Active Job / Polling State
  const [activeJob, setActiveJob] = useState<BulkUploadJob | null>(null);
  const [isPolling, setIsPolling] = useState<boolean>(false);
  const [copiedJobId, setCopiedJobId] = useState<boolean>(false);
  const [retryingJob, setRetryingJob] = useState<boolean>(false);
  const [retryNotice, setRetryNotice] = useState<string | null>(null);
  const [exportingErrors, setExportingErrors] = useState<boolean>(false);

  // Error Table State for Active Job
  const [jobErrors, setJobErrors] = useState<BulkUploadRowError[]>([]);
  const [errorsLoading, setErrorsLoading] = useState<boolean>(false);
  const [errorsPage, setErrorsPage] = useState<number>(1);
  const [errorsTotalCount, setErrorsTotalCount] = useState<number>(0);
  const [errorsOnlyUnresolved, setErrorsOnlyUnresolved] = useState<boolean>(false);
  const [expandedRowData, setExpandedRowData] = useState<Record<string, boolean>>({});

  // History State
  const [historyJobs, setHistoryJobs] = useState<BulkUploadJob[]>([]);
  const [historyLoading, setHistoryLoading] = useState<boolean>(false);
  const [historyTypeFilter, setHistoryTypeFilter] = useState<string>("ALL");
  const [historyStatusFilter, setHistoryStatusFilter] = useState<string>("ALL");

  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  const isMountedRef = useRef<boolean>(true);

  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Template Download Handlers
  // ---------------------------------------------------------------------------

  const handleDownloadTemplate = async (type: "vehicles" | "spare_parts") => {
    setTemplateDownloading(type);
    try {
      const blob = await api.marketplace.downloadBulkUploadTemplate(type);
      downloadBlob(blob, `${type}_upload_template.csv`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to download CSV template.";
      setFormError(msg);
    } finally {
      setTemplateDownloading(null);
    }
  };

  // ---------------------------------------------------------------------------
  // File Selection and Drag-and-Drop
  // ---------------------------------------------------------------------------

  const validateAndSetFile = (file: File) => {
    setFormError(null);
    const name = file.name.toLowerCase();

    // Check extension
    if (!name.endsWith(".csv") && !name.endsWith(".txt")) {
      setFormError("Only CSV text files (.csv) are supported. Excel (.xlsx) and other formats are not permitted.");
      setSelectedFile(null);
      return;
    }

    // Check file size limit: 15 MB
    const maxBytes = 15 * 1024 * 1024;
    if (file.size > maxBytes) {
      setFormError(`File size (${formatFileSize(file.size)}) exceeds the maximum allowed limit of 15 MB.`);
      setSelectedFile(null);
      return;
    }

    if (file.size === 0) {
      setFormError("Selected file is empty (0 bytes). Please select a valid CSV file with data rows.");
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  // ---------------------------------------------------------------------------
  // Form Submission
  // ---------------------------------------------------------------------------

  const handleSubmitUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setFormError("Please select a valid CSV file before uploading.");
      return;
    }

    setIsSubmitting(true);
    setFormError(null);

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("upload_type", uploadType);
    formData.append("duplicate_policy", duplicatePolicy);
    if (selectedOrgId) {
      formData.append("organisation", selectedOrgId);
    }

    try {
      const job = await api.marketplace.submitBulkUpload(formData);
      setActiveJob(job);
      setActiveTab("progress");
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      startPolling(job.id);
    } catch (err: unknown) {
      let msg = "Failed to submit bulk upload.";
      if (err instanceof ApiError) {
        msg = err.message;
      } else if (err instanceof Error) {
        msg = err.message;
      }
      setFormError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Error Management Handlers
  // ---------------------------------------------------------------------------

  const loadJobErrors = useCallback(async (jobId: string, page: number = 1, unresolvedOnly: boolean = false) => {
    setErrorsLoading(true);
    try {
      const res = await api.marketplace.getBulkUploadJobErrors(jobId, {
        page,
        page_size: 20,
        is_resolved: unresolvedOnly ? false : undefined,
      });
      setJobErrors(res.results || []);
      setErrorsTotalCount(res.count || 0);
      setErrorsPage(page);
    } catch (err: unknown) {
      console.error("Failed to load job row errors:", err);
    } finally {
      setErrorsLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Polling Job Status
  // ---------------------------------------------------------------------------

  const fetchJobStatus = useCallback(async (jobId: string) => {
    try {
      const job = await api.marketplace.getBulkUploadJob(jobId);
      if (!isMountedRef.current) return;
      setActiveJob(job);

      // Check if job reached a terminal state
      if (job.is_finished || ["COMPLETED", "PARTIALLY_FAILED", "FAILED"].includes(job.status)) {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setIsPolling(false);
        if (onUploadComplete) {
          onUploadComplete();
        }
        // Load errors if there are failures
        if (job.failed_rows > 0) {
          void loadJobErrors(job.id, 1, false);
        }
      }
    } catch (err: unknown) {
      console.warn("Bulk upload status poll error (retrying):", err);
    }
  }, [onUploadComplete, loadJobErrors]);

  const startPolling = useCallback((jobId: string) => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
    }
    setIsPolling(true);
    // Initial fetch
    void fetchJobStatus(jobId);

    // Poll every 2500ms
    pollingRef.current = setInterval(() => {
      void fetchJobStatus(jobId);
    }, 2500);
  }, [fetchJobStatus]);

  // Stop polling on close or unmount
  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    setIsPolling(false);
  };

  const handleExportErrors = async (jobId: string) => {
    setExportingErrors(true);
    try {
      const blob = await api.marketplace.exportBulkUploadJobErrors(jobId);
      downloadBlob(blob, `bulk_upload_errors_${jobId}.csv`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to download error CSV.";
      alert(msg);
    } finally {
      setExportingErrors(false);
    }
  };

  const handleRetryJob = async (jobId: string) => {
    setRetryingJob(true);
    setRetryNotice(null);
    try {
      const res = await api.marketplace.retryBulkUploadJob(jobId);
      setRetryNotice(res.detail || "Retry job dispatched successfully.");
      // Start polling again
      startPolling(jobId);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to retry job.";
      setRetryNotice(msg);
    } finally {
      setRetryingJob(false);
    }
  };

  const toggleRawData = (errId: string) => {
    setExpandedRowData((prev) => ({
      ...prev,
      [errId]: !prev[errId],
    }));
  };

  // ---------------------------------------------------------------------------
  // History Handlers
  // ---------------------------------------------------------------------------

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const params: { upload_type?: string; status?: string } = {};
      if (historyTypeFilter !== "ALL") params.upload_type = historyTypeFilter;
      if (historyStatusFilter !== "ALL") params.status = historyStatusFilter;

      const res = await api.marketplace.listBulkUploadJobs(params);
      setHistoryJobs(res.results || []);
    } catch (err: unknown) {
      console.error("Failed to load bulk upload history:", err);
    } finally {
      setHistoryLoading(false);
    }
  }, [historyTypeFilter, historyStatusFilter]);

  useEffect(() => {
    if (activeTab === "history") {
      queueMicrotask(() => {
        void loadHistory();
      });
    }
  }, [activeTab, loadHistory]);

  const handleSelectJobFromHistory = (job: BulkUploadJob) => {
    setActiveJob(job);
    setActiveTab("progress");
    if (!job.is_finished && ["PENDING", "PROCESSING", "PARSING"].includes(job.status)) {
      startPolling(job.id);
    } else {
      stopPolling();
      if (job.failed_rows > 0) {
        loadJobErrors(job.id, 1, false);
      } else {
        setJobErrors([]);
      }
    }
  };

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  const handleCopyJobId = (id: string) => {
    if (navigator?.clipboard?.writeText) {
      void navigator.clipboard.writeText(id);
      setCopiedJobId(true);
      setTimeout(() => setCopiedJobId(false), 2000);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "COMPLETED":
        return (
          <span className="px-2.5 py-1 rounded-full text-xs font-black bg-emerald-50 text-emerald-800 border border-emerald-300 flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            Completed
          </span>
        );
      case "PARTIALLY_FAILED":
        return (
          <span className="px-2.5 py-1 rounded-full text-xs font-black bg-amber-50 text-amber-900 border border-amber-300 flex items-center gap-1">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
            Partially Failed
          </span>
        );
      case "FAILED":
        return (
          <span className="px-2.5 py-1 rounded-full text-xs font-black bg-rose-50 text-rose-800 border border-rose-300 flex items-center gap-1">
            <XCircle className="w-3.5 h-3.5 text-rose-600" />
            Failed
          </span>
        );
      case "PROCESSING":
      case "PARSING":
        return (
          <span className="px-2.5 py-1 rounded-full text-xs font-black bg-blue-50 text-blue-800 border border-blue-300 flex items-center gap-1 animate-pulse">
            <RefreshCw className="w-3.5 h-3.5 text-blue-600 animate-spin" />
            Processing
          </span>
        );
      case "PENDING":
      default:
        return (
          <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-700 border border-slate-300 flex items-center gap-1">
            <Clock className="w-3.5 h-3.5 text-slate-500" />
            Pending Queue
          </span>
        );
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4">
      <div className="bg-white rounded-3xl max-w-4xl w-full max-h-[92vh] shadow-2xl flex flex-col overflow-hidden border border-slate-100">

        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between flex-shrink-0 bg-slate-900 text-white">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-500 text-slate-950 uppercase">
                B2B Bulk Upload
              </span>
              <span className="text-xs text-slate-400">Inventory Import Engine</span>
            </div>
            <h3 className="text-lg font-black text-white mt-1">
              Dealer & Workshop Bulk Inventory
            </h3>
          </div>

          <button
            onClick={() => {
              stopPolling();
              onClose();
            }}
            className="p-1.5 text-slate-400 hover:text-white rounded-xl hover:bg-slate-800 transition-colors"
            aria-label="Close bulk upload modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center justify-between px-6 py-2.5 border-b border-slate-200 bg-slate-50/70 text-xs">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab("upload")}
              className={`px-3 py-1.5 rounded-xl font-bold flex items-center gap-1.5 transition-all ${
                activeTab === "upload"
                  ? "bg-amber-500 text-slate-950 shadow-sm"
                  : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/70"
              }`}
            >
              <Upload className="w-3.5 h-3.5" />
              <span>Upload CSV</span>
            </button>

            {activeJob && (
              <button
                onClick={() => setActiveTab("progress")}
                className={`px-3 py-1.5 rounded-xl font-bold flex items-center gap-1.5 transition-all ${
                  activeTab === "progress"
                    ? "bg-amber-500 text-slate-950 shadow-sm"
                    : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/70"
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                <span>Job Status & Errors</span>
                {isPolling && (
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping inline-block" />
                )}
              </button>
            )}

            <button
              onClick={() => setActiveTab("history")}
              className={`px-3 py-1.5 rounded-xl font-bold flex items-center gap-1.5 transition-all ${
                activeTab === "history"
                  ? "bg-amber-500 text-slate-950 shadow-sm"
                  : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/70"
              }`}
            >
              <History className="w-3.5 h-3.5" />
              <span>Import History</span>
            </button>
          </div>

          {activeTab === "progress" && activeJob && (
            <div className="hidden sm:flex items-center gap-2 text-slate-500 font-mono text-[11px]">
              <span>Job #{activeJob.id.slice(0, 8)}</span>
              <button
                onClick={() => handleCopyJobId(activeJob.id)}
                className="hover:text-slate-800 transition-colors"
                title="Copy full job UUID"
              >
                {copiedJobId ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
              </button>
            </div>
          )}
        </div>

        {/* Modal Content */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">

          {/* ================================================================= */}
          {/* TAB 1: UPLOAD FORM */}
          {/* ================================================================= */}
          {activeTab === "upload" && (
            <form onSubmit={handleSubmitUpload} className="space-y-6">

              {/* Type Selection & Template Downloads */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

                {/* Upload Category Selection */}
                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-3">
                  <label className="text-xs font-black uppercase text-slate-700 tracking-wider block">
                    1. Select Inventory Category
                  </label>

                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setUploadType("VEHICLES")}
                      className={`p-3 rounded-xl border text-left flex flex-col gap-1 transition-all ${
                        uploadType === "VEHICLES"
                          ? "bg-white border-amber-500 shadow-sm ring-2 ring-amber-500/20"
                          : "bg-white/60 border-slate-200 hover:bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <Car className={`w-5 h-5 ${uploadType === "VEHICLES" ? "text-amber-500" : "text-slate-400"}`} />
                        {uploadType === "VEHICLES" && (
                          <span className="w-2 h-2 rounded-full bg-amber-500" />
                        )}
                      </div>
                      <span className="text-xs font-black text-slate-900 mt-1">Vehicles</span>
                      <span className="text-[10px] text-slate-500">VIN, Make, Model, MOT</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setUploadType("SPARE_PARTS")}
                      className={`p-3 rounded-xl border text-left flex flex-col gap-1 transition-all ${
                        uploadType === "SPARE_PARTS"
                          ? "bg-white border-amber-500 shadow-sm ring-2 ring-amber-500/20"
                          : "bg-white/60 border-slate-200 hover:bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <Wrench className={`w-5 h-5 ${uploadType === "SPARE_PARTS" ? "text-amber-500" : "text-slate-400"}`} />
                        {uploadType === "SPARE_PARTS" && (
                          <span className="w-2 h-2 rounded-full bg-amber-500" />
                        )}
                      </div>
                      <span className="text-xs font-black text-slate-900 mt-1">Spare Parts</span>
                      <span className="text-[10px] text-slate-500">MPN, Brand, HSN, GST</span>
                    </button>
                  </div>
                </div>

                {/* Templates & Guidance */}
                <div className="p-4 rounded-2xl bg-amber-50/50 border border-amber-200/70 space-y-3">
                  <label className="text-xs font-black uppercase text-amber-900 tracking-wider flex items-center gap-1.5">
                    <FileSpreadsheet className="w-4 h-4 text-amber-600" />
                    <span>2. Download Standard CSV Templates</span>
                  </label>
                  <p className="text-[11px] text-amber-800">
                    Always use the official DriverXtra CSV header specifications to avoid formatting errors.
                  </p>

                  <div className="flex flex-wrap gap-2 pt-1">
                    <button
                      type="button"
                      onClick={() => handleDownloadTemplate("vehicles")}
                      disabled={templateDownloading !== null}
                      className="px-3 py-2 bg-white hover:bg-amber-100/60 text-slate-800 text-xs font-bold rounded-xl border border-amber-300 flex items-center gap-1.5 transition-colors shadow-xs"
                    >
                      {templateDownloading === "vehicles" ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin text-amber-600" />
                      ) : (
                        <Download className="w-3.5 h-3.5 text-amber-600" />
                      )}
                      <span>Vehicle CSV Template</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleDownloadTemplate("spare_parts")}
                      disabled={templateDownloading !== null}
                      className="px-3 py-2 bg-white hover:bg-amber-100/60 text-slate-800 text-xs font-bold rounded-xl border border-amber-300 flex items-center gap-1.5 transition-colors shadow-xs"
                    >
                      {templateDownloading === "spare_parts" ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin text-amber-600" />
                      ) : (
                        <Download className="w-3.5 h-3.5 text-amber-600" />
                      )}
                      <span>Spare Parts CSV Template</span>
                    </button>
                  </div>
                </div>

              </div>

              {/* Organisation and Duplicate Policy Controls */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

                {/* Organisation / Dealership Selection */}
                {userOrgs && userOrgs.length > 0 ? (
                  <div className="space-y-1.5">
                    <label className="text-xs font-bold text-slate-700 flex items-center gap-1">
                      <Building2 className="w-3.5 h-3.5 text-slate-500" />
                      <span>Upload on behalf of Organisation / Dealership</span>
                    </label>
                    <select
                      value={selectedOrgId}
                      onChange={(e) => setSelectedOrgId(e.target.value)}
                      className="w-full text-xs font-medium px-3 py-2.5 rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500"
                    >
                      <option value="">Personal Seller Inventory (No Organisation)</option>
                      {userOrgs.map((org) => (
                        <option key={org.id} value={org.id}>
                          {org.name} ({org.user_role || "ADMIN"})
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    <label className="text-xs font-bold text-slate-700">Inventory Owner</label>
                    <div className="px-3 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-xs text-slate-600">
                      Personal Seller Inventory
                    </div>
                  </div>
                )}

                {/* Duplicate Policy */}
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-700 flex items-center gap-1">
                    <AlertTriangle className="w-3.5 h-3.5 text-slate-500" />
                    <span>Duplicate Listing Policy</span>
                  </label>
                  <select
                    value={duplicatePolicy}
                    onChange={(e) => setDuplicatePolicy(e.target.value as "SKIP" | "FAIL_ROW")}
                    className="w-full text-xs font-medium px-3 py-2.5 rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500"
                  >
                    <option value="SKIP">Skip Duplicates (Leave existing items unchanged - Recommended)</option>
                    <option value="FAIL_ROW">Mark as Error (Flag conflicting VINs or Brand+MPN as row errors)</option>
                  </select>
                </div>

              </div>

              {/* Drag-and-Drop File Zone */}
              <div className="space-y-2">
                <label className="text-xs font-bold text-slate-700 block">
                  Select CSV Import File
                </label>

                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-3xl p-6 sm:p-8 text-center cursor-pointer transition-all ${
                    isDragging
                      ? "border-amber-500 bg-amber-50/70"
                      : selectedFile
                      ? "border-emerald-400 bg-emerald-50/40"
                      : "border-slate-300 hover:border-slate-400 bg-slate-50/50 hover:bg-slate-50"
                  }`}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,text/csv,text/plain"
                    onChange={handleFileChange}
                    className="hidden"
                  />

                  {selectedFile ? (
                    <div className="flex flex-col items-center gap-2">
                      <div className="w-12 h-12 rounded-2xl bg-emerald-100 text-emerald-700 flex items-center justify-center">
                        <FileText className="w-6 h-6" />
                      </div>
                      <div className="space-y-0.5">
                        <p className="text-xs font-black text-slate-900">{selectedFile.name}</p>
                        <p className="text-[11px] font-mono text-slate-500">
                          {formatFileSize(selectedFile.size)} • Ready for processing
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedFile(null);
                          if (fileInputRef.current) fileInputRef.current.value = "";
                        }}
                        className="mt-2 text-xs font-bold text-rose-600 hover:text-rose-700"
                      >
                        Remove file and choose another
                      </button>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-2 text-slate-500">
                      <div className="w-12 h-12 rounded-2xl bg-amber-100 text-amber-700 flex items-center justify-center">
                        <Upload className="w-6 h-6" />
                      </div>
                      <div className="space-y-1">
                        <p className="text-xs font-bold text-slate-800">
                          Drag and drop your CSV file here, or{" "}
                          <span className="text-amber-600 underline font-black">browse files</span>
                        </p>
                        <p className="text-[11px] text-slate-400">
                          Supported format: Plain text CSV (.csv) • Maximum file size: 15 MB • Up to 5,000 rows
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Form Error Banner */}
              {formError && (
                <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-2xl text-xs text-rose-800 flex items-start gap-2.5">
                  <XCircle className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />
                  <div className="flex-1 font-medium">{formError}</div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2.5 text-xs font-bold text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-xl transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!selectedFile || isSubmitting}
                  className="px-5 py-2.5 bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 text-xs font-black rounded-xl transition-all shadow-md flex items-center gap-2"
                >
                  {isSubmitting ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin text-slate-950" />
                      <span>Submitting Import...</span>
                    </>
                  ) : (
                    <>
                      <Upload className="w-4 h-4" />
                      <span>Start Bulk Import</span>
                    </>
                  )}
                </button>
              </div>

            </form>
          )}

          {/* ================================================================= */}
          {/* TAB 2: ACTIVE JOB PROGRESS & REAL-TIME POLLING */}
          {/* ================================================================= */}
          {activeTab === "progress" && activeJob && (
            <div className="space-y-6">

              {/* Job Summary Banner */}
              <div className="p-5 rounded-2xl bg-slate-900 text-white space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-slate-400">
                        JOB ID: {activeJob.id}
                      </span>
                      <button
                        onClick={() => handleCopyJobId(activeJob.id)}
                        className="text-slate-400 hover:text-white"
                        title="Copy Job ID"
                      >
                        {copiedJobId ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                      </button>
                    </div>
                    <h4 className="text-sm font-black text-white mt-1 flex items-center gap-2">
                      <span>{activeJob.filename}</span>
                      <span className="text-xs font-normal text-slate-400">
                        ({formatFileSize(activeJob.file_size_bytes)})
                      </span>
                    </h4>
                  </div>

                  <div className="flex items-center gap-2">
                    {getStatusBadge(activeJob.status)}
                    <button
                      onClick={() => void fetchJobStatus(activeJob.id)}
                      className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
                      title="Force status refresh"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${isPolling ? "animate-spin" : ""}`} />
                    </button>
                  </div>
                </div>

                {/* Real-time Progress Bar */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs font-bold text-slate-300">
                    <span>Processing Progress</span>
                    <span className="font-mono text-amber-400">
                      {activeJob.progress_percentage}% ({activeJob.processed_rows} / {activeJob.total_rows || 0} rows)
                    </span>
                  </div>
                  <div className="w-full h-2.5 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all duration-300 ${
                        activeJob.status === "FAILED"
                          ? "bg-rose-500"
                          : activeJob.status === "PARTIALLY_FAILED"
                          ? "bg-amber-500"
                          : "bg-emerald-500"
                      }`}
                      style={{ width: `${Math.max(activeJob.progress_percentage, 4)}%` }}
                    />
                  </div>
                </div>

                {/* Counters Metrics Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 pt-2">
                  <div className="p-2.5 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">
                    <span className="text-[10px] text-slate-400 uppercase font-bold block">Total</span>
                    <span className="text-base font-black text-white">{activeJob.total_rows}</span>
                  </div>

                  <div className="p-2.5 rounded-xl bg-slate-800/80 border border-slate-700/60 text-center">
                    <span className="text-[10px] text-slate-400 uppercase font-bold block">Processed</span>
                    <span className="text-base font-black text-white">{activeJob.processed_rows}</span>
                  </div>

                  <div className="p-2.5 rounded-xl bg-emerald-950/40 border border-emerald-700/60 text-center">
                    <span className="text-[10px] text-emerald-400 uppercase font-bold block">Successful</span>
                    <span className="text-base font-black text-emerald-400">{activeJob.successful_rows}</span>
                  </div>

                  <div className="p-2.5 rounded-xl bg-rose-950/40 border border-rose-700/60 text-center">
                    <span className="text-[10px] text-rose-400 uppercase font-bold block">Failed</span>
                    <span className="text-base font-black text-rose-400">{activeJob.failed_rows}</span>
                  </div>

                  <div className="p-2.5 rounded-xl bg-amber-950/40 border border-amber-700/60 text-center">
                    <span className="text-[10px] text-amber-400 uppercase font-bold block">Duplicates</span>
                    <span className="text-base font-black text-amber-400">{activeJob.duplicate_rows}</span>
                  </div>
                </div>

              </div>

              {/* Retry Notice Alert */}
              {retryNotice && (
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900 flex items-center justify-between">
                  <span>{retryNotice}</span>
                  <button onClick={() => setRetryNotice(null)} className="text-amber-700 font-bold ml-2">
                    Dismiss
                  </button>
                </div>
              )}

              {/* Action Toolbar for Failed Jobs */}
              {activeJob.failed_rows > 0 && (
                <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h5 className="text-xs font-black text-slate-900">
                      Row-Level Validation & Processing Errors
                    </h5>
                    <p className="text-[11px] text-slate-500">
                      Download the error report with sanitised formulas or retry unresolved records.
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleExportErrors(activeJob.id)}
                      disabled={exportingErrors}
                      className="px-3 py-2 bg-white hover:bg-slate-100 text-slate-800 text-xs font-bold rounded-xl border border-slate-300 flex items-center gap-1.5 transition-colors shadow-xs"
                    >
                      {exportingErrors ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin text-slate-600" />
                      ) : (
                        <Download className="w-3.5 h-3.5 text-slate-600" />
                      )}
                      <span>Export Error CSV</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleRetryJob(activeJob.id)}
                      disabled={retryingJob || activeJob.status === "PROCESSING" || activeJob.status === "PARSING"}
                      className="px-3.5 py-2 bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 text-xs font-black rounded-xl transition-all shadow-xs flex items-center gap-1.5"
                    >
                      {retryingJob ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin text-slate-950" />
                      ) : (
                        <RotateCcw className="w-3.5 h-3.5" />
                      )}
                      <span>Retry Failed Rows</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Error Table */}
              {activeJob.failed_rows > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-700">
                      Showing {jobErrors.length} of {errorsTotalCount} error records
                    </span>

                    <button
                      onClick={() => {
                        const nextVal = !errorsOnlyUnresolved;
                        setErrorsOnlyUnresolved(nextVal);
                        loadJobErrors(activeJob.id, 1, nextVal);
                      }}
                      className="text-xs font-bold text-amber-700 hover:text-amber-800"
                    >
                      {errorsOnlyUnresolved ? "Show all errors" : "Show unresolved errors only"}
                    </button>
                  </div>

                  {errorsLoading ? (
                    <div className="p-8 text-center text-xs text-slate-500 flex items-center justify-center gap-2">
                      <RefreshCw className="w-4 h-4 animate-spin text-amber-500" />
                      <span>Loading error logs...</span>
                    </div>
                  ) : jobErrors.length === 0 ? (
                    <div className="p-6 text-center text-xs text-slate-500 bg-slate-50 rounded-2xl border border-slate-200">
                      No matching errors found.
                    </div>
                  ) : (
                    <div className="overflow-x-auto rounded-2xl border border-slate-200">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-100 text-slate-700 font-black border-b border-slate-200 text-[11px] uppercase">
                          <tr>
                            <th className="py-2.5 px-3">Row #</th>
                            <th className="py-2.5 px-3">Field</th>
                            <th className="py-2.5 px-3">Error Code</th>
                            <th className="py-2.5 px-3">Description</th>
                            <th className="py-2.5 px-3">Status</th>
                            <th className="py-2.5 px-3 text-right">Raw Data</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 text-slate-800">
                          {jobErrors.map((err) => (
                            <React.Fragment key={err.id}>
                              <tr className="hover:bg-slate-50/80 transition-colors">
                                <td className="py-2 px-3 font-mono font-bold text-slate-600">
                                  #{err.row_number}
                                </td>
                                <td className="py-2 px-3 font-mono font-bold text-slate-800">
                                  {err.field_name || "—"}
                                </td>
                                <td className="py-2 px-3">
                                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-50 text-rose-800 border border-rose-200">
                                    {err.error_code}
                                  </span>
                                </td>
                                <td className="py-2 px-3 text-slate-700 max-w-xs break-words">
                                  {err.error_message}
                                </td>
                                <td className="py-2 px-3">
                                  {err.is_resolved ? (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">
                                      Resolved
                                    </span>
                                  ) : (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800">
                                      Unresolved
                                    </span>
                                  )}
                                </td>
                                <td className="py-2 px-3 text-right">
                                  {err.raw_data && Object.keys(err.raw_data).length > 0 && (
                                    <button
                                      type="button"
                                      onClick={() => toggleRawData(err.id)}
                                      className="text-[11px] font-bold text-amber-600 hover:text-amber-800"
                                    >
                                      {expandedRowData[err.id] ? "Hide" : "View"}
                                    </button>
                                  )}
                                </td>
                              </tr>
                              {expandedRowData[err.id] && (
                                <tr className="bg-slate-50/90 text-xs">
                                  <td colSpan={6} className="p-3">
                                    <pre className="p-2.5 rounded-xl bg-slate-900 text-slate-200 font-mono text-[10px] overflow-x-auto">
                                      {JSON.stringify(err.raw_data, null, 2)}
                                    </pre>
                                  </td>
                                </tr>
                              )}
                            </React.Fragment>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* Pagination Controls */}
                  {errorsTotalCount > 20 && (
                    <div className="flex items-center justify-between text-xs pt-2">
                      <span className="text-slate-500">
                        Page {errorsPage} of {Math.ceil(errorsTotalCount / 20)}
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => loadJobErrors(activeJob.id, errorsPage - 1, errorsOnlyUnresolved)}
                          disabled={errorsPage <= 1}
                          className="px-2.5 py-1.5 rounded-lg border border-slate-200 disabled:opacity-40 hover:bg-slate-100 flex items-center gap-1 font-bold"
                        >
                          <ChevronLeft className="w-3.5 h-3.5" />
                          <span>Prev</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => loadJobErrors(activeJob.id, errorsPage + 1, errorsOnlyUnresolved)}
                          disabled={errorsPage * 20 >= errorsTotalCount}
                          className="px-2.5 py-1.5 rounded-lg border border-slate-200 disabled:opacity-40 hover:bg-slate-100 flex items-center gap-1 font-bold"
                        >
                          <span>Next</span>
                          <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Start New Import Button */}
              <div className="flex items-center justify-between pt-4 border-t border-slate-100 text-xs">
                <button
                  type="button"
                  onClick={() => setActiveTab("upload")}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold rounded-xl transition-colors"
                >
                  ← Upload Another Batch
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white font-bold rounded-xl transition-colors"
                >
                  Done
                </button>
              </div>

            </div>
          )}

          {/* ================================================================= */}
          {/* TAB 3: IMPORT HISTORY */}
          {/* ================================================================= */}
          {activeTab === "history" && (
            <div className="space-y-4">

              {/* Filters */}
              <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-slate-50 rounded-2xl border border-slate-200 text-xs">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-slate-600">Type:</span>
                    <select
                      value={historyTypeFilter}
                      onChange={(e) => setHistoryTypeFilter(e.target.value)}
                      className="px-2.5 py-1 rounded-lg border border-slate-300 bg-white font-medium focus:outline-none"
                    >
                      <option value="ALL">All Types</option>
                      <option value="VEHICLES">Vehicles</option>
                      <option value="SPARE_PARTS">Spare Parts</option>
                    </select>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-slate-600">Status:</span>
                    <select
                      value={historyStatusFilter}
                      onChange={(e) => setHistoryStatusFilter(e.target.value)}
                      className="px-2.5 py-1 rounded-lg border border-slate-300 bg-white font-medium focus:outline-none"
                    >
                      <option value="ALL">All Statuses</option>
                      <option value="COMPLETED">Completed</option>
                      <option value="PARTIALLY_FAILED">Partially Failed</option>
                      <option value="FAILED">Failed</option>
                      <option value="PROCESSING">Processing</option>
                      <option value="PENDING">Pending</option>
                    </select>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => void loadHistory()}
                  disabled={historyLoading}
                  className="px-3 py-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 font-bold flex items-center gap-1.5 text-slate-700"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${historyLoading ? "animate-spin" : ""}`} />
                  <span>Refresh</span>
                </button>
              </div>

              {/* History Table */}
              {historyLoading ? (
                <div className="p-12 text-center text-xs text-slate-500 flex items-center justify-center gap-2">
                  <RefreshCw className="w-4 h-4 animate-spin text-amber-500" />
                  <span>Loading upload history...</span>
                </div>
              ) : historyJobs.length === 0 ? (
                <div className="p-12 text-center text-xs text-slate-500 bg-slate-50 rounded-2xl border border-slate-200 space-y-2">
                  <Upload className="w-8 h-8 text-slate-300 mx-auto" />
                  <p className="font-bold text-slate-700">No import history found</p>
                  <p className="text-[11px] text-slate-400">
                    Upload your first vehicle or spare parts CSV to begin tracking batches.
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto rounded-2xl border border-slate-200">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-100 text-slate-700 font-black border-b border-slate-200 text-[11px] uppercase">
                      <tr>
                        <th className="py-2.5 px-3">Filename / Type</th>
                        <th className="py-2.5 px-3">Submitted</th>
                        <th className="py-2.5 px-3">Status</th>
                        <th className="py-2.5 px-3">Metrics</th>
                        <th className="py-2.5 px-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 text-slate-800">
                      {historyJobs.map((job) => (
                        <tr key={job.id} className="hover:bg-slate-50/80 transition-colors">
                          <td className="py-2.5 px-3">
                            <div className="font-bold text-slate-900">{job.filename}</div>
                            <div className="flex items-center gap-1.5 mt-0.5">
                              <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-slate-100 text-slate-600">
                                {job.upload_type === "VEHICLES" ? "Vehicles" : "Spare Parts"}
                              </span>
                              {job.organisation_name && (
                                <span className="text-[10px] text-slate-400">
                                  • {job.organisation_name}
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="py-2.5 px-3 text-slate-500 text-[11px]">
                            {new Date(job.created_at).toLocaleDateString("en-GB", {
                              day: "2-digit",
                              month: "short",
                              year: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </td>
                          <td className="py-2.5 px-3">{getStatusBadge(job.status)}</td>
                          <td className="py-2.5 px-3">
                            <div className="flex items-center gap-2 font-mono text-[11px]">
                              <span className="text-emerald-700 font-bold" title="Successful">
                                ✓ {job.successful_rows}
                              </span>
                              {job.failed_rows > 0 && (
                                <span className="text-rose-700 font-bold" title="Failed">
                                  ✗ {job.failed_rows}
                                </span>
                              )}
                              {job.duplicate_rows > 0 && (
                                <span className="text-amber-700 font-bold" title="Duplicate">
                                  ≈ {job.duplicate_rows}
                                </span>
                              )}
                              <span className="text-slate-400">/ {job.total_rows}</span>
                            </div>
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            <button
                              type="button"
                              onClick={() => handleSelectJobFromHistory(job)}
                              className="px-2.5 py-1 rounded-lg border border-slate-200 hover:bg-amber-500 hover:border-amber-500 hover:text-slate-950 text-slate-700 text-xs font-bold transition-all shadow-xs"
                            >
                              Details
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

            </div>
          )}

        </div>

      </div>
    </div>
  );
}
