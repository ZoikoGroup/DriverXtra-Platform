"use client";

import React, { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api/client";
import AuthSplitLayout from "@/components/auth/AuthSplitLayout";
import {
  CheckCircle2,
  Mail,
  KeyRound,
  ArrowRight,
  RefreshCw,
  ArrowLeft,
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
    <AuthSplitLayout activeTab="login">
      {/* Brand Header Inside Card */}
      <div className="text-center pb-3.5 xl:pb-4">
        <div className="inline-flex items-center justify-center gap-2 mb-1.5">
          <div className="w-9 h-9 rounded-xl bg-[#FFC20E] flex items-center justify-center font-black text-slate-950 text-lg shadow-md shadow-amber-400/20">
            DX
          </div>
          <span className="text-2xl font-black text-[#17212C] tracking-tight">
            Driver<span className="text-[#FFC20E]">Xtra</span>
          </span>
        </div>

        <h2 className="text-xl sm:text-2xl font-black text-[#17212C] tracking-tight">
          {success ? "Email Verified" : "Verify Email Address"}
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          {success
            ? "Your account has been successfully activated"
            : "Activate your account to access the platform"}
        </p>
      </div>

      {success ? (
        <div className="text-center py-4 space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-emerald-50 border border-emerald-200 flex items-center justify-center mx-auto text-emerald-600">
            <CheckCircle2 className="w-6 h-6" />
          </div>

          <div>
            <h3 className="text-base font-bold text-slate-900">Email Address Verified!</h3>
            <p className="text-xs sm:text-sm text-slate-600 mt-1 max-w-sm mx-auto">
              Your email address has been verified. You can now sign in to your DriverXtra account.
            </p>
          </div>

          <div className="pt-2">
            <button
              type="button"
              onClick={() => router.push("/login")}
              className="w-full h-12 bg-[#ffc20e] hover:bg-[#e8ac00] text-slate-950 font-black rounded-xl text-sm flex items-center justify-center gap-2 shadow-md hover:shadow-amber-400/20 transition-all"
            >
              <span>Proceed to Sign In</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {errorMsg && (
            <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs font-semibold">
              {errorMsg}
            </div>
          )}

          {resendMsg && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-800 text-xs font-semibold flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span>{resendMsg}</span>
            </div>
          )}

          {/* Token verification form */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleVerify();
            }}
            className="space-y-3"
          >
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                Verification Token <span className="text-[#FFC20E]">*</span>
              </label>
              <div className="relative">
                <input
                  type="text"
                  name="token"
                  autoComplete="off"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  required
                  placeholder="Paste your token from the email"
                  className="w-full h-10 sm:h-11 px-3.5 pl-10 bg-white border border-slate-300 rounded-xl text-xs text-slate-900 placeholder:text-slate-400 focus:border-[#FFC20E] focus:ring-2 focus:ring-[#FFC20E]/25 focus:outline-none transition-all font-mono"
                />
                <KeyRound className="w-4 h-4 text-slate-400 absolute left-3.5 top-3 sm:top-3.5 pointer-events-none" />
              </div>
            </div>

            <button
              type="submit"
              disabled={isVerifying}
              className="w-full h-11 sm:h-12 bg-[#FFC20E] hover:bg-[#E8AC00] text-slate-950 font-black rounded-xl text-sm sm:text-base flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <span>{isVerifying ? "Verifying..." : "Verify Email"}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>

          {/* Resend Section */}
          <div className="pt-3 border-t border-slate-200 space-y-2.5">
            <h4 className="text-xs font-bold text-slate-700">Didn&apos;t receive a token?</h4>
            <form onSubmit={handleResend} className="space-y-2.5">
              <div className="relative">
                <input
                  type="email"
                  name="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  placeholder="Enter your registered email"
                  className="w-full h-10 sm:h-11 px-3.5 pl-10 bg-white border border-slate-300 rounded-xl text-xs text-slate-900 placeholder:text-slate-400 focus:border-[#FFC20E] focus:ring-2 focus:ring-[#FFC20E]/25 focus:outline-none transition-all"
                />
                <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3 sm:top-3.5 pointer-events-none" />
              </div>

              <button
                type="submit"
                disabled={isResending}
                className="w-full h-10 sm:h-11 bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold rounded-xl text-xs flex items-center justify-center gap-2 border border-slate-300 transition-all disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 text-amber-600 ${isResending ? "animate-spin" : ""}`} />
                <span>{isResending ? "Sending link..." : "Resend Verification Email"}</span>
              </button>
            </form>
          </div>

          <div className="text-center pt-2">
            <Link
              href="/login"
              className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-900 font-medium transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Sign In</span>
            </Link>
          </div>
        </div>
      )}
    </AuthSplitLayout>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#f4f5f7] flex items-center justify-center text-slate-500 text-xs">
          Loading email verification...
        </div>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  );
}
