"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  api,
  ApiError,
  BackendOrganisation,
  BackendOrganisationMember,
  DealerOrganisationProfile,
} from "@/lib/api/client";
import {
  Building2,
  Users,
  Plus,
  ArrowLeft,
  UserPlus,
  Shield,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Lock,
  Globe,
  Tag,
  Calendar,
  Award,
  FileText,
  Clock,
  Sparkles,
  AlertTriangle,
  X,
} from "lucide-react";

export default function Phase1OrganisationsView() {
  const { user } = useAuth();

  const [organisations, setOrganisations] = useState<BackendOrganisation[]>([]);
  const [selectedOrg, setSelectedOrg] = useState<BackendOrganisation | null>(null);
  const [members, setMembers] = useState<BackendOrganisationMember[]>([]);

  const [isLoadingOrgs, setIsLoadingOrgs] = useState(true);
  const [isLoadingMembers, setIsLoadingMembers] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Create Organisation Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [newOrgType, setNewOrgType] = useState<BackendOrganisation["type"]>("DEALER_GROUP");
  const [newOrgJurisdiction, setNewOrgJurisdiction] = useState("GB-ENG");
  const [isCreatingOrg, setIsCreatingOrg] = useState(false);
  const [createOrgError, setCreateOrgError] = useState<string | null>(null);

  // Add Member State
  const [targetEmail, setTargetEmail] = useState("");
  const [targetRole, setTargetRole] = useState<"ADMIN" | "MEMBER" | "TECHNICIAN" | "ANALYST">("MEMBER");
  const [isAddingMember, setIsAddingMember] = useState(false);
  const [addMemberSuccess, setAddMemberSuccess] = useState<string | null>(null);
  const [addMemberError, setAddMemberError] = useState<string | null>(null);

  // Dealer Verification & Application State (Phase 7.1)
  const [dealerProfile, setDealerProfile] = useState<DealerOrganisationProfile | null>(null);
  const [isLoadingDealerProfile, setIsLoadingDealerProfile] = useState(false);
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [appRegNumber, setAppRegNumber] = useState("");
  const [appTaxId, setAppTaxId] = useState("");
  const [appWebsite, setAppWebsite] = useState("");
  const [appContactEmail, setAppContactEmail] = useState("");
  const [appContactPhone, setAppContactPhone] = useState("");
  const [appNotes, setAppNotes] = useState("");
  const [appRequestedTier, setAppRequestedTier] = useState("STANDARD");
  const [isSubmittingApp, setIsSubmittingApp] = useState(false);
  const [appSubmitError, setAppSubmitError] = useState<string | null>(null);
  const [appSubmitSuccess, setAppSubmitSuccess] = useState<string | null>(null);

  // Fetch Organisations accessible to the authenticated user
  const fetchOrganisations = useCallback(async () => {
    setIsLoadingOrgs(true);
    setErrorMsg(null);
    try {
      const data = await api.organisations.list();
      setOrganisations(data.results || []);
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Failed to load organisations.";
      setErrorMsg(msg);
    } finally {
      setIsLoadingOrgs(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    api.organisations.list()
      .then((data) => {
        if (!ignore) {
          setOrganisations(data.results || []);
          setIsLoadingOrgs(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          const msg = err instanceof ApiError ? err.message : "Failed to load organisations.";
          setErrorMsg(msg);
          setIsLoadingOrgs(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  // Fetch Members for Selected Organisation
  const fetchMembers = useCallback(async (orgId: string) => {
    setIsLoadingMembers(true);
    setAddMemberError(null);
    try {
      const memberList = await api.organisations.getMembers(orgId);
      setMembers(memberList || []);
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Failed to load organisation members.";
      setAddMemberError(msg);
    } finally {
      setIsLoadingMembers(false);
    }
  }, []);

  const fetchDealerProfile = useCallback(async (orgId: string) => {
    setIsLoadingDealerProfile(true);
    try {
      const res = await api.marketplace.getMyDealerApplication(orgId);
      if (res && res.has_application && res.application) {
        setDealerProfile(res.application);
      } else {
        setDealerProfile(null);
      }
    } catch {
      setDealerProfile(null);
    } finally {
      setIsLoadingDealerProfile(false);
    }
  }, []);

  const handleSelectOrg = (org: BackendOrganisation) => {
    setSelectedOrg(org);
    setAddMemberSuccess(null);
    setAddMemberError(null);
    setAppSubmitSuccess(null);
    setAppSubmitError(null);
    fetchMembers(org.id);
    fetchDealerProfile(org.id);
  };

  const handleBackToList = () => {
    setSelectedOrg(null);
    setMembers([]);
    setDealerProfile(null);
    setAddMemberSuccess(null);
    setAddMemberError(null);
    setAppSubmitSuccess(null);
    setAppSubmitError(null);
    fetchOrganisations();
  };

  const handleApplyDealer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedOrg) return;
    setIsSubmittingApp(true);
    setAppSubmitError(null);
    try {
      const profile = await api.marketplace.submitDealerApplication({
        organisation_id: selectedOrg.id,
        company_registration_number: appRegNumber.trim(),
        tax_id: appTaxId.trim(),
        website_url: appWebsite.trim(),
        contact_email: appContactEmail.trim() || undefined,
        contact_phone: appContactPhone.trim(),
        notes: appNotes.trim(),
        requested_tier: appRequestedTier,
      });
      setDealerProfile(profile);
      setShowApplyModal(false);
      setAppSubmitSuccess("Dealer verification application submitted successfully. An administrator will review your application.");
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Failed to submit dealer verification application.";
      setAppSubmitError(msg);
    } finally {
      setIsSubmittingApp(false);
    }
  };

  // Handle Organisation Creation
  const handleCreateOrg = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newOrgName.trim()) {
      setCreateOrgError("Organisation name is required.");
      return;
    }

    setIsCreatingOrg(true);
    setCreateOrgError(null);

    try {
      const created = await api.organisations.create({
        name: newOrgName.trim(),
        type: newOrgType,
        jurisdiction: newOrgJurisdiction.trim() || "GB-ENG",
      });

      setShowCreateModal(false);
      setNewOrgName("");
      setIsCreatingOrg(false);

      // Refresh list and select the newly created organisation
      await fetchOrganisations();
      handleSelectOrg(created);
    } catch (err: unknown) {
      setIsCreatingOrg(false);
      const msg = err instanceof ApiError ? err.message : "Failed to create organisation.";
      setCreateOrgError(msg);
    }
  };

  // Handle Adding Member to Organisation
  const handleAddMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedOrg) return;

    if (!targetEmail.trim()) {
      setAddMemberError("User email is required.");
      return;
    }

    setIsAddingMember(true);
    setAddMemberError(null);
    setAddMemberSuccess(null);

    try {
      const res = await api.organisations.addMember(selectedOrg.id, {
        email: targetEmail.trim().toLowerCase(),
        role: targetRole,
      });

      setIsAddingMember(false);
      setAddMemberSuccess(res.message || `User ${targetEmail} added as ${targetRole}.`);
      setTargetEmail("");

      // Refresh member list
      fetchMembers(selectedOrg.id);

      // Refresh orgs list to update member counts
      fetchOrganisations();
    } catch (err: unknown) {
      setIsAddingMember(false);
      const msg = err instanceof ApiError ? err.message : "Failed to add member to organisation.";
      setAddMemberError(msg);
    }
  };

  // Permission helper: only OWNER, ADMIN, or platform admin can add members
  const canManageMembers = selectedOrg && (
    selectedOrg.user_role === "OWNER" ||
    selectedOrg.user_role === "ADMIN" ||
    user?.is_staff ||
    user?.is_superuser
  );

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* ------------------------------------------------------------- */}
      {/* VIEW 1: ORGANISATIONS LIST VIEW                               */}
      {/* ------------------------------------------------------------- */}
      {!selectedOrg ? (
        <div className="space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
            <div>
              <h1 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-2">
                <Building2 className="w-5 h-5 text-amber-500" />
                <span>Organisations & Tenant Management</span>
              </h1>
              <p className="text-xs text-slate-500 mt-0.5">
                Organisation & Team Management • Manage your business entity and team member access
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={fetchOrganisations}
                disabled={isLoadingOrgs}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold transition-colors shadow-sm disabled:opacity-50"
                title="Reload organisations list"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoadingOrgs ? "animate-spin text-amber-500" : ""}`} />
                <span>Refresh</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setShowCreateModal(true);
                  setCreateOrgError(null);
                }}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-amber-400 hover:bg-amber-500 text-slate-950 text-xs font-black transition-all shadow hover:shadow-amber-400/20"
              >
                <Plus className="w-4 h-4" />
                <span>Create Organisation</span>
              </button>
            </div>
          </div>

          {/* Top-Level Error */}
          {errorMsg && (
            <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-300 text-rose-900 text-xs font-semibold flex items-center gap-2 shadow-sm">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Loading State */}
          {isLoadingOrgs ? (
            <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center text-xs text-slate-500">
              <div className="w-6 h-6 border-2 border-amber-400 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
              <span>Loading organisations...</span>
            </div>
          ) : organisations.length === 0 ? (
            /* Empty State */
            <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-amber-50 border border-amber-200 flex items-center justify-center mx-auto text-amber-600">
                <Building2 className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-900">No Organisations Found</h3>
                <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                  You are not currently a member of any organisation. Create an organisation to establish an entity and manage team roles.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowCreateModal(true)}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-amber-400 hover:bg-amber-500 text-slate-950 text-xs font-bold shadow transition-all"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Create Your First Organisation</span>
              </button>
            </div>
          ) : (
            /* Organisation Cards Grid */
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {organisations.map((org) => {
                const roleBadgeColor =
                  org.user_role === "OWNER"
                    ? "bg-amber-100 text-amber-900 border-amber-300"
                    : org.user_role === "ADMIN"
                    ? "bg-purple-100 text-purple-900 border-purple-300"
                    : "bg-slate-100 text-slate-800 border-slate-200";

                return (
                  <div
                    key={org.id}
                    className="bg-white rounded-2xl border border-slate-200 hover:border-amber-400/60 p-5 shadow-sm transition-all flex flex-col justify-between"
                  >
                    <div>
                      {/* Top Header of Card */}
                      <div className="flex items-start justify-between gap-2 pb-3 border-b border-slate-100">
                        <div className="min-w-0">
                          <h3 className="text-sm font-bold text-slate-900 truncate">
                            {org.name}
                          </h3>
                          <p className="text-[11px] font-mono text-slate-400 truncate mt-0.5">
                            slug: {org.slug}
                          </p>
                        </div>
                        <span
                          className={`text-[10px] font-black px-2 py-0.5 rounded border shrink-0 ${roleBadgeColor}`}
                        >
                          {org.user_role || "MEMBER"}
                        </span>
                      </div>

                      {/* Metadata Details */}
                      <div className="py-3 space-y-2 text-xs text-slate-600">
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] text-slate-400 flex items-center gap-1">
                            <Tag className="w-3 h-3" /> Type:
                          </span>
                          <span className="font-semibold text-slate-800">{org.type}</span>
                        </div>

                        <div className="flex items-center justify-between">
                          <span className="text-[11px] text-slate-400 flex items-center gap-1">
                            <Globe className="w-3 h-3" /> Jurisdiction:
                          </span>
                          <span className="font-semibold text-slate-800">{org.jurisdiction}</span>
                        </div>

                        <div className="flex items-center justify-between">
                          <span className="text-[11px] text-slate-400 flex items-center gap-1">
                            <Users className="w-3 h-3" /> Active Members:
                          </span>
                          <span className="font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded">
                            {org.member_count}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Action Button */}
                    <div className="pt-3 border-t border-slate-100">
                      <button
                        type="button"
                        onClick={() => handleSelectOrg(org)}
                        className="w-full h-9 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold flex items-center justify-center gap-1.5 transition-colors shadow-sm"
                      >
                        <Users className="w-3.5 h-3.5 text-amber-400" />
                        <span>View Members & Manage</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : (
        /* ------------------------------------------------------------- */
        /* VIEW 2: SELECTED ORGANISATION & MEMBERS MANAGEMENT            */
        /* ------------------------------------------------------------- */
        <div className="space-y-6">
          {/* Back Button & Selected Org Banner */}
          <div className="flex items-center gap-3 pb-3 border-b border-slate-200">
            <button
              type="button"
              onClick={handleBackToList}
              className="p-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 transition-colors shadow-sm"
              title="Return to organisations list"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-black text-slate-900">{selectedOrg.name}</h1>
                <span className="text-[10px] font-black px-2 py-0.5 rounded border bg-amber-100 text-amber-900 border-amber-300">
                  Your Role: {selectedOrg.user_role || "MEMBER"}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Type: {selectedOrg.type} • Jurisdiction: {selectedOrg.jurisdiction} • ID: <code className="font-mono text-[10px]">{selectedOrg.id}</code>
              </p>
            </div>
          </div>

          {/* Feedback Messages */}
          {addMemberSuccess && (
            <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-300 text-emerald-900 text-xs font-semibold flex items-center gap-2 shadow-sm animate-in fade-in">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span>{addMemberSuccess}</span>
            </div>
          )}

          {addMemberError && (
            <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-300 text-rose-900 text-xs font-semibold flex items-center gap-2 shadow-sm animate-in fade-in">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{addMemberError}</span>
            </div>
          )}

          {appSubmitSuccess && (
            <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-300 text-emerald-900 text-xs font-semibold flex items-center gap-2 shadow-sm animate-in fade-in">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span>{appSubmitSuccess}</span>
            </div>
          )}

          {/* B2B Dealership Standing & Tier Verification Card (Phase 7.1) */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-amber-500/10 flex items-center justify-center text-amber-600">
                  <Award className="w-4 h-4" />
                </div>
                <div>
                  <h2 className="text-sm font-bold text-slate-900">B2B Dealership & Trade Tier Standing</h2>
                  <p className="text-[11px] text-slate-500">Commercial trade verification and wholesale pricing status</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => fetchDealerProfile(selectedOrg.id)}
                disabled={isLoadingDealerProfile}
                className="p-1.5 rounded-lg border border-slate-200 text-slate-500 hover:text-slate-800 transition-colors"
                title="Refresh dealer verification status"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoadingDealerProfile ? "animate-spin text-amber-500" : ""}`} />
              </button>
            </div>

            <div className="p-5">
              {isLoadingDealerProfile ? (
                <div className="py-6 text-center text-xs text-slate-500 flex items-center justify-center gap-2">
                  <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin"></div>
                  <span>Checking dealer verification standing...</span>
                </div>
              ) : dealerProfile?.is_verified_dealer && dealerProfile.status === "ACTIVE" ? (
                <div className="p-4 rounded-xl bg-gradient-to-r from-emerald-50 via-teal-50 to-slate-50 border border-emerald-200 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-600 text-white shadow-sm">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Verified Active Dealer
                      </span>
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-900 border border-amber-300">
                        <Award className="w-3.5 h-3.5 text-amber-600" />
                        Tier: {dealerProfile.tier_details?.name || dealerProfile.dealer_tier?.name || "Standard Dealer"}
                      </span>
                    </div>
                    {dealerProfile.verified_at && (
                      <span className="text-[11px] text-slate-500">
                        Verified on {new Date(dealerProfile.verified_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>

                  <p className="text-xs text-slate-700 leading-relaxed">
                    This organisation is an approved commercial dealer partner. Eligible vehicles and spare parts are automatically discounted according to B2B pricing rules prior to statutory tax calculation (Indian GST / UK VAT).
                  </p>

                  <div className="pt-2 border-t border-emerald-200/60 flex items-center justify-between text-[11px] text-slate-600">
                    <span>
                      Baseline Discount: <strong className="text-slate-900 font-bold">{dealerProfile.tier_details?.baseline_discount_percentage ?? (dealerProfile.dealer_tier?.baseline_discount_percentage ?? "5.00")}%</strong>
                    </span>
                    {dealerProfile.custom_discount_cap && (
                      <span>
                        Discount Safety Cap: <strong className="text-slate-900 font-bold">{dealerProfile.custom_discount_cap}%</strong>
                      </span>
                    )}
                    {dealerProfile.verified_by_name && (
                      <span>
                        Verified By: <strong className="text-slate-900 font-bold">{dealerProfile.verified_by_name}</strong>
                      </span>
                    )}
                  </div>
                </div>
              ) : dealerProfile?.status === "PENDING" ? (
                <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-500 text-white shadow-sm">
                      <Clock className="w-3.5 h-3.5" />
                      Verification Application Pending Review
                    </span>
                    {dealerProfile.created_at && (
                      <span className="text-[11px] text-amber-800">
                        Submitted: {new Date(dealerProfile.created_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-amber-900 leading-relaxed">
                    Your dealer verification request is currently pending review by platform administrators. Once approved, trade tier pricing and stepped volume discounts will apply automatically.
                  </p>
                  {dealerProfile.application_data?.company_registration_number && (
                    <div className="text-[11px] text-amber-800 pt-1">
                      Registered Company: <strong>{dealerProfile.application_data.company_registration_number}</strong>
                      {dealerProfile.application_data.tax_id && ` • Tax ID: ${dealerProfile.application_data.tax_id}`}
                    </div>
                  )}
                </div>
              ) : dealerProfile?.status === "REJECTED" ? (
                <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-600 text-white shadow-sm">
                      <AlertTriangle className="w-3.5 h-3.5" />
                      Dealer Verification Rejected
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setAppRegNumber(dealerProfile.application_data?.company_registration_number || "");
                        setAppTaxId(dealerProfile.application_data?.tax_id || "");
                        setAppWebsite(dealerProfile.application_data?.website_url || "");
                        setAppContactEmail(dealerProfile.application_data?.contact_email || "");
                        setAppContactPhone(dealerProfile.application_data?.contact_phone || "");
                        setAppNotes(dealerProfile.application_data?.applicant_notes || "");
                        setShowApplyModal(true);
                      }}
                      className="text-xs font-bold text-rose-700 hover:text-rose-900 underline"
                    >
                      Update & Re-apply
                    </button>
                  </div>
                  <div className="p-3 rounded-lg bg-white border border-rose-200 text-xs text-rose-900">
                    <span className="font-bold">Reason for Rejection: </span>
                    <span>{dealerProfile.rejection_reason || "Application credentials could not be verified."}</span>
                  </div>
                </div>
              ) : (
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-amber-500" />
                      <span className="text-xs font-bold text-slate-900">Unlock B2B Wholesale & Dealership Pricing</span>
                    </div>
                    <p className="text-[11px] text-slate-500 max-w-xl">
                      Verified dealerships access exclusive commercial trade rate cards, stepped volume discounts on spare parts and vehicles, and statutory tax-exempt trade purchasing.
                    </p>
                  </div>
                  {selectedOrg.user_role === "OWNER" || selectedOrg.user_role === "ADMIN" || user?.is_staff ? (
                    <button
                      type="button"
                      onClick={() => {
                        setAppSubmitError(null);
                        setShowApplyModal(true);
                      }}
                      className="px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-600 text-slate-950 font-black text-xs flex items-center gap-1.5 transition-colors shadow-sm shrink-0"
                    >
                      <Award className="w-3.5 h-3.5" />
                      <span>Apply for Dealer Verification</span>
                    </button>
                  ) : (
                    <span className="text-[11px] text-slate-400 italic">
                      Contact organisation OWNER or ADMIN to request verification.
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Grid: Member List on Left, Add Member Form on Right */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left 2 Cols: Member Directory */}
            <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <Users className="w-4 h-4 text-amber-500" />
                  <h2 className="text-sm font-bold text-slate-900">
                    Active Organisation Members ({members.length})
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={() => fetchMembers(selectedOrg.id)}
                  disabled={isLoadingMembers}
                  className="p-1.5 rounded-lg border border-slate-200 text-slate-500 hover:text-slate-800 transition-colors"
                  title="Refresh member list"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isLoadingMembers ? "animate-spin text-amber-500" : ""}`} />
                </button>
              </div>

              {isLoadingMembers ? (
                <div className="py-8 text-center text-xs text-slate-500">
                  <div className="w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
                  <span>Loading members...</span>
                </div>
              ) : members.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-400">
                  No members found in this organisation.
                </div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {members.map((m) => (
                    <div
                      key={m.id}
                      className="py-3 flex items-center justify-between gap-3 text-xs"
                    >
                      <div className="min-w-0">
                        <div className="font-bold text-slate-900 truncate">
                          {m.full_name || m.email}
                        </div>
                        <div className="text-[11px] text-slate-500 truncate">
                          {m.email}
                        </div>
                        <div className="text-[10px] text-slate-400 mt-0.5 flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          <span>Joined: {new Date(m.joined_at).toLocaleDateString()}</span>
                        </div>
                      </div>

                      <div className="shrink-0 flex items-center gap-2">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                          m.role === "OWNER"
                            ? "bg-amber-100 text-amber-950 border-amber-300"
                            : m.role === "ADMIN"
                            ? "bg-purple-100 text-purple-950 border-purple-300"
                            : "bg-slate-100 text-slate-700 border-slate-200"
                        }`}>
                          {m.role}
                        </span>
                        {m.is_active && (
                          <span className="w-2 h-2 rounded-full bg-emerald-500" title="Active"></span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Right Col: Add Member Form (Guarded by Permission) */}
            <div className="bg-slate-50 rounded-2xl border border-slate-200 p-6 space-y-4">
              <div className="pb-3 border-b border-slate-200">
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                  <UserPlus className="w-4 h-4 text-amber-500" />
                  <span>Add Organisation Member</span>
                </h3>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Invite registered users and assign operational team permissions.
                </p>
              </div>

              {canManageMembers ? (
                <form onSubmit={handleAddMember} className="space-y-3.5">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">
                      Platform User Email <span className="text-amber-500">*</span>
                    </label>
                    <input
                      type="email"
                      value={targetEmail}
                      onChange={(e) => setTargetEmail(e.target.value)}
                      required
                      placeholder="registered.user@domain.com"
                      className="w-full h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 bg-white"
                    />
                    <p className="text-[10px] text-slate-400 mt-1">
                      The user must already be registered on DriverXtra.
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">
                      Assigned Role <span className="text-amber-500">*</span>
                    </label>
                    <select
                      value={targetRole}
                      onChange={(e) => setTargetRole(e.target.value as "ADMIN" | "MEMBER" | "TECHNICIAN" | "ANALYST")}
                      className="w-full h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 bg-white font-medium"
                    >
                      <option value="MEMBER">Member (Standard Access)</option>
                      <option value="ADMIN">Admin (Team Administration)</option>
                      <option value="TECHNICIAN">Technician (Workshop Bay)</option>
                      <option value="ANALYST">Analyst (Fleet / Operations)</option>
                    </select>
                    <div className="mt-1 flex items-center gap-1 text-[10px] text-slate-500">
                      <Lock className="w-3 h-3 text-slate-400" />
                      <span>Owner role cannot be assigned via invitation.</span>
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={isAddingMember}
                    className="w-full h-10 bg-amber-400 hover:bg-amber-500 text-slate-950 text-xs font-bold rounded-xl transition-all shadow hover:shadow-amber-400/20 disabled:opacity-60 flex items-center justify-center gap-1.5"
                  >
                    <UserPlus className="w-3.5 h-3.5" />
                    <span>{isAddingMember ? "Adding Member..." : "Add Member to Organisation"}</span>
                  </button>
                </form>
              ) : (
                <div className="p-4 rounded-xl bg-white border border-slate-200 text-center space-y-2">
                  <Shield className="w-6 h-6 text-slate-400 mx-auto" />
                  <div className="text-xs font-bold text-slate-800">
                    Restricted Role Permissions
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Only organisation <strong className="font-semibold text-slate-700">OWNER</strong> or <strong className="font-semibold text-slate-700">ADMIN</strong> can add members.
                  </p>
                  <div className="text-[10px] font-mono text-slate-400 bg-slate-50 p-2 rounded-lg">
                    Current Role: {selectedOrg.user_role || "MEMBER"}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* MODAL: CREATE ORGANISATION                                    */}
      {/* ------------------------------------------------------------- */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl w-full max-w-md p-6 shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Building2 className="w-4 h-4 text-amber-500" />
                <h3 className="text-sm font-bold text-slate-900">Create New Organisation</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-slate-600 text-sm font-bold"
              >
                ✕
              </button>
            </div>

            {createOrgError && (
              <div className="mt-3 p-3 rounded-xl bg-rose-50 border border-rose-300 text-rose-900 text-xs font-semibold flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>{createOrgError}</span>
              </div>
            )}

            <form onSubmit={handleCreateOrg} className="space-y-4 mt-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Organisation Name <span className="text-amber-500">*</span>
                </label>
                <input
                  type="text"
                  value={newOrgName}
                  onChange={(e) => setNewOrgName(e.target.value)}
                  required
                  placeholder="e.g. Apex Auto Group UK"
                  className="w-full h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Organisation Type <span className="text-amber-500">*</span>
                </label>
                <select
                  value={newOrgType}
                  onChange={(e) => setNewOrgType(e.target.value as BackendOrganisation["type"])}
                  className="w-full h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 bg-white"
                >
                  <option value="DEALER_GROUP">Dealer Group (Inventory & Sales)</option>
                  <option value="WORKSHOP">Workshop (Service & Bay Repair)</option>
                  <option value="FLEET_OPERATOR">Fleet Operator (Logistics)</option>
                  <option value="INDIVIDUAL">Individual / Personal Garage</option>
                  {(user?.is_superuser || user?.rawRoles?.includes("ADMIN") || user?.role === "MARKETPLACE_ADMIN") && (
                    <option value="INTERNAL_OPS">Internal Operations (Platform Admin Only)</option>
                  )}
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Jurisdiction Pack
                </label>
                <input
                  type="text"
                  value={newOrgJurisdiction}
                  onChange={(e) => setNewOrgJurisdiction(e.target.value)}
                  placeholder="GB-ENG"
                  className="w-full h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
                />
                <span className="text-[10px] text-slate-400 mt-1 block">
                  Default: GB-ENG (Operating Jurisdiction)
                </span>
              </div>

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-xs font-bold text-slate-600 hover:bg-slate-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isCreatingOrg}
                  className="px-5 py-2 rounded-xl bg-amber-400 hover:bg-amber-500 text-slate-950 text-xs font-black transition-all shadow hover:shadow-amber-400/20 disabled:opacity-60"
                >
                  {isCreatingOrg ? "Creating..." : "Create Organisation"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: APPLY FOR DEALER VERIFICATION (PHASE 7.1) */}
      {showApplyModal && selectedOrg && (
        <div className="fixed inset-0 z-50 bg-slate-950/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-200 animate-in zoom-in-95 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-4">
              <div className="flex items-center gap-2">
                <Award className="w-5 h-5 text-amber-500" />
                <h3 className="text-base font-black text-slate-900">
                  Dealer Verification Request
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowApplyModal(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {appSubmitError && (
              <div className="mb-4 p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-900 text-xs font-semibold flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>{appSubmitError}</span>
              </div>
            )}

            <form onSubmit={handleApplyDealer} className="space-y-4">
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1">
                <div className="font-bold text-slate-900">Applying Organisation:</div>
                <div className="text-slate-600 font-mono text-[11px]">{selectedOrg.name} ({selectedOrg.country}:{selectedOrg.jurisdiction})</div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Company Reg. Number
                  </label>
                  <input
                    type="text"
                    value={appRegNumber}
                    onChange={(e) => setAppRegNumber(e.target.value)}
                    placeholder="e.g. 12345678"
                    className="w-full h-9 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Tax / VAT / GSTIN ID
                  </label>
                  <input
                    type="text"
                    value={appTaxId}
                    onChange={(e) => setAppTaxId(e.target.value)}
                    placeholder="e.g. GB987654321"
                    className="w-full h-9 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Official Website
                </label>
                <input
                  type="url"
                  value={appWebsite}
                  onChange={(e) => setAppWebsite(e.target.value)}
                  placeholder="https://www.yourdealership.co.uk"
                  className="w-full h-9 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Trade Contact Email
                  </label>
                  <input
                    type="email"
                    value={appContactEmail}
                    onChange={(e) => setAppContactEmail(e.target.value)}
                    placeholder="b2b@dealership.com"
                    className="w-full h-9 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Trade Contact Phone
                  </label>
                  <input
                    type="tel"
                    value={appContactPhone}
                    onChange={(e) => setAppContactPhone(e.target.value)}
                    placeholder="+44 20 7123 4567"
                    className="w-full h-9 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Requested Tier Program
                </label>
                <select
                  value={appRequestedTier}
                  onChange={(e) => setAppRequestedTier(e.target.value)}
                  className="w-full h-9 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 bg-white"
                >
                  <option value="STANDARD">Standard Dealer (5% Trade Baseline)</option>
                  <option value="SILVER">Silver Dealer (10% Trade Baseline)</option>
                  <option value="GOLD">Gold Dealer (15% Trade Baseline)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Trade References & Business Overview
                </label>
                <textarea
                  rows={3}
                  value={appNotes}
                  onChange={(e) => setAppNotes(e.target.value)}
                  placeholder="Summarize your dealership operations, typical monthly volume, or existing franchise references..."
                  className="w-full p-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 resize-none"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowApplyModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-300 text-xs font-bold text-slate-600 hover:bg-slate-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingApp}
                  className="px-5 py-2 rounded-xl bg-amber-500 hover:bg-amber-600 text-slate-950 text-xs font-black transition-all shadow hover:shadow-amber-500/20 disabled:opacity-60 flex items-center gap-1.5"
                >
                  <Award className="w-3.5 h-3.5" />
                  <span>{isSubmittingApp ? "Submitting..." : "Submit Verification Request"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
