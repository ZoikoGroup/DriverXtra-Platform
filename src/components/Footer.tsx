"use client";

import React from "react";
import { ShieldCheck, Globe, Building2, Car, Settings, Wrench, Lock } from "lucide-react";

export default function Footer({ onNavigatePortal }: { onNavigatePortal: (portal: string) => void }) {
  return (
    <footer className="bg-slate-950 text-slate-400 text-xs border-t border-slate-800">
      <div className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-10 py-16">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-8 pb-12 border-b border-slate-800">
          {/* Brand Info */}
          <div className="col-span-2 space-y-3">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-amber-400 flex items-center justify-center font-extrabold text-slate-950 text-sm shadow">
                DX
              </div>
              <span className="font-black text-xl tracking-tight text-white">
                Driver<span className="text-amber-400">Xtra</span>
              </span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed max-w-sm">
              Global Automotive Commerce Infrastructure — a governed, multi-sided marketplace connecting individuals, dealers, fleets, workshops, and aftermarket suppliers.
            </p>
            <div className="pt-2 text-[11px] text-slate-500">
              A trading name of <strong className="text-slate-300">Zoiko Tech Inc.</strong>
            </div>
            <div className="flex items-center gap-2 text-emerald-400 font-semibold pt-1">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>Regulated Dual-Custody Escrow Active</span>
            </div>
          </div>

          {/* Column 1: Buy */}
          <div>
            <h4 className="font-bold text-white text-sm mb-3">Buy Vehicles</h4>
            <ul className="space-y-2">
              <li><button onClick={() => onNavigatePortal("marketplace")} className="hover:text-amber-400 transition-colors">Browse All Vehicles</button></li>
              <li><button onClick={() => onNavigatePortal("marketplace")} className="hover:text-amber-400 transition-colors">Used Vehicles</button></li>
              <li><button onClick={() => onNavigatePortal("marketplace")} className="hover:text-amber-400 transition-colors">Electric & Hybrid</button></li>
              <li><button onClick={() => onNavigatePortal("marketplace")} className="hover:text-amber-400 transition-colors">Certified Pre-Owned</button></li>
              <li><button onClick={() => onNavigatePortal("marketplace")} className="hover:text-amber-400 transition-colors">Escrow Protected Inventory</button></li>
            </ul>
          </div>

          {/* Column 2: Parts */}
          <div>
            <h4 className="font-bold text-white text-sm mb-3">Parts & Fitment</h4>
            <ul className="space-y-2">
              <li><button onClick={() => onNavigatePortal("parts")} className="hover:text-amber-400 transition-colors">Guaranteed Fitment Engine</button></li>
              <li><button onClick={() => onNavigatePortal("parts")} className="hover:text-amber-400 transition-colors">Brakes & Rotors</button></li>
              <li><button onClick={() => onNavigatePortal("parts")} className="hover:text-amber-400 transition-colors">Batteries & Ignition</button></li>
              <li><button onClick={() => onNavigatePortal("parts")} className="hover:text-amber-400 transition-colors">Wheels & Tires</button></li>
              <li><button onClick={() => onNavigatePortal("parts")} className="hover:text-amber-400 transition-colors">48h Return Policy</button></li>
            </ul>
          </div>

          {/* Column 3: Workspaces */}
          <div>
            <h4 className="font-bold text-white text-sm mb-3">B2B Workspaces</h4>
            <ul className="space-y-2">
              <li><button onClick={() => onNavigatePortal("b2b")} className="hover:text-amber-400 transition-colors">Dealer Portal (Doc 16)</button></li>
              <li><button onClick={() => onNavigatePortal("b2b")} className="hover:text-amber-400 transition-colors">Fleet Portfolio Manager</button></li>
              <li><button onClick={() => onNavigatePortal("services")} className="hover:text-amber-400 transition-colors">Workshop Bay Console (Doc 13)</button></li>
              <li><button onClick={() => onNavigatePortal("admin")} className="hover:text-amber-400 transition-colors">Operations Console (Doc 24)</button></li>
              <li><button onClick={() => onNavigatePortal("b2b")} className="hover:text-amber-400 transition-colors">DMS Ingestion Feeds</button></li>
            </ul>
          </div>

          {/* Column 4: Governance */}
          <div>
            <h4 className="font-bold text-white text-sm mb-3">Trust & Governance</h4>
            <ul className="space-y-2">
              <li><button onClick={() => onNavigatePortal("trust")} className="hover:text-amber-400 transition-colors">Escrow Protection Mechanics</button></li>
              <li><button onClick={() => onNavigatePortal("trust")} className="hover:text-amber-400 transition-colors">Buyer & Seller Protection</button></li>
              <li><button onClick={() => onNavigatePortal("trust")} className="hover:text-amber-400 transition-colors">Dispute Resolution Policy</button></li>
              <li><button onClick={() => onNavigatePortal("trust")} className="hover:text-amber-400 transition-colors">Jurisdiction Packs (Doc 18)</button></li>
              <li><button onClick={() => onNavigatePortal("trust")} className="hover:text-amber-400 transition-colors">Data Privacy & GDPR</button></li>
            </ul>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="pt-8 flex flex-col sm:flex-row items-center justify-between text-slate-500 gap-4">
          <div className="flex items-center gap-4">
            <span>© 2026 DriverXtra. All rights reserved.</span>
            <span>•</span>
            <span>Zoiko Tech Inc.</span>
            <span>•</span>
            <span className="font-mono text-[10px]">Architecture Roadmap v1.0</span>
          </div>

          <div className="flex items-center gap-3 text-slate-400">
            <Globe className="w-3.5 h-3.5 text-amber-400" />
            <span>Active Jurisdiction: <strong>United Kingdom (GBP £)</strong></span>
          </div>
        </div>
      </div>
    </footer>
  );
}
