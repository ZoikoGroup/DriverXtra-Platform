"use client";

import React, { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api/client";
import AuthSplitLayout from "@/components/auth/AuthSplitLayout";
import {
  Lock,
  KeyRound,
  Eye,
  EyeOff,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
} from "lucide-react";

function cleanToken(input: string): string {
  if (!input) return "";
  let val = input.trim();
  if (val.includes("token=")) {
    const match = val.match(/(?:[?&]|(?<!\w))token=([^&\s]+)/);
    if (match && match[1]) val = match[1].trim();
  }
  const labelMatch = val.match(/^(?:(?:verification|password\s+reset|reset)\s+)?token\s*[:=\-]\s*([^\s]+)/i);
  if (labelMatch && labelMatch[1]) val = labelMatch[1].trim();
  if (val.includes("&")) val = val.split("&")[0].trim();
  return val.replace(/^["']|["']$/g, "").trim();
}

function ResetPasswordContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const queryToken = searchParams.get("token") || "";

  const [token, setToken] = useState(() => cleanToken(queryToken));
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const targetToken = cleanToken(token);
    if (!targetToken) {
      setErrorMsg("Please enter your password reset token.");
      return;
    }

    if (!newPassword) {
      setErrorMsg("Please enter your new password.");
      return;
    }

    if (newPassword.length < 8) {
      setErrorMsg("Password must be at least 8 characters long.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setErrorMsg("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      await api.auth.confirmPasswordReset({
        token: targetToken,
        new_password: newPassword,
      });
      setSuccess(true);
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to reset password. The token may be expired or invalid.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthSplitLayout activeTab="forgot-password">
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
          {success ? "Password Updated" : "Set New Password"}
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          {success
            ? "Your credentials have been securely updated"
            : "Complete single-use password reset verification"}
        </p>
      </div>

      {success ? (
        <div className="text-center py-4 space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-emerald-50 border border-emerald-200 flex items-center justify-center mx-auto text-emerald-600">
            <CheckCircle2 className="w-6 h-6" />
          </div>

          <div>
            <h3 className="text-base font-bold text-slate-900">Password Reset Successful</h3>
            <p className="text-xs sm:text-sm text-slate-600 mt-2 max-w-sm mx-auto leading-relaxed">
              Your password has been updated and any existing sessions have been terminated. You can now sign in with your new credentials.
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
        <form onSubmit={handleSubmit} className="space-y-3">
          {errorMsg && (
            <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs font-semibold">
              {errorMsg}
            </div>
          )}

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
              Reset Token <span className="text-[#FFC20E]">*</span>
            </label>
            <div className="relative">
              <input
                type="text"
                name="token"
                autoComplete="off"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                required
                placeholder="Paste token from reset email"
                className="w-full h-10 sm:h-11 px-3.5 pl-10 bg-white border border-slate-300 rounded-xl text-xs text-slate-900 placeholder:text-slate-400 focus:border-[#FFC20E] focus:ring-2 focus:ring-[#FFC20E]/25 focus:outline-none transition-all font-mono"
              />
              <KeyRound className="w-4 h-4 text-slate-400 absolute left-3.5 top-3 sm:top-3.5 pointer-events-none" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
              New Password <span className="text-[#FFC20E]">*</span>
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                name="newPassword"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                placeholder="Minimum 8 characters"
                className="w-full h-10 sm:h-11 px-3.5 pl-10 pr-10 bg-white border border-slate-300 rounded-xl text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#FFC20E] focus:ring-2 focus:ring-[#FFC20E]/25 focus:outline-none transition-all"
              />
              <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-3 sm:top-3.5 pointer-events-none" />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3.5 top-2.5 sm:top-3 text-slate-400 hover:text-slate-700 transition-colors"
                aria-label="Toggle password view"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
              Confirm New Password <span className="text-[#FFC20E]">*</span>
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                name="confirmPassword"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                placeholder="Re-enter new password"
                className="w-full h-10 sm:h-11 px-3.5 pl-10 bg-white border border-slate-300 rounded-xl text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#FFC20E] focus:ring-2 focus:ring-[#FFC20E]/25 focus:outline-none transition-all"
              />
              <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-3 sm:top-3.5 pointer-events-none" />
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full h-11 sm:h-12 bg-[#FFC20E] hover:bg-[#E8AC00] text-slate-950 font-black rounded-xl text-sm sm:text-base flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <span>{isSubmitting ? "Resetting Password..." : "Update Password"}</span>
            <ArrowRight className="w-4 h-4" />
          </button>

          <div className="pt-2 text-center">
            <Link
              href="/login"
              className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-900 font-medium transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Sign In</span>
            </Link>
          </div>
        </form>
      )}
    </AuthSplitLayout>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#f4f5f7] flex items-center justify-center text-slate-500 text-xs">
          Loading password reset...
        </div>
      }
    >
      <ResetPasswordContent />
    </Suspense>
  );
}
