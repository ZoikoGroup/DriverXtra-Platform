"use client";

import React, { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api/client";
import {
  CheckCircle2,
  AlertCircle,
  Mail,
  KeyRound,
  ArrowRight,
  RefreshCw,
  ArrowLeft
} from "lucide-react";

function cleanToken(input: string): string {
  if (!input) return "";
  let val = input.trim();

  // 1. If contains token= parameter anywhere (URL, query string, or standalone token=)
  if (val.includes("token=")) {
    const match = val.match(/(?:[?&]|(?<!\w))token=([^&\s]+)/);
    if (match && match[1]) {
      val = match[1].trim();
    }
  }

  // 2. If labeled like "Verification Token: xyz", "Reset Token: xyz", "Token: xyz", "token : xyz", etc.
  const labelMatch = val.match(/^(?:(?:verification|password\s+reset|reset)\s+)?token\s*[:=\-]\s*([^\s]+)/i);
  if (labelMatch && labelMatch[1]) {
    val = labelMatch[1].trim();
  }

  // 3. If trailing query params were copied (e.g. "tok_val&email=...")
  if (val.includes("&")) {
    val = val.split("&")[0].trim();
  }

  // 4. Strip surrounding quotes and whitespace
  val = val.replace(/^["']|["']$/g, "").trim();
  return val;
}

function VerifyEmailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const queryToken = searchParams.get("token") || "";
  const queryEmail = searchParams.get("email") || "";

  const [token, setToken] = useState(() => cleanToken(queryToken));
  const [email, setEmail] = useState(queryEmail);
  const [isVerifying, setIsVerifying] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [success, setSuccess] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [resendMsg, setResendMsg] = useState<string | null>(null);

  const hasAutoVerifiedRef = React.useRef(false);

  const handleVerify = React.useCallback(async (tokenToVerify?: string) => {
    const raw = tokenToVerify || token;
    const targetToken = cleanToken(raw);
    if (!targetToken) {
      setErrorMsg("Please enter a verification token.");
      return;
    }

    setIsVerifying(true);
    setErrorMsg(null);
    setResendMsg(null);

    try {
      await api.auth.verifyEmail(targetToken);
      setSuccess(true);
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Invalid or expired verification token.");
    } finally {
      setIsVerifying(false);
    }
  }, [token]);

  // Auto-verify when token query parameter is present on mount
  React.useEffect(() => {
    if (queryToken && !hasAutoVerifiedRef.current) {
      const cleaned = cleanToken(queryToken);
      if (cleaned) {
        hasAutoVerifiedRef.current = true;
        // eslint-disable-next-line react-hooks/set-state-in-effect
        handleVerify(cleaned);
      }
    }
  }, [queryToken, handleVerify]);

  const handleResend = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanEmail = email.trim().toLowerCase();
    if (!cleanEmail) {
      setErrorMsg("Please enter your email to receive a new verification link.");
      return;
    }

    setIsResending(true);
    setErrorMsg(null);
    setResendMsg(null);

    try {
      const res = await api.auth.resendVerification(cleanEmail);
      setResendMsg(res.message || "A new verification link has been sent to your email.");
      setToken("");
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to resend verification email.");
    } finally {
      setIsResending(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col justify-center py-12 sm:px-6 lg:px-8 relative overflow-hidden">
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-amber-500/10 rounded-full blur-3xl pointer-events-none"></div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md relative z-10 text-center">
        <div className="inline-flex items-center gap-2.5 mb-2">
          <div className="w-10 h-10 rounded-xl bg-amber-400 flex items-center justify-center font-black text-slate-950 text-xl shadow-lg shadow-amber-400/20">
            DX
          </div>
          <span className="text-2xl font-black text-white tracking-tight">
            Driver<span className="text-amber-400">Xtra</span>
          </span>
        </div>

        <h2 className="text-xl font-bold tracking-tight text-white mt-2">
          Verify Email Address
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          Activate your account to access the platform
        </p>
      </div>

      <div className="mt-6 sm:mx-auto sm:w-full sm:max-w-lg relative z-10 px-4">
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl">
          {success ? (
            <div className="text-center py-6 space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mx-auto text-emerald-400">
                <CheckCircle2 className="w-6 h-6" />
              </div>

              <div>
                <h3 className="text-base font-bold text-white">Email Address Verified!</h3>
                <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                  Your email address has been verified. You can now sign in to your DriverXtra account.
                </p>
              </div>

              <div className="pt-2">
                <button
                  type="button"
                  onClick={() => router.push("/login")}
                  className="w-full h-11 bg-amber-400 hover:bg-amber-500 text-slate-950 font-black rounded-xl text-sm flex items-center justify-center gap-2 shadow-md transition-all hover:shadow-amber-400/20"
                >
                  <span>Proceed to Sign In</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {errorMsg && (
                <div className="p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs font-semibold flex items-start gap-2.5">
                  <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                  <span>{errorMsg}</span>
                </div>
              )}

              {resendMsg && (
                <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-emerald-300 text-xs font-semibold">
                  {resendMsg}
                </div>
              )}

              {/* Token verification form */}
              <form onSubmit={(e) => { e.preventDefault(); handleVerify(); }} className="space-y-4">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                    Verification Token
                  </label>
                  <div className="relative">
                    <input
                      type="text"
                      value={token}
                      onChange={(e) => setToken(e.target.value)}
                      required
                      placeholder="Paste your token from the email"
                      className="w-full h-11 px-3.5 pl-10 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white placeholder:text-slate-600 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400 font-mono text-xs"
                    />
                    <KeyRound className="w-4 h-4 text-slate-500 absolute left-3.5 top-3.5 pointer-events-none" />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isVerifying}
                  className="w-full h-11 bg-amber-400 hover:bg-amber-500 text-slate-950 font-black rounded-xl text-sm flex items-center justify-center gap-2 shadow-md transition-all disabled:opacity-50"
                >
                  <span>{isVerifying ? "Verifying..." : "Verify Email"}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </form>

              {/* Resend Section */}
              <div className="pt-4 border-t border-slate-800 space-y-3">
                <h4 className="text-xs font-bold text-slate-300">Didn&apos;t receive a token?</h4>
                <form onSubmit={handleResend} className="space-y-3">
                  <div className="relative">
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      placeholder="Enter your registered email"
                      className="w-full h-10 px-3.5 pl-10 bg-slate-950 border border-slate-700 rounded-xl text-xs text-white placeholder:text-slate-600 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                    />
                    <Mail className="w-4 h-4 text-slate-500 absolute left-3.5 top-3 pointer-events-none" />
                  </div>

                  <button
                    type="submit"
                    disabled={isResending}
                    className="w-full h-10 bg-slate-800 hover:bg-slate-700 text-white font-bold rounded-xl text-xs flex items-center justify-center gap-2 border border-slate-700 transition-all disabled:opacity-50"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 text-amber-400 ${isResending ? "animate-spin" : ""}`} />
                    <span>{isResending ? "Sending link..." : "Resend Verification Email"}</span>
                  </button>
                </form>
              </div>

              <div className="text-center pt-2">
                <Link
                  href="/login"
                  className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  <span>Back to Sign In</span>
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-950 flex items-center justify-center text-white text-xs">
          Loading email verification...
        </div>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  );
}
