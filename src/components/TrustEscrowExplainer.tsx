"use client";

import React from "react";
import {
  ShieldCheck,
  Lock,
  RotateCcw,
  QrCode,
  FileBadge,
  Scale,
  Sparkles,
  ArrowRight
} from "lucide-react";

export default function TrustEscrowExplainer() {
  const pillars = [
    {
      title: "Regulated Escrow Custody",
      desc: "Vehicle purchase deposits and funds are held securely in FCA/banking-grade dual custody. Funds are only released to the seller once you inspect and accept the vehicle.",
      icon: Lock,
      color: "text-amber-500",
      bg: "bg-amber-500/10",
      badge: "Doc 10 Payments Core",
    },
    {
      title: "Guaranteed Fitment or 100% Refund",
      desc: "Parts matched to your registered Garage vehicle are backed by our fitment liability guarantee. If it doesn’t install as specified, return it within 48h with zero hassle.",
      icon: RotateCcw,
      color: "text-emerald-500",
      bg: "bg-emerald-500/10",
      badge: "Doc 06 & 15 Protection",
    },
    {
      title: "Secure Digital Handover Pass",
      desc: "Upon physical vehicle collection, both buyer and dealer scan a tamper-proof cryptographic QR token. Handover is atomically committed, transferring ownership instantly.",
      icon: QrCode,
      color: "text-blue-500",
      bg: "bg-blue-500/10",
      badge: "Doc 09 Commerce Saga",
    },
    {
      title: "Maker-Checker Dispute Resolution",
      desc: "If an item arrives misdescribed or a service has defects, our dispute mediation process enforces legally-binding resolutions without unilateral account edits.",
      icon: Scale,
      color: "text-purple-500",
      bg: "bg-purple-500/10",
      badge: "Doc 15 & 24 Governance",
    },
  ];

  return (
    <section className="py-16 px-4 sm:px-6 lg:px-10 bg-slate-950 text-white relative overflow-hidden">
      {/* Background illumination */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[350px] bg-amber-500/5 rounded-full blur-3xl pointer-events-none"></div>

      <div className="mx-auto max-w-[1440px] relative z-10">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-400/10 border border-amber-400/30 text-amber-300 text-xs font-semibold mb-3">
            <ShieldCheck className="w-4 h-4 text-amber-400" />
            <span>Built-In Transactional Protection</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight">
            Why DriverXtra is Not Just Another Listings Site
          </h2>
          <p className="mt-3 text-sm sm:text-base text-slate-400">
            Traditional car sites leave you vulnerable to cash scams, fake odometers, and wrong parts. DriverXtra provides an engineered infrastructure where every transaction is verified, insured, and protected.
          </p>
        </div>

        {/* 4 Pillars Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {pillars.map((pillar, idx) => {
            const Icon = pillar.icon;
            return (
              <div
                key={idx}
                className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 flex flex-col justify-between hover:border-amber-400/60 transition-all duration-300 hover:shadow-2xl hover:shadow-amber-500/5"
              >
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <div className={`w-12 h-12 rounded-xl ${pillar.bg} flex items-center justify-center`}>
                      <Icon className={`w-6 h-6 ${pillar.color}`} />
                    </div>
                    <span className="text-[10px] font-bold text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
                      {pillar.badge}
                    </span>
                  </div>

                  <h3 className="text-base font-bold text-white mb-2">
                    {pillar.title}
                  </h3>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    {pillar.desc}
                  </p>
                </div>

                <div className="mt-6 pt-3 border-t border-slate-800/80 flex items-center gap-1.5 text-xs text-amber-400 font-bold">
                  <span>Engineered Invariant</span>
                  <Sparkles className="w-3.5 h-3.5" />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
