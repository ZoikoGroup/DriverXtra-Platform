"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/prototype-auth/auth-context";
import { CanonicalRole } from "@/lib/prototype-auth/types";
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
  Info
} from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const { login, availablePrototypeUsers } = useAuth();

  const [email, setEmail] = useState("mark.harrison@example.co.uk");
  const [password, setPassword] = useState("DriverXtra2026!");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError("Please provide both email and password.");
      return;
    }

    setIsSubmitting(true);
    login(email);
    router.replace("/platform");
  };

  const handleFastLogin = (targetEmail: string, role: CanonicalRole) => {
    setIsSubmitting(true);
    setEmail(targetEmail);
    login(targetEmail, role);
    router.replace("/platform");
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
          Platform Sign In
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          Identity & RBAC Architecture (Doc 04 §7) • Enter Enterprise Portal
        </p>
      </div>

      <div className="mt-6 sm:mx-auto sm:w-full sm:max-w-lg relative z-10 px-4">
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl">
          {/* Prototype Notice Banner */}
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-3.5 mb-6 text-xs text-amber-300 flex items-start gap-2.5">
            <Info className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <strong className="font-bold">Prototype Demonstration Environment:</strong>
              <div className="text-[11px] text-amber-200/80 mt-0.5">
                Authentication is handled client-side using documented RBAC archetypes. No real credentials are sent over the network.
              </div>
            </div>
          </div>

          {error && (
            <div className="mb-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs font-semibold">
              {error}
            </div>
          )}

          {/* Standard Form */}
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
                <button
                  type="button"
                  className="text-[11px] text-amber-400 hover:text-amber-300 font-semibold"
                  onClick={() => alert("Password recovery flow documented in Doc 04 §7 (Step-up verification required in production).")}
                >
                  Forgot password?
                </button>
              </div>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
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
              className="w-full h-11 bg-amber-400 hover:bg-amber-500 text-slate-950 font-black rounded-xl text-sm flex items-center justify-center gap-2 shadow-md transition-all hover:shadow-amber-400/20"
            >
              <span>{isSubmitting ? "Authenticating..." : "Sign In to Platform"}</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>

          {/* Prototype Quick Role Switcher */}
          <div className="mt-8 pt-6 border-t border-slate-800">
            <span className="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-3 text-center">
              Quick Sign In via Documented Archetype:
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
                    onClick={() => handleFastLogin(u.email, u.role)}
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
        </div>

        {/* Footer info */}
        <div className="mt-6 text-center text-xs text-slate-500">
          DriverXtra Global Automotive Commerce Infrastructure • Zoiko Tech Inc.
        </div>
      </div>
    </div>
  );
}
