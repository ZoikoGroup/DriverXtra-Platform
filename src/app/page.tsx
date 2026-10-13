"use client";

import React, { useState } from "react";
import Header from "@/components/Header";
import HeroSection from "@/components/HeroSection";
import QuickCategoryCards from "@/components/QuickCategoryCards";
import GaragePassportPreview from "@/components/GaragePassportPreview";
import FeaturedVehicles from "@/components/FeaturedVehicles";
import FitmentPartsShowcase from "@/components/FitmentPartsShowcase";
import WorkshopServicesSection from "@/components/WorkshopServicesSection";
import TrustEscrowExplainer from "@/components/TrustEscrowExplainer";
import DealerPortalView from "@/components/DealerPortalView";
import WorkshopBayView from "@/components/WorkshopBayView";
import AdminOpsView from "@/components/AdminOpsView";
import CheckoutModal from "@/components/CheckoutModal";
import Footer from "@/components/Footer";
import {
  Car,
  Building2,
  Wrench,
  ShieldAlert,
  Layers,
  CheckCircle2,
  ArrowRight,
  User,
  Lock,
  Sparkles
} from "lucide-react";

export default function Home() {
  const [activePortal, setActivePortal] = useState<string>("marketplace");
  const [checkoutItem, setCheckoutItem] = useState<{ item: any; type: "vehicle" | "part" | "service" } | null>(null);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 3000);
  };

  const handleSelectVehicle = (vehicle: any) => {
    setCheckoutItem({ item: vehicle, type: "vehicle" });
  };

  const handleAddToCart = (part: any) => {
    setCheckoutItem({ item: part, type: "part" });
  };

  const handleBookService = (service: any) => {
    setCheckoutItem({
      item: {
        title: `${service.name} — Full Service & MOT Inspection`,
        price: service.price,
        image: service.image,
      },
      type: "service",
    });
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900 selection:bg-amber-300 selection:text-slate-950">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 bg-slate-950 text-amber-300 px-5 py-3 rounded-2xl shadow-2xl border border-amber-400/40 text-xs font-bold flex items-center gap-2 animate-bounce">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Global Header */}
      <Header
        activePortal={activePortal}
        onPortalChange={(p) => {
          setActivePortal(p);
          window.scrollTo({ top: 0, behavior: "smooth" });
        }}
        onOpenAuthModal={() => setAuthModalOpen(true)}
      />

      {/* Main Content Area based on Active Portal */}
      <main className="flex-1">
        {activePortal === "b2b" ? (
          <DealerPortalView onBackToMarketplace={() => setActivePortal("marketplace")} />
        ) : activePortal === "services" ? (
          <div>
            <div className="bg-purple-950 text-white py-3 px-6 text-center text-xs flex items-center justify-center gap-3">
              <span>Viewing: <strong>Workshop Operations & Bay Console</strong></span>
              <button
                onClick={() => setActivePortal("marketplace")}
                className="underline text-amber-300 font-bold"
              >
                Switch to Consumer View
              </button>
            </div>
            <WorkshopBayView onBackToMarketplace={() => setActivePortal("marketplace")} />
          </div>
        ) : activePortal === "admin" ? (
          <AdminOpsView onBackToMarketplace={() => setActivePortal("marketplace")} />
        ) : (
          /* Public Marketplace & Garage Experience */
          <div>
            {/* Hero Section */}
            <HeroSection
              onSearchVehicles={() => {
                const el = document.getElementById("featured-vehicles");
                el?.scrollIntoView({ behavior: "smooth" });
              }}
              onNavigatePortal={(p) => setActivePortal(p)}
            />

            {/* Quick Pillars Overview */}
            <QuickCategoryCards
              onSelectCategory={(cat) => {
                if (cat === "vehicles") {
                  document.getElementById("featured-vehicles")?.scrollIntoView({ behavior: "smooth" });
                } else if (cat === "parts") {
                  document.getElementById("fitment-parts")?.scrollIntoView({ behavior: "smooth" });
                } else if (cat === "services") {
                  document.getElementById("workshop-services")?.scrollIntoView({ behavior: "smooth" });
                } else if (cat === "sell") {
                  setActivePortal("b2b");
                }
              }}
            />

            {/* Canonical Vehicle Master / My Garage Showcase */}
            <div id="garage-section">
              <GaragePassportPreview
                onShopParts={() => {
                  document.getElementById("fitment-parts")?.scrollIntoView({ behavior: "smooth" });
                }}
                onBookService={() => {
                  document.getElementById("workshop-services")?.scrollIntoView({ behavior: "smooth" });
                }}
              />
            </div>

            {/* Featured Vehicles with Escrow Badges */}
            <div id="featured-vehicles">
              <FeaturedVehicles onSelectVehicle={handleSelectVehicle} />
            </div>

            {/* Guaranteed Fitment Parts Section */}
            <div id="fitment-parts">
              <FitmentPartsShowcase onAddToCart={handleAddToCart} />
            </div>

            {/* Certified Workshop Services */}
            <div id="workshop-services">
              <WorkshopServicesSection onBookService={handleBookService} />
            </div>

            {/* Trust, Escrow & Governance Invariants */}
            <TrustEscrowExplainer />
          </div>
        )}
      </main>

      {/* Floating Workspace Switcher Pill */}
      <div className="fixed bottom-5 right-5 z-40 bg-slate-950/95 text-white p-2 rounded-2xl shadow-2xl border border-amber-400/30 backdrop-blur-md hidden sm:flex items-center gap-1.5 text-xs">
        <span className="text-[10px] font-black uppercase text-amber-400 px-2 py-0.5 tracking-wider">
          Demo Workspaces:
        </span>
        <button
          onClick={() => setActivePortal("marketplace")}
          className={`px-3 py-1.5 rounded-xl font-bold transition-all flex items-center gap-1.5 ${
            activePortal === "marketplace" ? "bg-amber-400 text-slate-950 shadow" : "text-slate-300 hover:text-white"
          }`}
        >
          <Car className="w-3.5 h-3.5" />
          <span>Consumer</span>
        </button>

        <button
          onClick={() => setActivePortal("b2b")}
          className={`px-3 py-1.5 rounded-xl font-bold transition-all flex items-center gap-1.5 ${
            activePortal === "b2b" ? "bg-amber-400 text-slate-950 shadow" : "text-slate-300 hover:text-white"
          }`}
        >
          <Building2 className="w-3.5 h-3.5" />
          <span>Dealer B2B (Doc 16)</span>
        </button>

        <button
          onClick={() => setActivePortal("services")}
          className={`px-3 py-1.5 rounded-xl font-bold transition-all flex items-center gap-1.5 ${
            activePortal === "services" ? "bg-amber-400 text-slate-950 shadow" : "text-slate-300 hover:text-white"
          }`}
        >
          <Wrench className="w-3.5 h-3.5" />
          <span>Workshop Bay (Doc 13)</span>
        </button>

        <button
          onClick={() => setActivePortal("admin")}
          className={`px-3 py-1.5 rounded-xl font-bold transition-all flex items-center gap-1.5 ${
            activePortal === "admin" ? "bg-amber-400 text-slate-950 shadow" : "text-slate-300 hover:text-white"
          }`}
        >
          <ShieldAlert className="w-3.5 h-3.5" />
          <span>Operations (Doc 24)</span>
        </button>
      </div>

      {/* Global Footer */}
      <Footer onNavigatePortal={(p) => setActivePortal(p)} />

      {/* Checkout / Escrow Reservation Modal */}
      {checkoutItem && (
        <CheckoutModal
          item={checkoutItem.item}
          type={checkoutItem.type}
          onClose={() => {
            setCheckoutItem(null);
            showToast("Transaction record committed to audit stream!");
          }}
        />
      )}

      {/* Sign In / Account Modal */}
      {authModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 sm:p-8 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-amber-400 flex items-center justify-center font-bold text-slate-950">
                  <User className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-base font-black text-slate-950">Sign In to DriverXtra</h3>
                  <p className="text-[10px] text-slate-500">Identity & RBAC (Doc 04 §7)</p>
                </div>
              </div>
              <button
                onClick={() => setAuthModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 font-bold"
              >
                ✕
              </button>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                setAuthModalOpen(false);
                showToast("Signed in as Primary Garage Owner (Mark Harrison)");
              }}
              className="space-y-4 mt-5"
            >
              <div>
                <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
                  Email Address
                </label>
                <input
                  type="email"
                  defaultValue="mark.harrison@example.co.uk"
                  className="w-full h-11 px-3 border border-slate-300 rounded-xl text-sm font-semibold"
                />
              </div>

              <div>
                <label className="block text-xs font-bold uppercase text-slate-500 mb-1">
                  Password
                </label>
                <input
                  type="password"
                  defaultValue="••••••••••••"
                  className="w-full h-11 px-3 border border-slate-300 rounded-xl text-sm font-semibold"
                />
              </div>

              <div className="text-[11px] text-slate-500 flex items-center justify-between">
                <label className="flex items-center gap-1.5 cursor-pointer">
                  <input type="checkbox" defaultChecked className="rounded text-amber-500" />
                  <span>Remember session (14 days)</span>
                </label>
                <a href="#" className="text-amber-600 font-bold">Forgot?</a>
              </div>

              <button
                type="submit"
                className="w-full h-11 bg-amber-400 hover:bg-amber-500 text-slate-950 font-black rounded-xl text-sm shadow transition-all"
              >
                Sign In to Platform
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
