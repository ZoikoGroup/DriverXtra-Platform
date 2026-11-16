"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import { PrototypeUser } from "@/lib/prototype-auth/types";
import { api } from "@/lib/api/client";
import AuthSplitLayout from "@/components/auth/AuthSplitLayout";
import {
  Lock,
  Mail,
  Eye,
  EyeOff,
  Building2,
  Wrench,
  Truck,
  ShieldAlert,
  Car,
  ArrowRight,
  ShieldCheck,
  KeyRound,
  Check,
  ChevronDown,
} from "lucide-react";

export default function LoginClient() {
  const router = useRouter();
  const {
    login,
    verifyMfaLogin,
    mfaChallenge,
    clearMfaChallenge,
    authError,
    clearAuthError,
    availablePrototypeUsers,
    isAuthenticated,
    isInitialized,
    user,
  } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isVerifyingMfa, setIsVerifyingMfa] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [resendMsg, setResendMsg] = useState<string | null>(null);
  const [enrollData, setEnrollData] = useState<{ secret: string; qr_code_uri: string } | null>(null);
  const [loadingEnroll, setLoadingEnroll] = useState(false);
  const [copiedSecret, setCopiedSecret] = useState(false);
  const [devPresetsOpen, setDevPresetsOpen] = useState(false);

  useEffect(() => {
    let ignore = false;
    if (mfaChallenge?.enrollmentRequired && mfaChallenge.preAuthToken) {
      const fetchEnrollment = async () => {
        setLoadingEnroll(true);
        try {
          const res = await api.auth.enrolMfa(mfaChallenge.preAuthToken!);
          if (!ignore) {
            setEnrollData({ secret: res.secret, qr_code_uri: res.qr_code_uri });
          }
        } catch (err) {
          if (!ignore) {
            setError(err instanceof Error ? err.message : "Failed to load MFA enrollment details.");
          }
        } finally {
          if (!ignore) {
            setLoadingEnroll(false);
          }
        }
      };
      fetchEnrollment();
    } else {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setEnrollData(null);
    }
    return () => {
      ignore = true;
    };
  }, [mfaChallenge]);

  const showDevLogin = process.env.NEXT_PUBLIC_ENABLE_DEV_LOGIN === "true";

  const getRedirectForRole = useCallback((userObj?: PrototypeUser | null, role?: string): string => {
    const r = (role || userObj?.activeRole || user?.activeRole || "").toUpperCase();
    const staffCode = (userObj?.staff_role?.code || user?.staff_role?.code || "").toUpperCase();

    if (r === "ADMIN") {
      return "/platform?tab=admin_marketplace_review";
    }
    if (r === "STAFF") {
      switch (staffCode) {
        case "DISPUTE_MANAGER":
          return "/platform?tab=admin_disputes_refunds";
        case "FINANCE_OFFICER":
          return "/platform?tab=admin_approvals";
        case "VERIFICATION_OFFICER":
          return "/platform?tab=admin_marketplace_review";
        case "SUPPORT_AGENT":
          return "/platform?tab=support_overview";
        default:
          return "/platform?tab=marketplace_browse";
      }
    }
    switch (r) {
      case "SELLER":
        return "/platform?tab=seller_inventory";
      case "WORKSHOP":
        return "/platform?tab=workshop_landing";
      case "BUYER":
      default:
        return "/platform?tab=marketplace_browse";
    }
  }, [user]);

  useEffect(() => {
    clearAuthError();
  }, [clearAuthError]);

  useEffect(() => {
    if (isInitialized && isAuthenticated) {
      router.replace(getRedirectForRole(user));
    }
  }, [isInitialized, isAuthenticated, router, user, getRedirectForRole]);

  const handleResend = async () => {
    if (!email) {
      setError("Please enter your email address to receive a verification link.");
      return;
    }
    setIsResending(true);
    setResendMsg(null);
    try {
      const res = await api.auth.resendVerification(email.trim().toLowerCase());
      setResendMsg(res.message || "Verification email sent. Please check your inbox.");
    } catch (err: unknown) {
      setResendMsg(err instanceof Error ? err.message : "Failed to send verification email.");
    } finally {
      setIsResending(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError("Please provide both email and password.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setResendMsg(null);
    clearAuthError();

    const result = await login(email, password);
    setIsSubmitting(false);

    if (result.success) {
      if (!result.mfaRequired) {
        router.replace(getRedirectForRole(result.user || user, result.activeRole));
      }
    } else {
      setError(result.error || authError || "Invalid email or password.");
    }
  };

  const handleMfaSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!mfaCode || mfaCode.trim().length !== 6) {
      setError("Please enter a valid 6-digit verification code.");
      return;
    }

    setIsVerifyingMfa(true);
    setError(null);

    const result = await verifyMfaLogin(mfaCode.trim());
    setIsVerifyingMfa(false);

    if (result.success) {
      router.replace(getRedirectForRole(result.user || user, result.activeRole));
    } else {
      setError(result.error || authError || "Invalid authentication code. Please try again.");
    }
  };

  const handleFastLogin = async (targetEmail: string) => {
    setEmail(targetEmail);
    if (targetEmail.includes("admin")) {
      setPassword("SuperAdminPassword123!");
    } else {
      setPassword("SecurePassword123!");
    }
    setError(null);
    clearAuthError();
  };

  const displayedError = error || authError;

  return (
    <AuthSplitLayout activeTab="login">
      {/* Brand Header Inside Card */}
      <div className="text-center pb-4 xl:pb-5">
        <div className="inline-flex items-center justify-center gap-2 mb-2">
          <div className="w-9 h-9 rounded-xl bg-[#FFC20E] flex items-center justify-center font-black text-slate-950 text-lg shadow-md shadow-amber-400/20">
            DX
          </div>
          <span className="text-2xl font-black text-[#17212C] tracking-tight">
            Driver<span className="text-[#FFC20E]">Xtra</span>
          </span>
        </div>

        <h2 className="text-xl sm:text-2xl font-black text-[#17212C] tracking-tight">
          {mfaChallenge ? "Two-Factor Authentication" : "Welcome back"}
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          {mfaChallenge
            ? "Enter 6-digit TOTP code from your authenticator app"
            : "Sign in to your DriverXtra account"}
        </p>
      </div>

      {/* Resend Verification Notice Banner */}
      {resendMsg && (
        <div className="mb-4 p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-800 text-xs font-semibold flex items-center gap-2">
          <Check className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{resendMsg}</span>
        </div>
      )}

      {/* Error Banner */}
      {displayedError && (
        <div className="mb-5 p-3.5 bg-rose-50 border border-rose-200 rounded-xl space-y-2">
          <div className="text-rose-800 text-xs font-semibold">{displayedError}</div>
          {(displayedError.toLowerCase().includes("not verified") ||
            displayedError.toLowerCase().includes("verify your email")) && (
            <div className="pt-2 flex items-center justify-between border-t border-rose-200/60 text-xs">
              <button
                type="button"
                onClick={handleResend}
                disabled={isResending}
                className="text-amber-700 hover:text-amber-800 font-bold underline disabled:opacity-50"
              >
                {isResending ? "Sending link..." : "Resend Verification Email"}
              </button>
              <Link
                href={`/verify-email?email=${encodeURIComponent(email)}`}
                className="text-slate-600 hover:text-slate-900 underline font-medium"
              >
                Enter Token
              </Link>
            </div>
          )}
        </div>
      )}

      {/* MFA Challenge State */}
      {mfaChallenge ? (
        <form onSubmit={handleMfaSubmit} className="space-y-5">
          <div className="p-4 bg-amber-50/70 border border-amber-200 rounded-2xl flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-400/20 flex items-center justify-center shrink-0">
              <ShieldCheck className="w-5 h-5 text-amber-700" />
            </div>
            <div className="text-xs">
              <div className="font-bold text-slate-900">
                {mfaChallenge.enrollmentRequired
                  ? "Mandatory Two-Factor Authentication Setup"
                  : "Staff / Security Verification Required"}
              </div>
              <div className="text-slate-600 mt-0.5">
                Account: <span className="text-amber-800 font-mono font-bold">{mfaChallenge.email}</span>
              </div>
            </div>
          </div>

          {mfaChallenge.enrollmentRequired && (
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-2xl space-y-3">
              <div className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                <KeyRound className="w-4 h-4 text-amber-600" />
                <span>Step 1: Set up in Authenticator App</span>
              </div>
              <p className="text-[11px] text-slate-600 leading-relaxed">
                Open Google Authenticator, Authy, or Microsoft Authenticator. Tap <strong>+</strong>, choose <strong>Enter a setup key</strong>, and paste the key below:
              </p>
              {loadingEnroll ? (
                <div className="p-3 bg-white border border-slate-200 rounded-xl text-center text-xs text-slate-400 animate-pulse">
                  Generating secure TOTP secret key...
                </div>
              ) : enrollData?.secret ? (
                <div className="flex items-center justify-between bg-white border border-slate-300 px-3.5 py-2.5 rounded-xl">
                  <div className="text-xs text-slate-900 font-mono font-bold tracking-widest select-all">
                    {enrollData.secret}
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(enrollData.secret);
                      setCopiedSecret(true);
                      setTimeout(() => setCopiedSecret(false), 2000);
                    }}
                    className="px-2.5 py-1 bg-amber-100 hover:bg-amber-200 border border-amber-300 rounded-lg text-amber-900 text-xs font-bold transition-all ml-2"
                  >
                    {copiedSecret ? "Copied!" : "Copy Key"}
                  </button>
                </div>
              ) : null}
            </div>
          )}

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              {mfaChallenge.enrollmentRequired
                ? "Step 2: Enter 6-Digit Verification Code"
                : "6-Digit Authenticator Code"}
            </label>
            <div className="relative">
              <input
                type="text"
                name="mfa-code"
                autoComplete="one-time-code"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ""))}
                required
                placeholder="Enter 6-digit code"
                className="w-full h-12 px-3.5 pl-10 bg-white border border-slate-300 rounded-xl text-sm font-mono tracking-widest text-slate-900 placeholder:text-slate-400 focus:border-[#ffc20e] focus:ring-2 focus:ring-[#ffc20e]/30 focus:outline-none transition-all"
              />
              <KeyRound className="w-4 h-4 text-slate-400 absolute left-3.5 top-4 pointer-events-none" />
            </div>
            <p className="text-[11px] text-slate-500 mt-1.5 text-center">
              Open Google Authenticator, Authy, or your 2FA app to view your code.
            </p>
          </div>

          <button
            type="submit"
            disabled={isVerifyingMfa || mfaCode.length !== 6}
            className="w-full h-12 bg-[#ffc20e] hover:bg-[#e8ac00] text-slate-950 font-black rounded-xl text-sm flex items-center justify-center gap-2 shadow-md hover:shadow-amber-400/20 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <span>
              {isVerifyingMfa
                ? "Verifying TOTP Code..."
                : mfaChallenge.enrollmentRequired
                ? "Verify & Activate 2FA"
                : "Verify & Complete Sign In"}
            </span>
            <ArrowRight className="w-4 h-4" />
          </button>

          <div className="text-center pt-2">
            <button
              type="button"
              onClick={() => {
                clearMfaChallenge();
                setError(null);
              }}
              className="text-xs text-slate-500 hover:text-slate-900 underline font-medium"
            >
              Cancel and return to password login
            </button>
          </div>
        </form>
      ) : (
        /* Standard Login Form */
        <form onSubmit={handleSubmit} className="space-y-3.5">
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
              Email address
            </label>
            <div className="relative">
              <input
                type="email"
                name="login-email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="name@company.com"
                className="w-full h-11 px-3.5 pl-10 bg-white border border-slate-300 rounded-xl text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#FFC20E] focus:ring-2 focus:ring-[#FFC20E]/25 focus:outline-none transition-all"
              />
              <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5 pointer-events-none" />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700">
                Password
              </label>
            </div>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                name="login-password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="Enter your password"
                className="w-full h-11 px-3.5 pl-10 pr-10 bg-white border border-slate-300 rounded-xl text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#FFC20E] focus:ring-2 focus:ring-[#FFC20E]/25 focus:outline-none transition-all"
              />
              <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5 pointer-events-none" />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3.5 top-3 text-slate-400 hover:text-slate-700 transition-colors"
                aria-label="Toggle password view"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Forgot Password Link */}
          <div className="flex justify-end pt-0.5">
            <Link
              href="/forgot-password"
              className="text-xs text-amber-700 hover:text-amber-800 font-bold hover:underline transition-colors"
            >
              Forgot password?
            </Link>
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full h-11 sm:h-12 bg-[#FFC20E] hover:bg-[#E8AC00] text-slate-950 font-black rounded-xl text-sm sm:text-base flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <span>{isSubmitting ? "Signing in..." : "Sign In"}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>
      )}

      {/* Path to Register */}
      {!mfaChallenge && (
        <div className="mt-4 text-center">
          <span className="text-xs text-slate-500">
            New to DriverXtra?{" "}
            <Link
              href="/register"
              className="text-amber-700 hover:text-amber-800 font-bold hover:underline"
            >
              Register
            </Link>
          </span>
        </div>
      )}

      {/* Dev Quick Login Presets (Gated behind NEXT_PUBLIC_ENABLE_DEV_LOGIN === "true") */}
      {!mfaChallenge && showDevLogin && (
        <div className="mt-6 pt-5 border-t border-slate-200">
          <button
            type="button"
            onClick={() => setDevPresetsOpen(!devPresetsOpen)}
            className="w-full flex items-center justify-between text-[11px] font-bold uppercase tracking-wider text-slate-600 hover:text-slate-900 transition-colors"
          >
            <span>Demonstration & Quick Access Accounts</span>
            <ChevronDown
              className={`w-3.5 h-3.5 transition-transform ${devPresetsOpen ? "rotate-180" : ""}`}
            />
          </button>

          {devPresetsOpen && (
            <div className="grid grid-cols-1 gap-2 pt-3 animate-in fade-in duration-150">
              {availablePrototypeUsers.map((u) => {
                let RoleIcon = Car;
                let badgeColor = "bg-blue-50 text-blue-700 border-blue-200";
                let badgeText = "Consumer";
                if (u.role === "INVENTORY_MANAGER") {
                  RoleIcon = Building2;
                  badgeColor = "bg-amber-50 text-amber-800 border-amber-200";
                  badgeText = "Dealer";
                } else if (u.role === "WORKSHOP_MANAGER") {
                  RoleIcon = Wrench;
                  badgeColor = "bg-purple-50 text-purple-700 border-purple-200";
                  badgeText = "Workshop";
                } else if (u.role === "FLEET_MANAGER") {
                  RoleIcon = Truck;
                  badgeColor = "bg-emerald-50 text-emerald-700 border-emerald-200";
                  badgeText = "Fleet";
                } else if (u.role === "MARKETPLACE_ADMIN") {
                  RoleIcon = ShieldAlert;
                  badgeColor = "bg-rose-50 text-rose-700 border-rose-200";
                  badgeText = "Admin Panel";
                }

                return (
                  <button
                    key={u.id}
                    type="button"
                    onClick={() => handleFastLogin(u.email)}
                    className="w-full text-left p-2.5 rounded-xl bg-slate-50 hover:bg-slate-100 border border-slate-200 hover:border-amber-400/50 transition-all flex items-center justify-between group"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="w-7 h-7 rounded-lg bg-white border border-slate-200 flex items-center justify-center shrink-0">
                        <RoleIcon className="w-3.5 h-3.5 text-amber-600" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-xs font-bold text-slate-900 group-hover:text-amber-800 transition-colors truncate">
                          {u.fullName}
                        </div>
                        <div className="text-[10px] text-slate-500 truncate">
                          {u.organizationName}
                        </div>
                      </div>
                    </div>

                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded border shrink-0 ${badgeColor}`}>
                      {badgeText}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </AuthSplitLayout>
  );
}
