"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/prototype-auth/auth-context";
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

export default function LoginPage() {
  const router = useRouter();
  const { login, verifyMfaLogin, mfaChallenge, clearMfaChallenge, authError, clearAuthError, availablePrototypeUsers, isAuthenticated, isInitialized } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isVerifyingMfa, setIsVerifyingMfa] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [resendMsg, setResendMsg] = useState<string | null>(null);

  const showDevLogin = process.env.NEXT_PUBLIC_ENABLE_DEV_LOGIN === "true";

  useEffect(() => {
    if (isInitialized && isAuthenticated) {
      router.replace("/platform");
    }
  }, [isInitialized, isAuthenticated, router]);

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
        router.replace("/platform");
      }
      // If mfaRequired, mfaChallenge state is set in AuthContext and UI switches to MFA prompt
    } else {
      setError(authError || "Invalid email or password.");
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

    const verified = await verifyMfaLogin(mfaCode.trim());
    setIsVerifyingMfa(false);

    if (verified) {
      router.replace("/platform");
    } else {
      setError(authError || "Invalid authentication code. Please try again.");
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
          {mfaChallenge ? "Two-Factor Authentication" : "Platform Sign In"}
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          {mfaChallenge
            ? "Enter 6-digit TOTP code from your authenticator app"
            : "Identity & RBAC Architecture (Doc 04 §7) • Enter Enterprise Portal"}
        </p>
      </div>

      <div className="mt-6 sm:mx-auto sm:w-full sm:max-w-lg relative z-10 px-4">
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl">
          {/* Environment Banner */}
          {!mfaChallenge && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-3.5 mb-6 text-xs text-amber-300 flex items-start gap-2.5">
              <Info className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <strong className="font-bold">Production Authentication Engine:</strong>
                <div className="text-[11px] text-amber-200/80 mt-0.5">
                  Connected to Django REST Framework backend. Session tokens and permissions are cryptographically verified server-side.
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
                  <div className="font-bold text-white">Staff / Security Verification Required</div>
                  <div className="text-slate-400 mt-0.5">Account: <span className="text-amber-300 font-mono">{mfaChallenge.email}</span></div>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                  6-Digit Authenticator Code
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
                <span>{isVerifyingMfa ? "Verifying TOTP Code..." : "Verify & Complete Sign In"}</span>
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
                  Work Email / Username
                </label>
                <div className="relative">
                  <input
                    type="email"
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
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    placeholder="••••••••••••"
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
                <span>{isSubmitting ? "Authenticating via Real API..." : "Sign In to Platform"}</span>
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
                Developer Autofill Presets (NEXT_PUBLIC_ENABLE_DEV_LOGIN=true):
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
