"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import {
  api,
  ApiError,
  StaffInvitePayload,
  StaffMemberItem,
  StaffInvitationItem,
  StaffRoleItem,
  StaffMetrics,
} from "@/lib/api/client";
import { useAuth } from "@/lib/prototype-auth/auth-context";
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
  Users,
  Search,
  RefreshCw,
  Edit3,
  UserX,
  Trash2,
  Send,
  Shield,
  Lock,
  Copy,
  CheckCheck,
  X,
  Check,
} from "lucide-react";

type ActiveTab = "directory" | "invitations" | "invite" | "roles";

export default function AdminStaffManagementView() {
  const { user: currentUser } = useAuth();

  // Navigation
  const [activeTab, setActiveTab] = useState<ActiveTab>("directory");

  // Data State
  const [metrics, setMetrics] = useState<StaffMetrics | null>(null);
  const [staffMembers, setStaffMembers] = useState<StaffMemberItem[]>([]);
  const [invitations, setInvitations] = useState<StaffInvitationItem[]>([]);
  const [roles, setRoles] = useState<StaffRoleItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Filters: Directory
  const [directorySearch, setDirectorySearch] = useState<string>("");
  const [directoryRoleFilter, setDirectoryRoleFilter] = useState<string>("ALL");
  const [directoryStatusFilter, setDirectoryStatusFilter] = useState<string>("ALL");
  const [directoryMfaFilter, setDirectoryMfaFilter] = useState<string>("ALL");

  // Filters: Invitations
  const [invitationSearch, setInvitationSearch] = useState<string>("");
  const [invitationStatusFilter, setInvitationStatusFilter] = useState<string>("ALL");

  // Invitation Form State
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteFirstName, setInviteFirstName] = useState("");
  const [inviteLastName, setInviteLastName] = useState("");
  const [inviteStaffRole, setInviteStaffRole] = useState<StaffInvitePayload["staff_role"]>("VERIFICATION_OFFICER");
  const [inviteDepartment, setInviteDepartment] = useState("Operations & Compliance");
  const [isInviting, setIsInviting] = useState(false);
  const [inviteResult, setInviteResult] = useState<{
    message: string;
    email: string;
    staff_role: string;
    invite_token?: string | null;
  } | null>(null);
  const [copiedToken, setCopiedToken] = useState(false);

  // Edit Modal State
  const [editingStaff, setEditingStaff] = useState<StaffMemberItem | null>(null);
  const [editRole, setEditRole] = useState<string>("");
  const [editDepartment, setEditDepartment] = useState<string>("");
  const [editStatus, setEditStatus] = useState<"ACTIVE" | "SUSPENDED">("ACTIVE");
  const [isUpdatingStaff, setIsUpdatingStaff] = useState(false);

  // Revoke Modal State
  const [revokingInvite, setRevokingInvite] = useState<StaffInvitationItem | null>(null);
  const [isRevoking, setIsRevoking] = useState(false);

  // Resend Loading State
  const [resendingInviteId, setResendingInviteId] = useState<string | null>(null);

  // Initial and Refresh Data Fetching
  const loadAllData = useCallback(async () => {
    try {
      setLoading(true);
      setErrorMsg(null);

      const [metricsResp, staffResp, invitesResp, rolesResp] = await Promise.all([
        api.admin.getStaffMetrics().catch(() => null),
        api.admin.listStaff(),
        api.admin.listInvitations(),
        api.admin.listStaffRoles().catch(() => ({ status: "success", roles: [] })),
      ]);

      if (metricsResp?.metrics) {
        setMetrics(metricsResp.metrics);
      }
      if (staffResp?.results) {
        setStaffMembers(staffResp.results);
      }
      if (invitesResp?.results) {
        setInvitations(invitesResp.results);
      }
      if (rolesResp?.roles) {
        setRoles(rolesResp.roles);
      }
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to load staff administration records.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let isMounted = true;
    (async () => {
      try {
        setLoading(true);
        setErrorMsg(null);
        const [metricsResp, staffResp, invitesResp, rolesResp] = await Promise.all([
          api.admin.getStaffMetrics().catch(() => null),
          api.admin.listStaff(),
          api.admin.listInvitations(),
          api.admin.listStaffRoles().catch(() => ({ status: "success", roles: [] })),
        ]);
        if (!isMounted) return;
        if (metricsResp?.metrics) setMetrics(metricsResp.metrics);
        if (staffResp?.results) setStaffMembers(staffResp.results);
        if (invitesResp?.results) setInvitations(invitesResp.results);
        if (rolesResp?.roles) setRoles(rolesResp.roles);
      } catch (err: unknown) {
        if (!isMounted) return;
        setErrorMsg(err instanceof ApiError ? err.message : "Failed to load staff administration records.");
      } finally {
        if (isMounted) setLoading(false);
      }
    })();
    return () => {
      isMounted = false;
    };
  }, []);

  // Handle Staff Invitation Submission
  const handleInviteSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail || !inviteFirstName || !inviteLastName) {
      setErrorMsg("Please fill out all required fields.");
      return;
    }

    setIsInviting(true);
    setErrorMsg(null);
    setInviteResult(null);

    try {
      const response = await api.admin.inviteStaff({
        email: inviteEmail.trim().toLowerCase(),
        first_name: inviteFirstName.trim(),
        last_name: inviteLastName.trim(),
        staff_role: inviteStaffRole,
        department: inviteDepartment.trim(),
      });

      setInviteResult({
        message: response.message,
        email: response.email,
        staff_role: response.staff_role,
        invite_token: response.invite_token,
      });

      setSuccessMsg(`Invitation dispatched to ${response.email}.`);

      // Clear form inputs
      setInviteEmail("");
      setInviteFirstName("");
      setInviteLastName("");

      // Refresh data
      loadAllData();
    } catch (err: unknown) {
      setErrorMsg(
        err instanceof ApiError
          ? err.message
          : "Failed to create staff invitation. Please verify permissions."
      );
    } finally {
      setIsInviting(false);
    }
  };

  // Open Edit Modal
  const openEditModal = (staff: StaffMemberItem) => {
    setEditingStaff(staff);
    setEditRole(staff.staff_role?.code || "SUPPORT_AGENT");
    setEditDepartment(staff.department || "Operations");
    setEditStatus(staff.status === "SUSPENDED" ? "SUSPENDED" : "ACTIVE");
  };

  // Submit Edit Staff Member
  const handleUpdateStaff = async () => {
    if (!editingStaff) return;
    setIsUpdatingStaff(true);
    setErrorMsg(null);

    try {
      await api.admin.updateStaff(editingStaff.id, {
        staff_role: editRole,
        department: editDepartment,
        status: editStatus,
      });

      setSuccessMsg(`Staff profile for ${editingStaff.email} updated successfully.`);
      setEditingStaff(null);
      loadAllData();
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to update staff member.");
    } finally {
      setIsUpdatingStaff(false);
    }
  };

  // Resend Invitation
  const handleResendInvite = async (invitation: StaffInvitationItem) => {
    setResendingInviteId(invitation.id);
    setErrorMsg(null);

    try {
      const resp = await api.admin.resendInvitation(invitation.id);
      setSuccessMsg(`Invitation refreshed and dispatched to ${resp.email}.`);
      loadAllData();
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to re-dispatch invitation email.");
    } finally {
      setResendingInviteId(null);
    }
  };

  // Revoke Invitation
  const handleRevokeInvite = async () => {
    if (!revokingInvite) return;
    setIsRevoking(true);
    setErrorMsg(null);

    try {
      await api.admin.revokeInvitation(revokingInvite.id);
      setSuccessMsg(`Invitation for ${revokingInvite.email} has been revoked.`);
      setRevokingInvite(null);
      loadAllData();
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to revoke invitation.");
    } finally {
      setIsRevoking(false);
    }
  };

  // Copy Token Helper
  const handleCopyToken = (token: string) => {
    navigator.clipboard.writeText(token);
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2000);
  };

  // Filtered Staff Members
  const filteredStaff = useMemo(() => {
    return staffMembers.filter((m) => {
      const matchesSearch =
        !directorySearch ||
        m.email.toLowerCase().includes(directorySearch.toLowerCase()) ||
        m.full_name.toLowerCase().includes(directorySearch.toLowerCase());

      const matchesRole =
        directoryRoleFilter === "ALL" ||
        (directoryRoleFilter === "ADMIN" && (m.is_superuser || m.roles.includes("ADMIN"))) ||
        m.staff_role?.code === directoryRoleFilter;

      const matchesStatus =
        directoryStatusFilter === "ALL" || m.status === directoryStatusFilter;

      const matchesMfa =
        directoryMfaFilter === "ALL" ||
        (directoryMfaFilter === "ENROLLED" && m.has_mfa_enabled) ||
        (directoryMfaFilter === "PENDING" && !m.has_mfa_enabled);

      return matchesSearch && matchesRole && matchesStatus && matchesMfa;
    });
  }, [staffMembers, directorySearch, directoryRoleFilter, directoryStatusFilter, directoryMfaFilter]);

  // Filtered Invitations
  const filteredInvitations = useMemo(() => {
    return invitations.filter((inv) => {
      const matchesSearch =
        !invitationSearch ||
        inv.email.toLowerCase().includes(invitationSearch.toLowerCase()) ||
        `${inv.first_name} ${inv.last_name}`.toLowerCase().includes(invitationSearch.toLowerCase());

      const matchesStatus =
        invitationStatusFilter === "ALL" || inv.status === invitationStatusFilter;

      return matchesSearch && matchesStatus;
    });
  }, [invitations, invitationSearch, invitationStatusFilter]);

  // Role Color Badge Helper
  const getRoleBadgeStyle = (code?: string) => {
    switch (code) {
      case "VERIFICATION_OFFICER":
        return "bg-amber-50 text-amber-900 border-amber-200";
      case "DISPUTE_MANAGER":
        return "bg-purple-50 text-purple-900 border-purple-200";
      case "FINANCE_OFFICER":
        return "bg-emerald-50 text-emerald-900 border-emerald-200";
      case "SUPPORT_AGENT":
        return "bg-sky-50 text-sky-900 border-sky-200";
      case "ADMIN":
        return "bg-slate-900 text-amber-400 border-slate-800";
      default:
        return "bg-slate-100 text-slate-800 border-slate-300";
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-amber-500" />
            <span>Staff Administration & Access Control</span>
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Phase 3 • Staff Directory, Sub-Role Provisioning & Secure Enterprise Invitations
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadAllData}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 transition shadow-sm disabled:opacity-50"
            title="Refresh Staff Data"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-amber-500" : "text-slate-500"}`} />
            <span>Refresh</span>
          </button>
          <span className="text-[10px] font-bold px-2.5 py-1 rounded-full bg-slate-900 text-amber-400 border border-slate-800">
            Platform Admin Control
          </span>
        </div>
      </div>

      {/* Operational Metrics Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-5 gap-3.5">
        <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Total Staff</span>
            <Users className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-2xl font-black text-slate-900 mt-2">
            {metrics?.total_staff ?? staffMembers.length}
          </div>
          <div className="text-[10px] text-slate-400 mt-1">Platform operations team</div>
        </div>

        <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-emerald-600 uppercase tracking-wider">Active</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-2xl font-black text-emerald-700 mt-2">
            {metrics?.active_staff ?? staffMembers.filter((m) => m.status === "ACTIVE").length}
          </div>
          <div className="text-[10px] text-slate-400 mt-1">Active platform accounts</div>
        </div>

        <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-amber-600 uppercase tracking-wider">Pending Invites</span>
            <Clock className="w-4 h-4 text-amber-500" />
          </div>
          <div className="text-2xl font-black text-amber-600 mt-2">
            {metrics?.pending_invitations ?? invitations.filter((i) => i.status === "PENDING").length}
          </div>
          <div className="text-[10px] text-slate-400 mt-1">Awaiting password activation</div>
        </div>

        <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-rose-600 uppercase tracking-wider">Suspended</span>
            <UserX className="w-4 h-4 text-rose-500" />
          </div>
          <div className="text-2xl font-black text-rose-600 mt-2">
            {metrics?.suspended_staff ?? staffMembers.filter((m) => m.status === "SUSPENDED").length}
          </div>
          <div className="text-[10px] text-slate-400 mt-1">Blocked access accounts</div>
        </div>

        <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-purple-600 uppercase tracking-wider">2FA Rate</span>
            <KeyRound className="w-4 h-4 text-purple-500" />
          </div>
          <div className="text-2xl font-black text-purple-700 mt-2">
            {metrics ? `${metrics.mfa_adoption_percentage}%` : "--"}
          </div>
          <div className="text-[10px] text-slate-400 mt-1">
            {metrics ? `${metrics.mfa_enrolled_count} of ${metrics.total_staff} enrolled` : "TOTP Enforcement"}
          </div>
        </div>
      </div>

      {/* Global Alerts */}
      {successMsg && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-300 text-emerald-900 text-xs font-semibold flex items-center justify-between gap-2 shadow-sm animate-in fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{successMsg}</span>
          </div>
          <button onClick={() => setSuccessMsg(null)} className="text-emerald-700 hover:text-emerald-900">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {errorMsg && (
        <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-300 text-rose-900 text-xs font-semibold flex items-center justify-between gap-2 shadow-sm animate-in fade-in">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{errorMsg}</span>
          </div>
          <button onClick={() => setErrorMsg(null)} className="text-rose-700 hover:text-rose-900">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Main Tabs Navigation */}
      <div className="flex border-b border-slate-200 space-x-2">
        <button
          onClick={() => setActiveTab("directory")}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold border-b-2 transition ${
            activeTab === "directory"
              ? "border-amber-500 text-amber-700 bg-amber-50/50 rounded-t-xl"
              : "border-transparent text-slate-500 hover:text-slate-900 hover:border-slate-300"
          }`}
        >
          <Users className="w-4 h-4" />
          <span>Staff Directory</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600">
            {staffMembers.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab("invitations")}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold border-b-2 transition ${
            activeTab === "invitations"
              ? "border-amber-500 text-amber-700 bg-amber-50/50 rounded-t-xl"
              : "border-transparent text-slate-500 hover:text-slate-900 hover:border-slate-300"
          }`}
        >
          <Clock className="w-4 h-4" />
          <span>Invitations Queue</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800">
            {invitations.filter((i) => i.status === "PENDING").length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab("invite")}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold border-b-2 transition ${
            activeTab === "invite"
              ? "border-amber-500 text-amber-700 bg-amber-50/50 rounded-t-xl"
              : "border-transparent text-slate-500 hover:text-slate-900 hover:border-slate-300"
          }`}
        >
          <UserPlus className="w-4 h-4" />
          <span>Issue Invitation</span>
        </button>

        <button
          onClick={() => setActiveTab("roles")}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-bold border-b-2 transition ${
            activeTab === "roles"
              ? "border-amber-500 text-amber-700 bg-amber-50/50 rounded-t-xl"
              : "border-transparent text-slate-500 hover:text-slate-900 hover:border-slate-300"
          }`}
        >
          <Shield className="w-4 h-4" />
          <span>Roles & Access Matrix</span>
        </button>
      </div>

      {/* Tab 1: Staff Directory */}
      {activeTab === "directory" && (
        <div className="space-y-4">
          {/* Filters Bar */}
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-center justify-between gap-3">
            <div className="relative w-full md:w-80">
              <input
                type="text"
                placeholder="Search by name or email..."
                value={directorySearch}
                onChange={(e) => setDirectorySearch(e.target.value)}
                className="w-full h-9 pl-9 pr-3 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-amber-500 bg-slate-50/50"
              />
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-3 pointer-events-none" />
            </div>

            <div className="flex flex-wrap items-center gap-2 w-full md:w-auto">
              <select
                value={directoryRoleFilter}
                onChange={(e) => setDirectoryRoleFilter(e.target.value)}
                className="h-9 px-3 rounded-xl border border-slate-200 text-xs bg-slate-50/50 text-slate-700 focus:outline-none focus:border-amber-500"
              >
                <option value="ALL">All Roles</option>
                <option value="ADMIN">Platform Administrator</option>
                <option value="VERIFICATION_OFFICER">Verification Officer</option>
                <option value="DISPUTE_MANAGER">Dispute Manager</option>
                <option value="FINANCE_OFFICER">Finance Officer</option>
                <option value="SUPPORT_AGENT">Support Agent</option>
              </select>

              <select
                value={directoryStatusFilter}
                onChange={(e) => setDirectoryStatusFilter(e.target.value)}
                className="h-9 px-3 rounded-xl border border-slate-200 text-xs bg-slate-50/50 text-slate-700 focus:outline-none focus:border-amber-500"
              >
                <option value="ALL">All Statuses</option>
                <option value="ACTIVE">Active</option>
                <option value="SUSPENDED">Suspended</option>
                <option value="PENDING">Pending</option>
              </select>

              <select
                value={directoryMfaFilter}
                onChange={(e) => setDirectoryMfaFilter(e.target.value)}
                className="h-9 px-3 rounded-xl border border-slate-200 text-xs bg-slate-50/50 text-slate-700 focus:outline-none focus:border-amber-500"
              >
                <option value="ALL">All MFA States</option>
                <option value="ENROLLED">MFA Enrolled</option>
                <option value="PENDING">MFA Pending</option>
              </select>
            </div>
          </div>

          {/* Directory Table */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/70 text-slate-500 uppercase tracking-wider text-[10px] font-bold">
                    <th className="py-3 px-4">Staff Member</th>
                    <th className="py-3 px-4">Sub-Role & Permissions</th>
                    <th className="py-3 px-4">Department</th>
                    <th className="py-3 px-4">Account Status</th>
                    <th className="py-3 px-4">2FA / MFA</th>
                    <th className="py-3 px-4">Joined / Created</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {loading && staffMembers.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-slate-400">
                        <div className="inline-flex items-center gap-2">
                          <RefreshCw className="w-4 h-4 animate-spin text-amber-500" />
                          <span>Loading staff records...</span>
                        </div>
                      </td>
                    </tr>
                  ) : filteredStaff.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-slate-400">
                        No staff members matching your filter criteria.
                      </td>
                    </tr>
                  ) : (
                    filteredStaff.map((staff) => (
                      <tr key={staff.id} className="hover:bg-slate-50/70 transition">
                        {/* Member */}
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-full bg-slate-900 text-amber-400 font-bold flex items-center justify-center shrink-0 text-xs">
                              {staff.first_name?.[0] || staff.email[0].toUpperCase()}
                            </div>
                            <div>
                              <div className="font-bold text-slate-900">{staff.full_name || "Unnamed"}</div>
                              <div className="text-[11px] text-slate-500 font-mono">{staff.email}</div>
                            </div>
                          </div>
                        </td>

                        {/* Role */}
                        <td className="py-3 px-4">
                          <span
                            className={`inline-block px-2 py-0.5 rounded-md text-[10px] font-bold border ${getRoleBadgeStyle(
                              staff.staff_role?.code
                            )}`}
                          >
                            {staff.staff_role?.name || (staff.is_superuser ? "Platform Administrator" : "Staff Member")}
                          </span>
                        </td>

                        {/* Department */}
                        <td className="py-3 px-4 text-slate-700 font-medium">
                          {staff.department || "Operations"}
                        </td>

                        {/* Status */}
                        <td className="py-3 px-4">
                          <span
                            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              staff.status === "ACTIVE"
                                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                : staff.status === "SUSPENDED"
                                ? "bg-rose-50 text-rose-700 border border-rose-200"
                                : "bg-amber-50 text-amber-700 border border-amber-200"
                            }`}
                          >
                            <span
                              className={`w-1.5 h-1.5 rounded-full ${
                                staff.status === "ACTIVE"
                                  ? "bg-emerald-500"
                                  : staff.status === "SUSPENDED"
                                  ? "bg-rose-500"
                                  : "bg-amber-500"
                              }`}
                            />
                            <span>{staff.status}</span>
                          </span>
                        </td>

                        {/* 2FA */}
                        <td className="py-3 px-4">
                          {staff.has_mfa_enabled ? (
                            <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700">
                              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                              <span>Enrolled</span>
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-400">
                              <Lock className="w-3.5 h-3.5 text-slate-400" />
                              <span>Not Enrolled</span>
                            </span>
                          )}
                        </td>

                        {/* Date */}
                        <td className="py-3 px-4 text-slate-500 text-[11px]">
                          {staff.date_joined ? new Date(staff.date_joined).toLocaleDateString() : "--"}
                        </td>

                        {/* Actions */}
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={() => openEditModal(staff)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 text-[11px] font-bold text-slate-700 hover:bg-slate-100 hover:text-slate-900 transition shadow-xs"
                          >
                            <Edit3 className="w-3 h-3 text-amber-600" />
                            <span>Edit Access</span>
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

      {/* Tab 2: Invitations Queue */}
      {activeTab === "invitations" && (
        <div className="space-y-4">
          {/* Filters Bar */}
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-center justify-between gap-3">
            <div className="relative w-full md:w-80">
              <input
                type="text"
                placeholder="Search invited emails or names..."
                value={invitationSearch}
                onChange={(e) => setInvitationSearch(e.target.value)}
                className="w-full h-9 pl-9 pr-3 rounded-xl border border-slate-200 text-xs focus:outline-none focus:border-amber-500 bg-slate-50/50"
              />
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-3 pointer-events-none" />
            </div>

            <div className="flex items-center gap-2 w-full md:w-auto">
              <select
                value={invitationStatusFilter}
                onChange={(e) => setInvitationStatusFilter(e.target.value)}
                className="h-9 px-3 rounded-xl border border-slate-200 text-xs bg-slate-50/50 text-slate-700 focus:outline-none focus:border-amber-500"
              >
                <option value="ALL">All Invitation Statuses</option>
                <option value="PENDING">Pending (Active Link)</option>
                <option value="ACCEPTED">Accepted (Password Set)</option>
                <option value="EXPIRED">Expired</option>
              </select>
            </div>
          </div>

          {/* Invitations Table */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/70 text-slate-500 uppercase tracking-wider text-[10px] font-bold">
                    <th className="py-3 px-4">Invited Recipient</th>
                    <th className="py-3 px-4">Role Assigned</th>
                    <th className="py-3 px-4">Department</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Sent Date</th>
                    <th className="py-3 px-4">Expires At</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {loading && invitations.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-slate-400">
                        <div className="inline-flex items-center gap-2">
                          <RefreshCw className="w-4 h-4 animate-spin text-amber-500" />
                          <span>Loading invitations...</span>
                        </div>
                      </td>
                    </tr>
                  ) : filteredInvitations.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-slate-400">
                        No invitations matching your filter criteria.
                      </td>
                    </tr>
                  ) : (
                    filteredInvitations.map((inv) => (
                      <tr key={inv.id} className="hover:bg-slate-50/70 transition">
                        <td className="py-3 px-4">
                          <div className="font-bold text-slate-900">
                            {inv.first_name || inv.last_name ? `${inv.first_name} ${inv.last_name}` : "Pending Staff"}
                          </div>
                          <div className="text-[11px] text-slate-500 font-mono">{inv.email}</div>
                        </td>

                        <td className="py-3 px-4">
                          <span
                            className={`inline-block px-2 py-0.5 rounded-md text-[10px] font-bold border ${getRoleBadgeStyle(
                              inv.staff_role
                            )}`}
                          >
                            {inv.staff_role_name || inv.staff_role}
                          </span>
                        </td>

                        <td className="py-3 px-4 text-slate-700 font-medium">
                          {inv.department || "Operations"}
                        </td>

                        <td className="py-3 px-4">
                          <span
                            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              inv.status === "ACCEPTED"
                                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                : inv.status === "EXPIRED"
                                ? "bg-rose-50 text-rose-700 border border-rose-200"
                                : "bg-amber-50 text-amber-700 border border-amber-200"
                            }`}
                          >
                            <span
                              className={`w-1.5 h-1.5 rounded-full ${
                                inv.status === "ACCEPTED"
                                  ? "bg-emerald-500"
                                  : inv.status === "EXPIRED"
                                  ? "bg-rose-500"
                                  : "bg-amber-500"
                              }`}
                            />
                            <span>{inv.status}</span>
                          </span>
                        </td>

                        <td className="py-3 px-4 text-slate-500 text-[11px]">
                          {inv.created_at ? new Date(inv.created_at).toLocaleDateString() : "--"}
                        </td>

                        <td className="py-3 px-4 text-slate-500 text-[11px]">
                          {inv.expires_at ? new Date(inv.expires_at).toLocaleString() : "--"}
                        </td>

                        <td className="py-3 px-4 text-right space-x-1.5">
                          {inv.status !== "ACCEPTED" && (
                            <>
                              <button
                                onClick={() => handleResendInvite(inv)}
                                disabled={resendingInviteId === inv.id}
                                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 text-[11px] font-bold text-slate-700 hover:bg-slate-100 transition shadow-xs disabled:opacity-50"
                                title="Generate a fresh token and email link"
                              >
                                <Send className={`w-3 h-3 ${resendingInviteId === inv.id ? "animate-spin text-amber-600" : "text-amber-600"}`} />
                                <span>{resendingInviteId === inv.id ? "Resending..." : "Resend Link"}</span>
                              </button>

                              <button
                                onClick={() => setRevokingInvite(inv)}
                                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-rose-200 text-[11px] font-bold text-rose-700 hover:bg-rose-50 transition shadow-xs"
                                title="Revoke invitation and delete pending user"
                              >
                                <Trash2 className="w-3 h-3 text-rose-600" />
                                <span>Revoke</span>
                              </button>
                            </>
                          )}
                          {inv.status === "ACCEPTED" && (
                            <span className="text-[11px] text-emerald-700 font-semibold flex items-center justify-end gap-1">
                              <Check className="w-3.5 h-3.5" />
                              <span>Active Member</span>
                            </span>
                          )}
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

      {/* Tab 3: Issue Invitation Form */}
      {activeTab === "invite" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h2 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                  <UserPlus className="w-4 h-4 text-amber-500" />
                  <span>Issue Platform Staff Invitation</span>
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Invited staff are provisioned with inactive status until they complete password setup via a cryptographically secure token.
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
                  Recipient: <strong className="font-mono">{inviteResult.email}</strong> as{" "}
                  <strong className="font-bold">{inviteResult.staff_role}</strong>.
                </div>
                {inviteResult.invite_token && (
                  <div className="pt-2 border-t border-emerald-200/60 flex items-center justify-between gap-3">
                    <span className="text-[10px] text-emerald-700 font-mono truncate max-w-sm">
                      Token: {inviteResult.invite_token}
                    </span>
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        onClick={() => handleCopyToken(inviteResult.invite_token!)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-100 hover:bg-emerald-200 text-emerald-800 font-semibold text-[11px] transition"
                      >
                        {copiedToken ? <CheckCheck className="w-3.5 h-3.5 text-emerald-700" /> : <Copy className="w-3.5 h-3.5" />}
                        <span>{copiedToken ? "Copied" : "Copy Token"}</span>
                      </button>
                      <Link
                        href={`/set-password?token=${encodeURIComponent(inviteResult.invite_token)}`}
                        className="inline-flex items-center gap-1 text-xs font-bold text-amber-700 hover:text-amber-800 underline"
                      >
                        <span>Open Activation Page</span>
                        <ExternalLink className="w-3.5 h-3.5" />
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            )}

            <form onSubmit={handleInviteSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Corporate Work Email <span className="text-amber-500">*</span>
                </label>
                <div className="relative">
                  <input
                    type="email"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
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
                      value={inviteFirstName}
                      onChange={(e) => setInviteFirstName(e.target.value)}
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
                      value={inviteLastName}
                      onChange={(e) => setInviteLastName(e.target.value)}
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
                    Operational Sub-Role <span className="text-amber-500">*</span>
                  </label>
                  <select
                    value={inviteStaffRole}
                    onChange={(e) => setInviteStaffRole(e.target.value as StaffInvitePayload["staff_role"])}
                    className="w-full h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 bg-slate-50/50 font-medium"
                  >
                    <option value="VERIFICATION_OFFICER">Verification Officer (seller.verify, listing.review)</option>
                    <option value="DISPUTE_MANAGER">Dispute Manager (dispute.manage, order.refund)</option>
                    <option value="FINANCE_OFFICER">Finance Officer (finance.payout, order.refund)</option>
                    <option value="SUPPORT_AGENT">Support Agent (Read-only customer support)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Department</label>
                  <div className="relative">
                    <input
                      type="text"
                      value={inviteDepartment}
                      onChange={(e) => setInviteDepartment(e.target.value)}
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
                  disabled={isInviting}
                  className="inline-flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-slate-950 text-xs font-bold transition-all shadow hover:shadow-amber-500/20 disabled:opacity-60"
                >
                  <UserPlus className="w-3.5 h-3.5" />
                  <span>{isInviting ? "Generating & Dispatching..." : "Create & Send Staff Invitation"}</span>
                </button>
              </div>
            </form>
          </div>

          {/* Quick Guide Card */}
          <div className="bg-slate-50 rounded-2xl border border-slate-200 p-6 space-y-4">
            <div className="pb-3 border-b border-slate-200">
              <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                Invitation Lifecycle & Governance
              </h3>
              <p className="text-[11px] text-slate-500 mt-0.5">
                DriverXtra staff accounts require strict dual-authorization.
              </p>
            </div>

            <div className="space-y-3 text-xs text-slate-600">
              <div className="p-3 bg-white rounded-xl border border-slate-200 space-y-1">
                <div className="font-bold text-slate-900 flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                  <span>48-Hour Token Window</span>
                </div>
                <p className="text-[11px] text-slate-500">
                  Each set-password link expires automatically after 48 hours. Admins can refresh or revoke at any time.
                </p>
              </div>

              <div className="p-3 bg-white rounded-xl border border-slate-200 space-y-1">
                <div className="font-bold text-slate-900 flex items-center gap-1.5">
                  <KeyRound className="w-3.5 h-3.5 text-purple-600" />
                  <span>MFA Enrollment On First Login</span>
                </div>
                <p className="text-[11px] text-slate-500">
                  Staff accounts must enroll a TOTP authenticator (Google Authenticator, 1Password) before accessing administrative tools.
                </p>
              </div>

              <div className="p-3 bg-white rounded-xl border border-slate-200 space-y-1">
                <div className="font-bold text-slate-900 flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-amber-600" />
                  <span>15-Minute Session Tokens</span>
                </div>
                <p className="text-[11px] text-slate-500">
                  Elevated operational credentials enforce short-lived 15-minute access lifetimes.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Roles & Permissions Matrix */}
      {activeTab === "roles" && (
        <div className="space-y-4">
          <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
            <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <Shield className="w-4 h-4 text-amber-500" />
              <span>Platform Staff Roles & Capabilities Matrix</span>
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              DriverXtra enforces role-based access control (RBAC). Staff users operate within scoped capability boundaries.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {roles.length > 0 ? (
              roles.map((r) => (
                <div key={r.id} className="p-5 bg-white rounded-2xl border border-slate-200 shadow-sm space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-bold text-slate-900">{r.name}</h3>
                      <span className="font-mono text-[10px] text-slate-500">{r.code}</span>
                    </div>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${getRoleBadgeStyle(r.code)}`}>
                      Operational
                    </span>
                  </div>

                  <p className="text-xs text-slate-600">{r.description || "Operational sub-role for platform management."}</p>

                  <div>
                    <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1.5">
                      Granted Permissions:
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {r.permissions && r.permissions.length > 0 ? (
                        r.permissions.map((p) => (
                          <span
                            key={p}
                            className="font-mono text-[10px] bg-slate-100 text-slate-800 border border-slate-200 px-2 py-0.5 rounded-md"
                          >
                            {p}
                          </span>
                        ))
                      ) : (
                        <span className="text-[11px] text-slate-400 italic">No elevated mutate permissions (Read-only queue).</span>
                      )}
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="col-span-2 p-8 text-center text-slate-400 bg-white rounded-2xl border border-slate-200">
                Loading role definitions...
              </div>
            )}
          </div>
        </div>
      )}

      {/* Edit Staff Member Modal */}
      {editingStaff && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <Edit3 className="w-4 h-4 text-amber-500" />
                <span>Modify Staff Access & Sub-Role</span>
              </h3>
              <button onClick={() => setEditingStaff(null)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="text-xs space-y-1">
              <div className="text-slate-500 font-medium">Editing user:</div>
              <div className="font-bold text-slate-900">{editingStaff.full_name}</div>
              <div className="text-slate-400 font-mono text-[11px]">{editingStaff.email}</div>
            </div>

            <div className="space-y-3.5">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Operational Sub-Role</label>
                <select
                  value={editRole}
                  onChange={(e) => setEditRole(e.target.value)}
                  className="w-full h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none bg-slate-50"
                >
                  <option value="VERIFICATION_OFFICER">Verification Officer (seller.verify, listing.review)</option>
                  <option value="DISPUTE_MANAGER">Dispute Manager (dispute.manage, order.refund)</option>
                  <option value="FINANCE_OFFICER">Finance Officer (finance.payout, order.refund)</option>
                  <option value="SUPPORT_AGENT">Support Agent (Read-only queues)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Department</label>
                <input
                  type="text"
                  value={editDepartment}
                  onChange={(e) => setEditDepartment(e.target.value)}
                  className="w-full h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none bg-slate-50"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Account Operational Status</label>
                <select
                  value={editStatus}
                  disabled={String(currentUser?.id) === String(editingStaff.id)}
                  onChange={(e) => setEditStatus(e.target.value as "ACTIVE" | "SUSPENDED")}
                  className="w-full h-10 px-3 rounded-xl border border-slate-300 text-xs text-slate-900 focus:border-amber-500 focus:outline-none bg-slate-50 disabled:opacity-50"
                >
                  <option value="ACTIVE">ACTIVE (Granted platform access)</option>
                  <option value="SUSPENDED">SUSPENDED (Revoke login access)</option>
                </select>
                {String(currentUser?.id) === String(editingStaff.id) && (
                  <p className="text-[10px] text-amber-600 mt-1">You cannot suspend your own administrator account.</p>
                )}
              </div>
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditingStaff(null)}
                className="px-4 py-2 rounded-xl border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleUpdateStaff}
                disabled={isUpdatingStaff}
                className="px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-600 text-slate-950 text-xs font-bold transition disabled:opacity-60"
              >
                {isUpdatingStaff ? "Saving Changes..." : "Save Modifications"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Revoke Invitation Modal */}
      {revokingInvite && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center shrink-0">
                <Trash2 className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-900">Revoke Staff Invitation?</h3>
                <p className="text-xs text-slate-500">This action will immediately invalidate the set-password link.</p>
              </div>
            </div>

            <div className="p-3 bg-slate-50 rounded-xl text-xs space-y-1">
              <div>Recipient: <strong className="font-mono text-slate-800">{revokingInvite.email}</strong></div>
              <div>Role: <strong>{revokingInvite.staff_role_name}</strong></div>
            </div>

            <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setRevokingInvite(null)}
                className="px-4 py-2 rounded-xl border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleRevokeInvite}
                disabled={isRevoking}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold transition disabled:opacity-60"
              >
                {isRevoking ? "Revoking..." : "Confirm Revoke"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
