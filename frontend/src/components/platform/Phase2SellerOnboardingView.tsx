"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  api,
  SellerApplication,
  SellerApplicationCreateUpdatePayload,
  BackendOrganisation,
  ApiError
} from "@/lib/api/client";
import {
  CheckCircle2,
  Clock,
  XCircle,
  AlertCircle,
  ShieldCheck,
  ShieldAlert,
  Send,
  Save,
  RefreshCw,
  X,
  FileText,
  User,
  MapPin,
  Landmark,
  Briefcase,
  Eye
} from "lucide-react";

export default function Phase2SellerOnboardingView({ initialTab }: { initialTab?: "my_application" | "admin_queue" }) {
  const { user } = useAuth();

  // Robust check for staff/admin permissions
  const isStaffOrAdmin = Boolean(
    user?.is_staff ||
    user?.is_superuser ||
    user?.role === "MARKETPLACE_ADMIN" ||
    user?.rawRoles?.includes("ADMIN") ||
    user?.rawRoles?.includes("STAFF")
  );

  // Active view tab: defaults to admin_queue if staff/admin or requested via prop
  const [activeTab, setActiveTab] = useState<"my_application" | "admin_queue">(
    initialTab || (isStaffOrAdmin ? "admin_queue" : "my_application")
  );

  // User's own application state
  const [application, setApplication] = useState<SellerApplication | null>(null);
  const [isLoadingApp, setIsLoadingApp] = useState(true);
  const [isSavingDraft, setIsSavingDraft] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Available organisations for association
  const [organisations, setOrganisations] = useState<BackendOrganisation[]>([]);

  // Form fields
  const [businessName, setBusinessName] = useState("");
  const [tradingName, setTradingName] = useState("");
  const [businessType, setBusinessType] = useState("LTD");
  const [registrationNumber, setRegistrationNumber] = useState("");
  const [vatNumber, setVatNumber] = useState("");
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [addressLine1, setAddressLine1] = useState("");
  const [addressLine2, setAddressLine2] = useState("");
  const [city, setCity] = useState("");
  const [stateProvince, setStateProvince] = useState("");
  const [postalCode, setPostalCode] = useState("");
  const [country, setCountry] = useState("United Kingdom");
  const [bankAccountName, setBankAccountName] = useState("");
  const [bankSortCode, setBankSortCode] = useState("");
  const [bankAccountNumber, setBankAccountNumber] = useState("");
  const [selectedOrgId, setSelectedOrgId] = useState<string>("");

  // Notification banners
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Admin Review section state (for staff / marketplace admins)
  const [adminApplications, setAdminApplications] = useState<SellerApplication[]>([]);
  const [isLoadingAdminList, setIsLoadingAdminList] = useState(false);
  const [adminFilterStatus, setAdminFilterStatus] = useState<string>("");
  const [reviewModalApp, setReviewModalApp] = useState<SellerApplication | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");
  const [isReviewing, setIsReviewing] = useState(false);

  const showSuccess = (msg: string) => {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(null), 5000);
  };

  // Populate form from application
  const populateForm = useCallback((app: SellerApplication) => {
    setBusinessName(app.business_name || "");
    setTradingName(app.trading_name || "");
    setBusinessType(app.business_type || "LTD");
    setRegistrationNumber(app.registration_number || "");
    setVatNumber(app.vat_number || "");
    setContactName(app.contact_name || "");
    setContactEmail(app.contact_email || "");
    setContactPhone(app.contact_phone || "");
    setAddressLine1(app.business_address_line1 || "");
    setAddressLine2(app.business_address_line2 || "");
    setCity(app.business_city || "");
    setStateProvince(app.business_state_province || "");
    setPostalCode(app.business_postal_code || "");
    setCountry(app.business_country || "United Kingdom");
    setBankAccountName(app.bank_account_name || "");
    setBankSortCode(app.bank_sort_code || "");
    setBankAccountNumber(app.bank_account_number || "");
    setSelectedOrgId(app.organisation || "");
  }, []);

  // Load user application on mount
  useEffect(() => {
    let ignore = false;
    api.seller.getMyApplication()
      .then((data) => {
        if (!ignore) {
          setApplication(data);
          if (data) {
            populateForm(data);
          } else if (user) {
            setContactName(user.fullName || "");
            setContactEmail(user.email || "");
            setContactPhone(user.phone_number || "");
          }
          setIsLoadingApp(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          if (err instanceof ApiError && err.code === 404) {
            setApplication(null);
            if (user) {
              setContactName(user.fullName || "");
              setContactEmail(user.email || "");
              setContactPhone(user.phone_number || "");
            }
          } else {
            setErrorMsg(err instanceof ApiError ? err.message : "Failed to load seller application.");
          }
          setIsLoadingApp(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [populateForm, user]);

  // Load user's organisations for dropdown
  useEffect(() => {
    let ignore = false;
    api.organisations.list().then((res) => {
      if (!ignore) setOrganisations(res.results || []);
    }).catch(() => {});
    return () => {
      ignore = true;
    };
  }, []);

  // Load Admin Applications if staff and on admin tab
  const loadAdminApplications = useCallback(async () => {
    if (!isStaffOrAdmin) return;
    try {
      setIsLoadingAdminList(true);
      const apps = await api.seller.listAdminApplications(adminFilterStatus || undefined);
      setAdminApplications(apps);
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to load admin seller applications queue.");
    } finally {
      setIsLoadingAdminList(false);
    }
  }, [isStaffOrAdmin, adminFilterStatus]);

  useEffect(() => {
    if (activeTab !== "admin_queue" || !isStaffOrAdmin) return;
    let ignore = false;
    api.seller.listAdminApplications(adminFilterStatus || undefined)
      .then((apps) => {
        if (!ignore) {
          setAdminApplications(apps);
          setIsLoadingAdminList(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setErrorMsg(err instanceof ApiError ? err.message : "Failed to load admin seller applications queue.");
          setIsLoadingAdminList(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [activeTab, isStaffOrAdmin, adminFilterStatus]);

  const getPayloadFromForm = (): SellerApplicationCreateUpdatePayload => {
    return {
      business_name: businessName.trim(),
      trading_name: tradingName.trim() || undefined,
      business_type: businessType,
      registration_number: registrationNumber.trim() || undefined,
      vat_number: vatNumber.trim() || undefined,
      contact_name: contactName.trim(),
      contact_email: contactEmail.trim(),
      contact_phone: contactPhone.trim(),
      business_address_line1: addressLine1.trim(),
      business_address_line2: addressLine2.trim() || undefined,
      business_city: city.trim(),
      business_state_province: stateProvince.trim() || undefined,
      business_postal_code: postalCode.trim(),
      business_country: country.trim(),
      bank_account_name: bankAccountName.trim() || undefined,
      bank_sort_code: bankSortCode.trim() || undefined,
      bank_account_number: bankAccountNumber.trim() || undefined,
      organisation: selectedOrgId || null,
    };
  };

  const handleSaveDraft = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!businessName.trim()) {
      setErrorMsg("Business name is required to save a draft application.");
      return;
    }
    try {
      setIsSavingDraft(true);
      setErrorMsg(null);
      const payload = getPayloadFromForm();
      const saved = await api.seller.saveDraft(payload);
      setApplication(saved);
      populateForm(saved);
      showSuccess("Seller application draft saved successfully.");
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to save application draft.");
    } finally {
      setIsSavingDraft(false);
    }
  };

  const handleSubmitApplication = async (e: React.FormEvent) => {
    e.preventDefault();
    // Validate required fields before submission
    if (!businessName.trim() || !contactName.trim() || !contactEmail.trim() || !addressLine1.trim() || !city.trim() || !postalCode.trim()) {
      setErrorMsg("Please complete all mandatory business and contact details before submitting.");
      return;
    }

    try {
      setIsSubmitting(true);
      setErrorMsg(null);
      // 1. Save draft updates first
      const payload = getPayloadFromForm();
      await api.seller.saveDraft(payload);
      // 2. Submit for review
      const res = await api.seller.submit();
      setApplication(res.application);
      populateForm(res.application);
      showSuccess("Application submitted successfully! Our compliance team will review your credentials.");
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to submit application.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAdminReview = async (action: "approve" | "reject") => {
    if (!reviewModalApp) return;
    if (action === "reject" && !rejectionReason.trim()) {
      setErrorMsg("A rejection reason is mandatory when rejecting a seller application.");
      return;
    }

    try {
      setIsReviewing(true);
      setErrorMsg(null);
      const updated = await api.seller.reviewApplication(reviewModalApp.id, {
        action,
        rejection_reason: action === "reject" ? rejectionReason.trim() : undefined,
      });

      showSuccess(`Application for ${updated.business_name} has been ${action === "approve" ? "APPROVED (Seller role granted)" : "REJECTED"}.`);
      setReviewModalApp(null);
      setRejectionReason("");
      await loadAdminApplications();
      if (application?.id === updated.id) {
        setApplication(updated);
      }
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : `Failed to ${action} application.`);
    } finally {
      setIsReviewing(false);
    }
  };

  const isFormLocked = application?.status === "PENDING" || application?.status === "APPROVED";

  return (
    <div className="p-6 max-w-[1440px] mx-auto space-y-6">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-amber-400 text-slate-950 font-black text-xs">
              Phase 2
            </span>
            <h1 className="text-xl font-black text-slate-950">Seller Onboarding & Verification</h1>
          </div>
          <p className="text-xs text-slate-600 mt-1">
            Register your dealership or workshop as a verified seller to unlock catalogue listings and commercial transactions.
          </p>
        </div>

        {/* Tab switch for Staff / Admin */}
        {isStaffOrAdmin && (
          <div className="flex items-center p-1 bg-slate-100 rounded-xl">
            <button
              onClick={() => setActiveTab("my_application")}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all ${
                activeTab === "my_application"
                  ? "bg-white text-slate-950 shadow-sm"
                  : "text-slate-600 hover:text-slate-950"
              }`}
            >
              My Application
            </button>
            <button
              onClick={() => setActiveTab("admin_queue")}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all ${
                activeTab === "admin_queue"
                  ? "bg-white text-slate-950 shadow-sm"
                  : "text-slate-600 hover:text-slate-950"
              }`}
            >
              Review Applications Queue
            </button>
          </div>
        )}
      </div>

      {/* Notifications */}
      {successMsg && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-300 text-emerald-900 text-xs font-semibold flex items-center gap-2 shadow-sm animate-in fade-in">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {errorMsg && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-300 text-rose-900 text-xs font-semibold flex items-center justify-between shadow-sm animate-in fade-in">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{errorMsg}</span>
          </div>
          <button onClick={() => setErrorMsg(null)} className="text-rose-500 hover:text-rose-700">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* ==================================================== */}
      {/* View 1: My Seller Application Form & Status          */}
      {/* ==================================================== */}
      {activeTab === "my_application" && (
        <div className="space-y-6">
          {/* Status Stepper / Banner */}
          {isLoadingApp ? (
            <div className="p-12 bg-white rounded-2xl border border-slate-200 text-center space-y-3">
              <div className="w-6 h-6 border-2 border-amber-400 border-t-transparent rounded-full animate-spin mx-auto"></div>
              <p className="text-xs font-bold text-slate-700">Verifying onboarding status from backend...</p>
            </div>
          ) : application ? (
            <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  {application.status === "APPROVED" ? (
                    <div className="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-600 flex items-center justify-center">
                      <ShieldCheck className="w-6 h-6" />
                    </div>
                  ) : application.status === "PENDING" ? (
                    <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-600 flex items-center justify-center">
                      <Clock className="w-6 h-6" />
                    </div>
                  ) : application.status === "REJECTED" ? (
                    <div className="w-10 h-10 rounded-xl bg-rose-100 text-rose-600 flex items-center justify-center">
                      <XCircle className="w-6 h-6" />
                    </div>
                  ) : (
                    <div className="w-10 h-10 rounded-xl bg-slate-100 text-slate-600 flex items-center justify-center">
                      <FileText className="w-6 h-6" />
                    </div>
                  )}

                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                      Application Status
                    </span>
                    <h3 className="text-base font-black text-slate-950 flex items-center gap-2">
                      <span>{application.business_name}</span>
                      <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase ${
                        application.status === "APPROVED"
                          ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                          : application.status === "PENDING"
                          ? "bg-amber-100 text-amber-800 border border-amber-300"
                          : application.status === "REJECTED"
                          ? "bg-rose-100 text-rose-800 border border-rose-300"
                          : "bg-slate-100 text-slate-700 border border-slate-300"
                      }`}>
                        {application.status}
                      </span>
                    </h3>
                  </div>
                </div>

                <div className="text-xs text-slate-500 sm:text-right">
                  <div>Created: <span className="font-semibold text-slate-800">{new Date(application.created_at).toLocaleDateString()}</span></div>
                  {application.submitted_at && (
                    <div>Submitted: <span className="font-semibold text-slate-800">{new Date(application.submitted_at).toLocaleDateString()}</span></div>
                  )}
                </div>
              </div>

              {/* Status Explanation Alerts */}
              {application.status === "APPROVED" && (
                <div className="p-4 bg-emerald-50 border border-emerald-300 rounded-xl text-emerald-900 text-xs space-y-1">
                  <div className="font-bold flex items-center gap-1.5">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                    <span>Verified Seller Privileges Activated</span>
                  </div>
                  <p className="text-[11px] text-emerald-800">
                    Your organisation has been verified by the DriverXtra compliance team. The <code className="font-mono font-bold">SELLER</code> role has been assigned to your account.
                  </p>
                </div>
              )}

              {application.status === "PENDING" && (
                <div className="p-4 bg-amber-50 border border-amber-300 rounded-xl text-amber-900 text-xs space-y-1">
                  <div className="font-bold flex items-center gap-1.5">
                    <Clock className="w-4 h-4 text-amber-600" />
                    <span>Application Under Active Review</span>
                  </div>
                  <p className="text-[11px] text-amber-800">
                    Your submission is queued for compliance verification. You will be notified once a marketplace administrator completes the review. Form fields are locked while under review.
                  </p>
                </div>
              )}

              {application.status === "REJECTED" && (
                <div className="p-4 bg-rose-50 border border-rose-300 rounded-xl text-rose-900 text-xs space-y-2">
                  <div className="font-bold flex items-center gap-1.5">
                    <ShieldAlert className="w-4 h-4 text-rose-600" />
                    <span>Application Requires Correction</span>
                  </div>
                  <div className="p-3 bg-white/80 rounded-lg border border-rose-200">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-rose-700 block mb-0.5">
                      Reviewer Reason:
                    </span>
                    <p className="text-xs font-semibold text-rose-950 font-mono">
                      &ldquo;{application.rejection_reason}&rdquo;
                    </p>
                  </div>
                  <p className="text-[11px] text-rose-800">
                    You can update the fields below to address the compliance requirements and resubmit for review.
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-3">
              <span className="text-[10px] font-black uppercase tracking-wider text-amber-500">
                New Seller Onboarding
              </span>
              <h3 className="text-base font-black text-slate-950">
                Apply to Sell on DriverXtra
              </h3>
              <p className="text-xs text-slate-600 max-w-2xl">
                To list vehicles, spare parts, and workshop inventory, please complete the commercial profile below. Save your application as a draft at any time, or submit directly for administrative verification.
              </p>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmitApplication} className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-6">
            {/* Section 1: Business Identity */}
            <div className="space-y-4">
              <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
                <Briefcase className="w-4 h-4 text-amber-500" />
                <h4 className="text-xs font-black uppercase tracking-wider text-slate-950">
                  1. Business Identity & Registration
                </h4>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Registered Business Name *</label>
                  <input
                    type="text"
                    placeholder="e.g. Apex Auto Holdings Ltd"
                    value={businessName}
                    onChange={(e) => setBusinessName(e.target.value)}
                    disabled={isFormLocked}
                    required
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Trading Name (Optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. Apex Parts"
                    value={tradingName}
                    onChange={(e) => setTradingName(e.target.value)}
                    disabled={isFormLocked}
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Business Entity Type *</label>
                  <select
                    value={businessType}
                    onChange={(e) => setBusinessType(e.target.value)}
                    disabled={isFormLocked}
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  >
                    <option value="SOLE_TRADER">Sole Trader</option>
                    <option value="PARTNERSHIP">Partnership</option>
                    <option value="LTD">Limited Company (Ltd)</option>
                    <option value="PLC">Public Limited Company (PLC)</option>
                    <option value="LLP">Limited Liability Partnership (LLP)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Companies House / Reg Number</label>
                  <input
                    type="text"
                    placeholder="e.g. 09182391"
                    value={registrationNumber}
                    onChange={(e) => setRegistrationNumber(e.target.value)}
                    disabled={isFormLocked}
                    className="w-full px-3 py-2 text-xs font-mono rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">VAT Registration Number</label>
                  <input
                    type="text"
                    placeholder="e.g. GB 982 1294 00"
                    value={vatNumber}
                    onChange={(e) => setVatNumber(e.target.value)}
                    disabled={isFormLocked}
                    className="w-full px-3 py-2 text-xs font-mono rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>
              </div>

              {/* Organisation Link */}
              {organisations.length > 0 && (
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Associate With Organisation (Optional)</label>
                  <select
                    value={selectedOrgId}
                    onChange={(e) => setSelectedOrgId(e.target.value)}
                    disabled={isFormLocked}
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  >
                    <option value="">-- Standalone Seller Account --</option>
                    {organisations.map((org) => (
                      <option key={org.id} value={org.id}>
                        {org.name} ({org.type})
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {/* Section 2: Contact Person */}
            <div className="space-y-4 pt-2">
              <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
                <User className="w-4 h-4 text-amber-500" />
                <h4 className="text-xs font-black uppercase tracking-wider text-slate-950">
                  2. Authorized Contact Representative
                </h4>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Contact Full Name *</label>
                  <input
                    type="text"
                    value={contactName}
                    onChange={(e) => setContactName(e.target.value)}
                    disabled={isFormLocked}
                    required
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Official Business Email *</label>
                  <input
                    type="email"
                    value={contactEmail}
                    onChange={(e) => setContactEmail(e.target.value)}
                    disabled={isFormLocked}
                    required
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Direct Phone Number *</label>
                  <input
                    type="tel"
                    value={contactPhone}
                    onChange={(e) => setContactPhone(e.target.value)}
                    disabled={isFormLocked}
                    required
                    placeholder="+44 7700 900123"
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>
              </div>
            </div>

            {/* Section 3: Commercial Address */}
            <div className="space-y-4 pt-2">
              <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
                <MapPin className="w-4 h-4 text-amber-500" />
                <h4 className="text-xs font-black uppercase tracking-wider text-slate-950">
                  3. Commercial Trading Address
                </h4>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Address Line 1 *</label>
                  <input
                    type="text"
                    value={addressLine1}
                    onChange={(e) => setAddressLine1(e.target.value)}
                    disabled={isFormLocked}
                    required
                    placeholder="Building name, street"
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Address Line 2</label>
                  <input
                    type="text"
                    value={addressLine2}
                    onChange={(e) => setAddressLine2(e.target.value)}
                    disabled={isFormLocked}
                    placeholder="Suite, unit, floor"
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">City / Town *</label>
                  <input
                    type="text"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    disabled={isFormLocked}
                    required
                    placeholder="London"
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">County / Province</label>
                  <input
                    type="text"
                    value={stateProvince}
                    onChange={(e) => setStateProvince(e.target.value)}
                    disabled={isFormLocked}
                    placeholder="Greater London"
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Postal Code *</label>
                  <input
                    type="text"
                    value={postalCode}
                    onChange={(e) => setPostalCode(e.target.value)}
                    disabled={isFormLocked}
                    required
                    placeholder="EC1A 1BB"
                    className="w-full px-3 py-2 text-xs uppercase font-mono rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Country *</label>
                  <input
                    type="text"
                    value={country}
                    onChange={(e) => setCountry(e.target.value)}
                    disabled={isFormLocked}
                    required
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>
              </div>
            </div>

            {/* Section 4: Settlement Banking Information */}
            <div className="space-y-4 pt-2">
              <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
                <Landmark className="w-4 h-4 text-amber-500" />
                <h4 className="text-xs font-black uppercase tracking-wider text-slate-950">
                  4. Commercial Settlement Account
                </h4>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Account Holder Name</label>
                  <input
                    type="text"
                    placeholder="Apex Auto Holdings Ltd"
                    value={bankAccountName}
                    onChange={(e) => setBankAccountName(e.target.value)}
                    disabled={isFormLocked}
                    className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Sort Code</label>
                  <input
                    type="text"
                    placeholder="20-00-00"
                    value={bankSortCode}
                    onChange={(e) => setBankSortCode(e.target.value)}
                    disabled={isFormLocked}
                    className="w-full px-3 py-2 text-xs font-mono rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Account Number</label>
                  <input
                    type="text"
                    placeholder="8 digits"
                    value={bankAccountNumber}
                    onChange={(e) => setBankAccountNumber(e.target.value)}
                    disabled={isFormLocked}
                    className="w-full px-3 py-2 text-xs font-mono rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:bg-slate-100"
                  />
                </div>
              </div>
            </div>

            {/* Action Bar */}
            {!isFormLocked && (
              <div className="pt-4 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={handleSaveDraft}
                  disabled={isSavingDraft || isSubmitting}
                  className="w-full sm:w-auto px-4 py-2.5 rounded-xl border border-slate-300 hover:bg-slate-50 text-slate-700 font-bold text-xs flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
                >
                  <Save className="w-3.5 h-3.5 text-slate-500" />
                  <span>{isSavingDraft ? "Saving Draft..." : "Save as Draft"}</span>
                </button>

                <button
                  type="submit"
                  disabled={isSubmitting || isSavingDraft}
                  className="w-full sm:w-auto bg-amber-400 hover:bg-amber-300 text-slate-950 font-bold px-6 py-2.5 rounded-xl text-xs flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-50"
                >
                  {isSubmitting ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Submitting...</span>
                    </>
                  ) : (
                    <>
                      <Send className="w-3.5 h-3.5" />
                      <span>{application?.status === "REJECTED" ? "Update & Resubmit for Review" : "Submit Application for Review"}</span>
                    </>
                  )}
                </button>
              </div>
            )}
          </form>
        </div>
      )}

      {/* ==================================================== */}
      {/* View 2: Staff / Admin Review Queue Table            */}
      {/* ==================================================== */}
      {activeTab === "admin_queue" && isStaffOrAdmin && (
        <div className="space-y-4">
          {/* Filter Bar */}
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-600">Filter Status:</span>
              <select
                value={adminFilterStatus}
                onChange={(e) => setAdminFilterStatus(e.target.value)}
                className="px-3 py-1.5 text-xs rounded-xl border border-slate-300 bg-white font-medium focus:outline-none focus:ring-2 focus:ring-amber-400"
              >
                <option value="">All Applications</option>
                <option value="PENDING">Pending Review</option>
                <option value="APPROVED">Approved</option>
                <option value="REJECTED">Rejected</option>
                <option value="DRAFT">Draft</option>
              </select>
            </div>

            <button
              onClick={loadAdminApplications}
              disabled={isLoadingAdminList}
              className="p-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-bold inline-flex items-center gap-1.5 self-start sm:self-auto"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoadingAdminList ? "animate-spin text-amber-500" : ""}`} />
              <span>Refresh Queue</span>
            </button>
          </div>

          {/* Table */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 border-b border-slate-200 uppercase font-bold text-[10px] tracking-wider">
                  <tr>
                    <th className="py-3 px-4">Applicant</th>
                    <th className="py-3 px-4">Business Name</th>
                    <th className="py-3 px-4">Entity Type</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Submitted</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {isLoadingAdminList ? (
                    <tr>
                      <td colSpan={6} className="py-12 text-center text-slate-500">
                        <div className="w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
                        <span>Loading applications from backend...</span>
                      </td>
                    </tr>
                  ) : adminApplications.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-12 text-center text-slate-400 italic">
                        No seller applications found matching current filter.
                      </td>
                    </tr>
                  ) : (
                    adminApplications.map((app) => (
                      <tr key={app.id} className="hover:bg-slate-50/70 transition-colors">
                        <td className="py-3 px-4">
                          <div className="font-bold text-slate-900">{app.user_full_name || app.contact_name}</div>
                          <div className="text-[11px] text-slate-500 font-mono">{app.user_email}</div>
                        </td>
                        <td className="py-3 px-4 font-bold text-slate-950">
                          {app.business_name}
                          {app.trading_name && (
                            <span className="text-[11px] font-normal text-slate-500 block">
                              t/a {app.trading_name}
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-slate-600 font-medium">
                          {app.business_type_display || app.business_type}
                        </td>
                        <td className="py-3 px-4">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-black uppercase ${
                            app.status === "APPROVED"
                              ? "bg-emerald-100 text-emerald-800"
                              : app.status === "PENDING"
                              ? "bg-amber-100 text-amber-800"
                              : app.status === "REJECTED"
                              ? "bg-rose-100 text-rose-800"
                              : "bg-slate-100 text-slate-700"
                          }`}>
                            {app.status}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-slate-500 text-[11px]">
                          {app.submitted_at ? new Date(app.submitted_at).toLocaleDateString() : "Draft"}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={() => {
                              setReviewModalApp(app);
                              setRejectionReason(app.rejection_reason || "");
                            }}
                            className="bg-slate-950 hover:bg-slate-800 text-white font-bold px-3 py-1.5 rounded-lg text-xs inline-flex items-center gap-1 shadow-sm"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            <span>Review</span>
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ==================================================== */}
      {/* Modal: Admin Application Review                     */}
      {/* ==================================================== */}
      {reviewModalApp && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-5 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <span className="text-[10px] font-black uppercase tracking-wider text-amber-500">
                  Compliance Verification
                </span>
                <h3 className="text-base font-black text-slate-950">
                  Review Seller Application
                </h3>
              </div>
              <button
                onClick={() => setReviewModalApp(null)}
                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Application Details Summary */}
            <div className="space-y-3 bg-slate-50 p-4 rounded-xl border border-slate-200 text-xs">
              <div className="grid grid-cols-2 gap-2 pb-2 border-b border-slate-200">
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase font-bold">Business Name</span>
                  <span className="font-bold text-slate-950">{reviewModalApp.business_name}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase font-bold">Entity Type</span>
                  <span className="font-bold text-slate-800">{reviewModalApp.business_type_display || reviewModalApp.business_type}</span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 pb-2 border-b border-slate-200">
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase font-bold">Company Reg</span>
                  <span className="font-mono font-bold text-slate-800">{reviewModalApp.registration_number || "None"}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase font-bold">VAT Number</span>
                  <span className="font-mono font-bold text-slate-800">{reviewModalApp.vat_number || "None"}</span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 pb-2 border-b border-slate-200">
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase font-bold">Contact Name</span>
                  <span className="font-bold text-slate-800">{reviewModalApp.contact_name}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase font-bold">Contact Email</span>
                  <span className="font-mono text-slate-800">{reviewModalApp.contact_email}</span>
                </div>
              </div>

              <div>
                <span className="text-slate-400 block text-[10px] uppercase font-bold">Trading Address</span>
                <span className="font-medium text-slate-800">
                  {reviewModalApp.business_address_line1}, {reviewModalApp.business_address_line2 ? `${reviewModalApp.business_address_line2}, ` : ""}{reviewModalApp.business_city}, {reviewModalApp.business_postal_code}, {reviewModalApp.business_country}
                </span>
              </div>
            </div>

            {/* Self-approval protection warning */}
            {reviewModalApp.user_email === user?.email && !user?.is_superuser && (
              <div className="p-3 bg-amber-50 border border-amber-300 rounded-xl text-amber-900 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
                <span>Security rule: You cannot approve your own seller application. Another staff member must adjudicate.</span>
              </div>
            )}

            {/* Rejection Reason Input */}
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Rejection Reason (Required if rejecting)
              </label>
              <textarea
                rows={3}
                placeholder="Specify what document or requirement is missing or failed verification..."
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-xl border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-amber-400"
              />
            </div>

            {/* Modal Actions */}
            <div className="pt-3 border-t border-slate-100 flex items-center justify-between">
              <button
                type="button"
                onClick={() => setReviewModalApp(null)}
                className="px-4 py-2 text-xs font-bold text-slate-600 hover:text-slate-800"
              >
                Close
              </button>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleAdminReview("reject")}
                  disabled={isReviewing}
                  className="bg-rose-600 hover:bg-rose-700 text-white font-bold px-4 py-2 rounded-xl text-xs flex items-center gap-1.5 transition-colors shadow-sm disabled:opacity-50"
                >
                  <XCircle className="w-3.5 h-3.5" />
                  <span>Reject Application</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleAdminReview("approve")}
                  disabled={isReviewing || reviewModalApp.user_email === user?.email}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-4 py-2 rounded-xl text-xs flex items-center gap-1.5 transition-colors shadow-sm disabled:opacity-50"
                  title={reviewModalApp.user_email === user?.email ? "You cannot review or approve your own application" : undefined}
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>Approve & Grant Seller Role</span>
                </button>
              </div>
            </div>
            {reviewModalApp.user_email === user?.email && (
              <p className="text-[11px] text-amber-700 bg-amber-50 p-2 rounded-lg border border-amber-200 mt-2 font-medium">
                Self-approval protection active: You cannot review or approve your own application. Another administrator must review this submission.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
