"use client";

import React, { useState } from "react";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import { PrototypeUser } from "@/lib/prototype-auth/types";
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
  RefreshCw
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
            Phase 1 verified profile retrieved from Django endpoint <code className="text-[11px] font-mono bg-slate-100 px-1.5 py-0.5 rounded text-slate-800">GET /api/v1/users/me/</code>
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
        {/* Left Column: Editable Profile Fields */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
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

          {/* Assigned Roles */}
          <div>
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              Assigned Platform Roles
            </label>
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
