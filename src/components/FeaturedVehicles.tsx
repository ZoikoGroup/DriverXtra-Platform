"use client";

import React, { useState } from "react";
import {
  Car,
  ShieldCheck,
  Fuel,
  Gauge,
  SlidersHorizontal,
  Bookmark,
  CheckCircle2,
  Lock,
  ArrowRight
} from "lucide-react";

interface Vehicle {
  id: string;
  title: string;
  year: number;
  make: string;
  price: number;
  monthly: number;
  mileage: number;
  transmission: string;
  fuel: string;
  location: string;
  sellerType: "Verified Dealer" | "Certified Private";
  image: string;
  escrowProtected: boolean;
  vinVerified: boolean;
}

interface FeaturedVehiclesProps {
  onSelectVehicle: (vehicle: Vehicle) => void;
}

export default function FeaturedVehicles({ onSelectVehicle }: FeaturedVehiclesProps) {
  const [activeFilter, setActiveFilter] = useState<string>("All");

  const sampleVehicles: Vehicle[] = [
    {
      id: "veh-001",
      title: "2024 Toyota RAV4 2.5 Hybrid Design AWD",
      year: 2024,
      make: "Toyota",
      price: 34995,
      monthly: 429,
      mileage: 8200,
      transmission: "Automatic",
      fuel: "Hybrid Petrol",
      location: "London, UK (12 mi)",
      sellerType: "Verified Dealer",
      image: "https://images.unsplash.com/photo-1581540222194-0def2dda95b8?auto=format&fit=crop&w=800&q=80",
      escrowProtected: true,
      vinVerified: true,
    },
    {
      id: "veh-002",
      title: "2023 BMW X3 xDrive30e M Sport (Pro Pack)",
      year: 2023,
      make: "BMW",
      price: 43500,
      monthly: 549,
      mileage: 14600,
      transmission: "Automatic",
      fuel: "Plug-in Hybrid",
      location: "Manchester, UK (45 mi)",
      sellerType: "Verified Dealer",
      image: "https://images.unsplash.com/photo-1555215695-3004980ad54e?auto=format&fit=crop&w=800&q=80",
      escrowProtected: true,
      vinVerified: true,
    },
    {
      id: "veh-003",
      title: "2023 Tesla Model 3 Long Range Dual Motor AWD",
      year: 2023,
      make: "Tesla",
      price: 31200,
      monthly: 385,
      mileage: 19400,
      transmission: "Single-Speed",
      fuel: "Electric (374 mi)",
      location: "Birmingham, UK (28 mi)",
      sellerType: "Certified Private",
      image: "https://images.unsplash.com/photo-1560958089-b8a1929cea89?auto=format&fit=crop&w=800&q=80",
      escrowProtected: true,
      vinVerified: true,
    },
    {
      id: "veh-004",
      title: "2024 Mercedes-Benz C 300 AMG Line Premium Plus",
      year: 2024,
      make: "Mercedes-Benz",
      price: 39800,
      monthly: 495,
      mileage: 6300,
      transmission: "9G-Tronic",
      fuel: "Mild Hybrid Petrol",
      location: "Bristol, UK (30 mi)",
      sellerType: "Verified Dealer",
      image: "https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?auto=format&fit=crop&w=800&q=80",
      escrowProtected: true,
      vinVerified: true,
    },
    {
      id: "veh-005",
      title: "2022 Porsche Macan GTS PDK (Sport Chrono)",
      year: 2022,
      make: "Porsche",
      price: 57900,
      monthly: 720,
      mileage: 22100,
      transmission: "Dual-Clutch PDK",
      fuel: "Twin-Turbo Petrol",
      location: "Leeds, UK (52 mi)",
      sellerType: "Verified Dealer",
      image: "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=800&q=80",
      escrowProtected: true,
      vinVerified: true,
    },
    {
      id: "veh-006",
      title: "2023 Audi Q4 e-tron 40 S Line (Tech Pack)",
      year: 2023,
      make: "Audi",
      price: 35400,
      monthly: 440,
      mileage: 11800,
      transmission: "Automatic",
      fuel: "Electric (316 mi)",
      location: "London, UK (8 mi)",
      sellerType: "Verified Dealer",
      image: "https://images.unsplash.com/photo-1606664515524-ed2f786a0bd6?auto=format&fit=crop&w=800&q=80",
      escrowProtected: true,
      vinVerified: true,
    },
  ];

  const filteredVehicles = activeFilter === "All"
    ? sampleVehicles
    : sampleVehicles.filter(v => v.make === activeFilter || (activeFilter === "Electric" && v.fuel.includes("Electric")));

  return (
    <section className="py-14 px-4 sm:px-6 lg:px-10 bg-slate-50 border-b border-slate-200">
      <div className="mx-auto max-w-[1440px]">
        {/* Section Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4">
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-amber-600">
              Verified Marketplace Inventory
            </span>
            <h2 className="text-2xl sm:text-3xl font-black text-slate-950 mt-1">
              Vehicles worth your attention
            </h2>
          </div>

          {/* Filter pills */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            {["All", "Toyota", "BMW", "Tesla", "Mercedes-Benz", "Electric"].map((filter) => (
              <button
                key={filter}
                onClick={() => setActiveFilter(filter)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-bold transition-all shrink-0 ${
                  activeFilter === filter
                    ? "bg-slate-950 text-white shadow"
                    : "bg-white text-slate-700 border border-slate-200 hover:border-slate-400"
                }`}
              >
                {filter}
              </button>
            ))}
          </div>
        </div>

        {/* Vehicles Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredVehicles.map((vehicle) => (
            <div
              key={vehicle.id}
              onClick={() => onSelectVehicle(vehicle)}
              className="group bg-white rounded-2xl overflow-hidden border border-slate-200 hover:border-slate-900 shadow-sm hover:shadow-xl transition-all duration-300 flex flex-col cursor-pointer"
            >
              {/* Image & Badges */}
              <div className="relative aspect-[16/10] bg-slate-100 overflow-hidden">
                <img
                  src={vehicle.image}
                  alt={vehicle.title}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                />
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                  }}
                  className="absolute top-3 right-3 w-8 h-8 rounded-full bg-white/90 backdrop-blur hover:bg-white text-slate-700 hover:text-amber-500 flex items-center justify-center shadow-md transition-colors"
                  aria-label="Save vehicle"
                >
                  <Bookmark className="w-4 h-4" />
                </button>

                <div className="absolute top-3 left-3 flex flex-col gap-1">
                  <span className="bg-slate-950/80 backdrop-blur text-white text-[10px] font-bold px-2 py-0.5 rounded-md flex items-center gap-1 shadow">
                    <ShieldCheck className="w-3 h-3 text-emerald-400" />
                    {vehicle.sellerType}
                  </span>
                  {vehicle.escrowProtected && (
                    <span className="bg-amber-400 text-slate-950 text-[10px] font-black px-2 py-0.5 rounded-md flex items-center gap-1 shadow">
                      <Lock className="w-2.5 h-2.5" />
                      Escrow Protected
                    </span>
                  )}
                </div>

                <div className="absolute bottom-3 left-3 bg-slate-950/90 backdrop-blur text-white px-2.5 py-1 rounded-md text-xs font-bold">
                  {vehicle.location}
                </div>
              </div>

              {/* Vehicle Specs */}
              <div className="p-5 flex-1 flex flex-col justify-between">
                <div>
                  <h3 className="text-base font-bold text-slate-950 group-hover:text-amber-600 transition-colors line-clamp-1">
                    {vehicle.title}
                  </h3>

                  <div className="grid grid-cols-3 gap-2 py-3 mt-2 border-y border-slate-100 text-xs text-slate-600">
                    <div className="flex items-center gap-1">
                      <Gauge className="w-3.5 h-3.5 text-slate-400" />
                      <span>{vehicle.mileage.toLocaleString()} mi</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <SlidersHorizontal className="w-3.5 h-3.5 text-slate-400" />
                      <span>{vehicle.transmission}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Fuel className="w-3.5 h-3.5 text-slate-400" />
                      <span className="truncate">{vehicle.fuel.split(" ")[0]}</span>
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-2 flex items-baseline justify-between">
                  <div>
                    <div className="text-xl font-black text-slate-950">
                      £{vehicle.price.toLocaleString()}
                    </div>
                    <div className="text-xs text-slate-500 font-medium">
                      from <strong className="text-slate-800">£{vehicle.monthly}/mo</strong> (PCP Finance)
                    </div>
                  </div>

                  <span className="inline-flex items-center gap-1 text-xs font-bold text-amber-600 group-hover:translate-x-0.5 transition-transform">
                    Reserve Online <ArrowRight className="w-3.5 h-3.5" />
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
