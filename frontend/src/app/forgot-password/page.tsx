"use client";

import React, { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api/client";
import AuthSplitLayout from "@/components/auth/AuthSplitLayout";
import {
  Mail,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  KeyRound,
} from "lucide-react";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) {
      setErrorMsg("Please enter your registered email address.");
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);
    setMessage(null);

    try {
      const res = await api.auth.requestPasswordReset(email.trim().toLowerCase());
      setSuccess(true);
      setMessage(res.message || "If an account exists with this email address, password reset instructions have been sent.");
    } catch (err: unknown) {
      setErrorMsg(err instanceof ApiError ? err.message : "Failed to process password reset request.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthSplitLayout activeTab="forgot-password">
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
          {success ? "Instructions Sent" : "Reset your password"}
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          {success
            ? "Check your inbox for password reset instructions"
            : "Enter your registered email address to receive a reset token"}
        </p>
      </div>

      {success ? (
        <div className="text-center py-4 space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-emerald-50 border border-emerald-200 flex items-center justify-center mx-auto text-emerald-600">
            <CheckCircle2 className="w-6 h-6" />
          </div>

          <div>
            <h3 className="text-base font-bold text-slate-900">Check your email</h3>
            <p className="text-xs sm:text-sm text-slate-600 mt-2 max-w-sm mx-auto leading-relaxed">
              {message}
            </p>
          </div>

          <div className="pt-3 space-y-2.5">
            <Link
              href={`/reset-password?email=${encodeURIComponent(email)}`}
              className="w-full h-12 bg-[#ffc20e] hover:bg-[#e8ac00] text-slate-950 font-black rounded-xl text-sm flex items-center justify-center gap-2 shadow-md hover:shadow-amber-400/20 transition-all"
            >
              <KeyRound className="w-4 h-4" />
              <span>Enter Reset Token</span>
            </Link>

            <Link
              href="/login"
              className="w-full h-11 bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold rounded-xl text-xs flex items-center justify-center gap-2 border border-slate-300 transition-all"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Back to Sign In</span>
            </Link>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3.5">
          {errorMsg && (
            <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs font-semibold">
              {errorMsg}
            </div>
          )}

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
              Registered Email Address <span className="text-[#FFC20E]">*</span>
            </label>
            <div className="relative">
              <input
                type="email"
                name="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="name@organization.com"
                className="w-full h-11 px-3.5 pl-10 bg-white border border-slate-300 rounded-xl text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#FFC20E] focus:ring-2 focus:ring-[#FFC20E]/25 focus:outline-none transition-all"
              />
              <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5 pointer-events-none" />
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full h-11 sm:h-12 bg-[#FFC20E] hover:bg-[#E8AC00] text-slate-950 font-black rounded-xl text-sm sm:text-base flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <span>{isSubmitting ? "Sending..." : "Send Reset Instructions"}</span>
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
