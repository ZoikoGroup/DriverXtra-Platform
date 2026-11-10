"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import { PrototypeUser } from "@/lib/prototype-auth/types";
import { api } from "@/lib/api/client";
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
  Info,
  ShieldCheck,
  KeyRound
} from "lucide-react";

export default function LoginClient() {
  const router = useRouter();
  const { login, verifyMfaLogin, mfaChallenge, clearMfaChallenge, authError, clearAuthError, availablePrototypeUsers, isAuthenticated, isInitialized, user } = useAuth();

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
    // Clear any stale auth errors on mount so unauthenticated users see a clean login screen
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
      // If mfaRequired, mfaChallenge state is set in AuthContext and UI switches to MFA prompt
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
    <div className="min-h-screen bg-slate-950 flex flex-col justify-center py-12 sm:px-6 lg:px-8 relative overflow-hidden">
      {/* Background radial glow */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-amber-500/10 rounded-full blur-3xl pointer-events-none"></div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md relative z-10 text-center">
        {/* Brand Logo */}
        <div className="inline-flex items-center gap-2.5 mb-2">
          <div className="w-10 h-10 rounded-xl bg-amber-400 flex items-center justify-center font-black text-slate-950 text-xl shadow-lg shadow-amber-400/20">
            DX
          </div>
          <span className="text-2xl font-black text-white tracking-tight">
            Driver<span className="text-amber-400">Xtra</span>
          </span>
        </div>

        <h2 className="text-xl font-bold tracking-tight text-white mt-2">
          {mfaChallenge ? "Two-Factor Authentication" : "Sign in to DriverXtra"}
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          {mfaChallenge
            ? "Enter 6-digit TOTP code from your authenticator app"
            : "Sign in to access your DriverXtra commercial portal"}
        </p>
      </div>

      <div className="mt-6 sm:mx-auto sm:w-full sm:max-w-lg relative z-10 px-4">
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl">
          {/* Environment Banner */}
          {!mfaChallenge && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-3.5 mb-6 text-xs text-amber-300 flex items-start gap-2.5">
              <Info className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <strong className="font-bold">Enterprise Sign-In:</strong>
                <div className="text-[11px] text-amber-200/80 mt-0.5">
                  Enter your registered DriverXtra credentials or business organisation account.
                </div>
              </div>
            </div>
          )}

          {resendMsg && (
            <div className="mb-4 p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-emerald-300 text-xs font-semibold">
              {resendMsg}
            </div>
          )}

          {displayedError && (
            <div className="mb-4 p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-xl space-y-2">
              <div className="text-rose-300 text-xs font-semibold">{displayedError}</div>
              {(displayedError.toLowerCase().includes("not verified") || displayedError.toLowerCase().includes("verify your email")) && (
                <div className="pt-1.5 flex items-center justify-between border-t border-rose-500/20 text-xs">
                  <button
                    type="button"
                    onClick={handleResend}
                    disabled={isResending}
                    className="text-amber-400 hover:text-amber-300 font-bold underline disabled:opacity-50"
                  >
                    {isResending ? "Sending link..." : "Resend Verification Email"}
                  </button>
                  <Link
                    href={`/verify-email?email=${encodeURIComponent(email)}`}
                    className="text-slate-300 hover:text-white underline font-medium"
                  >
                    Enter Token
                  </Link>
                </div>
              )}
            </div>
          )}

          {/* MFA Challenge Screen */}
          {mfaChallenge ? (
            <form onSubmit={handleMfaSubmit} className="space-y-5">
              <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-2xl flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-amber-400/20 flex items-center justify-center shrink-0">
                  <ShieldCheck className="w-5 h-5 text-amber-400" />
                </div>
                <div className="text-xs">
                  <div className="font-bold text-white">
                    {mfaChallenge.enrollmentRequired ? "Mandatory Two-Factor Authentication Setup" : "Staff / Security Verification Required"}
                  </div>
                  <div className="text-slate-400 mt-0.5">Account: <span className="text-amber-300 font-mono">{mfaChallenge.email}</span></div>
                </div>
              </div>

              {mfaChallenge.enrollmentRequired && (
                <div className="p-4 bg-slate-950/90 border border-amber-500/30 rounded-2xl space-y-3">
                  <div className="text-xs font-bold text-amber-300 flex items-center gap-1.5">
                    <KeyRound className="w-4 h-4 text-amber-400" />
                    <span>Step 1: Set up in Authenticator App</span>
                  </div>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    Open Google Authenticator, Authy, or Microsoft Authenticator on your phone. Tap <strong>+</strong>, choose <strong>Enter a setup key</strong>, and paste the key below:
                  </p>
                  {loadingEnroll ? (
                    <div className="p-3 bg-slate-900 border border-slate-800 rounded-xl text-center text-xs text-slate-400 animate-pulse">
                      Generating secure TOTP secret key...
                    </div>
                  ) : enrollData?.secret ? (
                    <div className="flex items-center justify-between bg-slate-900 border border-slate-700 px-3.5 py-2.5 rounded-xl">
                      <div className="text-xs text-amber-300 font-mono font-bold tracking-widest select-all">
                        {enrollData.secret}
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText(enrollData.secret);
                          setCopiedSecret(true);
                          setTimeout(() => setCopiedSecret(false), 2000);
                        }}
                        className="px-2.5 py-1 bg-amber-400/10 hover:bg-amber-400/20 border border-amber-400/30 rounded-lg text-amber-300 text-xs font-bold transition-all ml-2"
                      >
                        {copiedSecret ? "Copied!" : "Copy Key"}
                      </button>
                    </div>
                  ) : null}
                </div>
              )}

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                  {mfaChallenge.enrollmentRequired ? "Step 2: Enter 6-Digit Verification Code" : "6-Digit Authenticator Code"}
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
  className="w-full h-11 px-3.5 pl-10 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white placeholder:text-slate-600 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
/>

                  <KeyRound className="w-4 h-4 text-slate-500 absolute left-3.5 top-4 pointer-events-none" />
                </div>
                <p className="text-[11px] text-slate-400 mt-1 text-center">
                  Open Google Authenticator, Authy, or your 2FA app to view your code.
                </p>
              </div>

              <button
                type="submit"
                disabled={isVerifyingMfa || mfaCode.length !== 6}
                className="w-full h-11 bg-amber-400 hover:bg-amber-500 text-slate-950 font-black rounded-xl text-sm flex items-center justify-center gap-2 shadow-md transition-all hover:shadow-amber-400/20 disabled:opacity-60 disabled:cursor-not-allowed"
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

              <div className="text-center">
                <button
                  type="button"
                  onClick={() => {
                    clearMfaChallenge();
                    setError(null);
                  }}
                  className="text-xs text-slate-400 hover:text-white underline font-medium"
                >
                  Cancel and return to password login
                </button>
              </div>
            </form>
          ) : (
            /* Standard Login Form */
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                  Work Email or Username
                </label>
                <div className="relative">
                  <input
  type="email"
  name="login-email"
  autoComplete="off"
  value={email}
  onChange={(e) => setEmail(e.target.value)}
  required
  placeholder="name@organization.com"
  className="w-full h-11 px-3.5 pl-10 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white placeholder:text-slate-600 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
/>
                  <Mail className="w-4 h-4 text-slate-500 absolute left-3.5 top-3.5 pointer-events-none" />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-400">
                    Password
                  </label>
                  <Link
                    href="/forgot-password"
                    className="text-[11px] text-amber-400 hover:text-amber-300 font-semibold"
                  >
                    Forgot password?
                  </Link>
                </div>
                <div className="relative">
                  <input
  type={showPassword ? "text" : "password"}
  name="login-password"
  autoComplete="new-password"
  value={password}
  onChange={(e) => setPassword(e.target.value)}
  required
  placeholder="Enter your password"
  className="w-full h-11 px-3.5 pl-10 pr-10 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white placeholder:text-slate-600 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
/>
                  <Lock className="w-4 h-4 text-slate-500 absolute left-3.5 top-3.5 pointer-events-none" />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3.5 top-3 text-slate-500 hover:text-slate-300"
                    aria-label="Toggle password view"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full h-11 bg-amber-400 hover:bg-amber-500 text-slate-950 font-black rounded-xl text-sm flex items-center justify-center gap-2 shadow-md transition-all hover:shadow-amber-400/20 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <span>{isSubmitting ? "Signing in..." : "Sign In"}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          )}

          {/* Path to Register */}
          {!mfaChallenge && (
            <div className="mt-4 text-center">
              <span className="text-xs text-slate-400">
                Need a new platform account?{" "}
                <Link
                  href="/register"
                  className="text-amber-400 hover:text-amber-300 font-bold hover:underline inline-flex items-center gap-1"
                >
                  <span>Register here</span>
                </Link>
              </span>
            </div>
          )}

          {/* Dev Quick Login Presets (Gated behind NEXT_PUBLIC_ENABLE_DEV_LOGIN === "true") */}
          {!mfaChallenge && showDevLogin && (
            <div className="mt-8 pt-6 border-t border-slate-800">
              <span className="block text-[11px] font-bold uppercase tracking-wider text-amber-400 mb-3 text-center">
                Demonstration & Quick Access Accounts:
              </span>

              <div className="grid grid-cols-1 gap-2.5">
                {availablePrototypeUsers.map((u) => {
                  let RoleIcon = Car;
                  let badgeColor = "bg-blue-500/10 text-blue-400 border-blue-500/20";
                  let badgeText = "Consumer";
                  if (u.role === "INVENTORY_MANAGER") {
                    RoleIcon = Building2;
                    badgeColor = "bg-amber-500/10 text-amber-400 border-amber-500/20";
                    badgeText = "Dealer";
                  } else if (u.role === "WORKSHOP_MANAGER") {
                    RoleIcon = Wrench;
                    badgeColor = "bg-purple-500/10 text-purple-400 border-purple-500/20";
                    badgeText = "Workshop";
                  } else if (u.role === "FLEET_MANAGER") {
                    RoleIcon = Truck;
                    badgeColor = "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
                    badgeText = "Fleet";
                  } else if (u.role === "MARKETPLACE_ADMIN") {
                    RoleIcon = ShieldAlert;
                    badgeColor = "bg-rose-500/20 text-rose-300 border-rose-500/40";
                    badgeText = "Admin Panel";
                  }

                  return (
                    <button
                      key={u.id}
                      type="button"
                      onClick={() => handleFastLogin(u.email)}
                      className="w-full text-left p-3 rounded-xl bg-slate-950 hover:bg-slate-800/80 border border-slate-800 hover:border-amber-400/50 transition-all flex items-center justify-between group"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-8 h-8 rounded-lg bg-slate-800 flex items-center justify-center shrink-0">
                          <RoleIcon className="w-4 h-4 text-amber-400" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-xs font-bold text-white group-hover:text-amber-300 transition-colors truncate">
                            {u.fullName}
                          </div>
                          <div className="text-[10px] text-slate-400 truncate">
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
            </div>
          )}
        </div>

        {/* Footer info */}
        <div className="mt-6 text-center text-xs text-slate-500">
          DriverXtra Global Automotive Commerce Infrastructure • Zoiko Tech Inc.
        </div>
      </div>
    </div>
  );
}
