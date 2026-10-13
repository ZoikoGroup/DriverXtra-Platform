"use client";

import React, { useState } from "react";
import {
  Settings,
  CheckCircle2,
  ShieldCheck,
  ShoppingCart,
  Truck,
  RotateCcw,
  Sparkles,
  ArrowRight
} from "lucide-react";

interface PartItem {
  id: string;
  name: string;
  brand: string;
  partNumber: string;
  price: number;
  originalPrice?: number;
  sellerCount: number;
  fitsSelectedVehicle: boolean;
  image: string;
  category: string;
}

export default function FitmentPartsShowcase({ onAddToCart }: { onAddToCart: (part: PartItem) => void }) {
  const [selectedVehicle, setSelectedVehicle] = useState("2021 BMW 330i M Sport");

  const sampleParts: PartItem[] = [
    {
      id: "part-01",
      name: "Brembo Prime Two-Piece Front Brake Disc Rotor Set (348mm)",
      brand: "Brembo",
      partNumber: "09.C398.13",
      price: 215,
      originalPrice: 249,
      sellerCount: 4,
      fitsSelectedVehicle: true,
      image: "https://images.unsplash.com/photo-1600790142055-619df03207e6?auto=format&fit=crop&w=600&q=80",
      category: "Braking Systems",
    },
    {
      id: "part-02",
      name: "Bosch S5 A13 AGM Heavy Duty Stop-Start Car Battery (95Ah 850A)",
      brand: "Bosch",
      partNumber: "0 092 S5A 130",
      price: 184,
      originalPrice: 210,
      sellerCount: 6,
      fitsSelectedVehicle: true,
      image: "https://images.unsplash.com/photo-1599819811279-d5ad9cccf838?auto=format&fit=crop&w=600&q=80",
      category: "Electrical & Ignition",
    },
    {
      id: "part-03",
      name: "Michelin Pilot Sport 4S High Performance Tire 255/35 R19 96Y XL",
      brand: "Michelin",
      partNumber: "MIC-784912",
      price: 198,
      sellerCount: 3,
      fitsSelectedVehicle: true,
      image: "https://images.unsplash.com/photo-1578844251758-2f71da64c96f?auto=format&fit=crop&w=600&q=80",
      category: "Wheels & Tires",
    },
    {
      id: "part-04",
      name: "K&N High-Flow Replacement Lifetime Air Filter Engine Element",
      brand: "K&N Engineering",
      partNumber: "33-3136",
      price: 68,
      originalPrice: 79,
      sellerCount: 5,
      fitsSelectedVehicle: true,
      image: "https://images.unsplash.com/photo-1486262715619-67b85e0b08d3?auto=format&fit=crop&w=600&q=80",
      category: "Air Intake & Filters",
    },
  ];

  return (
    <section className="py-14 px-4 sm:px-6 lg:px-10 bg-white border-b border-slate-200">
      <div className="mx-auto max-w-[1440px]">
        {/* Section Heading & Vehicle Filter Bar */}
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                Fitment Architecture (Doc 06)
              </span>
              <span className="text-xs text-slate-500">• Canonical Product & Multi-Seller Offers</span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-black text-slate-950 mt-1.5">
              Parts with Guaranteed Fitment
            </h2>
          </div>

          {/* Active vehicle badge */}
          <div className="bg-slate-900 text-white px-4 py-2.5 rounded-xl flex items-center gap-3 border border-slate-800 shadow-sm">
            <div className="flex flex-col text-xs">
              <span className="text-slate-400 font-medium">Filtering compatible parts for:</span>
              <span className="font-bold text-amber-400">{selectedVehicle}</span>
            </div>
            <span className="text-xs bg-emerald-600 text-white font-extrabold px-2 py-0.5 rounded flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> Confirmed
            </span>
          </div>
        </div>

        {/* Parts Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {sampleParts.map((part) => (
            <div
              key={part.id}
              className="group bg-slate-50 rounded-2xl p-4 border border-slate-200 hover:border-slate-950 hover:bg-white shadow-sm hover:shadow-xl transition-all duration-300 flex flex-col justify-between"
            >
              <div>
                {/* Part Image */}
                <div className="relative aspect-square rounded-xl bg-white p-3 mb-4 overflow-hidden border border-slate-100 flex items-center justify-center">
                  <img
                    src={part.image}
                    alt={part.name}
                    className="max-h-full max-w-full object-cover group-hover:scale-105 transition-transform duration-300 rounded-lg"
                  />
                  {part.fitsSelectedVehicle && (
                    <div className="absolute top-2 left-2 bg-emerald-600 text-white text-[10px] font-black px-2 py-0.5 rounded shadow flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3 text-white" />
                      Guaranteed Fit
                    </div>
                  )}
                </div>

                <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                  {part.brand} • MPN: {part.partNumber}
                </div>

                <h3 className="text-sm font-bold text-slate-950 mt-1 line-clamp-2 leading-snug">
                  {part.name}
                </h3>

                <div className="mt-2 text-xs text-slate-500">
                  Available from <strong className="text-slate-800">{part.sellerCount} verified suppliers</strong>
                </div>
              </div>

              <div className="mt-5 pt-3 border-t border-slate-200">
                <div className="flex items-baseline justify-between mb-3">
                  <div className="text-lg font-black text-slate-950">
                    £{part.price}
                    {part.originalPrice && (
                      <span className="text-xs text-slate-400 line-through font-normal ml-1.5">
                        £{part.originalPrice}
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] text-emerald-700 font-bold bg-emerald-100 px-2 py-0.5 rounded">
                    Free Next-Day Delivery
                  </span>
                </div>

                <button
                  onClick={() => onAddToCart(part)}
                  className="w-full h-10 rounded-lg bg-amber-400 hover:bg-amber-500 text-slate-950 font-bold text-xs flex items-center justify-center gap-2 shadow-sm transition-all"
                >
                  <ShoppingCart className="w-3.5 h-3.5" />
                  <span>Add to Order (Escrow Staged)</span>
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Fitment Guarantee Banner */}
        <div className="mt-8 bg-emerald-50 border border-emerald-200 rounded-2xl p-4 sm:p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-emerald-600 text-white flex items-center justify-center shrink-0 shadow-sm">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <h4 className="text-sm sm:text-base font-bold text-emerald-950">
                DriverXtra Guaranteed Fitment Promise
              </h4>
              <p className="text-xs text-emerald-800 mt-0.5">
                If any part marked with the Guaranteed Fit badge does not install cleanly on your registered Garage vehicle, return it within 48 hours for an instant 100% refund, including return carriage fees.
              </p>
            </div>
          </div>
          <span className="text-xs font-bold text-emerald-900 underline cursor-pointer shrink-0">
            Read Fitment Policy (Doc 06) &rarr;
          </span>
        </div>
      </div>
    </section>
  );
}
