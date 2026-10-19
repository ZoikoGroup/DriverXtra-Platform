"use client";

import React, { useState } from "react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import { PrototypeUser } from "@/lib/prototype-auth/types";
import { api, ApiError } from "@/lib/api/client";
import {
  User,
  Mail,
  Phone,
  Shield,
  Building2,
  Lock,
  CheckCircle2,
  AlertCircle,
  Save,
  RefreshCw,
  KeyRound,
  ShieldCheck,
  Copy,
  Check
} from "lucide-react";

interface ProfileEditFormProps {
  user: PrototypeUser;
  onUpdate: (data: { first_name?: string; last_name?: string; phone_number?: string }) => Promise<boolean>;
}

function ProfileEditForm({ user, onUpdate }: ProfileEditFormProps) {
  const [firstName, setFirstName] = useState(user.first_name || "");
  const [lastName, setLastName] = useState(user.last_name || "");
  const [phoneNumber, setPhoneNumber] = useState(user.phone_number || "");
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setSaveSuccess(false);
    setErrorMsg(null);

    const success = await onUpdate({
      first_name: firstName,
      last_name: lastName,
      phone_number: phoneNumber,
    });

    setIsSaving(false);
    if (success) {
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 4000);
    } else {
      setErrorMsg("Failed to update profile. Please verify input values.");
    }
  };

  return (
    <div className="space-y-4">
      {/* Success Notification */}
      {saveSuccess && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-300 text-emerald-900 text-xs font-semibold flex items-center gap-2 shadow-sm animate-in fade-in">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>Profile updated successfully via <code className="font-mono text-[11px]">PATCH /api/v1/users/me/</code>.</span>
        </div>
      )}

      {/* Error Notification */}
      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-300 text-rose-900 text-xs font-semibold flex items-center gap-2 shadow-sm animate-in fade-in">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">
              First Name
            </label>
            <input
              type="text"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              placeholder="e.g. John"
              className="w-full h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 bg-slate-50/50"
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">
              Last Name
            </label>
            <input
              type="text"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              placeholder="e.g. Doe"
              className="w-full h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 bg-slate-50/50"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-bold text-slate-700 mb-1">
            Contact Phone Number
          </label>
          <div className="relative">
            <input
              type="tel"
              value={phoneNumber}
              onChange={(e) => setPhoneNumber(e.target.value)}
              placeholder="e.g. +44 7000 000000"
              className="w-full h-10 px-3 pl-9 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 bg-slate-50/50"
            />
            <Phone className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-3.5 pointer-events-none" />
          </div>
        </div>

        <div className="pt-2">
          <button
            type="submit"
            disabled={isSaving}
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-slate-950 text-xs font-bold transition-all shadow hover:shadow-amber-500/20 disabled:opacity-60"
          >
            <Save className="w-3.5 h-3.5" />
            <span>{isSaving ? "Saving to Backend..." : "Save Profile Changes"}</span>
          </button>
        </div>
      </form>
    </div>
  );
}

