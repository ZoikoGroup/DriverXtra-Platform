"use client";

import React, { useState } from "react";
import {
  Car,
  Settings,
  Wrench,
  BadgeDollarSign,
  Search,
  CheckCircle2,
  ShieldCheck,
  ChevronRight,
  Filter,
  Layers
} from "lucide-react";

interface HeroSectionProps {
  onSearchVehicles: (query: any) => void;
  onNavigatePortal: (portal: string) => void;
}

export default function HeroSection({ onSearchVehicles, onNavigatePortal }: HeroSectionProps) {
  const [activeTab, setActiveTab] = useState<"vehicles" | "parts" | "services" | "valuation">("vehicles");

  // Form states
  const [vehicleMake, setVehicleMake] = useState("BMW");
  const [vehicleModel, setVehicleModel] = useState("3 Series");
  const [maxPrice, setMaxPrice] = useState("30000");

  const [partYear, setPartYear] = useState("2021");
  const [partMake, setPartMake] = useState("BMW");
  const [partModel, setPartModel] = useState("330i M Sport");
  const [partCategory, setPartCategory] = useState("Brake Discs & Rotors");

  const [serviceType, setServiceType] = useState("Full Service & MOT");
  const [servicePostal, setServicePostal] = useState("SW1A 1AA");

  const [regPlate, setRegPlate] = useState("GF21 XTR");

  return (
    <section className="relative bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 text-white pt-10 pb-16 px-4 sm:px-6 lg:px-10 overflow-hidden">
      {/* Subtle ambient lighting */}
      <div className="absolute top-0 right-1/4 w-96 h-96 bg-amber-500/10 rounded-full blur-3xl pointer-events-none"></div>
      <div className="absolute bottom-0 left-10 w-80 h-80 bg-blue-500/10 rounded-full blur-3xl pointer-events-none"></div>

      <div className="mx-auto max-w-[1440px] relative z-10">
        <div className="max-w-3xl mb-8">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-400/10 border border-amber-400/30 text-amber-300 text-xs font-semibold mb-4">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping"></span>
            Canonical Architecture • 18 Bounded Contexts
          </div>
          <h1 className="text-3xl sm:text-5xl font-black tracking-tight text-white leading-tight">
            Buy, Sell, and Upgrade Vehicles <br className="hidden sm:inline" />
            with <span className="text-amber-400">Total Confidence</span>
          </h1>
          <p className="mt-3 text-base sm:text-lg text-slate-300 font-normal">
            Global automotive commerce infrastructure connecting individuals, verified dealers, certified workshops, and aftermarket suppliers with double-entry escrow protection.
          </p>
        </div>

        {/* Multi-Tab Interactive Search Console */}
        <div className="bg-white rounded-2xl shadow-2xl p-2 sm:p-4 text-slate-900 border border-slate-200">
          {/* Tabs */}
          <div className="flex border-b border-slate-200 pb-2 gap-1 overflow-x-auto">
            <button
              onClick={() => setActiveTab("vehicles")}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold transition-all shrink-0 ${
                activeTab === "vehicles"
                  ? "bg-amber-400 text-slate-950 shadow-sm"
                  : "text-slate-600 hover:text-slate-950 hover:bg-slate-100"
              }`}
            >
              <Car className="w-4 h-4" />
              <span>Buy Vehicles</span>
            </button>

            <button
              onClick={() => setActiveTab("parts")}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold transition-all shrink-0 ${
                activeTab === "parts"
                  ? "bg-amber-400 text-slate-950 shadow-sm"
                  : "text-slate-600 hover:text-slate-950 hover:bg-slate-100"
              }`}
            >
              <Settings className="w-4 h-4" />
              <span>Parts & Fitment</span>
              <span className="text-[10px] bg-slate-950 text-amber-300 font-extrabold px-1.5 py-0.5 rounded">
                Guaranteed Fit
              </span>
            </button>

            <button
              onClick={() => setActiveTab("services")}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold transition-all shrink-0 ${
                activeTab === "services"
                  ? "bg-amber-400 text-slate-950 shadow-sm"
                  : "text-slate-600 hover:text-slate-950 hover:bg-slate-100"
              }`}
            >
              <Wrench className="w-4 h-4" />
              <span>Book Workshop Service</span>
            </button>

            <button
              onClick={() => setActiveTab("valuation")}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold transition-all shrink-0 ${
                activeTab === "valuation"
                  ? "bg-amber-400 text-slate-950 shadow-sm"
                  : "text-slate-600 hover:text-slate-950 hover:bg-slate-100"
              }`}
            >
              <BadgeDollarSign className="w-4 h-4" />
              <span>Instant Valuation</span>
            </button>
          </div>

          {/* Form Content based on tab */}
          <div className="pt-4 px-2">
            {activeTab === "vehicles" && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 items-end">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
                    Make
                  </label>
                  <select
                    value={vehicleMake}
                    onChange={(e) => setVehicleMake(e.target.value)}
                    className="w-full h-11 px-3 rounded-lg border border-slate-300 bg-slate-50 font-semibold text-sm focus:border-amber-500 focus:outline-none"
                  >
                    <option value="Any">Any Make</option>
                    <option value="BMW">BMW</option>
                    <option value="Mercedes-Benz">Mercedes-Benz</option>
                    <option value="Audi">Audi</option>
                    <option value="Toyota">Toyota</option>
                    <option value="Tesla">Tesla</option>
                    <option value="Porsche">Porsche</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
                    Model
                  </label>
                  <select
                    value={vehicleModel}
                    onChange={(e) => setVehicleModel(e.target.value)}
                    className="w-full h-11 px-3 rounded-lg border border-slate-300 bg-slate-50 font-semibold text-sm focus:border-amber-500 focus:outline-none"
                  >
                    <option value="Any">Any Model</option>
                    <option value="3 Series">3 Series</option>
                    <option value="M4 Competition">M4 Competition</option>
                    <option value="C-Class">C-Class</option>
                    <option value="RAV4 Hybrid">RAV4 Hybrid</option>
                    <option value="Model 3">Model 3</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
                    Max Price
                  </label>
                  <select
                    value={maxPrice}
                    onChange={(e) => setMaxPrice(e.target.value)}
                    className="w-full h-11 px-3 rounded-lg border border-slate-300 bg-slate-50 font-semibold text-sm focus:border-amber-500 focus:outline-none"
                  >
                    <option value="15000">Up to £15,000</option>
                    <option value="25000">Up to £25,000</option>
                    <option value="35000">Up to £35,000</option>
                    <option value="50000">Up to £50,000</option>
                    <option value="100000">No Limit</option>
                  </select>
                </div>

                <button
                  onClick={() => onSearchVehicles({ make: vehicleMake, model: vehicleModel, maxPrice })}
                  className="h-11 w-full bg-slate-950 hover:bg-slate-800 text-amber-400 font-bold rounded-lg flex items-center justify-center gap-2 shadow-sm transition-all"
                >
                  <Search className="w-4 h-4" />
                  <span>Search 14,820 Vehicles</span>
                </button>
              </div>
            )}

            {activeTab === "parts" && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 items-end">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
                    Vehicle Year & Make
                  </label>
                  <input
                    type="text"
                    value={`${partYear} ${partMake}`}
                    onChange={(e) => setPartMake(e.target.value)}
                    className="w-full h-11 px-3 rounded-lg border border-slate-300 bg-slate-50 font-semibold text-sm"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
                    Exact Model & Trim
                  </label>
                  <input
                    type="text"
                    value={partModel}
                    onChange={(e) => setPartModel(e.target.value)}
                    className="w-full h-11 px-3 rounded-lg border border-slate-300 bg-slate-50 font-semibold text-sm"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
                    Part Category
                  </label>
                  <select
                    value={partCategory}
                    onChange={(e) => setPartCategory(e.target.value)}
                    className="w-full h-11 px-3 rounded-lg border border-slate-300 bg-slate-50 font-semibold text-sm"
                  >
                    <option value="Brake Discs & Rotors">Brakes & Rotors</option>
                    <option value="Air Filters & Intake">Engine & Filtration</option>
                    <option value="Suspension Kits">Suspension & Steering</option>
                    <option value="Exhaust Systems">Exhaust & Emissions</option>
                    <option value="Batteries">Batteries & Alternators</option>
                  </select>
                </div>

                <button
                  onClick={() => onNavigatePortal("parts")}
                  className="h-11 w-full bg-emerald-700 hover:bg-emerald-800 text-white font-bold rounded-lg flex items-center justify-center gap-2 shadow-sm transition-all"
                >
                  <CheckCircle2 className="w-4 h-4 text-emerald-300" />
                  <span>Find Guaranteed Parts</span>
                </button>
              </div>
            )}

            {activeTab === "services" && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
                    Service Required
                  </label>
                  <select
                    value={serviceType}
                    onChange={(e) => setServiceType(e.target.value)}
                    className="w-full h-11 px-3 rounded-lg border border-slate-300 bg-slate-50 font-semibold text-sm"
                  >
                    <option value="Full Service & MOT">Full Service + MOT</option>
                    <option value="Brake Inspection">Brake Inspection & Fluid</option>
                    <option value="Diagnostic Scan">Engine Diagnostic Scan</option>
                    <option value="Air Conditioning">Air Conditioning Recharge</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
                    Postcode / City
                  </label>
                  <input
                    type="text"
                    value={servicePostal}
                    onChange={(e) => setServicePostal(e.target.value)}
                    className="w-full h-11 px-3 rounded-lg border border-slate-300 bg-slate-50 font-semibold text-sm"
                    placeholder="e.g. SW1A 1AA"
                  />
                </div>

                <button
                  onClick={() => onNavigatePortal("services")}
                  className="h-11 w-full bg-slate-950 hover:bg-slate-800 text-amber-400 font-bold rounded-lg flex items-center justify-center gap-2"
                >
                  <Wrench className="w-4 h-4" />
                  <span>Find Certified Garages</span>
                </button>
              </div>
            )}

            {activeTab === "valuation" && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
                <div className="sm:col-span-2">
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
                    Enter Vehicle Registration Plate or VIN
                  </label>
                  <div className="flex items-center gap-2">
                    <div className="flex items-center h-11 bg-amber-400 rounded-lg px-3 border border-amber-500 font-black tracking-widest text-slate-950 text-base shadow-inner">
                      GB
                    </div>
                    <input
                      type="text"
                      value={regPlate}
                      onChange={(e) => setRegPlate(e.target.value.toUpperCase())}
                      className="w-full h-11 px-4 rounded-lg border-2 border-slate-300 bg-slate-50 font-black text-lg tracking-wider text-slate-900 uppercase"
                      placeholder="e.g. AB21 CDE"
                    />
                  </div>
                </div>

                <button
                  onClick={() => onNavigatePortal("sell")}
                  className="h-11 w-full bg-amber-400 hover:bg-amber-500 text-slate-950 font-black rounded-lg flex items-center justify-center gap-2 shadow-sm"
                >
                  <BadgeDollarSign className="w-5 h-5" />
                  <span>Get Instant Valuation</span>
                </button>
              </div>
            )}
          </div>

          {/* Verification footer indicator */}
          <div className="mt-3 pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between text-xs text-slate-500 px-2">
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1 text-slate-700 font-medium">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                Verified VIN Decoding
              </span>
              <span className="flex items-center gap-1 text-slate-700 font-medium">
                <ShieldCheck className="w-3.5 h-3.5 text-blue-600" />
                Regulated Escrow Custody
              </span>
              <span className="flex items-center gap-1 text-slate-700 font-medium">
                <CheckCircle2 className="w-3.5 h-3.5 text-amber-600" />
                Guaranteed Part Compatibility
              </span>
            </div>
            <button
              onClick={() => onNavigatePortal("garage")}
              className="text-amber-600 hover:text-amber-700 font-semibold flex items-center gap-1 mt-1 sm:mt-0"
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Manage Your Vehicle in My Garage &rarr;</span>
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
