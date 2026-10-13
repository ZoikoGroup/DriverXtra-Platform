"use client";

import React from "react";
import {
  Car,
  ShieldCheck,
  Calendar,
  Gauge,
  FileText,
  AlertCircle,
  Wrench,
  Settings,
  ChevronRight,
  Share2,
  CheckCircle2
} from "lucide-react";

interface GaragePassportPreviewProps {
  onShopParts: () => void;
  onBookService: () => void;
}

export default function GaragePassportPreview({ onShopParts, onBookService }: GaragePassportPreviewProps) {
  return (
    <section className="py-14 px-4 sm:px-6 lg:px-10 bg-white border-b border-slate-200">
      <div className="mx-auto max-w-[1440px]">
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-amber-600 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                Canonical Vehicle Master (Doc 05)
              </span>
              <span className="text-xs font-medium text-slate-500">• Single Authoritative Passport</span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-black text-slate-950 mt-1.5">
              My Garage: The Vehicle Lifecycle Passport
            </h2>
          </div>
          <p className="text-sm text-slate-600 max-w-lg">
            Every vehicle on DriverXtra has a verified lifecycle record. Maintenance work and parts purchases are written directly to this immutable passport, eliminating paper receipts and maximizing resale value.
          </p>
        </div>

        {/* Garage Vehicle Card Demo */}
        <div className="bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white rounded-3xl p-6 sm:p-8 shadow-2xl border border-slate-800 relative overflow-hidden">
          {/* Subtle background glow */}
          <div className="absolute top-0 right-0 w-96 h-96 bg-amber-500/10 rounded-full blur-3xl pointer-events-none"></div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
            {/* Left Column: Car Details */}
            <div className="lg:col-span-7">
              <div className="flex items-center gap-3 mb-3">
                <span className="px-2.5 py-1 rounded-md bg-amber-400 text-slate-950 text-xs font-black tracking-wide">
                  PRIMARY GARAGE VEHICLE
                </span>
                <span className="flex items-center gap-1 text-emerald-400 text-xs font-semibold">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  VIN Verified (DVLA & Manufacturer Database)
                </span>
              </div>

              <h3 className="text-2xl sm:text-4xl font-black text-white tracking-tight">
                2021 BMW 3 Series 330i M Sport Saloon
              </h3>
              <p className="text-sm text-slate-400 mt-1">
                2.0L TwinPower Turbo 258hp • 8-Speed Steptronic • Portimao Blue Metallic
              </p>

              {/* Stats badges */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-6">
                <div className="bg-slate-800/80 border border-slate-700/80 rounded-xl p-3">
                  <div className="flex items-center gap-1.5 text-slate-400 text-xs">
                    <Gauge className="w-3.5 h-3.5 text-amber-400" />
                    <span>Verified Odometer</span>
                  </div>
                  <div className="text-base sm:text-lg font-black text-white mt-1">
                    34,820 <span className="text-xs font-normal text-slate-400">mi</span>
                  </div>
                </div>

                <div className="bg-slate-800/80 border border-slate-700/80 rounded-xl p-3">
                  <div className="flex items-center gap-1.5 text-slate-400 text-xs">
                    <Calendar className="w-3.5 h-3.5 text-amber-400" />
                    <span>MOT Status</span>
                  </div>
                  <div className="text-base sm:text-lg font-black text-emerald-400 mt-1 flex items-center gap-1">
                    <CheckCircle2 className="w-4 h-4" /> Valid
                  </div>
                </div>

                <div className="bg-slate-800/80 border border-slate-700/80 rounded-xl p-3">
                  <div className="flex items-center gap-1.5 text-slate-400 text-xs">
                    <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
                    <span>Safety Recalls</span>
                  </div>
                  <div className="text-base sm:text-lg font-black text-emerald-400 mt-1">
                    0 Active
                  </div>
                </div>

                <div className="bg-slate-800/80 border border-slate-700/80 rounded-xl p-3">
                  <div className="flex items-center gap-1.5 text-slate-400 text-xs">
                    <FileText className="w-3.5 h-3.5 text-amber-400" />
                    <span>Service History</span>
                  </div>
                  <div className="text-base sm:text-lg font-black text-white mt-1">
                    100% Digital
                  </div>
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex flex-wrap gap-3 mt-8">
                <button
                  onClick={onShopParts}
                  className="px-5 py-3 rounded-xl bg-amber-400 hover:bg-amber-500 text-slate-950 font-bold text-sm flex items-center gap-2 shadow-sm transition-all"
                >
                  <Settings className="w-4 h-4" />
                  <span>Shop Guaranteed Fit Parts</span>
                </button>

                <button
                  onClick={onBookService}
                  className="px-5 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-bold text-sm flex items-center gap-2 border border-slate-700 transition-all"
                >
                  <Wrench className="w-4 h-4 text-amber-400" />
                  <span>Book Workshop Service</span>
                </button>

                <button
                  className="px-4 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 font-medium text-sm flex items-center gap-1.5 border border-slate-800"
                >
                  <Share2 className="w-4 h-4" />
                  <span>Share Digital Glovebox</span>
                </button>
              </div>
            </div>

            {/* Right Column: Digital Glovebox Timeline */}
            <div className="lg:col-span-5 bg-slate-950/90 border border-slate-800 rounded-2xl p-5">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Recent Verified Maintenance
                </span>
                <span className="text-[11px] font-semibold text-amber-400">
                  Authoritative Write-Back
                </span>
              </div>

              <div className="space-y-4 mt-4">
                <div className="flex items-start gap-3">
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 mt-1.5 ring-4 ring-emerald-500/20"></div>
                  <div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-white">Full Major Service & Brake Fluid</span>
                      <span className="text-slate-400">12 Sep 2026</span>
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Apex Bavarian Auto Care • 31,450 mi • Invoice #WO-98421
                    </p>
                    <span className="inline-block mt-1 text-[10px] font-semibold text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800">
                      Auto-Logged via WorkOrder Completion (Doc 13)
                    </span>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <div className="w-2.5 h-2.5 rounded-full bg-blue-400 mt-1.5 ring-4 ring-blue-500/20"></div>
                  <div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-white">Front Brake Pads Replacement</span>
                      <span className="text-slate-400">04 Jun 2026</span>
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Brembo P06088X • Guaranteed Fit Verified • 27,810 mi
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <div className="w-2.5 h-2.5 rounded-full bg-slate-500 mt-1.5"></div>
                  <div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-white">Annual Statutory Inspection (MOT)</span>
                      <span className="text-slate-400">15 Oct 2025</span>
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Pass with 0 Advisories • Verified DVLA Ingestion
                    </p>
                  </div>
                </div>
              </div>

              <div className="mt-5 pt-3 border-t border-slate-800 text-center">
                <span className="text-xs text-slate-400">
                  Estimated Resale Value Lift: <strong className="text-emerald-400 font-bold">+£1,450</strong> with verified digital history
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