function MFAEnrolmentSection({
  user,
  onRefresh,
}: {
  user: PrototypeUser;
  onRefresh: () => Promise<void>;
}) {
  const [enrolData, setEnrolData] = useState<{ secret: string; qr_code_uri: string } | null>(null);
  const [confirmCode, setConfirmCode] = useState("");
  const [isStartingEnrol, setIsStartingEnrol] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [copied, setCopied] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleStartEnrol = async () => {
    setIsStartingEnrol(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const data = await api.auth.enrolMfa();
      setEnrolData(data);
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to generate MFA secret.");
    } finally {
      setIsStartingEnrol(false);
    }
  };

  const handleConfirmMfa = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!confirmCode || confirmCode.trim().length !== 6) {
      setErrorMsg("Please enter a valid 6-digit TOTP code.");
      return;
    }

    setIsConfirming(true);
    setErrorMsg(null);
    try {
      await api.auth.verifyMfa(confirmCode.trim());
      setSuccessMsg("MFA has been successfully verified and activated on your account!");
      setEnrolData(null);
      setConfirmCode("");
      await onRefresh();
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Invalid code. Please re-enter the 6 digits from your app.");
    } finally {
      setIsConfirming(false);
    }
  };

  const handleCopySecret = () => {
    if (enrolData?.secret) {
      navigator.clipboard.writeText(enrolData.secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
      <div className="flex items-center justify-between pb-3 border-b border-slate-100">
        <div>
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-amber-500" />
            <span>Two-Factor Authentication (TOTP MFA)</span>
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Cryptographic time-based one-time password security for platform access (Doc 04 §7).
          </p>
        </div>

        <span
          className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
            user.has_mfa_enabled
              ? "bg-emerald-50 text-emerald-700 border-emerald-300"
              : "bg-amber-50 text-amber-800 border-amber-300"
          }`}
        >
          {user.has_mfa_enabled ? "MFA Active" : "Not Configured"}
        </span>
      </div>

      {successMsg && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-300 text-emerald-900 text-xs font-semibold flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-300 text-rose-900 text-xs font-semibold flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {user.has_mfa_enabled ? (
        <div className="p-4 rounded-xl bg-emerald-50/60 border border-emerald-200 text-xs text-emerald-950 flex items-start gap-3">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
          <div>
            <div className="font-bold">Two-Factor Authentication Is Active</div>
            <p className="text-emerald-800 mt-0.5 leading-relaxed">
              Your account is protected by TOTP MFA. Every subsequent sign in from Staff or Admin accounts will require a 6-digit authenticator verification code.
            </p>
          </div>
        </div>
      ) : enrolData ? (
        <form onSubmit={handleConfirmMfa} className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-4">
          <div className="text-xs text-slate-700 font-medium leading-relaxed">
            Scan or enter the following secret into your authenticator app (Google Authenticator, Authy, 1Password):
          </div>

          <div className="flex items-center gap-2 p-2.5 bg-white border border-slate-300 rounded-xl">
            <code className="text-xs font-mono font-bold text-slate-900 tracking-wider flex-1 truncate">
              {enrolData.secret}
            </code>
            <button
              type="button"
              onClick={handleCopySecret}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold transition-colors"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? "Copied" : "Copy"}</span>
            </button>
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">
              Enter 6-Digit Code to Confirm Enrolment
            </label>
            <div className="relative">
              <input
                type="text"
                maxLength={6}
                value={confirmCode}
                onChange={(e) => setConfirmCode(e.target.value.replace(/\D/g, ""))}
                placeholder="123456"
                required
                className="w-full h-11 px-3.5 pl-10 bg-white border border-slate-300 rounded-xl text-center text-base tracking-[0.3em] font-mono font-bold text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
              />
              <KeyRound className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5 pointer-events-none" />
            </div>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <button
              type="submit"
              disabled={isConfirming || confirmCode.length !== 6}
              className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-slate-950 text-xs font-bold transition-all shadow hover:shadow-amber-500/20 disabled:opacity-60"
            >
              <ShieldCheck className="w-4 h-4" />
              <span>{isConfirming ? "Activating 2FA..." : "Confirm & Enable 2FA"}</span>
            </button>

            <button
              type="button"
              onClick={() => {
                setEnrolData(null);
                setConfirmCode("");
                setErrorMsg(null);
              }}
              className="px-3.5 py-2.5 rounded-xl text-xs font-bold text-slate-600 hover:text-slate-900 hover:bg-slate-200 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl bg-slate-50 border border-slate-200">
          <div>
            <div className="text-xs font-bold text-slate-900">Authenticator Application (TOTP)</div>
            <div className="text-[11px] text-slate-500 mt-0.5">
              Enforce two-step login verification with temporary codes. Recommended for all accounts, required for Staff and Admin.
            </div>
          </div>

          <button
            type="button"
            onClick={handleStartEnrol}
            disabled={isStartingEnrol}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition-all shadow shrink-0 disabled:opacity-60"
          >
            <KeyRound className="w-3.5 h-3.5 text-amber-400" />
            <span>{isStartingEnrol ? "Generating Secret..." : "Enrol Authenticator"}</span>
          </button>
        </div>
      )}
    </div>
  );
}

export default function Phase1ProfileView() {
  const { user, updateProfile, refreshProfile, isLoading } = useAuth();

  if (!user) return null;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-2">
            <User className="w-5 h-5 text-amber-500" />
            <span>Authenticated User Profile & RBAC Identity</span>
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Verified identity & session tokens managed by Django endpoint <code className="text-[11px] font-mono bg-slate-100 px-1.5 py-0.5 rounded text-slate-800">GET /api/v1/users/me/</code>
          </p>
        </div>

        <button
          onClick={() => refreshProfile()}
          disabled={isLoading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold transition-colors shadow-sm disabled:opacity-50"
          title="Reload profile from backend"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-amber-500" : ""}`} />
          <span>Sync Profile</span>
        </button>
      </div>

      {/* Main Grid: Form on Left, Protected Identity on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Editable Profile Fields & MFA Enrolment */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
            <div className="flex items-center justify-between pb-4 mb-5 border-b border-slate-100">
              <div>
                <h2 className="text-sm font-bold text-slate-900">Personal Information</h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  These fields can be modified by the authenticated user.
                </p>
              </div>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                Permitted to Edit
              </span>
            </div>

            <ProfileEditForm
              key={`${user.id}-${user.first_name || ""}-${user.last_name || ""}-${user.phone_number || ""}`}
              user={user}
              onUpdate={updateProfile}
            />
          </div>

          {/* MFA Enrolment Card */}
          <MFAEnrolmentSection user={user} onRefresh={refreshProfile} />
        </div>

        {/* Right Column: Protected & Read-Only Fields */}
        <div className="bg-slate-50 rounded-2xl border border-slate-200 p-6 space-y-5">
          <div className="flex items-center justify-between pb-3 border-b border-slate-200">
            <div>
              <h2 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                <Lock className="w-3.5 h-3.5 text-slate-500" />
                <span>Protected Attributes</span>
              </h2>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Restricted fields governed by platform RBAC.
              </p>
            </div>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-200 text-slate-700">
              Read-Only
            </span>
          </div>

          {/* Primary Email */}
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              Account Email
            </label>
            <div className="flex items-center gap-2 p-2.5 bg-white border border-slate-200 rounded-xl text-xs text-slate-800">
              <Mail className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <span className="truncate font-semibold">{user.email}</span>
            </div>
          </div>

          {/* Account Status */}
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              Account Lifecycle Status
            </label>
            <div className="flex items-center gap-2 p-2.5 bg-white border border-slate-200 rounded-xl text-xs">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              <span className="font-bold text-slate-800">{user.status || "ACTIVE"}</span>
              <span className="text-[10px] text-slate-400 ml-auto">Verified</span>
            </div>
          </div>

          {/* Active Role and Assigned Roles */}
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              Active Role & Platform Roles
            </label>
            <div className="mb-2 p-2 rounded-xl bg-white border border-slate-200 flex items-center justify-between text-xs">
              <span className="text-slate-500 text-[11px]">Active Role Claim:</span>
              <span className="font-mono font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                {user.activeRole || user.role}
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5 mt-1">
              {(user.rawRoles && user.rawRoles.length > 0 ? user.rawRoles : [user.role]).map((r) => (
                <span
                  key={r}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-amber-100/80 border border-amber-300 text-amber-900 text-[11px] font-bold"
                >
                  <Shield className="w-3 h-3 text-amber-600" />
                  <span>{r}</span>
                </span>
              ))}
            </div>
          </div>

          {/* Staff Sub-Role & Permissions */}
          {user.staff_role && (
            <div>
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                Staff Sub-Role & Permissions
              </label>
              <div className="p-2.5 bg-white border border-slate-200 rounded-xl space-y-1.5">
                <div className="flex items-center justify-between text-xs font-bold text-slate-900">
                  <span>{user.staff_role.name}</span>
                  <span className="text-[10px] font-mono text-purple-700 bg-purple-50 px-1.5 py-0.5 rounded border border-purple-200">
                    {user.staff_role.code}
                  </span>
                </div>
                {user.permissions && user.permissions.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-1">
                    {user.permissions.map((p) => (
                      <span key={p} className="text-[10px] font-mono bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded">
                        {p}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Administrative Privileges */}
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              Elevated Privileges
            </label>
            <div className="grid grid-cols-2 gap-2 mt-1">
              <div className="p-2 rounded-xl bg-white border border-slate-200 text-center">
                <span className="block text-[10px] text-slate-500 font-bold uppercase">Platform Staff</span>
                <span className={`text-xs font-black ${user.is_staff ? "text-emerald-600" : "text-slate-400"}`}>
                  {user.is_staff ? "ENABLED" : "NONE"}
                </span>
              </div>
              <div className="p-2 rounded-xl bg-white border border-slate-200 text-center">
                <span className="block text-[10px] text-slate-500 font-bold uppercase">Superuser</span>
                <span className={`text-xs font-black ${user.is_superuser ? "text-emerald-600" : "text-slate-400"}`}>
                  {user.is_superuser ? "ENABLED" : "NONE"}
                </span>
              </div>
            </div>
          </div>

          {/* Organisation Memberships Summary */}
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              Active Organisations ({user.organisations ? user.organisations.length : 0})
            </label>
            <div className="space-y-1.5 mt-1">
              {user.organisations && user.organisations.length > 0 ? (
                user.organisations.map((org) => (
                  <div
                    key={org.organisation_id}
                    className="p-2 rounded-xl bg-white border border-slate-200 flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Building2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span className="font-bold text-slate-800 truncate">{org.organisation_name}</span>
                    </div>
                    <span className="text-[10px] font-black px-2 py-0.5 rounded bg-slate-100 text-slate-700 shrink-0">
                      {org.role}
                    </span>
                  </div>
                ))
              ) : (
                <div className="p-2.5 rounded-xl bg-white border border-slate-200 text-[11px] text-slate-500 text-center">
                  No organisation memberships assigned.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
