"use client";

import React from "react";
import Link from "next/link";
import {
  Car,
  Wrench,
  ShieldCheck,
  Truck,
  Sparkles,
  ChevronRight,
} from "lucide-react";

interface AuthSplitLayoutProps {
  children: React.ReactNode;
  activeTab?: "login" | "register" | "forgot-password" | null;
  cardHeader?: React.ReactNode;
}

export default function AuthSplitLayout({
  children,
  activeTab,
  cardHeader,
}: AuthSplitLayoutProps) {
  return (
    <div className="w-full min-h-screen min-h-[100dvh] flex flex-col lg:flex-row bg-[#F5F5F3] text-slate-900 overflow-x-hidden select-auto">
      {/* ========================================================================= */}
      {/* LEFT PANEL – CINEMATIC AUTOMOTIVE BRANDING (~58-60% width on Desktop)     */}
      {/* ========================================================================= */}
      <section
        aria-label="Automotive Marketplace Platform"
        className="relative w-full lg:w-[58%] xl:w-[60%] min-w-0 max-w-full min-h-screen flex flex-col justify-between p-4 sm:p-6 lg:p-7 xl:p-8 2xl:p-10 text-white bg-cover bg-center lg:bg-bottom shrink-0"
        style={{
          backgroundImage: `url('/images/driverxtra-login-bg.png')`,
        }}
      >
        {/* Cinematic Multi-stop Dark Navy/Charcoal Vignette Overlay */}
        <div
          className="absolute inset-0 bg-gradient-to-t from-slate-950/95 via-slate-950/60 to-slate-950/45 pointer-events-none z-0"
          aria-hidden="true"
        />
        {/* Subtle ambient warm atmospheric glow (clipped to prevent overflow) */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none select-none z-0" aria-hidden="true">
          <div className="absolute top-1/4 left-1/3 -translate-x-1/2 w-[450px] h-[450px] bg-amber-500/10 rounded-full blur-3xl" />
        </div>

        {/* --- Top Branding Bar --- */}
        <header className="relative z-10 flex items-center justify-between gap-2 shrink-0 w-full">
          <Link
            href="/"
            className="inline-flex items-center gap-2 sm:gap-3 focus:outline-none focus:ring-2 focus:ring-[#FFC20E] rounded-2xl transition-transform hover:scale-[1.01] min-w-0"
          >
            {/* DriverXtra Emblem */}
            <div className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl sm:rounded-2xl bg-[#FFC20E] flex items-center justify-center font-black text-slate-950 text-xl sm:text-2xl shadow-lg shadow-amber-400/25 shrink-0">
              DX
            </div>
            <div className="flex flex-col min-w-0">
              <span className="text-2xl sm:text-3xl font-black text-white tracking-tight leading-none truncate">
                Driver<span className="text-[#FFC20E]">Xtra</span>
              </span>
              <span className="text-[10px] uppercase font-bold tracking-widest text-slate-400 mt-1 truncate hidden sm:block">
                Global Automotive Marketplace
              </span>
            </div>
          </Link>

          {/* Translucent Rounded Badge */}
          <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/10 backdrop-blur-md border border-white/15 text-white/90 text-[10px] sm:text-[11px] font-bold tracking-wider uppercase shadow-xs select-none shrink-0 whitespace-nowrap">
            <span className="w-1.5 h-1.5 rounded-full bg-[#FFC20E] animate-pulse" />
            <span className="hidden sm:inline">A ZOIKO GROUP COMPANY</span>
            <span className="sm:hidden">ZOIKO GROUP</span>
          </div>
        </header>

        {/* --- Main Headline, Narrative & Category Cards --- */}
        <div className="relative z-10 my-6 lg:my-8 space-y-4 lg:space-y-5 max-w-2xl shrink-0">
          {/* Eyebrow */}
          <div className="inline-flex items-center gap-2 text-[#FFC20E] text-[11px] xl:text-xs font-black uppercase tracking-widest">
            <span className="w-5 h-[2px] bg-[#FFC20E] rounded-full inline-block" />
            <span>GLOBAL AUTOMOTIVE COMMERCE</span>
          </div>

          {/* Main Heading */}
          <h1 className="text-2xl sm:text-3xl lg:text-3xl xl:text-4xl 2xl:text-5xl font-black leading-[1.15] tracking-tight">
            <span className="text-white block">Everything automotive.</span>
            <span className="text-[#FFC20E] block">One connected marketplace.</span>
          </h1>

          {/* Supporting Text */}
          <p className="hidden sm:block text-slate-200 text-sm xl:text-base leading-relaxed max-w-xl font-normal">
            Buy, sell, finance, insure, service and manage vehicles, parts and mobility solutions — on one trusted global platform.
          </p>

          {/* Four Automotive Category Cards (Desktop / Tablet view) */}
          <div className="hidden sm:grid grid-cols-2 sm:grid-cols-4 gap-2.5 xl:gap-3 pt-1">
            <div className="p-3 rounded-2xl bg-slate-950/65 backdrop-blur-md border border-white/10 hover:border-[#FFC20E]/40 transition-all group flex flex-col justify-between">
              <div>
                <div className="w-8 h-8 rounded-xl bg-[#FFC20E]/15 border border-[#FFC20E]/30 flex items-center justify-center text-[#FFC20E] mb-2 group-hover:scale-105 transition-transform">
                  <Car className="w-4 h-4" />
                </div>
                <div className="text-xs xl:text-sm font-bold text-white leading-tight min-h-[2.4rem] flex items-center">
                  Vehicles &amp; EVs
                </div>
              </div>
              <div className="text-[10px] text-slate-400 mt-1">Showroom &amp; direct</div>
            </div>

            <div className="p-3 rounded-2xl bg-slate-950/65 backdrop-blur-md border border-white/10 hover:border-[#FFC20E]/40 transition-all group flex flex-col justify-between">
              <div>
                <div className="w-8 h-8 rounded-xl bg-[#FFC20E]/15 border border-[#FFC20E]/30 flex items-center justify-center text-[#FFC20E] mb-2 group-hover:scale-105 transition-transform">
                  <Wrench className="w-4 h-4" />
                </div>
                <div className="text-xs xl:text-sm font-bold text-white leading-tight min-h-[2.4rem] flex items-center">
                  Parts &amp; Accessories
                </div>
              </div>
              <div className="text-[10px] text-slate-400 mt-1">OEM &amp; verified fit</div>
            </div>

            <div className="p-3 rounded-2xl bg-slate-950/65 backdrop-blur-md border border-white/10 hover:border-[#FFC20E]/40 transition-all group flex flex-col justify-between">
              <div>
                <div className="w-8 h-8 rounded-xl bg-[#FFC20E]/15 border border-[#FFC20E]/30 flex items-center justify-center text-[#FFC20E] mb-2 group-hover:scale-105 transition-transform">
                  <ShieldCheck className="w-4 h-4" />
                </div>
                <div className="text-xs xl:text-sm font-bold text-white leading-tight min-h-[2.4rem] flex items-center">
                  Finance &amp; Insurance
                </div>
              </div>
              <div className="text-[10px] text-slate-400 mt-1">Rates &amp; protection</div>
            </div>

            <div className="p-3 rounded-2xl bg-slate-950/65 backdrop-blur-md border border-white/10 hover:border-[#FFC20E]/40 transition-all group flex flex-col justify-between">
              <div>
                <div className="w-8 h-8 rounded-xl bg-[#FFC20E]/15 border border-[#FFC20E]/30 flex items-center justify-center text-[#FFC20E] mb-2 group-hover:scale-105 transition-transform">
                  <Truck className="w-4 h-4" />
                </div>
                <div className="text-xs xl:text-sm font-bold text-white leading-tight min-h-[2.4rem] flex items-center">
                  Service &amp; Fleets
                </div>
              </div>
              <div className="text-[10px] text-slate-400 mt-1">Bays &amp; operations</div>
            </div>
          </div>
        </div>

        {/* --- Lower Content Area: Explore DriverXtra Floating Card & Bottom Branding Statement --- */}
        <div className="relative z-10 mt-auto pt-4 flex flex-col sm:flex-row items-start sm:items-end justify-between gap-4 shrink-0">
          {/* Bottom Footer Statement */}
          <div className="text-xs text-slate-300 max-w-xs xl:max-w-sm flex items-center gap-2 pb-2">
            <span className="w-2 h-2 rounded-full bg-[#FFC20E] shrink-0 animate-pulse" />
            <span>Built for buyers, sellers, dealers, suppliers and fleet operators worldwide.</span>
          </div>

          {/* Explore DriverXtra White Floating Card */}
          <aside
            aria-label="Explore Platform Modules"
            className="w-full sm:w-72 xl:w-80 bg-white/95 backdrop-blur-xl rounded-2xl p-3 xl:p-3.5 shadow-2xl border border-white/40 space-y-2 text-slate-900 hidden sm:block shrink-0 mb-2"
          >
            <div className="flex items-center justify-between pb-0.5">
              <div>
                <h2 className="text-xs font-black text-slate-900 tracking-tight">Explore DriverXtra</h2>
                <p className="text-[10px] text-slate-500">One destination for the automotive lifecycle</p>
              </div>
              <div className="w-6 h-6 rounded-lg bg-amber-100 text-[#E8AC00] flex items-center justify-center shrink-0">
                <Sparkles className="w-3.5 h-3.5" />
              </div>
            </div>

            <div className="space-y-1.5 text-left">
              <div className="flex items-center justify-between p-1.5 px-2.5 rounded-xl bg-slate-50/90 border border-slate-200/80 hover:bg-amber-50/50 hover:border-amber-300 transition-all group">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-6 h-6 rounded-lg bg-amber-400/20 text-amber-800 flex items-center justify-center shrink-0">
                    <Car className="w-3.5 h-3.5" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-bold text-slate-900 group-hover:text-amber-800 transition-colors">Find vehicles</div>
                    <div className="text-[9px] text-slate-500">New, used &amp; electric</div>
                  </div>
                </div>
                <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-slate-700 transition-colors shrink-0" />
              </div>

              <div className="flex items-center justify-between p-1.5 px-2.5 rounded-xl bg-slate-50/90 border border-slate-200/80 hover:bg-amber-50/50 hover:border-amber-300 transition-all group">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-6 h-6 rounded-lg bg-amber-400/20 text-amber-800 flex items-center justify-center shrink-0">
                    <Wrench className="w-3.5 h-3.5" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-bold text-slate-900 group-hover:text-amber-800 transition-colors">Source parts</div>
                    <div className="text-[9px] text-slate-500">Parts, tools &amp; accessories</div>
                  </div>
                </div>
                <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-slate-700 transition-colors shrink-0" />
              </div>

              <div className="flex items-center justify-between p-1.5 px-2.5 rounded-xl bg-slate-50/90 border border-slate-200/80 hover:bg-amber-50/50 hover:border-amber-300 transition-all group">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-6 h-6 rounded-lg bg-amber-400/20 text-amber-800 flex items-center justify-center shrink-0">
                    <Truck className="w-3.5 h-3.5" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-bold text-slate-900 group-hover:text-amber-800 transition-colors">Manage mobility</div>
                    <div className="text-[9px] text-slate-500">Services, fleets &amp; partners</div>
                  </div>
                </div>
                <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-slate-700 transition-colors shrink-0" />
              </div>
            </div>
          </aside>
        </div>
      </section>

      {/* ========================================================================= */}
      {/* RIGHT PANEL – WARM OFF-WHITE WITH DISTINCTIVE GEOMETRIC ACCENTS           */}
      {/* ========================================================================= */}
      <section
        aria-label="Authentication Panel"
        className="relative w-full lg:w-[42%] xl:w-[40%] min-w-0 max-w-full min-h-screen flex flex-col justify-between p-3.5 sm:p-5 xl:p-8 2xl:p-10 bg-[#F5F5F3] shrink-0"
      >
        {/* Background Geometric Accent Layer - strictly clipped to prevent horizontal overflow */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none select-none z-0" aria-hidden="true">
          {/* Prominent Yellow Diagonal Geometric Accent in Upper-Right Corner */}
          <div
            className="absolute -top-12 -right-12 w-64 h-64 sm:w-80 sm:h-80 xl:w-96 xl:h-96 bg-[#FFC20E]"
            style={{
              clipPath: "polygon(100% 0, 15% 0, 100% 85%)",
            }}
          />
          {/* Secondary Warm Gold Facet for Geometric Depth */}
          <div
            className="absolute -top-12 -right-12 w-48 h-48 sm:w-60 sm:h-60 xl:w-72 xl:h-72 bg-[#E8AC00] opacity-60"
            style={{
              clipPath: "polygon(100% 0, 42% 0, 100% 58%)",
            }}
          />

          {/* Dark Navy Geometric Diagonal Accent in Lower-Right Corner */}
          <div
            className="absolute -bottom-10 -right-10 w-52 h-52 sm:w-64 sm:h-64 xl:w-72 xl:h-72 bg-[#17212C]"
            style={{
              clipPath: "polygon(100% 100%, 100% 20%, 20% 100%)",
            }}
          />
        </div>

        {/* Center Container: Premium White Authentication Card */}
        <div className="relative z-10 w-full max-w-[530px] mx-auto my-auto py-1 sm:py-2">
          <div className="bg-white rounded-2xl sm:rounded-3xl shadow-xl shadow-slate-300/40 border border-slate-200/90 overflow-hidden transition-all">
            {/* Top Navigation Tabs: Equal Width, Linked to Next.js routes */}
            <nav
              aria-label="Authentication Navigation Tabs"
              className="grid grid-cols-3 border-b border-slate-200/90 bg-slate-50/90"
            >
              <Link
                href="/login"
                className={`py-2.5 px-1 sm:px-2 text-center text-xs sm:text-sm font-bold transition-all relative ${
                  activeTab === "login"
                    ? "bg-white text-[#17212C] font-black shadow-xs border-b-2 border-[#FFC20E]"
                    : "text-slate-500 hover:text-slate-900 hover:bg-slate-100/80"
                }`}
              >
                Login
              </Link>
              <Link
                href="/register"
                className={`py-2.5 px-1 sm:px-2 text-center text-xs sm:text-sm font-bold transition-all border-x border-slate-200/90 relative ${
                  activeTab === "register"
                    ? "bg-white text-[#17212C] font-black shadow-xs border-b-2 border-[#FFC20E]"
                    : "text-slate-500 hover:text-slate-900 hover:bg-slate-100/80"
                }`}
              >
                Register
              </Link>
              <Link
                href="/forgot-password"
                className={`py-2.5 px-1 sm:px-2 text-center text-xs sm:text-sm font-bold transition-all relative truncate ${
                  activeTab === "forgot-password"
                    ? "bg-white text-[#17212C] font-black shadow-xs border-b-2 border-[#FFC20E]"
                    : "text-slate-500 hover:text-slate-900 hover:bg-slate-100/80"
                }`}
              >
                <span className="sm:hidden">Reset</span>
                <span className="hidden sm:inline">Reset Password</span>
              </Link>
            </nav>

            {/* Form Content Padding */}
            <div className="p-4 sm:p-5 xl:p-7">
              {cardHeader}
              {children}
            </div>
          </div>
        </div>

        {/* Right Section Footer Links & Legal Disclaimers (Outside card, pinned near bottom) */}
        <footer className="relative z-10 w-full max-w-[530px] mx-auto pt-2 shrink-0 flex flex-col sm:flex-row items-center justify-between gap-2 text-[10px] sm:text-[11px] text-slate-500 text-center sm:text-left select-none">
          <div className="flex items-center gap-2.5 font-semibold text-slate-600">
            <Link href="#" className="hover:text-slate-900 transition-colors">
              Privacy
            </Link>
            <span className="text-slate-300">·</span>
            <Link href="#" className="hover:text-slate-900 transition-colors">
              Terms
            </Link>
            <span className="text-slate-300">·</span>
            <Link href="#" className="hover:text-slate-900 transition-colors">
              Accessibility
            </Link>
            <span className="text-slate-300">·</span>
            <Link href="#" className="hover:text-slate-900 transition-colors">
              Help
            </Link>
          </div>

          <div className="text-[10px] text-slate-400 space-y-0.5 text-center sm:text-right">
            <div>© 2026 Zoiko Mobility Inc.</div>
            <div className="text-[9px] text-slate-400">DriverXtra is a trading name of Zoiko Mobility Inc.</div>
          </div>
        </footer>
      </section>
    </div>
  );
}
