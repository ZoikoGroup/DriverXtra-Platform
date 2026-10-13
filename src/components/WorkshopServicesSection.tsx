"use client";

import React from "react";
import {
  Wrench,
  MapPin,
  Star,
  Calendar,
  CheckCircle2,
  Clock,
  ShieldCheck,
  FileCheck2,
  ArrowRight
} from "lucide-react";

export default function WorkshopServicesSection({ onBookService }: { onBookService: (service: any) => void }) {
  const workshops = [
    {
      id: "ws-01",
      name: "Apex Bavarian Performance & MOT Centre",
      rating: 4.9,
      reviews: 142,
      distance: "2.4 miles away • London SE1",
      specialty: "German Specialist (BMW, VAG, Mercedes)",
      price: 189,
      slotsAvailable: "Tomorrow at 10:00 AM",
      verified: true,
      image: "https://images.unsplash.com/photo-1613214149922-f1809c99b414?auto=format&fit=crop&w=600&q=80",
    },
    {
      id: "ws-02",
      name: "GreenTech EV & Hybrid Certified Bay",
      rating: 4.8,
      reviews: 98,
      distance: "3.8 miles away • London E14",
      specialty: "High-Voltage Battery & Hybrid Diagnostics",
      price: 165,
      slotsAvailable: "Thursday at 09:30 AM",
      verified: true,
      image: "https://images.unsplash.com/photo-1486006920555-c77dce18193b?auto=format&fit=crop&w=600&q=80",
    },
    {
      id: "ws-03",
      name: "Precision Master Mechanics & MOT Bay",
      rating: 4.9,
      reviews: 215,
      distance: "5.1 miles away • London SW4",
      specialty: "Full Mechanical, Brakes & Statutory Testing",
      price: 149,
      slotsAvailable: "Today at 02:00 PM",
      verified: true,
      image: "https://images.unsplash.com/photo-1517524008697-84bbe3c3fd98?auto=format&fit=crop&w=600&q=80",
    },
  ];

  return (
    <section className="py-14 px-4 sm:px-6 lg:px-10 bg-slate-50 border-b border-slate-200">
      <div className="mx-auto max-w-[1440px]">
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-purple-700 bg-purple-50 px-2 py-0.5 rounded border border-purple-200">
                Services Architecture (Doc 13)
              </span>
              <span className="text-xs text-slate-500">• Verified Service Bays & Automatic Write-Back</span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-black text-slate-950 mt-1.5">
              Certified Workshop Bookings
            </h2>
          </div>

          <p className="text-sm text-slate-600 max-w-md">
            Book certified automotive workshops with upfront quotes, live digital work order tracking, and tamper-proof write-back to your vehicle’s permanent service record.
          </p>
        </div>

        {/* Workshop Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {workshops.map((ws) => (
            <div
              key={ws.id}
              className="group bg-white rounded-2xl overflow-hidden border border-slate-200 hover:border-slate-950 shadow-sm hover:shadow-xl transition-all duration-300 flex flex-col justify-between"
            >
              <div>
                <div className="relative aspect-[16/9] bg-slate-100 overflow-hidden">
                  <img
                    src={ws.image}
                    alt={ws.name}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                  />
                  <div className="absolute top-3 left-3 bg-slate-950/80 backdrop-blur text-white text-[10px] font-bold px-2 py-0.5 rounded-md flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3 text-emerald-400" />
                    KYB Verified Workshop
                  </div>
                  <div className="absolute bottom-3 left-3 bg-white/95 backdrop-blur text-slate-900 px-2.5 py-0.5 rounded text-xs font-bold flex items-center gap-1 shadow">
                    <Star className="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
                    <span>{ws.rating} ({ws.reviews})</span>
                  </div>
                </div>

                <div className="p-5">
                  <h3 className="text-base font-bold text-slate-950 group-hover:text-amber-600 transition-colors">
                    {ws.name}
                  </h3>

                  <div className="flex items-center gap-1 text-xs text-slate-500 mt-1">
                    <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span>{ws.distance}</span>
                  </div>

                  <div className="mt-3 inline-block bg-slate-100 text-slate-700 text-xs px-2.5 py-1 rounded font-medium">
                    {ws.specialty}
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-100 flex items-center gap-2 text-xs text-emerald-700 font-semibold">
                    <Clock className="w-3.5 h-3.5" />
                    <span>Next Slot: {ws.slotsAvailable}</span>
                  </div>
                </div>
              </div>

              <div className="p-5 pt-0">
                <div className="flex items-baseline justify-between mb-3">
                  <div>
                    <span className="text-xs text-slate-500">Major Service from</span>
                    <div className="text-xl font-black text-slate-950">£{ws.price}</div>
                  </div>
                  <span className="text-[10px] text-slate-600 bg-slate-100 px-2 py-1 rounded font-medium">
                    Fixed Price Guarantee
                  </span>
                </div>

                <button
                  onClick={() => onBookService(ws)}
                  className="w-full h-11 rounded-lg bg-slate-950 hover:bg-slate-800 text-amber-400 font-bold text-xs flex items-center justify-center gap-2 transition-all shadow-sm"
                >
                  <Calendar className="w-4 h-4" />
                  <span>Reserve Workshop Bay</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
