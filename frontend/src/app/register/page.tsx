"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import { api } from "@/lib/api/client";
import AuthSplitLayout from "@/components/auth/AuthSplitLayout";
import {
  Lock,
  Mail,
  User,
  Phone,
  Eye,
  EyeOff,
  ArrowRight,
  Car,
  CheckCircle2,
} from "lucide-react";

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");

  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [resendMsg, setResendMsg] = useState<string | null>(null);

  const handleResend = async () => {
    if (!email) return;
    setIsResending(true);
    setResendMsg(null);
    try {
      const res = await api.auth.resendVerification(email.trim().toLowerCase());
      setResendMsg(res.message || "Verification email resent successfully.");
    } catch (err: unknown) {
      setResendMsg(err instanceof Error ? err.message : "Failed to resend verification email.");
    } finally {
      setIsResending(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setErrorMsg("Email and password are required.");
      return;
    }

    if (password.length < 8) {
      setErrorMsg("Password must be at least 8 characters long.");
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    const result = await register({
      email: email.trim().toLowerCase(),
      password,
      first_name: firstName.trim() || undefined,
      last_name: lastName.trim() || undefined,
      phone_number: phoneNumber.trim() || undefined,
      roles: ["BUYER"],
    });

    setIsSubmitting(false);

    if (result.success) {
      setSuccess(true);
    } else {
      setErrorMsg(result.error || "Registration failed. Please check form inputs.");
    }
  };

  return (
    <AuthSplitLayout activeTab="register">
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
          {success ? "Verify Your Account" : "Create your account"}
        </h2>
        <p className="text-xs text-slate-500 mt-0.5">
          {success
            ? "We sent a confirmation link to your email"
            : "Join the connected automotive commerce platform"}
        </p>
      </div>

      {/* Success / Verification Flow */}
      {success ? (
        <div className="text-center py-4 space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-amber-100 border border-amber-300 flex items-center justify-center mx-auto text-amber-700">
            <Mail className="w-6 h-6" />
          </div>

          <div>
            <h3 className="text-base font-bold text-slate-900">Check your inbox</h3>
            <p className="text-xs sm:text-sm text-slate-600 mt-1 max-w-sm mx-auto">
              We sent a verification link to <span className="text-amber-800 font-bold">{email}</span>. Please verify your email before signing in.
            </p>
          </div>

          {resendMsg && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-800 text-xs font-semibold flex items-center justify-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span>{resendMsg}</span>
            </div>
          )}

          <div className="pt-2 space-y-3">
            <button
              type="button"
              onClick={handleResend}
              disabled={isResending}
              className="w-full h-11 bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold rounded-xl text-xs flex items-center justify-center gap-2 border border-slate-300 transition-all disabled:opacity-50"
            >
              <Mail className="w-4 h-4 text-amber-600" />
              <span>{isResending ? "Sending..." : "Resend Verification Email"}</span>
            </button>

            <Link
              href={`/verify-email?email=${encodeURIComponent(email)}`}
              className="block text-center text-xs text-amber-700 hover:text-amber-800 font-bold hover:underline"
            >
              Have a verification token? Enter it here
            </Link>

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
        <>
          {errorMsg && (
            <div className="mb-5 p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs font-semibold">
              {errorMsg}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3">
            {/* Email */}
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                Work Email <span className="text-[#FFC20E]">*</span>
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
                  className="w-full h-10 sm:h-11 px-3.5 pl-10 bg-white border border-slate-300 rounded-xl text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#FFC20E] focus:ring-2 focus:ring-[#FFC20E]/25 focus:outline-none transition-all"
                />
                <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3 sm:top-3.5 pointer-events-none" />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                Password <span className="text-[#FFC20E]">*</span> (min 8 chars)
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  name="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
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

            {/* First and Last Name */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                  First Name
                </label>
                <div className="relative">
                  <input
                    type="text"
                    name="firstName"
                    autoComplete="given-name"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    placeholder="John"
                    className="w-full h-10 sm:h-11 px-3.5 pl-10 bg-white border border-slate-300 rounded-xl text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#FFC20E] focus:ring-2 focus:ring-[#FFC20E]/25 focus:outline-none transition-all"
                  />
                  <User className="w-4 h-4 text-slate-400 absolute left-3.5 top-3 sm:top-3.5 pointer-events-none" />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                  Last Name
                </label>
                <div className="relative">
                  <input
                    type="text"
                    name="lastName"
                    autoComplete="family-name"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    placeholder="Doe"
                    className="w-full h-10 sm:h-11 px-3.5 pl-10 bg-white border border-slate-300 rounded-xl text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#FFC20E] focus:ring-2 focus:ring-[#FFC20E]/25 focus:outline-none transition-all"
                  />
                  <User className="w-4 h-4 text-slate-400 absolute left-3.5 top-3 sm:top-3.5 pointer-events-none" />
                </div>
              </div>
            </div>

            {/* Phone Number */}
            <div>
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                Phone Number
              </label>
              <div className="relative">
                <input
                  type="tel"
                  name="phoneNumber"
                  autoComplete="tel"
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  placeholder="+44 7000 000000"
                  className="w-full h-10 sm:h-11 px-3.5 pl-10 bg-white border border-slate-300 rounded-xl text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#FFC20E] focus:ring-2 focus:ring-[#FFC20E]/25 focus:outline-none transition-all"
                />
                <Phone className="w-4 h-4 text-slate-400 absolute left-3.5 top-3 sm:top-3.5 pointer-events-none" />
              </div>
            </div>

            {/* Account Type Notice */}
            <div className="p-2 sm:p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-slate-600 text-[10px] sm:text-[11px] flex items-start gap-2">
              <Car className="w-3.5 h-3.5 text-[#E8AC00] shrink-0 mt-0.5" />
              <span>
                <strong className="text-slate-800">Account Access: Buyer.</strong> To become a verified <strong className="text-slate-800">Seller</strong> or <strong className="text-slate-800">Workshop</strong>, submit verification in your platform dashboard.
              </span>
            </div>

            {/* Submit button */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full h-10 sm:h-11 bg-[#FFC20E] hover:bg-[#E8AC00] text-slate-950 font-black rounded-xl text-sm sm:text-base flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-60 disabled:cursor-not-allowed mt-1"
            >
              <span>{isSubmitting ? "Creating Account..." : "Create Account"}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>

          {/* Path to Login */}
          <div className="mt-2.5 pt-2 border-t border-slate-200 text-center">
            <span className="text-xs text-slate-500">
              Already have an account?{" "}
              <Link
                href="/login"
                className="text-amber-700 hover:text-amber-800 font-bold hover:underline"
              >
                Sign In
              </Link>
            </span>
          </div>
        </>
      )}
    </AuthSplitLayout>
  );
}
