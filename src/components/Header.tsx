"use client";

import React, { useState } from "react";
import {
  Search,
  Bookmark,
  MessageSquareText,
  User,
  Settings,
  CirclePlus,
  Menu,
  X,
  ChevronDown,
  ShieldCheck,
  Wrench,
  Car,
  Layers,
  Building2,
  FileCheck2,
  ArrowRight
} from "lucide-react";

interface HeaderProps {
  activePortal: string;
  onPortalChange: (portal: string) => void;
  onOpenAuthModal?: () => void;
}

export default function Header({ activePortal, onPortalChange, onOpenAuthModal }: HeaderProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [activeNavDropdown, setActiveNavDropdown] = useState<string | null>(null);

  const navItems = [
    { id: "marketplace", label: "Buy Vehicles", icon: Car },
    { id: "sell", label: "Sell Vehicles", icon: CirclePlus },
    { id: "parts", label: "Parts & Accessories", badge: "Guaranteed Fit", icon: Settings },
    { id: "services", label: "Book Services", icon: Wrench },
    { id: "garage", label: "My Garage", badge: "Live", icon: Layers },
    { id: "b2b", label: "For Business & Fleets", icon: Building2 },
    { id: "trust", label: "Trust & Safety", icon: ShieldCheck },
  ];

  return (
    <header className="sticky top-0 z-50 shadow-sm transition-shadow">
      {/* Top Jurisdiction & Trust Banner */}
      <div className="bg-slate-900 text-slate-300 text-xs py-1.5 px-4 sm:px-6 lg:px-10 border-b border-slate-800">
        <div className="mx-auto max-w-[1440px] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 text-amber-400 font-medium">
              <ShieldCheck className="w-3.5 h-3.5 text-amber-400" />
              Global Automotive Commerce Infrastructure
            </span>
            <span className="hidden md:inline text-slate-500">|</span>
            <span className="hidden md:inline text-slate-400">
              PostgreSQL System of Record • Dual-Custody Escrow Protection
            </span>
          </div>
          <div className="flex items-center gap-4 text-slate-300">
            <span className="hidden sm:inline">Jurisdiction: <strong className="text-white">UK & International (GBP £)</strong></span>
            <button
              onClick={() => onPortalChange(activePortal === "admin" ? "marketplace" : "admin")}
              className="text-amber-400 hover:text-amber-300 font-semibold underline text-xs"
            >
              {activePortal === "admin" ? "Exit Admin Console" : "Operations Console (Doc24)"}
            </button>
          </div>
        </div>
      </div>

      {/* Main Brand & Action Header */}
      <div className="border-b border-slate-200 bg-white/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1440px] items-center gap-3 px-4 sm:px-6 lg:px-10 h-16">
          {/* Logo */}
          <div 
            onClick={() => onPortalChange("marketplace")}
            className="flex items-center gap-2 cursor-pointer shrink-0 transition-transform hover:scale-[1.02]"
          >
            <div className="w-9 h-9 rounded-xl bg-slate-950 flex items-center justify-center border border-amber-400/30 shadow-sm">
              <span className="font-extrabold text-amber-400 text-lg tracking-tighter">DX</span>
            </div>
            <div className="flex flex-col">
              <span className="font-black text-xl tracking-tight text-slate-950 flex items-center">
                Driver<span className="text-amber-500">Xtra</span>
              </span>
              <span className="text-[9px] uppercase tracking-wider text-slate-500 font-medium -mt-1">
                A Zoiko Tech Inc. Platform
              </span>
            </div>
          </div>

          {/* Search bar */}
          <div className="ml-auto hidden md:flex items-center w-full max-w-[420px] h-10 rounded-full border border-slate-300 bg-slate-50/80 px-4 focus-within:border-amber-500 focus-within:bg-white focus-within:ring-2 focus-within:ring-amber-400/20 transition-all">
            <input
              type="text"
              placeholder="Search make, model, part number, or VIN…"
              className="w-full bg-transparent text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none"
            />
            <button className="text-slate-500 hover:text-amber-600 transition-colors p-1">
              <Search className="w-4 h-4" />
            </button>
          </div>

          {/* User Nav Actions */}
          <nav className="ml-auto hidden sm:flex items-center gap-1 md:ml-4">
            <button 
              onClick={() => onPortalChange("garage")}
              className="flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg text-slate-700 hover:bg-slate-100 transition-colors"
            >
              <Bookmark className="w-[18px] h-[18px]" />
              <span className="text-[10px] font-medium">Saved</span>
            </button>
            <button 
              onClick={() => onPortalChange("messages")}
              className="flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg text-slate-700 hover:bg-slate-100 transition-colors relative"
            >
              <MessageSquareText className="w-[18px] h-[18px]" />
              <span className="text-[10px] font-medium">Messages</span>
              <span className="absolute top-1 right-2.5 w-2 h-2 rounded-full bg-amber-500"></span>
            </button>
            <button 
              onClick={onOpenAuthModal}
              className="flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg text-slate-700 hover:bg-slate-100 transition-colors"
            >
              <User className="w-[18px] h-[18px]" />
              <span className="text-[10px] font-medium">Sign In</span>
            </button>
          </nav>

          <span className="hidden lg:block h-6 w-px bg-slate-200 mx-1"></span>

          {/* Quick CTA Actions */}
          <button 
            onClick={() => onPortalChange("parts")}
            className="hidden lg:inline-flex items-center gap-2 h-10 px-4 rounded-lg border border-slate-300 text-sm font-semibold text-slate-800 hover:border-slate-950 hover:bg-slate-950 hover:text-white transition-all shadow-sm"
          >
            <Settings className="w-4 h-4" />
            <span>Find Parts</span>
          </button>

          <button 
            onClick={() => onPortalChange("sell")}
            className="inline-flex items-center gap-2 h-10 px-4 rounded-lg bg-amber-400 hover:bg-amber-500 text-slate-950 text-sm font-bold shadow-sm transition-all hover:shadow"
          >
            <CirclePlus className="w-4 h-4" />
            <span>Sell Vehicle</span>
          </button>

          {/* Mobile menu button */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="lg:hidden p-2 text-slate-700 hover:bg-slate-100 rounded-lg"
            aria-label="Toggle Navigation"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>
      </div>

      {/* Signature Amber Navigation Bar (Matching driverxtra.com) */}
      <nav className="bg-amber-400 hidden lg:block border-y border-amber-500/30">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between px-6">
          <ul className="flex items-center gap-1 xl:gap-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activePortal === item.id;
              return (
                <li key={item.id}>
                  <button
                    onClick={() => onPortalChange(item.id)}
                    className={`flex items-center gap-1.5 px-3.5 py-3 text-sm font-bold tracking-tight transition-all relative ${
                      isActive
                        ? "text-slate-950 bg-amber-300/60 rounded-t-lg shadow-inner"
                        : "text-slate-900 hover:text-white hover:bg-amber-500/50"
                    }`}
                  >
                    <Icon className="w-4 h-4 shrink-0 text-slate-900" />
                    <span>{item.label}</span>
                    {item.badge && (
                      <span className="text-[10px] font-extrabold uppercase px-1.5 py-0.2 bg-slate-900 text-amber-300 rounded ml-1">
                        {item.badge}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>

          <div className="flex items-center gap-3 py-2 text-xs font-semibold text-slate-900">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-600 animate-pulse"></span>
              Escrow System Active
            </span>
          </div>
        </div>
      </nav>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="lg:hidden bg-white border-b border-slate-200 px-4 py-4 space-y-2">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => {
                onPortalChange(item.id);
                setMobileMenuOpen(false);
              }}
              className="w-full flex items-center justify-between p-2.5 rounded-lg text-slate-800 font-semibold hover:bg-amber-50"
            >
              <div className="flex items-center gap-2">
                <item.icon className="w-4 h-4 text-amber-500" />
                <span>{item.label}</span>
              </div>
              {item.badge && (
                <span className="text-[10px] bg-slate-900 text-amber-400 px-2 py-0.5 rounded font-bold">
                  {item.badge}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </header>
  );
}
