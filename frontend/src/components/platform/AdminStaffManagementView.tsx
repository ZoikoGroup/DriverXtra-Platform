"use client";

import React, { useState } from "react";
import Link from "next/link";
import { api, ApiError, StaffInvitePayload } from "@/lib/api/client";
import {
  ShieldCheck,
  UserPlus,
  Mail,
  User,
  Building2,
  CheckCircle2,
  AlertCircle,
  Clock,
  KeyRound,
  ExternalLink,
  ShieldAlert
} from "lucide-react";

export default function AdminStaffManagementView() {
  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [staffRole, setStaffRole] = useState<StaffInvitePayload["staff_role"]>("VERIFICATION_OFFICER");
  const [department, setDepartment] = useState("Operations & Compliance");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [inviteResult, setInviteResult] = useState<{
    message: string;
    email: string;
    staff_role: string;
    invite_token?: string | null;
  } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !firstName || !lastName) {
      setErrorMsg("Please fill out all required fields.");
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);
    setInviteResult(null);

    try {
      const response = await api.admin.inviteStaff({
        email: email.trim().toLowerCase(),
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        staff_role: staffRole,
        department: department.trim(),
      });

      setInviteResult({
        message: response.message,
        email: response.email,
        staff_role: response.staff_role,
        invite_token: response.invite_token,
      });

      // Clear form inputs
      setEmail("");
      setFirstName("");
      setLastName("");
    } catch (err: unknown) {
      setErrorMsg(
        err instanceof ApiError
          ? err.message
          : "Failed to create staff invitation. Please verify permissions."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-amber-500" />
            <span>Staff Administration & Access Control</span>
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Staff Invitations & Roles • Manage team access and administrative permissions
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold px-2.5 py-1 rounded-full bg-slate-900 text-amber-400 border border-slate-800">
            Restricted Platform Access
          </span>
        </div>
      </div>

      {/* Security Policies Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm flex items-start gap-3">
          <div className="w-8 h-8 rounded-xl bg-amber-50 border border-amber-200 flex items-center justify-center shrink-0">
            <Clock className="w-4 h-4 text-amber-600" />
          </div>
          <div className="text-xs">
            <div className="font-bold text-slate-900">15-Minute Session Tokens</div>
            <div className="text-slate-500 text-[11px] mt-0.5">
              Staff and Admin access tokens automatically expire after 15 minutes, requiring active refresh.
            </div>
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm flex items-start gap-3">
          <div className="w-8 h-8 rounded-xl bg-purple-50 border border-purple-200 flex items-center justify-center shrink-0">
            <KeyRound className="w-4 h-4 text-purple-600" />
          </div>
          <div className="text-xs">
            <div className="font-bold text-slate-900">Mandatory TOTP MFA</div>
            <div className="text-slate-500 text-[11px] mt-0.5">
              All staff users must complete time-based one-time password verification on login.
            </div>
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm flex items-start gap-3">
          <div className="w-8 h-8 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center shrink-0">
            <ShieldAlert className="w-4 h-4 text-emerald-600" />
          </div>
          <div className="text-xs">
            <div className="font-bold text-slate-900">Maker-Checker Controls</div>
            <div className="text-slate-500 text-[11px] mt-0.5">
              ApprovalRequest model enforces maker != checker segregation for sensitive reviews.
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Invitation Form */}
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-5">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <h2 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                <UserPlus className="w-4 h-4 text-amber-500" />
                <span>Issue Staff Invitation</span>
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Invited staff are created with inactive status until they redeem their single-use set-password token.
              </p>
            </div>
          </div>

          {inviteResult && (
            <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-xs space-y-2 animate-in fade-in">
              <div className="flex items-center gap-2 text-emerald-900 font-bold">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>{inviteResult.message}</span>
              </div>
              <div className="text-emerald-800 text-[11px]">
                Invited user: <strong className="font-mono">{inviteResult.email}</strong> as{" "}
                <strong className="font-bold">{inviteResult.staff_role}</strong>.
              </div>
              {inviteResult.invite_token && (
                <div className="pt-2 border-t border-emerald-200/60 flex items-center justify-between">
                  <span className="text-[10px] text-emerald-700 font-mono truncate max-w-xs">
                    Token: {inviteResult.invite_token.slice(0, 12)}...
                  </span>
                  <Link
                    href={`/set-password?token=${encodeURIComponent(inviteResult.invite_token)}`}
                    className="inline-flex items-center gap-1 text-xs font-bold text-amber-700 hover:text-amber-800 underline"
                  >
                    <span>Open Activation Link</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </Link>
                </div>
              )}
            </div>
          )}

          {errorMsg && (
            <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-300 text-rose-900 text-xs font-semibold flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Corporate Work Email <span className="text-amber-500">*</span>
              </label>
              <div className="relative">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  placeholder="officer.name@driverxtra.com"
                  className="w-full h-10 px-3 pl-9 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 bg-slate-50/50"
                />
                <Mail className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-3.5 pointer-events-none" />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  First Name <span className="text-amber-500">*</span>
                </label>
                <div className="relative">
                  <input
                    type="text"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    required
                    placeholder="e.g. Sarah"
                    className="w-full h-10 px-3 pl-9 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 bg-slate-50/50"
                  />
                  <User className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-3.5 pointer-events-none" />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Last Name <span className="text-amber-500">*</span>
                </label>
                <div className="relative">
                  <input
                    type="text"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    required
                    placeholder="e.g. Jenkins"
                    className="w-full h-10 px-3 pl-9 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 bg-slate-50/50"
                  />
                  <User className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-3.5 pointer-events-none" />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Staff Sub-Role & Permissions <span className="text-amber-500">*</span>
                </label>
                <select
                  value={staffRole}
                  onChange={(e) => setStaffRole(e.target.value as StaffInvitePayload["staff_role"])}
                  className="w-full h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 bg-slate-50/50 font-medium"
                >
                  <option value="VERIFICATION_OFFICER">Verification Officer (seller.verify, listing.review)</option>
                  <option value="DISPUTE_MANAGER">Dispute Manager (dispute.manage, order.refund)</option>
                  <option value="FINANCE_OFFICER">Finance Officer (finance.payout, order.refund)</option>
                  <option value="SUPPORT_AGENT">Support Agent (Read-only customer support)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Department
                </label>
                <div className="relative">
                  <input
                    type="text"
                    value={department}
                    onChange={(e) => setDepartment(e.target.value)}
                    placeholder="e.g. Trust & Safety"
                    className="w-full h-10 px-3 pl-9 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 bg-slate-50/50"
                  />
                  <Building2 className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-3.5 pointer-events-none" />
                </div>
              </div>
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={isSubmitting}
                className="inline-flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-slate-950 text-xs font-bold transition-all shadow hover:shadow-amber-500/20 disabled:opacity-60"
              >
                <UserPlus className="w-3.5 h-3.5" />
                <span>{isSubmitting ? "Generating Staff Invite..." : "Create & Send Staff Invitation"}</span>
              </button>
            </div>
          </form>
        </div>

        {/* Right Col: Sub-Role Matrix Reference */}
        <div className="bg-slate-50 rounded-2xl border border-slate-200 p-6 space-y-4">
          <div className="pb-3 border-b border-slate-200">
            <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
              Staff Sub-Role Permission Matrix
            </h3>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Platform staff roles and enforced operational privileges.
            </p>
          </div>

          <div className="space-y-3">
            <div className="p-3 bg-white rounded-xl border border-slate-200 text-xs space-y-1">
              <div className="font-bold text-slate-900">Verification Officer</div>
              <div className="text-[10px] text-slate-500">Reviews seller applications and moderate listings.</div>
              <div className="flex flex-wrap gap-1 mt-1">
                <span className="font-mono text-[10px] bg-amber-50 text-amber-800 border border-amber-200 px-1.5 py-0.2 rounded">
                  seller.verify
                </span>
                <span className="font-mono text-[10px] bg-amber-50 text-amber-800 border border-amber-200 px-1.5 py-0.2 rounded">
                  listing.review
                </span>
              </div>
            </div>

            <div className="p-3 bg-white rounded-xl border border-slate-200 text-xs space-y-1">
              <div className="font-bold text-slate-900">Dispute Manager</div>
              <div className="text-[10px] text-slate-500">Mediates customer escrow disputes and processes refunds.</div>
              <div className="flex flex-wrap gap-1 mt-1">
                <span className="font-mono text-[10px] bg-purple-50 text-purple-800 border border-purple-200 px-1.5 py-0.2 rounded">
                  dispute.manage
                </span>
                <span className="font-mono text-[10px] bg-purple-50 text-purple-800 border border-purple-200 px-1.5 py-0.2 rounded">
                  order.refund
                </span>
              </div>
            </div>

            <div className="p-3 bg-white rounded-xl border border-slate-200 text-xs space-y-1">
              <div className="font-bold text-slate-900">Finance Officer</div>
              <div className="text-[10px] text-slate-500">Releases settlement payouts and ledger adjustments.</div>
              <div className="flex flex-wrap gap-1 mt-1">
                <span className="font-mono text-[10px] bg-emerald-50 text-emerald-800 border border-emerald-200 px-1.5 py-0.2 rounded">
                  finance.payout
                </span>
                <span className="font-mono text-[10px] bg-emerald-50 text-emerald-800 border border-emerald-200 px-1.5 py-0.2 rounded">
                  order.refund
                </span>
              </div>
            </div>

            <div className="p-3 bg-white rounded-xl border border-slate-200 text-xs space-y-1">
              <div className="font-bold text-slate-900">Support Agent</div>
              <div className="text-[10px] text-slate-500">Read-only customer support assistance and inquiry handling.</div>
              <div className="text-[10px] text-slate-400 italic">No elevated mutate permissions.</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
