"use client";

import React from "react";
import { Car, CircleDollarSign, Wrench, Settings, ArrowRight, ShieldCheck } from "lucide-react";

interface QuickCategoryCardsProps {
  onSelectCategory: (category: string) => void;
}

export default function QuickCategoryCards({ onSelectCategory }: QuickCategoryCardsProps) {
  const categories = [
    {
      id: "vehicles",
      title: "Buy Vehicles",
      description: "Search 14,000+ certified dealer and verified private cars with double-entry escrow funds protection.",
      icon: Car,
      badge: "Escrow Protected",
      cta: "Browse Inventory",
      color: "from-blue-600/10 to-indigo-600/10",
      accent: "text-blue-600",
    },
    {
      id: "sell",
      title: "Sell Vehicles",
      description: "Instant valuation, verified buyer matching, transparent seller fees, and automated title transfer assistance.",
      icon: CircleDollarSign,
      badge: "Instant Valuation",
      cta: "Start Listing",
      color: "from-amber-500/10 to-orange-500/10",
      accent: "text-amber-600",
    },
    {
      id: "parts",
      title: "Parts & Accessories",
      description: "OEM & aftermarket parts validated by our Canonical Fitment Engine. Guaranteed to fit your exact vehicle.",
      icon: Settings,
      badge: "Guaranteed Fit",
      cta: "Find Parts",
      color: "from-emerald-600/10 to-teal-600/10",
      accent: "text-emerald-600",
    },
    {
      id: "services",
      title: "Finance & Services",
      description: "Book certified workshop bays, arrange MOTs, and compare pre-qualified finance rates from regulated lenders.",
      icon: Wrench,
      badge: "Verified Workshops",
      cta: "Book Appointment",
      color: "from-purple-600/10 to-pink-600/10",
      accent: "text-purple-600",
    },
  ];

  return (
    <section className="py-12 px-4 sm:px-6 lg:px-10 bg-slate-50 border-b border-slate-200">
      <div className="mx-auto max-w-[1440px]">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between mb-8 gap-4">
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-amber-600">
              Ecosystem Overview
            </span>
            <h2 className="text-2xl sm:text-3xl font-black text-slate-950 mt-1">
              Start with what you need
            </h2>
          </div>
          <p className="text-sm text-slate-600 max-w-md">
            Built as a unified automotive commerce infrastructure so every purchase, service, and sale is recorded to your vehicle’s permanent digital record.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {categories.map((cat) => {
            const Icon = cat.icon;
            return (
              <div
                key={cat.id}
                onClick={() => onSelectCategory(cat.id)}
                className="group relative bg-white rounded-2xl p-6 border border-slate-200 hover:border-slate-900 shadow-sm hover:shadow-xl transition-all duration-300 cursor-pointer flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${cat.color} flex items-center justify-center`}>
                      <Icon className={`w-6 h-6 ${cat.accent}`} />
                    </div>
                    <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
                      {cat.badge}
                    </span>
                  </div>

                  <h3 className="text-lg font-bold text-slate-900 group-hover:text-amber-600 transition-colors">
                    {cat.title}
                  </h3>
                  <p className="text-xs text-slate-600 mt-2 leading-relaxed">
                    {cat.description}
                  </p>
                </div>

                <div className="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between text-xs font-bold text-slate-900 group-hover:text-amber-600">
                  <span>{cat.cta}</span>
                  <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
