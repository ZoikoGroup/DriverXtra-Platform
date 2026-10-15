"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import {
  Lock,
  Mail,
  User,
  Phone,
  Eye,
  EyeOff,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  ShieldCheck,
  Building2,
  Wrench,
  Car
} from "lucide-react";

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [selectedRole, setSelectedRole] = useState<"BUYER" | "SELLER" | "WORKSHOP">("BUYER");

  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

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
      roles: [selectedRole],
    });

    setIsSubmitting(false);

    if (result.success) {
      setSuccess(true);
    } else {
      setErrorMsg(result.error || "Registration failed. Please check form inputs.");
    }
  };

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
          Create Platform Account
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          Phase 1 Identity Registration • Real API Integration
        </p>
      </div>

      <div className="mt-6 sm:mx-auto sm:w-full sm:max-w-lg relative z-10 px-4">
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl">
          {/* Success Banner */}
          {success ? (
            <div className="text-center py-6 space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mx-auto text-emerald-400">
                <CheckCircle2 className="w-6 h-6" />
              </div>

              <div>
                <h3 className="text-base font-bold text-white">Registration Successful</h3>
                <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                  Your account has been created with role <span className="text-amber-400 font-bold">{selectedRole}</span>. You can now sign in with your credentials.
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
            <>
              {errorMsg && (
                <div className="mb-5 p-3.5 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs font-semibold flex items-start gap-2.5">
                  <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                  <span>{errorMsg}</span>
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                {/* Email */}
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                    Email Address <span className="text-amber-400">*</span>
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

                {/* Password */}
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                    Password <span className="text-amber-400">*</span> (min 8 chars)
                  </label>
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      placeholder="••••••••"
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

                {/* First and Last Name */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                      First Name
                    </label>
                    <div className="relative">
                      <input
                        type="text"
                        value={firstName}
                        onChange={(e) => setFirstName(e.target.value)}
                        placeholder="John"
                        className="w-full h-11 px-3.5 pl-10 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white placeholder:text-slate-600 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                      />
                      <User className="w-4 h-4 text-slate-500 absolute left-3.5 top-3.5 pointer-events-none" />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                      Last Name
                    </label>
                    <div className="relative">
                      <input
                        type="text"
                        value={lastName}
                        onChange={(e) => setLastName(e.target.value)}
                        placeholder="Doe"
                        className="w-full h-11 px-3.5 pl-10 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white placeholder:text-slate-600 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                      />
                      <User className="w-4 h-4 text-slate-500 absolute left-3.5 top-3.5 pointer-events-none" />
                    </div>
                  </div>
                </div>

                {/* Phone Number */}
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                    Phone Number
                  </label>
                  <div className="relative">
                    <input
                      type="tel"
                      value={phoneNumber}
                      onChange={(e) => setPhoneNumber(e.target.value)}
                      placeholder="+44 7000 000000"
                      className="w-full h-11 px-3.5 pl-10 bg-slate-950 border border-slate-700 rounded-xl text-sm text-white placeholder:text-slate-600 focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                    />
                    <Phone className="w-4 h-4 text-slate-500 absolute left-3.5 top-3.5 pointer-events-none" />
                  </div>
                </div>

                {/* Permitted Platform Role */}
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1.5">
                    Permitted Account Role
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedRole("BUYER")}
                      className={`p-3 rounded-xl border text-left transition-all ${
                        selectedRole === "BUYER"
                          ? "bg-amber-400/10 border-amber-400 text-amber-300"
                          : "bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700"
                      }`}
                    >
                      <Car className="w-4 h-4 mb-1.5" />
                      <div className="text-xs font-bold">Buyer</div>
                      <div className="text-[10px] opacity-75">Customer</div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setSelectedRole("SELLER")}
                      className={`p-3 rounded-xl border text-left transition-all ${
                        selectedRole === "SELLER"
                          ? "bg-amber-400/10 border-amber-400 text-amber-300"
                          : "bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700"
                      }`}
                    >
                      <Building2 className="w-4 h-4 mb-1.5" />
                      <div className="text-xs font-bold">Seller</div>
                      <div className="text-[10px] opacity-75">Dealer</div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setSelectedRole("WORKSHOP")}
                      className={`p-3 rounded-xl border text-left transition-all ${
                        selectedRole === "WORKSHOP"
                          ? "bg-amber-400/10 border-amber-400 text-amber-300"
                          : "bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700"
                      }`}
                    >
                      <Wrench className="w-4 h-4 mb-1.5" />
                      <div className="text-xs font-bold">Workshop</div>
                      <div className="text-[10px] opacity-75">Provider</div>
                    </button>
                  </div>
                  <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-slate-500">
                    <ShieldCheck className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                    <span>Administrative and staff privileges are strictly prohibited for public self-registration.</span>
                  </div>
                </div>

                {/* Submit button */}
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full h-11 bg-amber-400 hover:bg-amber-500 text-slate-950 font-black rounded-xl text-sm flex items-center justify-center gap-2 shadow-md transition-all hover:shadow-amber-400/20 disabled:opacity-60 disabled:cursor-not-allowed mt-2"
                >
                  <span>{isSubmitting ? "Creating Account..." : "Create Account"}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </form>

              {/* Path to Login */}
              <div className="mt-6 pt-5 border-t border-slate-800 text-center">
                <span className="text-xs text-slate-400">
                  Already have a registered account?{" "}
                  <Link
                    href="/login"
                    className="text-amber-400 hover:text-amber-300 font-bold hover:underline inline-flex items-center gap-1"
                  >
                    <span>Sign In</span>
                    <ArrowRight className="w-3 h-3" />
                  </Link>
                </span>
              </div>
            </>
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
